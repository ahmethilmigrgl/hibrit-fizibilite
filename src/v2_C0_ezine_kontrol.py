"""
v2 Faz C ön adım — Ezine'de atlas aktarımı kontrolü (önce/sonra).

Aynı hava verisi (Open-Meteo ERA5, 2014–2023) ve aynı tasarım türbini (E-141/4200, 120 m) ile:
    • atlas kuralı: türbin yerleşimi kapalı / 2 km / 3 km
    • v1 kalibre ay × saat matrisi (Ezine santralleriyle doğrudan kalibrasyon; v1 nihai profil %37,7)
    • KF kopyalama sınaması: aynı atlas K'sı vekil E-92/2350 @ 80 m ile
Komşu santrallerin kendi türbinleri, gözlenen KF'leri ve R = K / c değerleri de yazılır.

Çalıştırma: .venv/bin/python src/v2_C0_ezine_kontrol.py
Çıktı: outputs/v2C/C0_ezine_kontrol.csv, outputs/v2C/C0_ezine_komsular.csv
"""

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, config_oku
from src.saha import saha_cfg, saha_olustur
from src.uretim import genel, ruzgar

CIKTI = CIKTILAR / "v2C"


def main() -> None:
    cfg0 = config_oku()
    taban = saha_olustur("Çanakkale-Ezine", 39.79, 26.33)
    satir = []
    hava = None
    for etiket, yer, yar in [("yerleşim kapalı (nokta)", False, 2.0), ("yerleşim 2 km", True, 2.0), ("yerleşim 3 km", True, 3.0)]:
        s = replace(taban, turbin_yerlesimi=yer, yerlesim_yaricap_km=yar)
        cfg = saha_cfg(s, cfg0)
        cr = cfg["uretim"]["ruzgar"]
        hava = hava if hava is not None else genel.hava_verisi(s, 2014, 2023, "open_meteo", cfg)
        K, b = genel.k_matrisi(s, hava, "atlas", cfg)
        for tm, gb in [("E-141/4200", 120), ("E-92/2350", 80)]:
            kf, _ = ruzgar.ruzgar_kapasite_faktoru(hava, cr, k_matris=K, turbin_modeli=tm, gobek=gb)
            satir.append(
                {
                    "durum": etiket,
                    "turbin": f"{tm} @ {gb} m",
                    "gwa_100m": b["gwa_hiz"],
                    "c_saha": b["c"],
                    "K_ort": float(K.to_numpy().mean()),
                    "res_kf_%": 100 * float(kf.mean()),
                    "guven": b["guven"],
                }
            )
    s = replace(taban, turbin_yerlesimi=True)
    cfg = saha_cfg(s, cfg0)
    Kv1, _ = genel.k_matrisi(s, hava, "v1", cfg)
    kf, _ = ruzgar.ruzgar_kapasite_faktoru(hava, cfg["uretim"]["ruzgar"], k_matris=Kv1, turbin_modeli="E-141/4200", gobek=120)
    satir.append(
        {
            "durum": "v1 kalibre matris (aynı veri)",
            "turbin": "E-141/4200 @ 120 m",
            "K_ort": float(Kv1.to_numpy().mean()),
            "res_kf_%": 100 * float(kf.mean()),
        }
    )
    df = pd.DataFrame(satir)
    CIKTI.mkdir(parents=True, exist_ok=True)
    df.to_csv(CIKTI / "C0_ezine_kontrol.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    print(df.round(3).to_string(index=False))
    a, mat = aktarim.atlas()
    ci = aktarim.santral_c()
    tan = aktarim.tanimlayicilar(39.79, 26.33)
    k = aktarim.komsular(39.79, 26.33, tan, cfg0)
    kom = a.set_index("epias_id").loc[k["epias_id"].astype(int)]
    kom = kom.assign(
        mesafe_km=k["mesafe_km"].to_numpy(),
        K_ort=[float(mat[int(i)].mean()) for i in kom.index],
        c_turbin=[ci[int(i)] for i in kom.index],
    )
    kom["R"] = kom["K_ort"] / kom["c_turbin"]
    kom = kom[["ad", "mesafe_km", "turbin", "gobek", "gozlenen_kf", "gozlenen_kf_tum", "gwa_turbin", "era5_100m", "c_turbin", "K_ort", "R"]]
    kom.to_csv(CIKTI / "C0_ezine_komsular.csv", encoding="utf-8-sig", float_format="%.3f")
    print("\nKomşular:\n", kom.round(3).to_string())
    print("Ulusal medyan R:", round(float(np.median([mat[int(i)].mean() / ci[int(i)] for i in a["epias_id"]])), 3))


if __name__ == "__main__":
    main()
