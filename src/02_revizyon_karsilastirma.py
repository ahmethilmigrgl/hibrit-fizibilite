"""
Aşama 2 revizyonu — önce/sonra karşılaştırması (rüzgâr gün içi şekil düzeltmesi)

Üç durum aynı kodla, yalnızca config seçenekleri değiştirilerek üretilir (config dosyası değişmez):
    1) Aşama 2       : sabit k = 1,065, ERA5/PVGIS anlık zaman
    2) Hiza          : sabit k, [t, t+1) aralık ortalaması zaman tanımı
    3) Revizyon      : ay × saat k matrisi + aralık zaman tanımı (güncel varsayılan)

Çıktı: outputs/02_piyasa/revizyon_karsilastirma.csv
Çalıştırma: .venv/bin/python src/02_revizyon_karsilastirma.py
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.piyasa import analiz as a
from src.uretim import degiskenlik
from src.uretim.profil import saha_profilleri

DURUMLAR = {
    "1) Aşama 2: sabit k, anlık zaman": {"yontem": "sabit", "hiza": "anlik"},
    "2) Sabit k, aralık hizası": {"yontem": "sabit", "hiza": "aralik"},
    "3) Revizyon: ay × saat k, aralık hizası": {"yontem": "ay_saat", "hiza": "aralik"},
}


def durum_cfg(cfg: dict, yontem: str, hiza: str) -> dict:
    c = copy.deepcopy(cfg)
    c["uretim"]["ruzgar"]["ruzgar_kalibrasyon_yontemi"]["value"] = yontem
    c["uretim"]["ruzgar"]["zaman_hizasi"]["value"] = hiza
    c["uretim"]["gunes"]["zaman_hizasi"]["value"] = hiza
    return c


def main():
    cfg = config_oku()
    kod = deger(cfg["saha"]["kod"])
    saha = cfg["aday_sahalar"][kod]
    y1, y2 = deger(cfg["uretim"]["yillar_tam"])
    ptf = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")["ptf_usd"]

    satirlar = {}
    for ad, d in DURUMLAR.items():
        df, _ = saha_profilleri(kod, saha["enlem"], saha["boylam"], y1, y2, durum_cfg(cfg, d["yontem"], d["hiza"]))
        df["hibrit_toplam"] = df["ges_kf"] + df["res_kf"]
        df["hibrit_satilan"] = df["hibrit_toplam"].clip(upper=1.0)
        yillik = degiskenlik.yillik_uretim(df, ["res_kf", "hibrit_satilan"])
        res, hib = degiskenlik.p50_p90(yillik["res_kf"]), degiskenlik.p50_p90(yillik["hibrit_satilan"])
        yk = a.yakalanan_fiyat(ptf, df[["ges_kf", "res_kf", "hibrit_satilan"]], "Y")
        yk = yk[yk["saat"] > 8000]
        # 2024+ uzantı (10 hava yılı × gerçek fiyat), eşzamanlılık düzeltmeli
        uz = a.hava_yillari_ile_yakalanan(ptf, df[["res_kf", "hibrit_satilan"]], [2021, 2022, 2023, 2025, 2026])
        uz = uz.groupby("fiyat_yili")[["res_kf_oran", "hibrit_satilan_oran"]].mean()
        fark = (uz.loc[[2021, 2022, 2023]] - yk.loc[[2021, 2022, 2023], ["res_kf_oran", "hibrit_satilan_oran"]]).mean()
        tsi = (df.index.hour + 3) % 24
        prof = df["res_kf"].groupby(tsi).mean()
        satirlar[ad] = {
            "RES KF [%]": 100 * df["res_kf"].mean(),
            "RES gün içi tepe saati (TSİ)": int(prof.idxmax()),
            "RES öğleden sonra (13–16) / gece (0–5) KF oranı": prof.loc[13:16].mean() / prof.loc[0:5].mean(),
            "GES–RES saatlik korelasyon": df["ges_kf"].corr(df["res_kf"]),
            "1 MW RES P50 [MWh/yıl]": res["P50 (ampirik medyan)"],
            "1 MW RES P90 normal [MWh/yıl]": res["P90 (normal: ort − 1.282σ)"],
            "Hibrit 1+1/1 P50 [MWh/yıl]": hib["P50 (ampirik medyan)"],
            "Hibrit 1+1/1 P90 normal [MWh/yıl]": hib["P90 (normal: ort − 1.282σ)"],
            "Hibrit değişkenlik katsayısı [%]": hib["Değişkenlik katsayısı [%]"],
            "Hibrit kesinti [%]": 100 * (1 - df["hibrit_satilan"].sum() / df["hibrit_toplam"].sum()),
            "Bağlantı kullanım oranı [%]": 100 * df["hibrit_satilan"].mean(),
            "RES yakalanma oranı 2014–23 ort.": yk["res_kf_oran"].mean(),
            "RES yakalanma oranı 2023": yk.loc[2023, "res_kf_oran"],
            "RES yakalanma oranı 2025 (uzantı, düzeltilmiş)": uz.loc[2025, "res_kf_oran"] - fark["res_kf_oran"],
            "RES yakalanma oranı 2026 Oca–Eyl (uzantı, düzeltilmiş)": uz.loc[2026, "res_kf_oran"] - fark["res_kf_oran"],
            "GES yakalanma oranı 2023": yk.loc[2023, "ges_kf_oran"],
            "Hibrit yakalanma oranı 2014–23 ort.": yk["hibrit_satilan_oran"].mean(),
            "Hibrit yakalanma oranı 2025 (uzantı, düzeltilmiş)": uz.loc[2025, "hibrit_satilan_oran"] - fark["hibrit_satilan_oran"],
        }
        print(f"{ad}: tamam")
    tablo = pd.DataFrame(satirlar)
    tablo.to_csv(CIKTILAR / "02_piyasa" / "revizyon_karsilastirma.csv", encoding="utf-8-sig", float_format="%.4f")
    pd.set_option("display.width", 250)
    print(tablo.round(3).to_string())


if __name__ == "__main__":
    main()
