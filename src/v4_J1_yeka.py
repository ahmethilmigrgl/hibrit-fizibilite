"""
v4 Faz J1 — YEKA RES teklif stratejisi: lot değerlemesi, rakip değer modeli (en çok olabilirlik), doğrulama, R26 tahminleri.

1. Değerleme: 18 yarışma (2024: 5, 2025: 6, 2026: 7) için bizim modelimizin başabaş katkı payı (€/MW) ve alım fiyatı eğimi.
2. Rakip değer modeli: V = v̂ + δ + γ ln(MW/150) + s ε; gözlenen katkı payı = ikinci en yüksek değer. 11 geçmiş yarışmayla
   en çok olabilirlik; bootstrap güven aralıkları; büyüklük terimli/terimsiz AIC.
3. Doğrulama: birini dışarıda bırak — her geçmiş yarışmanın katkı payı kalanlarla tahmin edilir; %80 aralığının kapsama oranı.
4. Piyasa primi duyarlılığı: CAPEX, WACC, uzun dönem fiyat ve bileşimi δ'nın ne kadarını kapatıyor (config v4.yeka.duyarlilik).
5. R26 (2 Kasım 2026): lot başına fiyat aşaması (tabana inme olasılığı), katkı payı dağılımı (n = başvuru sayısı) ve 2025
   rekabet düzeyiyle (n = 12) karşılaştırma.
Çıktılar: outputs/v4J/J1_*.csv|json|png, data/atlas/v4_yeka.json (uygulama)
Çalıştırma: .venv/bin/python src/v4_J1_yeka.py [--bootstrap 300]
"""

import json
import sys
import warnings
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.yeka import muzayede as M
from src.yeka.deger import lot_degerle, yarismalar

CIKTI = CIKTILAR / "v4J"


def degerleme(ekstra: dict | None = None, egim: bool = True) -> pd.DataFrame:
    y = deger(config_oku()["v4"]["yeka"])
    Y = yarismalar()
    sat = []
    for k, lot in Y.iterrows():
        r = lot_degerle(k, ekstra=ekstra)
        e = None
        if egim:
            r2 = lot_degerle(k, ekstra=ekstra, fiyat_sent=r["fiyat_sent"] + 1.0)
            e = r2["basabas_eur_mw"]["ortalama"] - r["basabas_eur_mw"]["ortalama"]
        katki = lot.get("katki_mw")
        sat.append(
            {
                "kod": k, "yil": int(lot["yil"]), "il": lot["il"], "ilce": r["nokta"]["ilce"], "mw": float(lot["mw"]), "teklif": int(lot["teklif"]),
                "para": lot["para"], "res_kf": r["res_kf"], "guven": r["guven"], "baglanti_usd_mw": r["baglanti_usd_mw"],
                "baglanti_kaynak": r["baglanti_kaynak"], "v_ort": r["basabas_eur_mw"]["ortalama"], "v_sd": r["basabas_eur_mw"]["sd"],
                "v_p10": r["basabas_eur_mw"]["p10"], "v_p90": r["basabas_eur_mw"]["p90"], "egim_eur_mw_sent": e,
                "e_npv_musd_100mw": r["e_npv_musd_100mw"], "e_npv_tuccar_musd_100mw": r["e_npv_tuccar_musd_100mw"],
                "katki_eur_mw": (katki / y["kur"]["eurusd_2025_ocak"] if lot["para"] == "USD" else katki) if pd.notna(katki) else np.nan,
            }
        )  # fmt: skip
    return pd.DataFrame(sat).set_index("kod")


def ima_edilen(d: pd.DataFrame, buyukluk: bool) -> list[dict]:
    """Duyarlılık: bizim varsayımlarımız piyasanınkine yaklaştırılınca piyasa primi δ ne kadar kapanıyor (config v4.yeka.duyarlilik)."""
    h = d[d["katki_eur_mw"].notna()]
    d0 = M.tahmin(h["katki_eur_mw"], h["v_ort"], h["mw"], h["teklif"], buyukluk)["delta"]
    sonuc = [
        {
            "ad": "Bizim varsayımlarımız",
            "ad_en": "Our assumptions",
            "delta": d0,
            "kapanan_oran": 0.0,
            "v_ort_ortalama": float(h["v_ort"].mean()),
        }
    ]
    for x in deger(config_oku()["v4"]["yeka"])["duyarlilik"]:
        v = degerleme(x["ekstra"], egim=False).loc[h.index, "v_ort"]
        dl = M.tahmin(h["katki_eur_mw"], v, h["mw"], h["teklif"], buyukluk)["delta"]
        sonuc.append(
            {"ad": x["ad"], "ad_en": x.get("ad_en", x["ad"]), "delta": dl, "kapanan_oran": 1 - dl / d0, "v_ort_ortalama": float(v.mean())}
        )
        print(f"   {x['ad']}: δ {dl / 1e3:.0f} bin €/MW (kapanan %{100 * (1 - dl / d0):.0f})")
    return sonuc


