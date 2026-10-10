"""
v3 D0 — ERA5 100 m rüzgâr yönü gridi (Türkiye, 2014–2023 saatlik): çevrimdışı indirme + hücre başına paketleme.

Kaynak: Copernicus CDS 'reanalysis-era5-single-levels' (u100, v100), Türkiye kutusu, 0,25°, yarım yıllık istekler.
Kişisel CDS anahtarı yalnız bu çevrimdışı betikte (.env). Yarıda kalırsa kaldığı yerden devam eder.
Günlük: data/raw/era5_yon/indirme.log. Çıktı: data/grid/era5_yon_tr/v1/*.npz (git'e girmez).

Çalıştırma (arka planda):  nohup .venv/bin/python src/v3_D0_era5_yon_grid.py > /dev/null 2>&1 &
Yalnız paketleme:          .venv/bin/python src/v3_D0_era5_yon_grid.py paketle
"""

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ayarlar import cds_istemcisi
from src.kaynaklar import era5_grid, era5_yon

ALAN = [42.25, 25.75, 35.75, 44.75]  # K, B, G, D (era5_grid kara hücrelerini kapsar)
DONEMLER = [(y, aylar) for y in range(2014, 2024) for aylar in (range(1, 7), range(7, 13))]
PARALEL = 3


def _gunluk() -> logging.Logger:
    era5_yon.HAM.mkdir(parents=True, exist_ok=True)
    g = logging.getLogger("era5_yon")
    if not g.handlers:
        h = logging.FileHandler(era5_yon.HAM / "indirme.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        g.addHandler(h)
        g.setLevel(logging.INFO)
    return g


def indir(yil: int, aylar) -> Path:
    yol = era5_yon.HAM / f"uv100_{yil}_{aylar[0]:02d}.nc"
    if yol.exists():
        return yol
    gecici = yol.with_suffix(".part")
    cds_istemcisi().retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": ["reanalysis"],
            "variable": ["100m_u_component_of_wind", "100m_v_component_of_wind"],
            "year": [str(yil)],
            "month": [f"{m:02d}" for m in aylar],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": ALAN,
            "grid": [0.25, 0.25],
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(gecici),
    )
    gecici.rename(yol)
    return yol


def main() -> None:
    g = _gunluk()
    if len(sys.argv) < 2 or sys.argv[1] != "paketle":
        for tur in (1, 2, 3):
            eksik = [(y, a) for y, a in DONEMLER if not (era5_yon.HAM / f"uv100_{y}_{a[0]:02d}.nc").exists()]
            g.info(f"Tur {tur}: {len(eksik)} eksik dönem")
            if not eksik:
                break
            with ThreadPoolExecutor(max_workers=PARALEL) as hv:
                isler = {hv.submit(indir, y, a): (y, a[0]) for y, a in eksik}
                for f in as_completed(isler):
                    try:
                        f.result()
                        g.info(f"tamam {isler[f]}")
                    except Exception as ex:
                        g.warning(f"hata {isler[f]}: {type(ex).__name__}: {str(ex)[:200]}")
            time.sleep(5)
    dosyalar = sorted(era5_yon.HAM.glob("uv100_*.nc"))
    if len(dosyalar) < len(DONEMLER):
        g.warning(f"Paketleme ertelendi: {len(dosyalar)}/{len(DONEMLER)} dönem")
        return
    n = era5_yon.paketle_yil_dosyalari(dosyalar, era5_grid.kara_hucreleri())
    g.info(f"BİTTİ. Paketlenen hücre: {n}")


if __name__ == "__main__":
    main()
