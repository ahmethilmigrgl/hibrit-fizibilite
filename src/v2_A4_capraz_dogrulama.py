"""
v2 A4/Ö3/Ö4 — Kalibrasyon aktarım kuralının "birini dışarıda bırak" çapraz doğrulaması, GWA modu karşılaştırması
(1 km nokta / 250 m nokta / türbin yerleşimi) ve güven seviyeleri (bootstrap güven aralıklarıyla).

Her kullanılabilir atlas santrali sırayla yokmuş gibi tahmin edilir; tahmini matrisle santralin kendi ERA5 hücresinden
(vekil türbin) üretilen KF, gözlenen KF ile karşılaştırılır. Yerleşim modunda hem santral hem tahmin edilen noktanın GWA hızı,
çevresindeki en rüzgârlı 250 m hücrelerden (santral: kurulu güç / 3 MW türbin, 3 km) hesaplanır.

Çalıştırma: .venv/bin/python src/v2_A4_capraz_dogrulama.py
Çıktı: outputs/v2/A4_capraz_dogrulama.csv, A4_ozet.csv, A4_guven_bootstrap.csv; data/atlas/guven_seviyeleri.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.atlas import kalibrasyon as K
from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.kaynaklar import era5_cds
from src.piyasa import veri
from src.piyasa.epias import EpiasIstemcisi
from src.uretim import kalibrasyon as kal

GMODLAR = ["nokta1km", "nokta250", "yerlesim"]
CIKTI = CIKTILAR / "v2"


def veriler(cfg: dict):
    """Santral başına referans modeli ve gözlenen KF (bir kez hesaplanır)."""
    cr = cfg["uretim"]["ruzgar"]
    df, _ = aktarim.atlas()
    ist = EpiasIstemcisi()
    out = {}
    for r in df.itertuples():
        u = veri.uretim_cek(ist, "2014-01-01", "2026-09-30", santral_id=int(r.epias_id))
        m = kal.referans_model(era5_cds.indir(r.enlem, r.boylam), cr, K.VEKIL_TURBIN, K.VEKIL_GOBEK)
        g = K.V1.degisken_kapasiteli_kf(u["toplam"].loc[:"2025-12-31 23:00"].astype(float)).reindex(m.indeks).clip(upper=1.05).to_numpy()
        out[int(r.epias_id)] = (m, g)
    return out


def calistir(cfg: dict, data: dict) -> pd.DataFrame:
    df, _ = aktarim.atlas()
    satir = []
    for gmod in GMODLAR:
        ci = aktarim.santral_c(gmod)
        for r in df.itertuples():
            m, g = data[int(r.epias_id)]
            ok = ~np.isnan(g)
            gun_g = pd.Series(g[ok]).groupby(m.saat[ok]).mean()
            tan = {"rakim_m": r.rakim_m, "karmasiklik": r.karmasiklik, "kiyi_km": r.kiyi_km}
            komsu = aktarim.komsular(r.enlem, r.boylam, tan, cfg, haric=int(r.epias_id))
            gwa_hiz = ci[int(r.epias_id)] * r.era5_100m
            for y in ["yok", "gwa", "dogrudan", "gwa_olcekli"] if gmod == "yerlesim" else ["gwa", "gwa_olcekli"]:
                Km, b = aktarim.tahmin(r.enlem, r.boylam, r.era5_100m, y, cfg, haric=int(r.epias_id), tan=tan, gwa_hiz=gwa_hiz, gmod=gmod)
                kf = m.kf_matris(Km)
                gun_m = pd.Series(kf[ok]).groupby(m.saat[ok]).mean()
                k0 = komsu.iloc[0] if len(komsu) else None
                satir.append(
                    {
                        "gmod": gmod,
                        "yontem": y,
                        "epias_id": r.epias_id,
                        "ad": r.ad,
                        "guven_eski": b["guven"],
                        "en_yakin_km": float(k0["mesafe_km"]) if k0 is not None else np.nan,
                        "komsu_rakim_farki": abs(float(k0["rakim_m"]) - r.rakim_m) if k0 is not None else np.nan,
                        "komsu_karmasiklik_farki": abs(float(k0["karmasiklik"]) - r.karmasiklik) if k0 is not None else np.nan,
                        "komsu_sayisi": len(komsu),
                        "kiyi": r.kiyi_km < 20,
                        "karmasiklik": r.karmasiklik,
                        "rakim_m": r.rakim_m,
                        "gozlenen_kf": float(g[ok].mean()),
                        "kf_hatasi_puan": 100 * float(kf[ok].mean() - g[ok].mean()),
                        "gunici_rmse_puan": 100 * float(np.sqrt(((gun_m - gun_g) ** 2).mean())),
                        "korelasyon": float(np.corrcoef(kf[ok], g[ok])[0, 1]),
                    }
                )
    return pd.DataFrame(satir)


def ozet(x: pd.DataFrame) -> pd.Series:
    e = x["kf_hatasi_puan"]
    return pd.Series(
        {
            "santral": len(x),
            "ort_hata": e.mean(),
            "mutlak_medyan": e.abs().median(),
            "rmse": np.sqrt((e**2).mean()),
            "mutlak_p90": e.abs().quantile(0.9),
            "gunici_rmse_medyan": x["gunici_rmse_puan"].median(),
            "korelasyon_medyan": x["korelasyon"].median(),
        }
    )


def bootstrap(e: np.ndarray, n: int = 4000, tohum: int = 42) -> dict:
    rng = np.random.default_rng(tohum)
    a = np.abs(e)
    orn = rng.choice(a, (n, len(a)), replace=True)
    med, p90 = np.median(orn, 1), np.quantile(orn, 0.9, axis=1)
    return {
        "medyan": np.median(a),
        "medyan_alt": np.quantile(med, 0.05),
        "medyan_ust": np.quantile(med, 0.95),
        "p90": np.quantile(a, 0.9),
        "p90_alt": np.quantile(p90, 0.05),
        "p90_ust": np.quantile(p90, 0.95),
    }


def seviye(r: pd.Series, cfg: dict) -> str:
    """Ö4 güven seviyeleri: en yakın benzer komşu ≤ 15 km yüksek, 15–30 km orta, yoksa düşük (config v2.guven)."""
    gv = deger(cfg["v2"]["guven"])
    if r["komsu_sayisi"] > 0 and r["en_yakin_km"] <= gv["yuksek_km"]:
        return "yüksek"
    if r["komsu_sayisi"] > 0 and r["en_yakin_km"] <= gv["orta_km"]:
        return "orta"
    return "düşük"


def main() -> None:
    cfg = config_oku()
    pd.set_option("display.width", 230)
    cv = calistir(cfg, veriler(cfg))
    CIKTI.mkdir(parents=True, exist_ok=True)
    cv.to_csv(CIKTI / "A4_capraz_dogrulama.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    yontem = cv.groupby(["gmod", "yontem"]).apply(ozet, include_groups=False)
    print("GWA modu × yöntem:\n", yontem.round(2).to_string())
    kural = cv[(cv["gmod"] == deger(cfg["v2"]["aktarim"])["gwa_modu"]) & (cv["yontem"] == "gwa_olcekli")].copy()
    kural["guven"] = kural.apply(seviye, axis=1, cfg=cfg)
    kural.to_csv(CIKTI / "A4_kural_seviyeler.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    sira = ["yüksek", "orta", "düşük"]
    gs = kural.groupby("guven").apply(ozet, include_groups=False).reindex(sira)
    gs["goreli_rmse_%"] = 100 * gs["rmse"] / (100 * kural["gozlenen_kf"].mean())
    bs = pd.DataFrame({s: bootstrap(kural.loc[kural["guven"] == s, "kf_hatasi_puan"].to_numpy()) for s in sira}).T
    print(
        "\nGüven seviyeleri (kural):\n",
        gs.round(2).to_string(),
        "\n\nBootstrap %90 güven aralıkları (mutlak hata, puan):\n",
        bs.round(2).to_string(),
    )
    pd.concat({"yontem": yontem}).to_csv(CIKTI / "A4_ozet.csv", encoding="utf-8-sig", float_format="%.3f")
    bs.to_csv(CIKTI / "A4_guven_bootstrap.csv", encoding="utf-8-sig", float_format="%.3f")
    tablo = gs[["santral", "ort_hata", "rmse", "mutlak_medyan", "mutlak_p90", "goreli_rmse_%", "gunici_rmse_medyan"]].join(
        bs[["medyan_alt", "medyan_ust", "p90_alt", "p90_ust"]]
    )
    tablo.to_csv(KOK / "data" / "atlas" / "guven_seviyeleri.csv", encoding="utf-8-sig", float_format="%.3f")


if __name__ == "__main__":
    main()