def main() -> None:
    B = int(sys.argv[sys.argv.index("--bootstrap") + 1]) if "--bootstrap" in sys.argv else 300
    CIKTI.mkdir(parents=True, exist_ok=True)
    y = deger(config_oku()["v4"]["yeka"])
    mek = y["mekanizma"]
    print("1. Değerleme")
    d = degerleme()
    h = d[d["katki_eur_mw"].notna()]
    print("2. Rakip değer modeli")
    t1 = M.tahmin(h["katki_eur_mw"], h["v_ort"], h["mw"], h["teklif"], True)
    t0 = M.tahmin(h["katki_eur_mw"], h["v_ort"], h["mw"], h["teklif"], False)
    buyukluk = t1["aic"] < t0["aic"]
    t = t1 if buyukluk else t0
    ga = M.bootstrap(h["katki_eur_mw"], h["v_ort"], h["mw"], h["teklif"], B=B, buyukluk=buyukluk)
    print(f"   büyüklük terimli AIC {t1['aic']:.1f}, terimsiz {t0['aic']:.1f} → {'terimli' if buyukluk else 'terimsiz'}; {t}; GA {ga}")
    print("3. Birini dışarıda bırak")
    loo = M.birini_disarida_birak(h["katki_eur_mw"], h["v_ort"], h["mw"], h["teklif"], buyukluk)
    lo = pd.DataFrame(loo)
    lo.index = h.index
    kapsama = float(((lo["gozlenen"] >= lo["p10"]) & (lo["gozlenen"] <= lo["p90"])).mean())
    print(f"   %80 aralığı kapsama {kapsama:.0%} ({len(lo)} yarışma)")
    print("4. Piyasa primi duyarlılığı")
    ima = ima_edilen(d, buyukluk)
    print("5. R26 tahminleri")
    r26 = []
    for k, r in d[d["yil"] == 2026].iterrows():
        mu = r["v_ort"] + t["delta"] + t["gamma"] * np.log(r["mw"] / M.MW_REF)
        for n_, etiket in ((int(r["teklif"]), "basvuru"), (12, "2025_rekabeti")):
            ik = M.ikinci_en_yuksek(mu, t["s"], n_, 200_000, tohum=zlib.crc32(k.encode()) % 1000)
            fa = M.fiyat_asamasi(ik, r["egim_eur_mw_sent"], mek["taban_sent"], mek["tavan_sent"], mek["katki_baslangic_eur_mw"])
            r26.append({"kod": k, "n": n_, "senaryo": etiket, "mu_rakip": mu, **fa})
    r26 = pd.DataFrame(r26)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(r26.round(3))
    d.join(lo[["p10", "p50", "p90", "yuzdelik"]].add_prefix("loo_")).to_csv(CIKTI / "J1_lotlar.csv")
    r26.to_csv(CIKTI / "J1_r26_tahmin.csv", index=False)
    model = {
        "secilen": "buyukluk" if buyukluk else "sabit",
        "buyukluk": t1,
        "sabit": t0,
        "guven_araligi_90": ga,
        "loo_kapsama_80": kapsama,
        "duyarlilik": ima,
    }
    (CIKTI / "J1_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    paket = {
        "model": {**t, "secilen": model["secilen"], "guven_araligi_90": ga, "loo_kapsama_80": kapsama, "mw_ref": M.MW_REF},
        "duyarlilik": ima,
        "mekanizma": mek,
        "lotlar": json.loads(d.join(lo[["p10", "p50", "p90", "yuzdelik"]].add_prefix("loo_")).reset_index().to_json(orient="records", force_ascii=False)),
        "r26": json.loads(r26.to_json(orient="records", force_ascii=False)),
    }  # fmt: skip
    (KOK / "data" / "atlas" / "v4_yeka.json").write_text(json.dumps(paket, ensure_ascii=False, indent=1), encoding="utf-8")
    grafik(lo, h)


def grafik(lo: pd.DataFrame, h: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(lo))
    ax.vlines(x, lo["p10"] / 1e3, lo["p90"] / 1e3, color="0.6", lw=6, alpha=0.6, label="Birini dışarıda bırak %80 aralığı")
    ax.plot(x, lo["p50"] / 1e3, "o", color="0.3", label="Tahmin (medyan)")
    ax.plot(x, lo["gozlenen"] / 1e3, "D", color="C1", label="Gözlenen katkı payı")
    ax.set_xticks(x, lo.index, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("Katkı payı (bin €/MW)")
    ax.set_title("YEKA RES 2024–25: rakip değer modelinin birini dışarıda bırak doğrulaması")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(CIKTI / "J1_dogrulama.png", dpi=130)


if __name__ == "__main__":
    main()
