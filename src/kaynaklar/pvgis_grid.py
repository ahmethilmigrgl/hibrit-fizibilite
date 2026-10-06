"""
Türkiye GES kapasite faktörü gridi (PVGIS-SARAH3, 2014–2023, saatlik) — ERA5 gridiyle aynı 0,25° hücreler.

Her kara hücresi için hücre içindeki, hücre merkezine en yakın kara noktasında (ilçe ızgarası) PVGIS seriescalc çağrılır
ve v1 güneş modeliyle (pvlib PVWatts, config uretim.gunes) saatlik AC KF hesaplanır. Yalnız KF saklanır (uint16, ×1e4):
ham ışınım bileşenleri hücre başına ~5 MB tutardı. Config'teki güneş varsayımları değişirse grid yeniden üretilmelidir
(manifest'te config özeti var).

Dosya: data/grid/pvgis_tr/{surum}/{enlem:.2f}_{boylam:.2f}.npz — kf (uint16), egim, nokta_enlem, nokta_boylam, bas (ISO UTC)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ayarlar import KOK, deger

GRID_SURUMU = "v1"
YILLAR = (2014, 2023)
KLASOR = KOK / "data" / "grid" / "pvgis_tr" / GRID_SURUMU


def dosya_adi(enlem: float, boylam: float) -> str:
    from src.kaynaklar.era5_grid import hucre

    e, b = hucre(enlem, boylam)
    return f"{e:.2f}_{b:.2f}.npz"


def temsil_noktasi(e: float, b: float) -> tuple[float, float]:
    """Hücre (merkez e, b; ±0,125°) içinde merkeze en yakın kara pikseli (ilçe ızgarası)."""
    from src.kaynaklar import sinirlar

    p = sinirlar._yukle()
    n, m = p["izgara"].shape
    enl = p["ust"] - (np.arange(n) + 0.5) * p["adim"]
    boy = p["sol"] + (np.arange(m) + 0.5) * p["adim"]
    ii = np.where(np.abs(enl - e) <= 0.125)[0]
    jj = np.where(np.abs(boy - b) <= 0.125)[0]
    alt = p["izgara"][np.ix_(ii, jj)] > 0
    if not alt.any():
        return e, b
    a, c = np.where(alt)
    d = (enl[ii][a] - e) ** 2 + ((boy[jj][c] - b) * np.cos(np.radians(e))) ** 2
    k = int(np.argmin(d))
    return float(enl[ii][a[k]]), float(boy[jj][c[k]])


def config_ozeti(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg["uretim"]["gunes"], sort_keys=True, default=str).encode()).hexdigest()[:12]


def indir_ve_paketle(e: float, b: float, cfg: dict) -> Path:
    import pvlib

    from src.uretim import gunes

    yol = KLASOR / dosya_adi(e, b)
    if yol.exists():
        return yol
    KLASOR.mkdir(parents=True, exist_ok=True)
    cg = cfg["uretim"]["gunes"]
    ne, nb = temsil_noktasi(e, b)
    veri, meta = pvlib.iotools.get_pvgis_hourly(
        ne,
        nb,
        start=YILLAR[0],
        end=YILLAR[1],
        surface_azimuth=deger(cg["azimut"]),
        optimal_surface_tilt=True,
        components=True,
        url=deger(cg["pvgis_url"]),
        timeout=180,
    )
    kf = gunes.gunes_kapasite_faktoru(veri, meta, cg)
    tmp = yol.with_suffix(".tmp.npz")
    np.savez_compressed(
        tmp,
        kf=np.clip(np.round(kf.to_numpy() * 1e4), 0, 65535).astype(np.uint16),
        egim=np.float32(gunes.optimum_egim(meta)),
        nokta_enlem=np.float32(ne),
        nokta_boylam=np.float32(nb),
        bas=np.array(str(kf.index[0].tz_convert("UTC").tz_localize(None))),
    )
    tmp.rename(yol)
    return yol


def ac(z: dict | Path) -> pd.Series:
    """Nokta dosyası → saatlik GES KF serisi (UTC indeks, v1 güneş modeli çıktısıyla aynı tanım)."""
    if isinstance(z, Path):
        z = dict(np.load(z))
    kf = z["kf"].astype(np.float32) / 1e4
    ind = pd.date_range(pd.Timestamp(str(z["bas"])), periods=len(kf), freq="h", tz="UTC")
    s = pd.Series(kf, index=ind, name="ges_kf")
    s.attrs["egim"] = float(z["egim"])
    return s
