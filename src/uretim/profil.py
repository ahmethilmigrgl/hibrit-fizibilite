"""
Bir saha için saatlik GES ve RES kapasite faktörü profillerini üretir (UTC).

Ham veriler önbellekten okunur (data/raw), bu yüzden config.yaml'daki bir varsayım
(ör. ruzgar_hiz_kalibrasyon_katsayisi, kirpma_kaybi) değişince profiller yeniden
indirme yapılmadan saniyeler içinde yeniden üretilir.
"""

from __future__ import annotations

import pandas as pd

from src.ayarlar import KOK, deger
from src.uretim import gunes, ruzgar


def saha_profilleri(kod: str, enlem: float, boylam: float, y1: int, y2: int, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """
    Döndürür:
        df   — indeks zaman_utc (saat başı, UTC); sütunlar:
               ges_kf, res_kf (ana türbin), res_kf_e126 (duyarlılık türbini),
               v100_ham, v_gobek_ham [m/s] (kalibrasyonsuz), hava_yogunlugu [kg/m³]
               Zaman tanımı config'e bağlı (zaman_hizasi = "aralik" → her satır [t, t+1) UTC aralık ortalaması)
        bilgi — PVGIS meta verisi, ERA5 grid noktası, eksik saat sayısı
    """
    cg, cr = cfg["uretim"]["gunes"], cfg["uretim"]["ruzgar"]

    isinim, meta = gunes.pvgis_isinim_indir(kod, enlem, boylam, y1, y2, cg)
    era5 = ruzgar.era5_coklu_yil(kod, enlem, boylam, y1, y2, cr)

    # Kalibrasyon yöntemi: sabit k ya da ay × saat k matrisi (yalnızca seçilen saha için kurulmuştur)
    k_matris = None
    if deger(cr["ruzgar_kalibrasyon_yontemi"]) == "ay_saat":
        if kod != deger(cfg["saha"]["kod"]):
            raise ValueError("Ay × saat k matrisi yalnızca seçilen saha için kalibre edildi.")
        k_matris = pd.read_parquet(KOK / deger(cr["k_matris_dosyasi"]))

    ges_kf = gunes.gunes_kapasite_faktoru(isinim, meta, cg)
    res_kf, ara = ruzgar.ruzgar_kapasite_faktoru(era5, cr, k_matris=k_matris)
    res_alt, _ = ruzgar.ruzgar_kapasite_faktoru(era5, cr, deger(cr["turbin_duyarlilik"]), k_matris=k_matris)

    df = pd.concat(
        [
            ges_kf.rename("ges_kf"),
            res_kf.rename("res_kf"),
            res_alt.rename("res_kf_e126"),
            ara["v100"].rename("v100_ham"),
            ara["v_gobek"].rename("v_gobek_ham"),
            ara["yogunluk"].rename("hava_yogunlugu"),
        ],
        axis=1,
        join="inner",
    )
    df.index.name = "zaman_utc"

    beklenen = pd.date_range(f"{y1}-01-01", f"{y2}-12-31 23:00", freq="h", tz="UTC")
    bilgi = {
        "meta": meta,
        "era5_grid": (float(era5["latitude"].iloc[0]), float(era5["longitude"].iloc[0])),
        "eksik_saat": len(beklenen.difference(df.index)),
        "tekrar_eden_saat": int(df.index.duplicated().sum()),
    }
    return df, bilgi
