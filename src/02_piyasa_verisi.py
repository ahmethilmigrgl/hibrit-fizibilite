"""
Aşama 2 — EPİAŞ verisinin indirilmesi ve işlenmesi

    • Saatlik PTF (TL, USD, EUR)                      → data/processed/ptf_2014_guncel.parquet
    • Türkiye geneli kaynak bazında saatlik üretim    → data/processed/uretim_turkiye_2014_guncel.parquet
    • Ezine çevresi RES'lerin saatlik üretimi         → data/processed/ezine_res_santralleri.parquet
    • Azami uzlaştırma fiyatı (AUF), aylık            → data/processed/auf_2022_2023.parquet

Ham yanıtlar data/raw/epias altında önbelleğe alınır; tekrar çalıştırmada yalnızca eksik parçalar indirilir.
Tüm zaman damgaları UTC'dir (dönüşüm kuralları: src/piyasa/veri.py).

Çalıştırma: .venv/bin/python src/02_piyasa_verisi.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import ISLENMIS_VERI, config_oku, deger
from src.piyasa.epias import EpiasIstemcisi
from src.piyasa.veri import auf_cek, ptf_cek, uretim_cek


def main():
    cfg = config_oku()
    bas, son = deger(cfg["piyasa"]["veri_baslangic"]), deger(cfg["piyasa"]["veri_bitis"])
    c = EpiasIstemcisi()
    ISLENMIS_VERI.mkdir(parents=True, exist_ok=True)

    print(f"PTF {bas} → {son} ...", flush=True)
    ptf = ptf_cek(c, bas, son)
    ptf.to_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")
    print(f"  {len(ptf)} saat, doldurulan {int(ptf.dolduruldu.sum())}", flush=True)

    print("Türkiye geneli üretim ...", flush=True)
    ur = uretim_cek(c, bas, son)
    ur.to_parquet(ISLENMIS_VERI / "uretim_turkiye_2014_guncel.parquet")
    print(f"  {len(ur)} saat, doldurulan {int(ur.dolduruldu.sum())}", flush=True)

    print("Azami uzlaştırma fiyatı (AUF) ...", flush=True)
    auf_cek(c).to_parquet(ISLENMIS_VERI / "auf_2022_2023.parquet")

    parcalar = []
    for kod, s in cfg["kalibrasyon_santralleri"].items():
        print(f"Santral: {s['ad']} (id {s['epias_id']}) ...", flush=True)
        d = uretim_cek(c, bas, son, santral_id=s["epias_id"])
        parcalar.append(d["toplam"].rename(kod))
    santraller = pd.concat(parcalar, axis=1)
    santraller.index.name = "zaman_utc"
    santraller.to_parquet(ISLENMIS_VERI / "ezine_res_santralleri.parquet")
    print("Tamamlandı.", flush=True)


if __name__ == "__main__":
    main()
