# CLAUDE.md — Hibrit Fizibilite Projesi

Bu dosya her oturumda referans alınır. Kurallar burada; değişirse önce burayı güncelle.

## Projenin amacı
Türkiye'de seçilecek bir saha için güneş (GES), rüzgâr (RES) ve batarya (BESS) kapasitelerini,
**şebeke bağlantı kısıtı altında proje değerini (NPV) en yüksek yapacak şekilde** boyutlandıran
ve sonucu **belirsizlik altında (Monte Carlo)** test eden bir fizibilite modeli.

Proje bir CV/portföy çalışmasıdır: yenilenebilir enerji yatırım / proje geliştirme pozisyonlarına
başvuru için hazırlanıyor. Sonuçlar, varsayımlar ve formülasyonlar mülakatta açıklanabilir olmalı.

## Kullanıcı profili ve iletişim
- Endüstri mühendisliği öğrencisi.
- Python orta düzey (pandas/numpy rahat). **Optimizasyonu daha önce hiç uygulamadı** →
  optimizasyon kodunu ve kavramlarını adım adım, sade dille açıkla; yeni kavramı ilk kullanımda tanımla.
- **Dil: Türkçe.** Sohbet, kod yorumları, print/log çıktıları, grafik başlıkları ve dokümanlar Türkçe.
  (Değişken/fonksiyon adları ASCII olabilir; ör. `kapasite_ges`.)

## Teknik kurallar
- **Python 3.10/3.11**, sanal ortam `.venv`, bağımlılıklar `requirements.txt`.
  - Sistem Python'u 3.14 olduğu için `.venv`, `uv` ile kurulan Python 3.11 üzerinden oluşturuldu:
    `uv venv --python 3.11 .venv && uv pip install -r requirements.txt --python .venv/bin/python`
  - Çalıştırma: `.venv/bin/python src/<script>.py`
- **Optimizasyon:** Pyomo + HiGHS (`highspy` paketi, `SolverFactory("appsi_highs")`).
- **Varsayımlar koda gömülmez.** CAPEX, OPEX, kur, iskonto oranı, proje ömrü vb. `config.yaml`
  içinde tutulur; her birinin **kaynağı ve notu** yazılır. Kod bu değerleri config'den okur.
  (İstisna: `src/00_kurulum_testi.py` bir ısınma örneğidir, verileri bilerek kod içindedir.)
- **Klasörler:**
  - `data/raw` — ham indirilen veri (git'e eklenmez)
  - `data/processed` — işlenmiş veri (git'e eklenmez)
  - `src` — Python modülleri/scriptleri
  - `notebooks` — keşif ve analiz defterleri
  - `outputs` — grafikler ve sonuç tabloları
  - `docs` — açıklamalar ve matematiksel formülasyonlar
- **API kimlik bilgileri yalnızca `.env`** içinde (şablon: `.env.example`). Asla koda veya git'e girmez.
  Kodda `python-dotenv` ile okunur.
- **Her optimizasyon modelinin matematiksel formülasyonu** (kümeler, parametreler, karar
  değişkenleri, amaç fonksiyonu, kısıtlar) `docs/` altına markdown olarak yazılır. Kullanıcı
  bunları mülakatta açıklayabilmeli: bağlayıcı kısıtlar ve sonucun sezgisel yorumu da eklenir.
- Kodda modeller şu bloklarla yazılır: Kümeler → Parametreler → Karar değişkenleri → Amaç → Kısıtlar → Çözüm/rapor.
- **Her aşama bitince git commit** at (Türkçe, açıklayıcı mesaj).

## Aşamalar
0. **Kurulum** — klasör yapısı, ortam, ısınma LP modeli (`src/00_kurulum_testi.py`, `docs/00_isinma_modeli.md`) ✅
1. **Saha seçimi + üretim modeli:** PVGIS (güneş, pvlib) ve ERA5 (rüzgâr, cdsapi + türbin güç eğrisi)
   ile çok yıllı saatlik üretim profilleri. ✅ Saha: **Çanakkale-Ezine**; profiller
   `data/processed/ezine_profiller_2014_2023.parquet` (UTC, MW AC başına KF), bkz. `docs/01_uretim_modeli.md`.
   Açık iş: Aşama 2'de EPİAŞ santral üretimiyle `ruzgar_hiz_kalibrasyon_katsayisi` kalibrasyonu;
   EPİAŞ (TSİ) verisi `Europe/Istanbul` ile UTC'ye çevrilmeli (2016 öncesi yaz saati var).
2. **Piyasa analizi:** EPİAŞ Şeffaflık Platformu saatlik PTF, güneş/rüzgâr yakalanan fiyat
   (capture price/rate), kanibalizasyon trendi, kur etkisi. ✅ Bkz. `docs/02_piyasa_analizi.md`.
   Rüzgâr kalibre edildi (k = 1,065). EPİAŞ istemcisi: `src/piyasa/epias.py` (TGT otomatik yenileme,
   önbellek, hata gövdesinde kullanıcı adı/IP yazdırılmaz).
   **Revizyon (yapıldı):** zaman hizası (tüm seriler [t, t+1) UTC aralık ortalaması) + ay × saat hız
   katsayısı matrisi (`data/processed/ruzgar_k_ay_saat.parquet`, yöntem `ruzgar_kalibrasyon_yontemi`).
   Öncesi/sonrası: `outputs/02_piyasa/revizyon_karsilastirma.csv`, eski çıktılar `outputs/revizyon_oncesi/`.
3. **Finansal model:** nakit akışı, NPV, IRR, LCOE. ✅ Bkz. `docs/03_finansal_model.md`. Çekirdek:
   `src/finans/model.py → proje_degerle(konfig, varsayimlar, fiyat_senaryosu, uretim_profili, bess_dispatch=None)`
   — reel USD, 10 hava yılı × 2 fiyat şekli yılı beklenen değer; batarya geliri için `bess_dispatch` kancası
   (net enjeksiyon dizisi, şekil (yıl, hava, şekil, 8760)) Aşama 4'te doldurulacak. Borç: `src/finans/borc.py`.
4. **Optimizasyon:** GES/RES/BESS kapasite boyutlandırma + saatlik batarya dispatch + şebeke kısıtı
   ve curtailment içeren MILP; küçük modelden başlayıp adım adım büyüt, gerekirse temsilî günlerle
   boyutu küçült.
5. **Risk simülasyonu:** Monte Carlo (hava yılı, fiyat, kur, CAPEX, batarya yıpranması), P50/P90,
   NPV/IRR dağılımları, tornado grafiği.
6. **Streamlit dashboard, README, kısa rapor.**
