"""
v3 E1 — Türkiye eğim ve rakım gridi (250 m, GWA 250 m karolarıyla hizalı), Copernicus DEM GLO-90'dan.

Kaynak: Copernicus DEM GLO-90 (AWS açık veri, COG 1° karolar, 3″ ≈ 90 m). Lisans: ücretsiz, atıfla yeniden dağıtılabilir
("Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by
the European Union and ESA; all rights reserved"; v2 rakım gridinde de kullanıldı).
Yöntem: 90 m pikselde eğim = atan(|∇z|) (merkezi farklar, metre aralıkla; doğu-batı aralığı cos(enlem) ile), sonra 3 × 3
piksel blokta (0,0025° = 9″) ortalama ve en büyük eğim, ortalama rakım.
Çıktı: data/grid/egim_tr/v1/{e}_{b}.npz — egim_ort (uint8, 0,25° adım → değer/4), egim_azami (uint8, derece), rakim (int16, m)
Çalıştırma (çevrimdışı, ~1 GB okuma): .venv/bin/python src/v3_E1_egim_grid.py
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.ayarlar import KOK

URL = "https://copernicus-dem-90m.s3.amazonaws.com/{a}/{a}.tif"
KLASOR = KOK / "data" / "grid" / "egim_tr" / "v1"
ALT, UST, SOL, SAG = 35, 43, 25, 46
N = 1200


def karo(e: int, b: int) -> str:
    yol = KLASOR / f"{e}_{b}.npz"
    if yol.exists():
        return "var"
    import rasterio

    ad = f"Copernicus_DSM_COG_30_N{e:02d}_00_E{b:03d}_00_DEM"
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open(URL.format(a=ad)) as r:
            z = r.read(1, out_shape=(N, N)).astype(np.float32)
    except rasterio.errors.RasterioIOError:
        return "yok"
    enlem = e + 1 - (np.arange(N) + 0.5) / N
    dy = 111320.0 / N
    dx = (111320.0 / N) * np.cos(np.radians(enlem))[:, None]
    gy, gx = np.gradient(z)
    egim = np.degrees(np.arctan(np.hypot(gx / dx, gy / dy)))
    b3 = egim.reshape(400, 3, 400, 3)
    z3 = z.reshape(400, 3, 400, 3).mean((1, 3))
    np.savez_compressed(
        yol,
        egim_ort=np.clip(np.round(b3.mean((1, 3)) * 4), 0, 255).astype(np.uint8),
        egim_azami=np.clip(np.round(b3.max((1, 3))), 0, 255).astype(np.uint8),
        rakim=np.round(z3).astype(np.int16),
        ust=np.float64(e + 1),
        sol=np.float64(b),
        adim=np.float64(1 / 400),
    )
    return "tamam"


def main() -> None:
    KLASOR.mkdir(parents=True, exist_ok=True)
    isler = [(e, b) for e in range(ALT, UST) for b in range(SOL, SAG)]
    with ThreadPoolExecutor(max_workers=6) as hv:
        sonuc = list(hv.map(lambda x: karo(*x), isler))
    print({k: sonuc.count(k) for k in set(sonuc)})


if __name__ == "__main__":
    main()
