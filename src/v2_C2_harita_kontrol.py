"""
v2 Faz C2 — Ön tarama haritasının bilinen rüzgârlı bölgelerde makullük kontrolü.

Her bölge için: haritadaki hücrelerin RES KF'si (medyan, en yüksek) ve en iyi tasarımın başabaş fiyatı; bölgedeki kalibre
santrallerin gözlenen KF'si (talimat/arıza saatleri hariç), türbin vekilleri; santralin bulunduğu hücrenin model KF'si.
Beklenti: hücre KF'si (E-141/4200 ya da E-126/V112, 105–135 m, türbin yerleşimi 2 km) santrallerin gözlenen KF'sine yakın ya da
üstünde (santraller çoğunlukla 2–3,5 MW, 80–100 m, eski türbinler; hücrenin temsilî noktası sırtta olmayabilir).
Çıktı: outputs/v2C/C2_harita_kontrol.csv
Çalıştırma: .venv/bin/python src/v2_C2_harita_kontrol.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, KOK
from src.kaynaklar.era5_grid import hucre

BOLGELER = {  # (enlem alt, enlem üst, boylam alt, boylam üst)
    "Biga yarımadası (Çanakkale)": (39.4, 40.5, 26.0, 27.6),
    "Karaburun (İzmir)": (38.4, 38.8, 26.3, 26.7),
    "İzmir kuzeyi (Aliağa–Bergama–Soma)": (38.7, 39.3, 26.8, 27.8),
    "Hatay": (35.8, 36.9, 35.8, 36.6),
    "Sivas": (38.8, 40.2, 36.5, 38.6),
}


def main() -> None:
    ot = pd.read_parquet(KOK / "data" / "atlas" / "on_tarama.parquet")
    ot = ot[ot["hata"] == ""]
    a, _ = aktarim.atlas()
    satir = []
    for ad, (e0, e1, b0, b1) in BOLGELER.items():
        h = ot[ot["hucre_enlem"].between(e0, e1) & ot["hucre_boylam"].between(b0, b1)]
        s = a[a["enlem"].between(e0, e1) & a["boylam"].between(b0, b1)]
        hk = []
        for r in s.itertuples():
            he, hb = hucre(r.enlem, r.boylam)
            x = ot[(ot["hucre_enlem"] == he) & (ot["hucre_boylam"] == hb)]
            hk.append(float(x["res_kf"].iloc[0]) if len(x) else float("nan"))
        satir.append(
            {
                "bolge": ad,
                "hucre": len(h),
                "hucre_res_kf_medyan_%": 100 * h["res_kf"].median(),
                "hucre_res_kf_azami_%": 100 * h["res_kf"].max(),
                "basabas_en_iyi_medyan": h["basabas_en_iyi"].median(),
                "basabas_en_iyi_en_dusuk": h["basabas_en_iyi"].min(),
                "guven_yuksek_payi_%": 100 * (h["guven"] == "yüksek").mean(),
                "santral": len(s),
                "santral_gozlenen_kf_medyan_%": 100 * s["gozlenen_kf"].median() if len(s) else float("nan"),
                "santral_gozlenen_kf_azami_%": 100 * s["gozlenen_kf"].max() if len(s) else float("nan"),
                "santral_hucresi_model_kf_medyan_%": 100 * pd.Series(hk).median() if hk else float("nan"),
                "santral_turbinleri": ", ".join(s["turbin"].value_counts().head(3).index),
            }
        )
    df = pd.DataFrame(satir)
    (CIKTILAR / "v2C").mkdir(parents=True, exist_ok=True)
    df.to_csv(CIKTILAR / "v2C" / "C2_harita_kontrol.csv", index=False, encoding="utf-8-sig", float_format="%.1f")
    print(df.round(1).T.to_string())


if __name__ == "__main__":
    main()
