"""
Open-Meteo tarihsel hava API'si (ERA5 tabanlı) istemcisi — anahtarsız, çalışma zamanı rüzgâr kaynağı (v2).

Kullanım koşulları (open-meteo.com/en/terms, Ekim 2026): ücretsiz API yalnız ticari olmayan kullanım; 600 çağrı/dk,
5.000/saat, 10.000/gün, 300.000/ay. 10'dan fazla değişken ya da 2 haftadan uzun dönem içeren istek kesirli olarak birden
çok çağrı sayılır (10 yıl saatlik ≈ 260 çağrı). Veri lisansı CC BY 4.0. Bu yüzden yanıtlar diske önbelleklenir.

Çıktı v1 CDS ERA5 biçimine çevrilir (u100, v100, u10, v10 [m/s], t2m [K], sp [Pa]; UTC indeks), böylece
src/uretim/ruzgar.py fonksiyonları değişmeden kullanılır.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.ayarlar import HAM_VERI

URL = "https://archive-api.open-meteo.com/v1/archive"
KLASOR = HAM_VERI / "open_meteo"
DEGISKENLER = ["wind_speed_100m", "wind_direction_100m", "wind_speed_10m", "wind_direction_10m", "temperature_2m", "surface_pressure"]
KULLANICI = "hibrit-fizibilite/2.0 (egitim amacli, ticari olmayan)"


def _dosya(enlem: float, boylam: float, bas: str, son: str, model: str) -> Path:
    return KLASOR / f"om_{model}_{enlem:.4f}_{boylam:.4f}_{bas}_{son}.parquet"


def indir(enlem: float, boylam: float, bas: str, son: str, model: str = "era5", deneme: int = 4) -> pd.DataFrame:
    """
    Bir nokta için saatlik veri (önbellekli). model="era5" yalnız ERA5 (0,25°) kullanır; Open-Meteo'nun varsayılan
    'best_match' karışımı 100 m rüzgârı içermeyen ERA5-Land'i de karıştırabileceği için açıkça seçilir.
    Döndürür: v1 ERA5 sütunları + 'om_enlem', 'om_boylam' (Open-Meteo'nun kullandığı grid noktası) öznitelikleri.
    """
    yol = _dosya(enlem, boylam, bas, son, model)
    if yol.exists():
        return pd.read_parquet(yol)
    KLASOR.mkdir(parents=True, exist_ok=True)
    parametre = {
        "latitude": enlem,
        "longitude": boylam,
        "start_date": bas,
        "end_date": son,
        "hourly": ",".join(DEGISKENLER),
        "models": model,
        "wind_speed_unit": "ms",
        "timezone": "GMT",
    }
    for i in range(deneme):
        r = requests.get(URL, params=parametre, headers={"User-Agent": KULLANICI}, timeout=180)
        if r.status_code == 200:
            break
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(30 * (i + 1))
            continue
        raise RuntimeError(f"Open-Meteo hata {r.status_code}: {r.text[:200]}")
    else:
        raise RuntimeError("Open-Meteo: deneme sayısı aşıldı (istek limiti?)")
    j = r.json()
    s = j["hourly"]
    zaman = pd.to_datetime(s["time"], utc=True)
    df = pd.DataFrame(index=pd.DatetimeIndex(zaman, name="zaman_utc"))
    for h in ("100", "10"):
        hiz = np.asarray(s[f"wind_speed_{h}m"], float)
        yon = np.deg2rad(np.asarray(s[f"wind_direction_{h}m"], float))  # meteorolojik: rüzgârın geldiği yön
        df[f"u{h}"] = -hiz * np.sin(yon)
        df[f"v{h}"] = -hiz * np.cos(yon)
    df["t2m"] = np.asarray(s["temperature_2m"], float) + 273.15
    df["sp"] = np.asarray(s["surface_pressure"], float) * 100.0
    df.attrs = {"om_enlem": j["latitude"], "om_boylam": j["longitude"], "om_rakim": j.get("elevation")}
    df["om_enlem"], df["om_boylam"] = j["latitude"], j["longitude"]
    df.to_parquet(yol)
    return df
