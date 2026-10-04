"""
Çevrimdışı ERA5 nokta zaman serisi (CDS, kişisel anahtar — yalnız ön hesaplama betiklerinde; web uygulamasında asla).
Grid hücresi bazında önbellek: data/raw/era5_hucre/era5_{enlem}_{boylam}_{bas}_{son}.parquet (v1 sütunları).
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

from src.ayarlar import HAM_VERI, cds_istemcisi

VERI_SETI = "reanalysis-era5-single-levels-timeseries"
KLASOR = HAM_VERI / "era5_hucre"
DEGISKENLER = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
    "2m_temperature",
    "surface_pressure",
]


def hucre(enlem: float, boylam: float) -> tuple[float, float]:
    """En yakın 0,25° ERA5 grid noktası."""
    return float(np.round(enlem * 4) / 4), float(np.round(boylam * 4) / 4)


def indir(enlem: float, boylam: float, bas: str = "2014-01-01", son: str = "2025-12-31") -> pd.DataFrame:
    he, hb = hucre(enlem, boylam)
    yol = KLASOR / f"era5_{he:.2f}_{hb:.2f}_{bas}_{son}.parquet"
    if yol.exists():
        return pd.read_parquet(yol)
    KLASOR.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".zip")
    cds_istemcisi().retrieve(
        VERI_SETI,
        {"variable": DEGISKENLER, "location": {"longitude": hb, "latitude": he}, "date": [f"{bas}/{son}"], "data_format": "csv"},
        str(gecici),
    )
    with zipfile.ZipFile(gecici) as z:
        ad = next(n for n in z.namelist() if n.endswith(".csv"))
        df = pd.read_csv(z.open(ad), parse_dates=["valid_time"])
    gecici.unlink()
    df = df.set_index("valid_time")
    df.index = df.index.tz_localize("UTC")
    df.index.name = "zaman_utc"
    df = df[~df.index.duplicated()][["u100", "v100", "u10", "v10", "t2m", "sp"]]
    df.to_parquet(yol)
    return df
