"""
Tüm hattı sırayla çalıştıran giriş noktası.

Kullanım:
    .venv/bin/python calistir.py --asama all        # baştan sona (ilk kurulumda ~3-4 saat, çoğu veri indirme)
    .venv/bin/python calistir.py --asama 3          # yalnızca bir aşama
    .venv/bin/python calistir.py --asama 4 5 6      # birkaç aşama
    .venv/bin/python calistir.py --listele          # adımları ve gereken kimlik bilgilerini göster
    .venv/bin/python calistir.py --asama all --kuru # çalıştırmadan ne yapılacağını göster

Kimlik bilgileri yalnızca .env'den okunur (şablon: .env.example) ve hiçbir zaman yazdırılmaz.
İndirilen ham yanıtlar data/raw altında önbelleğe alınır; önbellek doluysa adımlar kimlik bilgisi olmadan da çalışır.

Bağımlılık notu (ilk kurulum): rüzgâr profili, Aşama 2'deki kalibrasyonun ürettiği ay × saat katsayı matrisine
(data/processed/ruzgar_k_ay_saat.parquet) ihtiyaç duyar. Bu yüzden "all" sırası: saha taraması → EPİAŞ verisi →
rüzgâr kalibrasyonu → üretim profilleri → piyasa analizi → ...
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
PY = sys.executable

# (aşama, betik, gereken kimlik bilgisi, açıklama)
ADIMLAR = [
    ("0", "00_kurulum_testi.py", None, "Isınma LP modeli (Pyomo + HiGHS kurulum testi)"),
    ("1", "01_saha_taramasi.py", "CDS", "Aday sahaların taranması (PVGIS + ERA5)"),
    ("2", "02_piyasa_verisi.py", "EPİAŞ", "PTF, üretim, AUF, santral üretimleri, yan hizmet ve YEK-G verisi"),
    ("2", "02_ruzgar_kalibrasyonu.py", "CDS", "ERA5 rüzgâr modelinin Ezine RES'leriyle kalibrasyonu (ay × saat katsayısı)"),
    ("1", "01_uretim_profilleri.py", "CDS", "Ezine için 10 yıllık saatlik GES/RES profilleri ve P50/P90"),
    ("2", "02_piyasa_analizi.py", None, "Yakalanan fiyat, kanibalizasyon, ördek eğrisi"),
    ("2", "02_revizyon_karsilastirma.py", None, "Rüzgâr gün içi şekil revizyonunun önce/sonra karşılaştırması"),
    ("3", "03_finansal_model.py", None, "Nakit akışı, NPV/IRR/LCOE, borç, tornado"),
    ("4", "04_optimizasyon.py", None, "Batarya dispatch LP'leri ve kapasite MILP'i"),
    ("5", "05_gelir_yigini.py", None, "Gelir yığını (yan hizmet, PPA, depolamalı lisans) ile yeniden optimizasyon"),
    ("5", "05_monte_carlo.py", None, "Monte Carlo risk simülasyonu"),
    ("5", "05_stres_testi.py", None, "Yan hizmet doyum stres testi, fırsat penceresi, erteleme, esnek batarya"),
    ("7", "07_sistem_kesintisi.py", "EPİAŞ", "Sistem kaynaklı kesinti (YAT talimatları; ERA5 2024-26 gerekir)"),
    ("7", "07_gelir_yapilari.py", None, "Tüccar / PPA / YEKDEM + kesinti Monte Carlo, teşvik, CO2"),
    ("7", "07_takvim.py", None, "Proje takvimi: CPM + Monte Carlo, COD dağılımı, kritiklik"),
    ("7", "07_baz_vaka.py", None, "Nihai baz vaka metrikleri (config.yaml → nihai_baz_vaka)"),
    ("7", "07_risk_kaydi.py", None, "Risk kaydı (Excel) ve ısı haritası"),
    ("6", "06_gezgin_tablolari.py", None, "Dashboard tasarım gezgini işletme tabloları"),
    ("6", "06_sonuclari_paketle.py", None, "Dashboard/rapor için results/ klasörü (küçük, toplulaştırılmış)"),
    ("6", "06_rapor_pdf.py", None, "docs/RAPOR.md → outputs/RAPOR.pdf"),
]
KIMLIK = {"CDS": ["CDS_URL", "CDS_KEY"], "EPİAŞ": ["EPIAS_USERNAME", "EPIAS_PASSWORD"]}


def kimlik_var(tur: str) -> bool:
    """Gerekli .env anahtarları tanımlı mı? (değerler okunur ama asla yazdırılmaz)"""
    try:
        from dotenv import dotenv_values
        env = {**dotenv_values(KOK / ".env"), **os.environ}
    except ImportError:
        env = dict(os.environ)
    return all(env.get(k) for k in KIMLIK[tur])


def main():
    ap = argparse.ArgumentParser(description="Hibrit fizibilite hattını çalıştırır.")
    ap.add_argument("--asama", nargs="+", default=[], help="0-7 veya 'all'")
    ap.add_argument("--listele", action="store_true", help="Adımları listele")
    ap.add_argument("--kuru", action="store_true", help="Çalıştırmadan göster")
    a = ap.parse_args()

    if a.listele or not a.asama:
        print(f"{'Aşama':<6}{'Betik':<32}{'Kimlik bilgisi':<22}Açıklama")
        for asama, betik, kim, acik in ADIMLAR:
            durum = "" if kim is None else (" (.env tamam)" if kimlik_var(kim) else " (.env eksik)")
            print(f"{asama:<6}{betik:<32}{(kim or '-') + durum:<22}{acik}")
        print("\nÖrnek: .venv/bin/python calistir.py --asama all")
        return

    secim = [x for x in ADIMLAR if "all" in a.asama or x[0] in a.asama]
    for asama, betik, kim, acik in secim:
        if kim and not kimlik_var(kim):
            print(f"UYARI: {betik} {kim} kimlik bilgisi ister (.env içinde {', '.join(KIMLIK[kim])}); "
                  "önbellek yoksa bu adım başarısız olur.", flush=True)
        print(f"\n=== Aşama {asama}: {betik} — {acik}", flush=True)
        if a.kuru:
            continue
        t0 = time.time()
        r = subprocess.run([PY, str(KOK / "src" / betik)], cwd=KOK)
        if r.returncode != 0:
            sys.exit(f"HATA: {betik} {r.returncode} koduyla bitti; hat durduruldu.")
        print(f"--- {betik} tamamlandı ({(time.time() - t0) / 60:.1f} dk)", flush=True)


if __name__ == "__main__":
    main()
