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
  - `tests` — pytest testleri (`.venv/bin/python -m pytest -q`)
  - `results` — dashboard ve rapor için küçük, toplulaştırılmış sonuçlar (repoya girer, < 1 MB)
  - `dashboard` — Streamlit Community Cloud giriş noktası (hafif requirements)
  - `docs/kariyer` — kişisel kariyer materyalleri (gitignore'da, repoya girmez)
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
   boyutu küçült. ✅ Bkz. `docs/04_optimizasyon.md`. Modüller `src/optimizasyon/`
   (batarya, hibrit + `dispatch_kancasi`, temsili_gunler, kapasite). Kapasite MILP'i: türbin sayısı tamsayı,
   yatırım kararı ikili (`yatirim="serbest"|"zorunlu"`), seviyelendirilmiş fiyat + vergi düzeltmeli yıllıklandırma.
   Ana sonuçlar tam yılla (≈36 s), ızgaralar 24 temsilî günle. Finansal modele ekonomik kesinti, batarya
   yenilemesi ve yıpranma eklendi; başabaş fiyat `src/finans/metrikler.py`. Düzenleyici anahtarlar: `duzenleme.*`.
5. **Gelir yığını + risk simülasyonu:** ✅ Bkz. `docs/05_risk_ve_gelir_yigini.md`. Bölüm A: yan hizmet (SFK, ikili
   katılım ≥30 MW), dengesizlik azaltımı, YEK-G, PPA, depolamalı lisans → `kapasite_coz(..., gelir=...)`, anahtarlar
   `gelir_yigini.*`; `src/05_gelir_yigini.py`. Bölüm B: `src/risk/` (işletme tabloları + ara değerleme, vektörize
   nakit akışı), `src/05_monte_carlo.py`, dağılımlar `monte_carlo.*`. İşletme tabloları
   `data/processed/isletme_tablolari/` altında önbellekli (tasarım değişirse yeniden üretilir).
   **Stres testi (Aşama 6 Bölüm A):** SFK doyum modeli `src/risk/doyum.py`, `src/05_stres_testi.py`, parametreler
   `stres_testi.*`; öneri değişti (RES 58,8 + 30 MW aşamalı batarya + PPA), bkz. docs/05 §9.
6. **Paketleme ve yayın:** ✅ Giriş noktası `calistir.py --asama all|0..6`; testler `tests/`; dashboard `app.py`
   (yalnızca `results/` + `config.yaml`, pyomo gerektirmez; gezgin motoru `src/risk/gezgin.py`, ızgara
   `src/06_gezgin_tablolari.py`); `src/06_sonuclari_paketle.py` → `results/`; rapor `docs/RAPOR.md` →
   `src/06_rapor_pdf.py` → `outputs/RAPOR.pdf` (Chrome headless). README İngilizce, README.tr.md Türkçe.
7. **Tamamlayıcı analizler (gerçek dünya):** ✅ Bkz. `docs/07_tamamlayici_analizler.md`. Sistem kaynaklı kesinti
   (`src/07_sistem_kesintisi.py`, EPİAŞ DGP talimat özetleri + ERA5 2024-26 ile referans santral analizi),
   gelir yapıları tüccar/PPA/YEKDEM + teşvik + CO2 (`src/07_gelir_yapilari.py`; değerleyicide `phi`, `ppa_fiyat`,
   `kesinti_gelir/enerji` kancaları), CPM + Monte Carlo takvim (`src/07_takvim.py`), risk kaydı (`src/07_risk_kaydi.py`).
   Parametreler `kesinti`, `yekdem`, `tesvik`, `karbon`, `takvim`. Öneri değişti: inşaata hazır proje + (endeksli) YEKDEM,
   batarya kararı FID'de.
