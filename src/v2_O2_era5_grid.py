"""
v2 Ö2 — Türkiye kara hücreleri için ERA5 grid indirmesi (2014–2023), gözetimsiz ve kaldığı yerden devam eder.

Günlük: data/grid/era5_tr/{surum}/indirme.log (hücre başına başarı/hata). Bitince manifest.json (dosya adı, boyut, sha256).
Kişisel CDS anahtarı yalnız bu çevrimdışı betikte.

Çalıştırma (arka planda):  nohup .venv/bin/python src/v2_O2_era5_grid.py > /dev/null 2>&1 &
"""

import hashlib
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kaynaklar import era5_grid as G

PARALEL = 4


def manifest() -> None:
    kayit = []
    for f in sorted(G.KLASOR.glob("*.npz")):
        if f.name.endswith(".tmp.npz"):
            continue
        kayit.append({"dosya": f.name, "bayt": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    (G.KLASOR / "manifest.json").write_text(
        json.dumps(
            {
                "surum": G.GRID_SURUMU,
                "donem": G.YILLAR,
                "nokta_sayisi": len(kayit),
                "bicim": "uint16: v100,v10 cm/s; t2m K×50; sp Pa/2; bas ISO UTC",
                "dosyalar": kayit,
            },
            ensure_ascii=False,
            indent=0,
        )
    )


def main() -> None:
    G.KLASOR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=G.KLASOR / "indirme.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for ad in ("cdsapi", "urllib3", "ecmwf", "datapi", "multiurl"):
        logging.getLogger(ad).setLevel(logging.WARNING)
    hucreler = G.kara_hucreleri()
    eksik = [h for h in hucreler if not (G.KLASOR / G.dosya_adi(*h)).exists()]
    logging.info("Başlangıç: %d hücre, %d eksik", len(hucreler), len(eksik))
    for tur in range(3):  # başarısızlar için 3 tur
        if not eksik:
            break
        hata = []
        with ThreadPoolExecutor(max_workers=PARALEL) as hv:
            gorev = {hv.submit(G.indir_ve_paketle, *h): h for h in eksik}
            for i, f in enumerate(as_completed(gorev), 1):
                h = gorev[f]
                try:
                    f.result()
                    logging.info("tamam %s (%d/%d)", G.dosya_adi(*h), i, len(eksik))
                except Exception as ex:
                    hata.append(h)
                    logging.error("HATA %s: %s", G.dosya_adi(*h), type(ex).__name__)
        eksik = hata
        logging.info("Tur %d bitti; %d hata", tur + 1, len(eksik))
        if eksik:
            time.sleep(300)
    manifest()
    logging.info("BİTTİ. Eksik kalan: %d", len(eksik))


if __name__ == "__main__":
    main()
