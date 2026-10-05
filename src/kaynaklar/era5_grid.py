"""
Türkiye ERA5 nokta grid veri seti (v2 ana rüzgâr kaynağı; Open-Meteo yedek).

Biçim (nokta başına sıkıştırılmış .npz, 2014–2023 saatlik, UTC; sürüm GRID_SURUMU):
    v100, v10 : uint16, cm/s           (hız; yön gerekmez — model yalnız hız büyüklüğünü kullanır)
    t2m       : uint16, K × 50         (2 m sıcaklık; 0,02 K çözünürlük)
    sp        : uint16, Pa / 2         (yüzey basıncı; 2 Pa çözünürlük)
    bas       : başlangıç saati (ISO, UTC), saat sayısı = dizi uzunluğu
Kuantalama hatası: hız 0,005 m/s, sıcaklık 0,01 K, basınç 1 Pa — v1 rüzgâr modelinde ihmal edilebilir.
Dosya adı: {enlem:.2f}_{boylam:.2f}.npz (0,25° ERA5 grid noktası).
Yerel klasör: data/grid/era5_tr/{surum}/ (git'e girmez; Hugging Face veri deposuna yüklenir, bkz. hf_veri.py).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.ayarlar import KOK

GRID_SURUMU = "v1"
YILLAR = ("2014-01-01", "2023-12-31")
KLASOR = KOK / "data" / "grid" / "era5_tr" / GRID_SURUMU
VERI_SETI = "reanalysis-era5-single-levels-timeseries"
DEGISKENLER = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
    "2m_temperature",
    "surface_pressure",
]


def hucre(enlem: float, boylam: float) -> tuple[float, float]:
    return float(np.round(enlem * 4) / 4), float(np.round(boylam * 4) / 4)


def dosya_adi(enlem: float, boylam: float) -> str:
    e, b = hucre(enlem, boylam)
    return f"{e:.2f}_{b:.2f}.npz"


def kara_hucreleri() -> list[tuple[float, float]]:
    """Türkiye karasına (ilçe ızgarası) değen 0,25° ERA5 hücreleri."""
    from src.kaynaklar import sinirlar

    p = sinirlar._yukle()
    n, m = p["izgara"].shape
    enl = p["ust"] - (np.arange(n) + 0.5) * p["adim"]
    boy = p["sol"] + (np.arange(m) + 0.5) * p["adim"]
    ii, jj = np.where(p["izgara"] > 0)
    return sorted(set(zip(np.round(enl[ii] * 4) / 4, np.round(boy[jj] * 4) / 4)))


def paketle(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """CDS ERA5 tablosu (u100, v100, u10, v10, t2m, sp) → kuantalanmış diziler."""
    return {
        "v100": np.clip(np.round(np.hypot(df["u100"], df["v100"]) * 100), 0, 65535).astype(np.uint16),
        "v10": np.clip(np.round(np.hypot(df["u10"], df["v10"]) * 100), 0, 65535).astype(np.uint16),
        "t2m": np.clip(np.round(df["t2m"] * 50), 0, 65535).astype(np.uint16),
        "sp": np.clip(np.round(df["sp"] / 2), 0, 65535).astype(np.uint16),
        "bas": np.array(str(df.index[0].tz_convert("UTC").tz_localize(None))),
    }


def ac(z: dict | Path) -> pd.DataFrame:
    """Nokta dosyası → v1 rüzgâr modelinin beklediği tablo (u = hız, v = 0; t2m K, sp Pa; UTC indeks)."""
    if isinstance(z, Path):
        z = dict(np.load(z))
    n = len(z["v100"])
    idx = pd.date_range(str(z["bas"]), periods=n, freq="h", tz="UTC", name="zaman_utc")
    return pd.DataFrame(
        {"u100": z["v100"] / 100.0, "v100": 0.0, "u10": z["v10"] / 100.0, "v10": 0.0, "t2m": z["t2m"] / 50.0, "sp": z["sp"] * 2.0},
        index=idx,
    )


def indir_ve_paketle(enlem: float, boylam: float) -> Path:
    """Tek hücre: CDS'den indir, paketle, kaydet (varsa atla). Kişisel CDS anahtarı — yalnız çevrimdışı."""
    from src.ayarlar import cds_istemcisi

    yol = KLASOR / dosya_adi(enlem, boylam)
    if yol.exists():
        return yol
    KLASOR.mkdir(parents=True, exist_ok=True)
    e, b = hucre(enlem, boylam)
    # Atlas için daha önce indirilen hücre (2014–2025) varsa yeniden indirmeden kullan
    from src.kaynaklar import era5_cds

    onceki = era5_cds.KLASOR / f"era5_{e:.2f}_{b:.2f}_2014-01-01_2025-12-31.parquet"
    if onceki.exists():
        df = pd.read_parquet(onceki).loc[: f"{YILLAR[1]} 23:00"]
        tmp = yol.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, **paketle(df))
        tmp.rename(yol)
        return yol
    gecici = yol.with_suffix(".zip.part")
    cds_istemcisi().retrieve(
        VERI_SETI,
        {"variable": DEGISKENLER, "location": {"longitude": b, "latitude": e}, "date": [f"{YILLAR[0]}/{YILLAR[1]}"], "data_format": "csv"},
        str(gecici),
    )
    with zipfile.ZipFile(gecici) as zf:
        ad = next(x for x in zf.namelist() if x.endswith(".csv"))
        df = pd.read_csv(io.BytesIO(zf.read(ad)), parse_dates=["valid_time"])
    gecici.unlink()
    df = df.set_index("valid_time")
    df.index = df.index.tz_localize("UTC")
    df = df[~df.index.duplicated()].sort_index()
    tmp = yol.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **paketle(df))
    tmp.rename(yol)  # atomik: yarım dosya bırakmaz
    return yol
