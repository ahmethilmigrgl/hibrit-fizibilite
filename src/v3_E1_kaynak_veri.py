"""
v3 E1/E4 — Elle derlenen, kaynaklı küçük veri dosyaları (data/atlas/, CC BY 4.0; kaynaklar dosyalarda):
    tedarik_kaynaklari.csv  proje kargosu limanları ve yerli bileşen üreticileri (konum ilçe/liman düzeyinde yaklaşık)
    goc_koridorlari.json    süzülen kuş göç darboğazları ve koridorları — YAKLAŞIK risk katmanı (yerinde ornitoloji
                            çalışmasının yerini tutmaz)
    teias_yeka_baglanti.csv YEKA RES-2025 TEİAŞ bağlantı görüşleri (trafo merkezi, gerilim, hat uzunluğu)
Çalıştırma: .venv/bin/python src/v3_E1_kaynak_veri.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import KOK

ATLAS = KOK / "data" / "atlas"
TUREB = "TÜREB (Ocak 2025) 'Türkiye Rüzgar Enerjisi Mevcut Durum Analiz Raporu', IPA III/2023/450-707, §3.3"

# ad, tür, bileşenler, il/ilçe, enlem, boylam, doğrulandı, kaynak, not
KAYNAKLAR = [
    (
        "Aliağa limanları (Nemport, Batı Liman, SOCAR)",
        "liman",
        "kanat;kule;nasel;gobek",
        "İzmir/Aliağa",
        38.835,
        26.945,
        True,
        f"{TUREB} (İzmir limanları); Atlas Lashing 'Aliağa limanlarında rüzgar enerjisi lashingi'",
        "İzmir körfezinin proje kargo terminalleri",
    ),
    ("Bandırma Limanı (Çelebi)", "liman", "kanat;kule;nasel;gobek", "Balıkesir/Bandırma", 40.355, 27.975, True, TUREB, ""),
    ("Gemlik limanları (Gemport, Borusan)", "liman", "kanat;kule;nasel;gobek", "Bursa/Gemlik", 40.425, 29.105, True, TUREB, ""),
    (
        "Samsunport",
        "liman",
        "kanat;kule;nasel;gobek",
        "Samsun/Tekkeköy",
        41.285,
        36.360,
        True,
        f"{TUREB}; DARGEB 'Samsunport' (proje kargo, 350.000 m² açık saha)",
        "",
    ),
    (
        "Port Akdeniz",
        "liman",
        "kanat;kule;nasel;gobek",
        "Antalya/Konyaaltı",
        36.835,
        30.610,
        True,
        "DARGEB 'Port Akdeniz': elleçlenen ana proje kargolar rüzgar türbinlerini içerir",
        "",
    ),
    (
        "Limakport İskenderun",
        "liman",
        "kanat;kule;nasel;gobek",
        "Hatay/İskenderun",
        36.590,
        36.180,
        False,
        "—",
        "ADAY: genel/konteyner limanı; rüzgar türbini proje kargosu kaydı doğrulanamadı → modelde varsayılan olarak kullanılmaz",
    ),
    (
        "TPI Composites (İzmir tesisleri)",
        "uretici",
        "kanat",
        "İzmir/Menemen (yaklaşık)",
        38.600,
        27.070,
        True,
        f"{TUREB}; enerjirehberi.com.tr (2024) 'İzmir'de iki ayrı üretim tesisi'",
        "kapasite yayımlanmamış; konum ilçe düzeyinde yaklaşık",
    ),
    (
        "Nordex Türkiye (nasel montajı)",
        "uretici",
        "nasel;gobek",
        "İzmir (yaklaşık)",
        38.470,
        27.210,
        True,
        "enerjirehberi.com.tr (2024): İzmir'de bileşen üretimi ve montaj",
        "yalnız Nordex türbinleri için; konum il düzeyinde yaklaşık",
    ),
    (
        "Ateş Wind Power (kule)",
        "uretici",
        "kule",
        "İzmir/Bergama",
        39.120,
        27.180,
        True,
        f"{TUREB} (Ateş Çelik); aeworldmap (merkez Bergama, İzmir-Çanakkale yolu 83. km)",
        "kapasite yayımlanmamış",
    ),
    (
        "Gesbey (kule)",
        "uretici",
        "kule",
        "Balıkesir/Gönen (Bandırma OSB)",
        40.230,
        27.840,
        True,
        f"{TUREB}; Beyçelik/Gesbey kurumsal sayfası; Para Dergi 2023 (ikinci fabrika)",
        "yıllık 430 kule kapasitesi (Gesbey)",
    ),
    (
        "Çimtaş (kule)",
        "uretici",
        "kule",
        "Bursa/Gemlik (yaklaşık)",
        40.400,
        29.120,
        False,
        TUREB,
        "TÜREB üretici olarak listeliyor; tesis konumu doğrulanamadı (Bursa olarak varsayıldı)",
    ),
    (
        "TEMSAN (kule)",
        "uretici",
        "kule",
        "Ankara (yaklaşık)",
        39.950,
        32.700,
        False,
        TUREB,
        "TÜREB üretici olarak listeliyor; tesis konumu doğrulanamadı (Ankara merkezi)",
    ),
]

# Göç koridorları: (ad, poli çizgi [(enlem, boylam)], yüksek risk yarıçapı km, orta risk yarıçapı km, kaynak)
GOC = [
    (
        "İstanbul Boğazı",
        [(41.23, 29.12), (41.10, 29.06), (40.99, 29.02)],
        10,
        40,
        "Doğa Derneği: dünyanın en önemli üç süzülen kuş darboğazından biri; Bosphorus sayımları (Bird Study 2014; Forestist 2007 sonbahar sayımı; 2008'de 19 günde 141.844 yırtıcı)",
    ),
    (
        "Çanakkale Boğazı – Gelibolu",
        [(40.42, 26.68), (40.15, 26.39), (40.00, 26.20)],
        10,
        30,
        "Batı Türkiye'de göç su yüzeyinin en dar olduğu iki darboğazda: İstanbul Boğazı ve Gelibolu Yarımadası–Çanakkale Boğazı (Bosphorus göç literatürü)",
    ),
    (
        "Amanos Dağları – Belen geçidi",
        [(36.20, 36.05), (36.49, 36.20), (36.90, 36.40), (37.20, 36.55)],
        15,
        40,
        "Doğa Derneği (Amanos/Belen üç büyük darboğazdan biri); 'Migration dynamics of soaring birds between autumn 2015 and spring 2019 at the Belen pass' (650.151 süzülen kuş)",
    ),
    (
        "Doğu Karadeniz Dağları – Çoruh vadisi",
        [(41.52, 41.55), (41.36, 41.68), (41.18, 41.82), (40.82, 41.55)],
        15,
        35,
        "Doğa Derneği (Doğu Karadeniz Dağları/Çoruh vadisi); Jobson vd. 2021 Sandgrouse 43 (Batum en yüksek sonbahar sayımlarından)",
    ),
    (
        "Doğu Karadeniz kıyı koridoru",
        [(41.40, 41.40), (41.02, 40.52), (41.00, 39.70)],
        0,
        25,
        "Batum darboğazına uzanan kıyı göç hattı (Jobson vd. 2021); yalnız orta risk",
    ),
    (
        "Sarımazı (Ceyhan)",
        [(36.75, 35.70), (36.85, 35.85)],
        0,
        20,
        "Jobson vd. 2021 Sandgrouse 43: Karadeniz–Akdeniz göç yolunun darboğazları arasında 'Sarımazı, Ceyhan'",
    ),
]

YEKA = [
    ("R25-SİVAS RES", 500, "Sivas", "Bozok TM", 400, 210, "yeni EİH"),
    ("R25-BALIKESİR-1 RES", 160, "Balıkesir", "Uygar RES TM", 400, 46, "yeni EİH"),
    ("R25-BALIKESİR-2 RES", 120, "Balıkesir", "Çan Havza TM", 400, 52, "yeni EİH"),
    ("R25-BALIKESİR-3 RES", 110, "Balıkesir", "Soma RES TM", 400, 26, "yeni EİH"),
    (
        "R25-AYDIN-DENİZLİ RES",
        140,
        "Aydın/Denizli",
        "Alaşehir TM – Kızıldere-1 JES EİH (girdi-çıktı)",
        154,
        14,
        "2 × 7 km + 10 km yenileme",
    ),
    ("R25-KÜTAHYA RES", 120, "Kütahya", "Emet TM", 154, 24, "+ 33 km yenileme"),
]


def main() -> None:
    k = pd.DataFrame(KAYNAKLAR, columns=["ad", "tur", "bilesenler", "konum", "enlem", "boylam", "dogrulandi", "kaynak", "not"])
    k.to_csv(ATLAS / "tedarik_kaynaklari.csv", index=False, encoding="utf-8-sig")
    g = {
        "aciklama": (
            "YAKLAŞIK süzülen kuş göç darboğazları ve koridorları: literatürde adı geçen darboğazların kabaca çizilmiş eksenleri ve "
            "tampon yarıçapları (yüksek / orta risk). Yerinde ornitoloji çalışmasının (en az iki göç dönemi gözlem) yerini TUTMAZ; "
            "yalnız ön eleme ve uyarı içindir."
        ),
        "lisans": "CC BY 4.0 (kendi derlemem; kaynaklar her öğede)",
        "koridorlar": [{"ad": a, "eksen": p, "yuksek_km": y, "orta_km": o, "kaynak": s} for a, p, y, o, s in GOC],
    }
    (ATLAS / "goc_koridorlari.json").write_text(json.dumps(g, ensure_ascii=False, indent=1))
    pd.DataFrame(YEKA, columns=["proje", "mw", "il", "trafo_merkezi", "kv", "hat_km", "not"]).assign(
        kaynak="ETKB 'YEKA RES-2025 TEİAŞ bağlantı görüşleri' (enerji.gov.tr, 2025-09-09)"
    ).to_csv(ATLAS / "teias_yeka_baglanti.csv", index=False, encoding="utf-8-sig")
    print(k[["ad", "tur", "dogrulandi"]].to_string())


if __name__ == "__main__":
    main()
