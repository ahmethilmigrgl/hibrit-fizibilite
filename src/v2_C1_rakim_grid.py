"""
v2 Faz C1 — Türkiye rakım ızgarası (0,02°), çevrimdışı.

Kaynak: Copernicus DEM GLO-90 (AWS açık veri, Cloud Optimized GeoTIFF; Open-Meteo yükseklik API'sinin de kullandığı DEM —
atlas santral rakımlarıyla aynı kaynak). 1° × 1° karoların yalnız düşük çözünürlüklü özet katmanı okunur (alan ortalaması,
50 × 50 hücre). Uygulama çalışırken DEM'e bağlanmaz; arazi.rakim() bu ızgarayı okur.
Çıktı: data/grid/rakim_tr/v1/rakim_002.npz — rakim (int16 m; −32768 = veri yok/deniz), ust, sol, adim
Atıf: "Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
the European Union and ESA; all rights reserved."

Çalıştırma: .venv/bin/python src/v2_C1_rakim_grid.py
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import rasterio
from rasterio.enums import Resampling

from src.kaynaklar.arazi import RAKIM_GRID

YOK = -32768
UST, SOL, ALT, SAG, N = 43, 25, 35, 45, 50  # 1° karo başına 50 hücre → 0,02°
URL = "https://copernicus-dem-90m.s3.amazonaws.com/{a}/{a}.tif"


def karo(e: int, b: int) -> np.ndarray | None:
    ad = f"Copernicus_DSM_COG_30_N{e:02d}_00_E{b:03d}_00_DEM"
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open(URL.format(a=ad)) as r:
            return r.read(1, out_shape=(N, N), resampling=Resampling.average)
    except rasterio.errors.RasterioIOError:  # karo yok (deniz)
        return None


def main() -> None:
    rakim = np.full(((UST - ALT) * N, (SAG - SOL) * N), YOK, dtype=np.int16)
    isler = [(e, b) for e in range(ALT, UST) for b in range(SOL, SAG)]
    with ThreadPoolExecutor(8) as hv:
        for (e, b), a in zip(isler, hv.map(lambda x: karo(*x), isler), strict=True):
            if a is not None:
                i0, j0 = (UST - 1 - e) * N, (b - SOL) * N
                rakim[i0 : i0 + N, j0 : j0 + N] = np.clip(np.round(a), -1000, 6000).astype(np.int16)
    RAKIM_GRID.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RAKIM_GRID, rakim=rakim, ust=np.float64(UST), sol=np.float64(SOL), adim=np.float64(1 / N))
    print("Tamam:", RAKIM_GRID, round(RAKIM_GRID.stat().st_size / 1e6, 2), "MB;", int((rakim != YOK).sum()), "hücre")


if __name__ == "__main__":
    main()
