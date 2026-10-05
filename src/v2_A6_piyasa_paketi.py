"""
v2 Faz A6 — Uygulamaya gömülecek ulusal piyasa paketi (tek komutla yeniden üretilir).

İçerik (data/atlas/piyasa/):
    saatlik.parquet  — UTC saatlik: PTF (TL, USD), Türkiye geneli rüzgâr ve güneş (lisanslı) üretimi [MWh],
                       SFK/PFK kapasite fiyatı (TL ve USD, 2023+), SMF (TL, USD)
    yillik.csv       — yıl sonu kurulu güç (rüzgâr, güneş; TEİAŞ), yıllık ortalama PTF (USD), rüzgâr/güneş yakalanma oranı
    parametreler.json — fiyat senaryoları, Monte Carlo, stres testi, gelir yığını ve YEKDEM parametreleri (config'ten)
    ozet.json        — kapsam, son veri tarihi, kaynak ve atıf metni
Lisans/koşul: EPİAŞ Şeffaflık Platformu verileri "kaynak gösterilmek suretiyle çoğaltılabilir ve kullanılabilir"
(seffaflik.epias.com.tr, Ekim 2026). Atıf: "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)".

Çalıştırma:
    .venv/bin/python src/v2_A6_piyasa_paketi.py              # mevcut işlenmiş veriden paket
    .venv/bin/python src/v2_A6_piyasa_paketi.py --guncelle   # önce EPİAŞ'tan yeni ayları çeker (src/02_piyasa_verisi.py;
                                                             # kişisel kimlik bilgisi yalnız bu çevrimdışı adımda)
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import ISLENMIS_VERI, KOK, config_oku, deger

PAKET = KOK / "data" / "atlas" / "piyasa"
ATIF = "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)"


def main() -> None:
    if "--guncelle" in sys.argv:
        subprocess.run([sys.executable, str(KOK / "src" / "02_piyasa_verisi.py")], check=True)
    cfg = config_oku()
    ptf = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")
    ur = pd.read_parquet(ISLENMIS_VERI / "uretim_turkiye_2014_guncel.parquet")
    yh = pd.read_parquet(ISLENMIS_VERI / "yan_hizmet_2023_guncel.parquet")
    s = pd.DataFrame({"ptf_tl": ptf["ptf_tl"], "ptf_usd": ptf["ptf_usd"], "ruzgar_mwh": ur["ruzgar"], "gunes_mwh": ur["gunes"]})
    for k in ["sfk_fiyat", "pfk_fiyat", "smf", "sfk_fiyat_usd", "pfk_fiyat_usd", "smf_usd"]:
        s[k] = yh[k].reindex(s.index)
    s = s.astype("float32")
    s.index.name = "zaman_utc"
    PAKET.mkdir(parents=True, exist_ok=True)
    s.to_parquet(PAKET / "saatlik.parquet", compression="zstd")

    yil = s.index.tz_convert("Europe/Istanbul").year
    g = s.assign(yil=yil)
    yakala = lambda kol: (
        (g["ptf_usd"] * g[kol]).groupby(g["yil"]).sum() / g[kol].groupby(g["yil"]).sum() / g.groupby("yil")["ptf_usd"].mean()
    )
    kg = cfg["kurulu_guc_turkiye"]
    yillik = pd.DataFrame(
        {
            "ptf_usd_ort": g.groupby("yil")["ptf_usd"].mean(),
            "ruzgar_yakalanma": yakala("ruzgar_mwh"),
            "gunes_yakalanma": yakala("gunes_mwh"),
            "saat": g.groupby("yil").size(),
        }
    )
    for t in ("ruzgar", "gunes"):
        if t in kg:
            yillik[f"kurulu_{t}_mw"] = pd.Series(deger(kg[t]) if isinstance(kg[t], dict) and "value" in kg[t] else kg[t])
    yillik.index.name = "yil"
    yillik.to_csv(PAKET / "yillik.csv", encoding="utf-8-sig", float_format="%.4f")

    anahtar = ["fiyat_senaryolari", "monte_carlo", "stres_testi", "gelir_yigini", "yekdem", "yekdem_opsiyon", "kesinti", "ortak_surucu"]
    param = {k: cfg[k] for k in anahtar if k in cfg}
    (PAKET / "parametreler.json").write_text(json.dumps(param, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ozet = {
        "ilk_saat_utc": str(s.index.min()),
        "son_saat_utc": str(s.index.max()),
        "son_ptf_saati_utc": str(s["ptf_usd"].dropna().index.max()),
        "satir": len(s),
        "atif": ATIF,
        "kosul": "EPİAŞ verileri kaynak gösterilerek çoğaltılabilir; EPİAŞ verilerden doğabilecek zararlardan sorumlu değildir.",
        "uretilme": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
    }
    (PAKET / "ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1), encoding="utf-8")
    boyut = sum(f.stat().st_size for f in PAKET.iterdir()) / 1e6
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    print(f"Paket: {PAKET.relative_to(KOK)} ({boyut:.2f} MB)")
    print(yillik.round(3).to_string())


if __name__ == "__main__":
    main()
