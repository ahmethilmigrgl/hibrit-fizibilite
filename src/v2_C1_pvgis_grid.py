"""
v2 Faz C1 — Türkiye kara hücreleri için GES KF gridi (PVGIS-SARAH3, 2014–2023), gözetimsiz ve kaldığı yerden devam eder.

PVGIS anahtarsız bir API'dir (JRC; sınır 30 istek/s). Günlük: data/grid/pvgis_tr/v1/indirme.log; bitince manifest.json
(dosya, boyut, sha256, güneş config özeti). Uygulama çalışırken PVGIS'e bağlanmaz; bu grid'i okur.

Çalıştırma (arka planda):  nohup .venv/bin/python src/v2_C1_pvgis_grid.py > /dev/null 2>&1 &
"""

import hashlib
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ayarlar import config_oku
from src.kaynaklar import era5_grid
from src.kaynaklar import pvgis_grid as P

PARALEL = 4


def manifest(cfg: dict) -> None:
    kayit = [
        {"dosya": f.name, "bayt": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        for f in sorted(P.KLASOR.glob("*.npz"))
        if not f.name.endswith(".tmp.npz")
    ]
    (P.KLASOR / "manifest.json").write_text(
        json.dumps(
            {
                "surum": P.GRID_SURUMU,
                "donem": P.YILLAR,
                "nokta_sayisi": len(kayit),
                "gunes_config_ozeti": P.config_ozeti(cfg),
                "bicim": "kf uint16 ×1e4 (saatlik AC KF, 1 MWac başına); egim derece; bas ISO UTC",
                "dosyalar": kayit,
            },
            ensure_ascii=False,
            indent=0,
        )
    )


def main() -> None:
    cfg = config_oku()
    P.KLASOR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=P.KLASOR / "indirme.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    hucreler = era5_grid.kara_hucreleri()
    eksik = [h for h in hucreler if not (P.KLASOR / P.dosya_adi(*h)).exists()]
    logging.info("Başlangıç: %d hücre, %d eksik", len(hucreler), len(eksik))
    for tur in range(3):
        if not eksik:
            break
        hata = []
        with ThreadPoolExecutor(max_workers=PARALEL) as hv:
            gorev = {hv.submit(P.indir_ve_paketle, *h, cfg): h for h in eksik}
            for i, f in enumerate(as_completed(gorev), 1):
                h = gorev[f]
                try:
                    f.result()
                    logging.info("tamam %s (%d/%d)", P.dosya_adi(*h), i, len(eksik))
                except Exception as ex:
                    hata.append(h)
                    logging.error("HATA %s: %s %s", P.dosya_adi(*h), type(ex).__name__, str(ex)[:120])
        eksik = hata
        logging.info("Tur %d bitti; %d hata", tur + 1, len(eksik))
        if eksik:
            time.sleep(120)
    manifest(cfg)
    logging.info("BİTTİ. Eksik kalan: %d", len(eksik))


if __name__ == "__main__":
    main()
