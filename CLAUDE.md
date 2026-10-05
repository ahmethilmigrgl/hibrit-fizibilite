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
   **Ö1–Ö2 (tutarlılık):** YEKDEM'de batarya deşarjı da YEKDEM fiyatından (`IsletmeLP(desarj_sozlesmeli=True)`,
   `src/risk/yekdem_tablo.py`); PPA finansal fark sözleşmesi (`tuccar_dispatch`). Nihai baz vaka `config.yaml →
   nihai_baz_vaka` (`src/07_baz_vaka.py` → `outputs/07/baz_vaka.csv`): yatırım önerilmez (E[NPV] −11,4 M$). Ana sayılar
   bu dosyadan okunmalı.
   **Güncelleme 2 (tutarlılık):** YEKDEM yıllık opsiyon (md. 4/2, 5/1, 8/1; `config.yaml → yekdem_opsiyon`, karar 30 Kasım'da
   bilinen bilgiyle), ortak batarya sürücüsü (`ortak_surucu`: kurulu batarya → SFK, kesinti, kanibalizasyon), inşaata hazır
   takvim (COD P50 Kas 2029). Baz vaka: E[NPV] +1,5 M$ → dar kapsamlı durum tespiti + teklif (azami prim ~1,5 M$).
   Durum tespiti bilgi değeri: `outputs/07/durum_tespiti_bilgi_degeri.csv`. Sürücü kapalı karşılaştırma:
   `ORTAK_SURUCU=0 SADECE_G=1 .venv/bin/python src/07_gelir_yapilari.py`.
8. **Karar paketi:** ✅ `outputs/08/`. Excel modeli (`src/08_excel_model.py`: FAST benzeri, formüllü; LibreOffice ile yeniden
   hesap, 48/48 senaryo Python ile mutabık, `excel_mutabakat.csv`), yatırım memosu (`Yatirim_Memosu.md` → PDF,
   `src/08_memo_pdf.py`), sunum (`src/08_sunum_grafikleri.py` + `src/08_sunum.py` → `Sunum.pptx/.pdf`, 13 slayt),
   LinkedIn karuseli (`src/08_karusel.py` → `docs/kariyer/`). Memo kararı: 0,5 M$ durum tespiti + ≤1,5 M$ primle bağlayıcı
   olmayan teklif. Belgeler dashboard Yöntem sekmesinden ve README'den indirilebilir. LibreOffice: `~/Applications/LibreOffice.app`.
   **Güncelleme 3 (Aşama 9 Bölüm A):** fiyat süreci artık `fiyat_uzun_ortalama.tanim = "ortalama"` (58 = beklenen değer,
   `monte_carlo.log_merkez`; YEKDEM kararı `fiyat_tahmini`/`yekdem_katilim`). Deterministik → Monte Carlo köprüsü
   `src/07_fark_ayristirma.py [once|sonra]`. Baz vaka E[NPV] −1,66 M$ → karar (b) rafa kaldır, tetikleyicileri izle.
   Aşama 5–6 çıktıları (outputs/05_risk) medyan tanımıyla kaldı (tarihsel).
9. **Yayın öncesi kalite turu:** ✅ Bölüm A yukarıda (Güncelleme 3). Bölüm B: ruff (`pyproject.toml`; karusel betiği
   hariç), tip ipuçları/docstring, CI `.github/workflows/ci.yml` (ruff + `pytest -m "not veri"`; geliştirme bağımlılıkları
   `requirements-dev.txt`), `DATA_SOURCES.md` (Copernicus/PVGIS/EPİAŞ atıfları birebir), `docs/MODEL_DOGRULAMA.md`,
   dashboard cilası (Hakkında, `dashboard/favicon.png`, TR/EN sayı biçimi `tablo()`/`ciz()`, Markdown'da `$` kaçışı),
   README ekran görüntüleri `docs/img/`, `CHANGELOG.md`, etiket v1.0.0. Repo henüz push edilmedi (`REPO_URL` yer tutucu).

---

## v2 — Türkiye geneli saha tarama ve analiz uygulaması (dal: `v2-genel`)
**Amaç:** Projeyi yalnız Ezine için değil, kullanıcının Türkiye'de seçtiği herhangi bir saha için hızlı tarama ve tam
analiz yapan, herkese açık bir web uygulamasına dönüştürmek. v1.0.0 (Ezine analizi, `main` dalı ve etiket) değiştirilmez;
tüm v2 işi `v2-genel` dalında.

**Fazlar** (Faz A kullanıcı tarafından tanımlandı; B ve C taslaktır, başlarken kullanıcıyla netleştirilir):
- **Faz A — Veri altyapısı ve genelleştirme:** çalışma zamanı rüzgâr kaynağı (Open-Meteo), Global Wind Atlas, Türkiye
  RES kalibrasyon atlası (çevrimdışı EPİAŞ), kalibrasyon aktarım kuralı ve güven seviyeleri, sahaya bağlı parametreler
  (il/ilçe, TEİAŞ tarife bölgesi, türbin seçimi), ulusal piyasa paketi, saha nesnesiyle genelleştirilmiş hat + regresyon.
- **Faz B — Web uygulaması (taslak):** saha seçimi (harita/il-ilçe), hızlı tarama (dakikalar içinde) ve tam analiz
  (optimizasyon + Monte Carlo) akışları, sonuç raporu.
- **Faz C — Yayın ve işletim (taslak):** barındırma, önbellek/istek limiti yönetimi, izleme, kullanıcı dokümanı.

**Mimari kurallar (v2):**
- Web uygulaması çalışırken hiçbir kişisel kimlik bilgisi (CDS, EPİAŞ) kullanılmaz. EPİAŞ ve CDS yalnız çevrimdışı ön
  hesaplama betiklerinde; uygulama yalnız ön hesaplanmış dosyalar ve anahtarsız açık API'lerle çalışır.
- Saha bir parametredir: saha nesnesi (ad, enlem, boylam, il, ilçe, şebeke bağlantı MW, arazi/kapasite sınırları,
  isteğe bağlı kullanıcı varsayımları). Tüm hat bu nesneyle çalışır; Ezine'ye özgü sabit kalmaz.
- Her veri kaynağının lisansı ve kullanım koşulları (ticari olmayan kullanım, istek limitleri, atıf metni) kendi
  sayfasından doğrulanır ve DATA_SOURCES.md'ye yazılır. Herkese açık uygulamada kullanımı engelleyen koşul varsa durulur
  ve kullanıcıya sorulur.
- Kişisel bilgi gerektiren indirme formları (ör. GEM) kullanıcı tarafından doldurulur.
   **Faz A durumu (2026-10-05):** ✅ kod ve analiz; bkz. `docs/v2_A_veri_altyapisi.md`. Modüller: `src/saha.py`,
   `src/kaynaklar/` (open_meteo, gwa, sinirlar, arazi, era5_cds), `src/atlas/` (kalibrasyon, aktarim), `src/uretim/genel.py`;
   betikler `src/v2_A*.py`. Atlas: 90 kalibre santral; aktarım kuralı GWA ölçekli (komşu ≤ 30 km), güven seviyeleri
   `data/atlas/guven_seviyeleri.csv`. Açık kararlar (kullanıcı): `data/atlas/` commit edilsin mi (v1 kuralı "data/ commit
   edilmez"), yedek ERA5 grid indirmesi (~7–8 saat CDS), GEM tracker (form ile kullanıcı indirir).
