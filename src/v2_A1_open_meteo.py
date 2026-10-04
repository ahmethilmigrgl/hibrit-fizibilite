"""
v2 Faz A1 — Open-Meteo (ERA5) ile CDS ERA5'in Ezine noktasında karşılaştırılması (2014–2023).

Aynı ERA5 grid noktası (39,75 K; 26,25 D). Karşılaştırılanlar: 100 m ve 10 m hız (saatlik korelasyon, ortalama fark,
RMSE), sıcaklık/basınç, ve v1 rüzgâr modeliyle (aynı türbin, göbek, ay × saat kalibrasyon matrisi) hesaplanan RES
kapasite faktörü (yıllık ortalama ve saatlik fark).

Çalıştırma: .venv/bin/python src/v2_A1_open_meteo.py
Çıktı: outputs/v2/A1_open_meteo_cds.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.kaynaklar import open_meteo as om
from src.uretim import ruzgar

CIKTI = CIKTILAR / "v2"


def main() -> None:
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    cds = ruzgar.era5_coklu_yil("canakkale_ezine", 39.79, 26.33, 2014, 2023, cr)
    cds = cds[~cds.index.duplicated()]
    omd = om.indir(39.75, 26.25, "2014-01-01", "2023-12-31")
    ortak = cds.index.intersection(omd.index)
    c, o = cds.loc[ortak], omd.loc[ortak]
    satir = {}
    for h in ("100", "10"):
        vc, vo = np.hypot(c[f"u{h}"], c[f"v{h}"]), np.hypot(o[f"u{h}"], o[f"v{h}"])
        satir[f"{h} m hız: saatlik korelasyon"] = float(np.corrcoef(vc, vo)[0, 1])
        satir[f"{h} m hız: ortalama CDS [m/s]"] = float(vc.mean())
        satir[f"{h} m hız: ortalama Open-Meteo [m/s]"] = float(vo.mean())
        satir[f"{h} m hız: ortalama fark OM − CDS [m/s]"] = float((vo - vc).mean())
        satir[f"{h} m hız: RMSE [m/s]"] = float(np.sqrt(((vo - vc) ** 2).mean()))
    satir["2 m sıcaklık: ortalama fark [K]"] = float((o["t2m"] - c["t2m"]).mean())
    satir["Yüzey basıncı: ortalama fark [hPa]"] = float((o["sp"] - c["sp"]).mean() / 100)
    # v1 rüzgâr modeli: config türbini + göbek, ay × saat kalibrasyon matrisi
    km = pd.read_parquet(ISLENMIS_VERI / Path(deger(cr["k_matris_dosyasi"])).name)
    kf_c, _ = ruzgar.ruzgar_kapasite_faktoru(c, cr, k_matris=km)
    kf_o, _ = ruzgar.ruzgar_kapasite_faktoru(o.drop(columns=["om_enlem", "om_boylam"]), cr, k_matris=km)
    satir["RES KF: ortalama CDS [%]"] = 100 * float(kf_c.mean())
    satir["RES KF: ortalama Open-Meteo [%]"] = 100 * float(kf_o.mean())
    satir["RES KF: fark OM − CDS [puan]"] = 100 * float((kf_o - kf_c).mean())
    satir["RES KF: saatlik korelasyon"] = float(np.corrcoef(kf_c, kf_o)[0, 1])
    yil = pd.DataFrame({"c": kf_c, "o": kf_o}).groupby(kf_c.index.year).mean()
    satir["RES KF: yıllık en büyük mutlak fark [puan]"] = 100 * float((yil["o"] - yil["c"]).abs().max())
    gun_c = kf_c.groupby((kf_c.index.hour + 3) % 24).mean()
    gun_o = kf_o.groupby((kf_o.index.hour + 3) % 24).mean()
    satir["RES KF: gün içi profil en büyük fark [puan]"] = 100 * float((gun_o - gun_c).abs().max())
    satir["Ortak saat sayısı"] = float(len(ortak))
    CIKTI.mkdir(parents=True, exist_ok=True)
    s = pd.Series(satir, name="değer")
    s.to_csv(CIKTI / "A1_open_meteo_cds.csv", encoding="utf-8-sig", float_format="%.5f")
    print(s.round(4).to_string())


if __name__ == "__main__":
    main()
