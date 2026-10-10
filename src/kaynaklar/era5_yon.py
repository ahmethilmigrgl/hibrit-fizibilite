"""
ERA5 100 m rüzgâr YÖNÜ gridi (v3 Faz D1): rüzgâr gülü ve saatlik iz verimi için.

v2 ERA5 nokta gridi (era5_grid.py) yalnız hız büyüklüğünü saklar. Yön, CDS 'reanalysis-era5-single-levels' gridli
ürününden (u100, v100; Türkiye kutusu, 0,25°, 2014–2023 saatlik) çevrimdışı indirilir ve hücre başına paketlenir:
    yon : uint8, 10°'lik sektör (0 = kuzeyden esen, 0–35); saat sayısı era5_grid ile aynı (2014-01-01 00 UTC'den)
Dosya: data/grid/era5_yon_tr/v1/{enlem:.2f}_{boylam:.2f}.npz (veri katmanı: grid/era5_yon_tr/v1/...).
Hücre dosyası yoksa (ör. indirme sürüyor) atlas santral hücrelerinin ham u/v'si (data/raw/era5_hucre) ya da en yakın
hücre kullanılır; o da yoksa yön dağılımı tek biçimli kabul edilir (rüzgâr gülü 'bilinmiyor' olarak işaretlenir).
Kişisel CDS anahtarı yalnız indirme betiğinde (src/v3_D0_era5_yon_grid.py); uygulama yalnız paketlenmiş dosyaları okur.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.ayarlar import HAM_VERI, KOK

SURUM = "v1"
KLASOR = KOK / "data" / "grid" / "era5_yon_tr" / SURUM
HAM = HAM_VERI / "era5_yon"
SEKTOR = 36  # 10°
BAS = "2014-01-01 00:00"


def hucre(enlem: float, boylam: float) -> tuple[float, float]:
    return float(np.round(enlem * 4) / 4), float(np.round(boylam * 4) / 4)


def dosya_adi(enlem: float, boylam: float) -> str:
    e, b = hucre(enlem, boylam)
    return f"{e:.2f}_{b:.2f}.npz"


def yon_derece(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Meteorolojik yön (rüzgârın ESTİĞİ yön, kuzey = 0°, saat yönünde): (270° − atan2(v, u)) mod 360."""
    return np.mod(270.0 - np.degrees(np.arctan2(v, u)), 360.0)


def sektor(derece: np.ndarray, n: int = SEKTOR) -> np.ndarray:
    w = 360.0 / n
    return (np.floor(np.mod(np.asarray(derece) + w / 2, 360.0) / w) % n).astype(np.uint8)


@lru_cache(maxsize=32)
def _ham_hucre(e: float, b: float) -> np.ndarray | None:
    """Atlas için indirilmiş ham ERA5 hücresi (u100, v100) → saatlik yön [°] (2014-01-01'den)."""
    p = HAM_VERI / "era5_hucre" / f"era5_{e:.2f}_{b:.2f}_2014-01-01_2025-12-31.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["u100", "v100"]).loc[:"2023-12-31 23:00"]
    return yon_derece(d["u100"].to_numpy(), d["v100"].to_numpy())


def saatlik_yon(enlem: float, boylam: float, n_saat: int | None = None) -> tuple[np.ndarray | None, str]:
    """
    Sahanın ERA5 hücresi için saatlik yön [°] (2014-01-01 00 UTC'den) ve kaynak etiketi.
    Öncelik: yön gridi → ham santral hücresi → 0,5° içindeki en yakın yön grid hücresi → None (tek biçimli).
    """
    from src import veri_katmani

    e, b = hucre(enlem, boylam)
    p = veri_katmani.yol(f"grid/era5_yon_tr/{SURUM}/{dosya_adi(e, b)}", zorunlu=False)
    if p is not None:
        y = np.load(p)["yon"].astype(float) * (360.0 / SEKTOR)
        return (y if n_saat is None else y[:n_saat]), "era5_yon_grid"
    h = _ham_hucre(e, b)
    if h is not None:
        return (h if n_saat is None else h[:n_saat]), "era5_hucre"
    for de, db in sorted(((i * 0.25, j * 0.25) for i in (-2, -1, 0, 1, 2) for j in (-2, -1, 0, 1, 2)), key=lambda x: x[0] ** 2 + x[1] ** 2):
        if de == db == 0:
            continue
        p = veri_katmani.yol(f"grid/era5_yon_tr/{SURUM}/{dosya_adi(e + de, b + db)}", zorunlu=False)
        if p is not None:
            y = np.load(p)["yon"].astype(float) * (360.0 / SEKTOR)
            return (y if n_saat is None else y[:n_saat]), "era5_yon_grid_komsu"
        h = _ham_hucre(e + de, b + db)
        if h is not None:
            return (h if n_saat is None else h[:n_saat]), "era5_hucre_komsu"
    return None, "yok"


def paketle_yil_dosyalari(dosyalar: list[Path], hucreler: list[tuple[float, float]]) -> int:
    """İndirilen yıllık netCDF'lerden (u100, v100) hücre başına uint8 yön sektörü dosyaları üretir."""
    import xarray as xr

    KLASOR.mkdir(parents=True, exist_ok=True)
    ds = xr.open_mfdataset([str(d) for d in sorted(dosyalar)], combine="by_coords")
    zaman = "valid_time" if "valid_time" in ds.dims else "time"
    ds = ds.sortby(zaman)
    lat = ds["latitude"].to_numpy()
    lon = ds["longitude"].to_numpy()
    sayi = 0
    for e, b in hucreler:
        i, j = int(np.argmin(np.abs(lat - e))), int(np.argmin(np.abs(lon - b)))
        if abs(lat[i] - e) > 1e-6 or abs(lon[j] - b) > 1e-6:
            continue
        u = ds["u100"].isel(latitude=i, longitude=j).to_numpy()
        v = ds["v100"].isel(latitude=i, longitude=j).to_numpy()
        np.savez_compressed(KLASOR / dosya_adi(e, b), yon=sektor(yon_derece(u, v)), bas=np.array(BAS))
        sayi += 1
    return sayi
