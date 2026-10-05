"""
v2 Faz A3-3 — Türkiye RES kalibrasyon atlası (çevrimdışı; EPİAŞ önbelleği + ERA5 hücreleri).

Her eşleşen santral için: k (sabit), ay × saat matrisi, metrikler, kalite bayrakları ve saha tanımlayıcıları
(rakım, arazi karmaşıklığı, kıyıya uzaklık, GWA ve ERA5 100 m ortalama hızları).
Çıktı (uygulamaya gömülebilir, ham EPİAŞ verisi yok):
    data/atlas/kalibrasyon_atlasi.csv       — santral özeti (konumlar © OpenStreetMap katkıcıları, ODbL)
    data/atlas/kalibrasyon_matrisleri.npz   — santral başına 12 × 24 k matrisi ve gözlenen ay × saat KF (float16)
    outputs/v2/A3_k_haritasi.png, A3_k_bolgesel.csv

Çalıştırma: .venv/bin/python src/v2_A3_atlas.py [--eksikleri-atla]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import src.gorsel as g
from src.atlas import kalibrasyon as K
from src.ayarlar import CIKTILAR, HAM_VERI, KOK, config_oku
from src.kaynaklar import arazi, era5_cds, gwa
from src.piyasa import veri
from src.piyasa.epias import EpiasIstemcisi

ATLAS = KOK / "data" / "atlas"
CIKTI = CIKTILAR / "v2"
CEYREK = 51  # 2014Ç1 – 2026Ç3


def main() -> None:
    eksik_atla = "--eksikleri-atla" in sys.argv
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    e = pd.read_csv(ATLAS / "santral_eslestirme.csv")
    e = e[e["epias_id"].notna()].copy()
    e["epias_id"] = e["epias_id"].astype(int)
    ist = EpiasIstemcisi()
    satir, matris, gozlenen = [], {}, {}
    for _, r in e.iterrows():
        klasor = HAM_VERI / "epias" / f"uretim_santral_{r['epias_id']}"
        hucre = era5_cds.hucre(r["enlem"], r["boylam"])
        era5_yol = era5_cds.KLASOR / f"era5_{hucre[0]:.2f}_{hucre[1]:.2f}_2014-01-01_2025-12-31.parquet"
        if eksik_atla and (not klasor.exists() or len(list(klasor.glob("*.json"))) < CEYREK or not era5_yol.exists()):
            continue
        u = veri.uretim_cek(ist, "2014-01-01", "2026-09-30", santral_id=int(r["epias_id"]))
        era5 = era5_cds.indir(r["enlem"], r["boylam"])
        try:
            sk = K.kalibre_et(u["toplam"], era5, cr, r["osm_mw"] if pd.notna(r["osm_mw"]) else None)
        except K.KSinirDisi:
            satir.append(
                {"epias_id": r["epias_id"], "ad": r["epias_ad"], "enlem": r["enlem"], "boylam": r["boylam"], "sinif": "k_sinir_disi"}
            )
            continue
        if sk is None:
            satir.append(
                {"epias_id": r["epias_id"], "ad": r["epias_ad"], "enlem": r["enlem"], "boylam": r["boylam"], "sinif": "veri_yetersiz"}
            )
            continue
        v100 = float(np.hypot(era5["u100"], era5["v100"]).mean())
        try:
            gw = gwa.nokta(r["enlem"], r["boylam"])["ws_ort"]
        except ValueError:
            gw = np.nan
        satir.append(
            {
                "epias_id": r["epias_id"],
                "ad": r["epias_ad"],
                "osm_id": r["osm_id"],
                "enlem": r["enlem"],
                "boylam": r["boylam"],
                "osm_mw": r["osm_mw"],
                **sk.ozet,
                "sinif": K.kalite_sinifi(sk.ozet, gw / v100),
                "R_artik": sk.ozet["k_sabit"] / (gw / v100),
                "era5_100m": v100,
                "gwa_100m": gw,
                "gwa_era5_orani": gw / v100,
                "kiyi_km": arazi.kiyi_km(r["enlem"], r["boylam"]),
                "karmasiklik": arazi.karmasiklik(r["enlem"], r["boylam"]),
            }
        )
        matris[str(r["epias_id"])] = sk.matris.astype(np.float16)
        gozlenen[str(r["epias_id"])] = sk.gozlenen_ay_saat.astype(np.float16)
    df = pd.DataFrame(satir)
    ok = df["enlem"].notna()
    df.loc[ok, "rakim_m"] = arazi.rakim(list(zip(df.loc[ok, "enlem"], df.loc[ok, "boylam"])))
    df.to_csv(ATLAS / "kalibrasyon_atlasi.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    np.savez_compressed(
        ATLAS / "kalibrasyon_matrisleri.npz", **{f"k_{k}": v for k, v in matris.items()}, **{f"g_{k}": v for k, v in gozlenen.items()}
    )
    print(df["sinif"].value_counts().to_string())
    analiz(df)


def analiz(df: pd.DataFrame) -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    d = df[df["sinif"].isin(["temiz", "kullanilabilir"])].copy()
    d["bolge"] = np.select([d["kiyi_km"] < 20, d["kiyi_km"] < 80], ["kıyı (<20 km)", "kıyıya yakın (20–80 km)"], "iç (>80 km)")
    d["karmasiklik_sinifi"] = pd.qcut(d["karmasiklik"], 3, labels=["düşük", "orta", "yüksek"])
    d["rakim_sinifi"] = pd.cut(d["rakim_m"], [-1, 300, 800, 4000], labels=["<300 m", "300–800 m", ">800 m"])
    tablolar = []
    for grup in ["bolge", "karmasiklik_sinifi", "rakim_sinifi"]:
        t = d.groupby(grup, observed=True).agg(
            santral=("k_sabit", "size"),
            k_medyan=("k_sabit", "median"),
            k_p10=("k_sabit", lambda x: x.quantile(0.1)),
            k_p90=("k_sabit", lambda x: x.quantile(0.9)),
            gwa_era5_medyan=("gwa_era5_orani", "median"),
            gunici_genlik=("k_gunici_genlik", "median"),
        )
        t.insert(0, "gruplama", grup)
        tablolar.append(t.reset_index().rename(columns={grup: "grup"}))
    tab = pd.concat(tablolar)
    kor = {
        f"k ~ {c}": float(d["k_sabit"].corr(d[c], method="spearman"))
        for c in ["kiyi_km", "rakim_m", "karmasiklik", "gwa_era5_orani", "era5_100m"]
    }
    tab.to_csv(CIKTI / "A3_k_bolgesel.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.Series(kor, name="Spearman").to_csv(CIKTI / "A3_k_korelasyon.csv", encoding="utf-8-sig", float_format="%.3f")
    print(tab.round(3).to_string(index=False))
    print(json.dumps({k: round(v, 3) for k, v in kor.items()}, ensure_ascii=False))
    harita(d)


def harita(d: pd.DataFrame) -> None:
    import matplotlib.colors as mc

    P = gwa._yukle()
    z = np.where(P["ws_ort"] > 0, P["ws_ort"] / P["olcek"], np.nan)
    n, m = z.shape
    kapsam = [P["sol"], P["sol"] + m * P["adim"], P["ust"] - n * P["adim"], P["ust"]]
    fig, axs = plt.subplots(2, 1, figsize=(12, 10.5))
    paneller = [
        ("k_sabit", "Sabit hız katsayısı k = gözlenen / ERA5 (log ölçek)", "YlOrRd", mc.LogNorm(vmin=0.8, vmax=3.2)),
        ("R_artik", "GWA düzeltmesinden arta kalan R = k / (GWA/ERA5)", "RdBu_r", mc.TwoSlopeNorm(vmin=0.7, vcenter=1.0, vmax=1.4)),
    ]
    for ax, (kol, baslik_, cmap, norm) in zip(axs, paneller):
        ax.imshow(z, extent=kapsam, cmap="Greys", vmin=2, vmax=12, alpha=0.45)
        sc = ax.scatter(
            d["boylam"],
            d["enlem"],
            c=d[kol],
            cmap=cmap,
            norm=norm,
            s=22 + d["osm_mw"].fillna(20) / 3,
            edgecolor="black",
            linewidth=0.4,
            zorder=3,
        )
        cb = fig.colorbar(sc, ax=ax, shrink=0.85)
        cb.set_label(kol)
        ax.set_title(baslik_, loc="left")
        ax.set_xlim(25.6, 44.9)
        ax.set_ylim(35.8, 42.2)
        ax.set_aspect(1.25)
    g.baslik(
        fig,
        "Türkiye RES kalibrasyon atlası: ERA5 iç ve dağlık kesimde rüzgârı ciddi düşük gösteriyor",
        f"{len(d)} santral. Üst: k kıyıda ~1,4, içeride ~2,3. Alt: GWA düzeltmesi sonrası artık R çoğunlukla 0,9–1,3 (GWA farkın çoğunu açıklıyor).",
    )
    fig.tight_layout(rect=(0, 0.01, 1, 0.94))
    g.kaynak_notu(
        fig,
        "Kaynak: EPİAŞ Şeffaflık Platformu (santral üretimi), ERA5 (Copernicus), Global Wind Atlas 3.0 (DTU), konumlar © OpenStreetMap katkıcıları. Kendi hesaplamam.",
    )
    fig.savefig(CIKTI / "A3_k_haritasi.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
