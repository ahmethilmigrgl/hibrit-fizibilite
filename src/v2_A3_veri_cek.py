"""
v2 Faz A3-2 — Kalibrasyon atlası için ham veri (çevrimdışı; kişisel CDS/EPİAŞ anahtarları yalnız burada).
Eşleşen her santral: EPİAŞ gerçek zamanlı üretim 2014–2026 (önbellek data/raw/epias/uretim_santral_{id}),
santral noktasının ERA5 hücresi 2014–2025 (önbellek data/raw/era5_hucre). Yarıda kalırsa kaldığı yerden devam eder.

Çalıştırma: .venv/bin/python src/v2_A3_veri_cek.py
"""

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import KOK
from src.kaynaklar import era5_cds
from src.piyasa import veri
from src.piyasa.epias import EpiasIstemcisi


def log(m: str) -> None:
    print(time.strftime("%H:%M:%S"), m, flush=True)


def main() -> None:
    e = pd.read_csv(KOK / "data" / "atlas" / "santral_eslestirme.csv")
    e = e[e["epias_id"].notna()]
    hucreler = sorted({era5_cds.hucre(a, b) for a, b in zip(e["enlem"], e["boylam"])})
    hata = []

    def cds_is():
        def bir(h):
            try:
                era5_cds.indir(*h)
            except Exception as ex:
                hata.append(("era5", h, type(ex).__name__))

        with ThreadPoolExecutor(max_workers=4) as hv:
            for i, _ in enumerate(hv.map(bir, hucreler), 1):
                if i % 10 == 0:
                    log(f"ERA5 hücre {i}/{len(hucreler)}")
        log("ERA5 bitti")

    t = threading.Thread(target=cds_is)
    t.start()
    ist = EpiasIstemcisi()
    for i, sid in enumerate(e["epias_id"].astype(int), 1):
        try:
            veri.uretim_cek(ist, "2014-01-01", "2026-09-30", santral_id=sid)
        except Exception as ex:
            hata.append(("epias", sid, type(ex).__name__))
        if i % 10 == 0:
            log(f"EPİAŞ santral {i}/{len(e)}")
    log("EPİAŞ bitti")
    t.join()
    log(f"Hatalar: {len(hata)} {hata[:20]}")


if __name__ == "__main__":
    main()
