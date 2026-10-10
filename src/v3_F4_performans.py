"""
v3 F4 — Santral performans izleme (çevrimdışı; aylık güncelleme betiği).

1. data/processed/izleme_gunluk.parquet yoksa ya da --veri verilirse: EPİAŞ önbelleği + ERA5 hücreleri + atlas k matrisleri →
   santral başına günlük gözlenen ve beklenen üretim (src/izleme/veri.py). Yeni ay için önce EPİAŞ önbelleğini güncelleyin
   (kimlik bilgisi yalnız bu ön hesaplamada, .env).
2. Analiz (src/izleme/analiz.py): olay ayıklama, akran normalizasyonu, taban dönem, Shewhart/EWMA/CUSUM (ARL0 kalibrasyonu),
   durum, tahmini kayıp, yapay arıza testi.
Çıktılar (yalnız türetilmiş tablolar; ham saatlik veri yok): data/atlas/izleme/{aylik.parquet, gunluk.parquet, durum.csv, dogrulama.json}
Çalıştırma: .venv/bin/python src/v3_F4_performans.py [--veri]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import KOK


def main() -> None:
    from src.izleme import analiz, veri

    p = KOK / "data" / "processed" / "izleme_gunluk.parquet"
    if "--veri" in sys.argv or not p.exists():
        veri.hazirla(p)
    r = analiz.analiz()
    d = r["dogrulama"]
    pd.set_option("display.width", 200)
    print(json.dumps({k: v for k, v in d.items() if k != "yapay_ariza"}, ensure_ascii=False, indent=1, default=float))
    print(
        pd.DataFrame(d["yapay_ariza"])
        .pivot_table(index=["dusus", "sure_hafta"], columns="kart", values=["yakalama", "gecikme_medyan_hafta"])
        .round(2)
    )
    du = r["durum"]
    print(
        du[du["durum"] != "normal"][["kod", "ad", "il", "durum", "son_acik", "alarm_donem_ewma", "b_akran", "kayip_mwh", "kayip_usd"]]
        .round(3)
        .to_string()
    )
    print(du[du["ad"].str.contains("SÖKE|MERYEM", case=False)].T.to_string())


if __name__ == "__main__":
    main()
