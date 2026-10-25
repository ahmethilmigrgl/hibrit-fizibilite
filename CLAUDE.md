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
  - `data/atlas` — **istisna: git'e girer.** Uygulamaya gömülen küçük türetilmiş paketler (atlas, GWA, sınırlar, piyasa
    paketi); her dosyanın kaynağı ve lisansı `data/atlas/README.md`'de (OSM türevleri ODbL, GWA CC BY 4.0). Santral bazında
    ham saatlik EPİAŞ verisi buraya konmaz.
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
   `data/atlas/guven_seviyeleri.csv` (mesafeye dayalı: yüksek ≤15 km, orta 15–30, düşük komşu yok; bootstrap GA'lı).
   **Faz A açık konular kapatıldı (Ö1–Ö4):** `data/atlas` commit istisnası + `data/atlas/README.md` lisans notu;
   ERA5 Türkiye grid indirmesi (`src/v2_O2_era5_grid.py`, devam ettirilebilir, `data/grid/era5_tr/v1/indirme.log`,
   1.464 kara hücresi) + Hugging Face düzeni (`src/kaynaklar/hf_veri.py`, kart `hf/README.md`, yükleme `src/v2_hf_yukle.py`
   — kullanıcı HF_TOKEN ile çalıştırır); GWA 250 m (`src/kaynaklar/gwa250.py`, 17 MB karo) + türbin yerleşimi seçeneği
   (`Saha.turbin_yerlesimi`, yarıçap 2 km); güven seviyeleri yeniden tanımlandı.
- **Faz B — Analiz motoru:** ✅ bkz. `docs/v2_B_analiz_motoru.md`. `src/motor/` → `analiz_et(saha, "hizli"|"tam",
   KullaniciVarsayimlari, ilerleme)` → `Sonuc` (JSON + parquet + grafik verisi + iki dilli gerekçeler). Hızlı tarama ~2 s
   (profil önbellekte), tam analiz çalışma zamanı "hafif" işletme tablolarıyla; sonuç önbelleği + tek tam analiz kilidi +
   zaman aşımı (`onbellek.py`); saha raporu HTML/PDF (`rapor.py`). MILP'in SFK geliri doyum beklentisiyle ölçeklenir
   (`sfk_milp_carpani`). Doğrulama `src/v2_B5_regresyon.py` (Ezine vs v1 baz vaka), `src/v2_B5_dogrulama.py
   tutarlilik|tarama|sure` → `outputs/v2B/`. Testler `tests/test_v2_motor.py`. 2 çekirdek benzetimi:
   `MOTOR_CEKIRDEK=2 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`.
- **Faz C — Web uygulaması (yerel):** ✅ bkz. `docs/v2_C_arayuz.md`. Giriş `app.py` (st.navigation: `uygulama/sayfa_analiz.py`
   açılış haritası + saha seçimi + analiz, `sayfa_vaka.py` v1 Ezine, `sayfa_yontem.py`); yardımcılar `uygulama/ortak.py`
   (TR/EN, `md()` $ kaçışı, istek sınırı), `servis.py`, `harita.py`. **Tüm çalışma anı veri okumaları `src/veri_katmani.py`**
   (`config v2.veri_erisim.mod = "yerel"`; dış API yok). Gridler `data/grid/` (repoda yok): ERA5 (`v2_O2`), PVGIS GES KF
   (`v2_C1_pvgis_grid.py`), rakım (`v2_C1_rakim_grid.py`, Copernicus DEM), GWA 250 m. Ön tarama `src/v2_C2_on_tarama.py` →
   `data/atlas/on_tarama.parquet`. **Ön adım düzeltmesi:** santraller kendi türbin vekiliyle kalibre (`src/v2_C0_santral_turbinleri.py`,
   `src/atlas/turbinler.py`, `config v2.santral_turbin`), santral c'si gerçek türbin konumlarından (`santral_c()` modsuz),
   güven iki seviye (≤30 km yüksek), türbin yerleşimi varsayılan açık. Testler: `tests/test_v2_uygulama.py` (AppTest;
   `MOTOR_KUCUK=1` yalnız testte küçük tam analiz), tarayıcı `src/v2_C8_tarayici.py` (Playwright + Chrome) → `docs/img/v2/`.
   Yöntem sayfası sayıları `results/v2_dogrulama.json` (`src/v2_C9_sonuclari_paketle.py`). Hugging Face/yayın bu fazda yok.
   **Revizyon R (2026-10-07):** aktarım kuralı `config v2.aktarim` (kıyı oranı 0,7, büzülme `r_buzulme_n0: 2`;
   `aktarim.r_duzelt`), güven yüksek ≤ 30 km; modern türbin doğrulaması `src/v2_R3_modern_turbin.py`; üst sınır
   `config v2.uygulama.ust_sinir_kf` (gözlenen azami %45,6); adalar `src/kaynaklar/adalar.py` + `config v2.adalar`
   (sıralamalardan varsayılan hariç); tam analiz hızı: `IsletmeLPHizli` (highspy) + MILP `tam_milp_temsili_gun: 96`
   (karşılaştırma için `MOTOR_LP=pyomo`, `MOTOR_TAM_MILP=tamyil`); betikler `src/v2_R1..R5_*.py` → `outputs/v2R/`.
   Bkz. docs/v2_A §5c, docs/v2_C §9.
- **Arayüz tasarım sistemi "Eşik" (dal `v2-arayuz`, 2026-10-07'de `v2-genel`'e birleştirildi):** ✅ bkz. `docs/v2_tasarim_sistemi.md`. Görünüm `uygulama/tasarim/` altında
   (`tokenlar.py` tek renk/yazı kaynağı, `stil.py` CSS + tema düğmesi, `bilesenler.py`, `grafik.py` ortak Plotly şablonu).
   Açık tema = yatırım raporu, koyu tema = kontrol odası. **Renk kodu yalnız `tokenlar.py`'de**; değişince
   `.venv/bin/python src/v2_tasarim_tema.py` (`.streamlit/config.toml` + logolar üretilir, elle düzenlenmez). Harita altlığı
   karosuz (`data/atlas/altlik_tr.geojson`), yazı tipleri yerel (`static/fonts`, OFL). Testler `tests/test_v2_tasarim.py`.

---

## v3 — Endüstri mühendisliği eklentileri (dal: `v3-ie`, `v2-genel`'den)
**Amaç:** Uygulamaya endüstri mühendisliği perspektifinden (yöneylem araştırması, benzetim, güvenilirlik, tesis yerleşimi,
çok kriterli karar, lojistik, portföy) özellikler eklemek; her yeni modelin matematiksel formülasyonu docs'ta, mülakatta
açıklanabilir. v2 (`v2-genel`) değiştirilmez; tüm iş `v3-ie` dalında. Hugging Face/yayın adımı ve push yok. Mevcut testler
geçmeli, mevcut akışlar bozulmamalı; arayüz eklemeleri "Eşik" tasarım sistemiyle (`uygulama/tasarim/`).

**Fazlar:**
- **Faz D — Türbin yerleşimi optimizasyonu + bakım ve güvenilirlik.**
- **Faz E — Coğrafi katmanlar + çok kriterli saha seçimi (AHP/TOPSIS) + lojistik ve tedarik zinciri.** (Faz D'deki
  `src/yerlesim/alan.py` dışlama katmanı arayüzü yol, yerleşim, koruma alanı, eğim katmanlarıyla doldurulacak.)
- **Faz F — Çoklu saha portföy optimizasyonu + santral performans izleme.** (Faz D'deki `src/bakim/stok.py` baz stok
  optimizasyonu sahalar arası havuzlamaya genişletilecek.)

**Faz D durumu (2026-10-10):** ✅ bkz. `docs/v3_D_yerlesim_bakim.md`. Modüller `src/yerlesim/` (turbin, ruzgar_gulu,
alan + dışlama arayüzü, iz: PyWake referansı + hızlı vekil, yontemler: MILP Glover / GA / SA / ızgara, analiz),
`src/bakim/` (hava pencereleri, SimPy ayrık olay simülasyonu, çizelge MILP'i, baz stok), `src/motor/v3.py` (motor bağlantısı),
`src/kaynaklar/era5_yon.py` (ERA5 100 m yön gridi, `src/v3_D0_era5_yon_grid.py`, çevrimdışı CDS). Arayüz `uygulama/v3_bolumler.py`.
Config `v3.kayip` (göreli kayıp kuralı, taban kayıp ≈ %6,3), `v3.yerlesim`, `v3.bakim`. Motor seçenekleri
`KullaniciVarsayimlari(yerlesim_bakim, yerlesim_yontemi, bakim_modeli, bakim_stratejisi)`; `yerlesim_bakim=False` ya da
`kalibrasyon="v1"` v2 davranışını aynen verir. Kapasite MILP'i `opt["iz_verim"]` ile türbin sayısına bağlı iz verimini ikili
seçimle kesin temsil eder. Atlas: iz kaybı artığı açıklamadı → matrisler güncellenmedi (`atlas_iz_arindirma: false`), göreli
kural kullanılır. Betikler `src/v3_D*.py` → `outputs/v3D/`; testler `tests/test_v3_D.py`. Veri: `data/atlas/osm_turbinler.csv`,
`santral_iz_kaybi.csv`, `v3_hizli_tablolar.csv`; yön gridi `data/grid/era5_yon_tr/v1/` (repoda yok). Veri sürümü `v3D-2026-10`.

**Ön adım (Ö1–Ö4, 2026-10-10):** ✅ bkz. `docs/v3_E_cbs_cok_kriterli_lojistik.md` §0. İşletme modeli `src/bakim/isletme.py`
(`config v3.isletme`: varsayılan FSA 20 $/kW-yıl + sahip kalemleri 14 = 34; `KullaniciVarsayimlari(isletme_modeli="kendi")`),
kayıp tablosu `src/uretim/kayip.py` (`v3.kayip.tablo`), bakım duyarlılığı `data/atlas/v3_bakim_duyarlilik.json`; betikler
`src/v3_E0_*.py` → `outputs/v3E/E0_*`; testler `tests/test_v3_E0.py`.

**Faz E durumu (2026-10-10):** ✅ bkz. `docs/v3_E_cbs_cok_kriterli_lojistik.md` §1–8. Modüller `src/cbs/` (katmanlar: CBS gridi +
`CBSDislama` → Faz D dışlama arayüzü; baglanti: mesafe/gerilim maliyeti; lojistik: ağır nakliye ağı + ulaştırma LP'si; altyapi:
motora uygulama — `teknoloji.sebeke.capex`, `res.capex` lojistik farkı, COD'ye teslim gecikmesi; cok_kriterli: AHP/TOPSIS/
dayanıklılık/AUC; kriterler: hücre tablosu, profiller, değer fonksiyonu). Anahtar `KullaniciVarsayimlari(altyapi_maliyetleri=True)`
(False = ön adım sonrası davranış). Config `v3.cbs`, `v3.baglanti`, `v3.lojistik`, `v3.cok_kriterli` (TOPSIS değer fonksiyonu
standardizasyonu; `normalizasyon: vektor` klasik). Çevrimdışı: Geofabrik PBF `data/raw/osm_pbf/` → `src/v3_E1_osm_katmanlar.py`
(pyosmium) → `src/v3_E1_cbs_grid.py` (`data/grid/cbs_tr/v1`), eğim `src/v3_E1_egim_grid.py` (`data/grid/egim_tr/v1`), nakliye ağı
`src/v3_E4_nakliye_agi.py` (`data/grid/lojistik_tr/v1`), hücre tablosu `src/v3_E2_hucre_tablosu.py`, ön tarama
`src/v3_E2_on_tarama.py` (v2 sürümü `outputs/v3E/on_tarama_v2.parquet`), çok kriterli `src/v3_E3_cok_kriterli.py`, harita
katmanları `src/v3_E5_harita_katmanlari.py`, doğrulama `src/v3_E6_*.py` → `outputs/v3E/`. Arayüz: altyapı katmanları (isteğe
bağlı, açılışta yüklenmez), saha kartı bağlantı/lojistik, tam analizde "Lojistik ve bağlantı", yeni sayfa `uygulama/sayfa_cok_kriterli.py`
(`/cok-kriterli`). WDPA lisansı nedeniyle koruma alanları OSM'den; TEİAŞ lisanslı kapasite yayımlamıyor (ana sınırlama).
Testler `tests/test_v3_E.py`.

**Faz F ön adım (2026-10-10):** ✅ bkz. `docs/v3_F_portfoy_performans.md` §0 ve `docs/v1_duzeltme_notu.md`. Ö1: v1'de RES sigortası +
arazi kirası çift sayılmış (35.000 $/MW-yıl "her şey dahil" + ayrı kalemler); düzeltme anahtarı config `v1_duzeltme.cift_sayim`
(varsayılan false) / `V1_CIFT_SAYIM=1`; düzeltilmiş baz vaka `outputs/07/v1_cift_sayim/` (E[NPV] −1,66 → +0,92 M$, karar (b) → (a));
Excel'de seçilebilir (96/96 mutabık); v1 belgelerine yalnız "Düzeltme notu" kutusu. v2 motorunda da var, v3 FSA'da yok.
Ö2: bağlantı mesafesi belirsizliği — atanan/en yakın oran (YEKA RES-2025/26, `data/atlas/baglanti_orani.json`, ln r ~ N(−0,31; 0,94)),
config `v3.baglanti.belirsizlik`; CAPEX beklenen değerle, MC'de `girdi["capex_sebeke"]` çarpanı.

**Faz F durumu (2026-10-11):** ✅ bkz. `docs/v3_F_portfoy_performans.md`. Portföy `src/portfoy/` (adaylar: 40 aday × 2–4 tasarım ×
2.000 ortak senaryo — fiyat, ERA5 hava yılı, SFK, CAPEX, YEKDEM ortak tohumla; model hatası, bağlantı, COD sahaya özgü
`tohum_saha`; sinerji: işletme ölçeği/kendi bakımı, Poisson taban stok havuzu, toplu indirim, çok sahalı ulaştırma; model:
scipy.optimize.milp (HiGHS) ortalama–CVaR, Rockafellar–Uryasev, ε-kısıt etkin sınır; analiz: çeşitlendirme varyans
ayrıştırması, kaba kuvvet). Motor MC `mc_calistir(..., tohum_saha=)` ve dönüşte `ortak`. İzleme `src/izleme/` (aylık oran,
bölgesel/YAT ayıklama, akran ağırlığı b, kayan taban [t−30, t−7], Shewhart/EWMA/CUSUM ARL0 = 48 ay blok bootstrap,
yapay arıza testi). Betikler `src/v3_F1_adaylar.py` (~4 saat), `src/v3_F3_portfoy.py`, `src/v3_F4_performans.py` (aylık güncelleme),
`src/v3_F6_tarayici.py`; paketler `data/atlas/portfoy/`, `data/atlas/izleme/`; config `v3.portfoy`, `v3.performans`
(`santral_adlari_goster: false`). Sayfalar `uygulama/sayfa_portfoy.py`, `sayfa_performans.py`. Testler `tests/test_v3_F.py`.
Sürüm etiketi v3.0.0-rc1 (push yok).

**v3 kapanış (2026-10-11, etiket v3.0.0-rc2):** optimize edicinin laneti `src/portfoy/lanet.py` + `src/v3_G1_optimizer_laneti.py`
(→ `data/atlas/portfoy/lanet.json`; `PV.yukle(duzeltme=True)` varsayılan, `src/v3_F3_portfoy.py --duzeltmesiz` önce/sonra);
Lazard kapsamı belirsiz → `docs/v1_duzeltme_notu.md` iki yorum (A/B); ERA5 yön gridi paketli (`era5_yon.paketle_hizli`);
özet `docs/PROJE_OZETI.md`; betik çıktıları `outputs/v3G/`.

---

## v4 — Sektör özellikleri (dal: `v4-sektor`, `v3-ie`'den)
**Amaç:** IPP / proje geliştirme / yatırım pozisyonlarında doğrudan sorulan dört özellik. v3 (`v3-ie`) değiştirilmez;
push ve yayın yok (yayın bu fazlardan sonra ayrı adım). Kullanıcı kararları (2026-10-25): merit order "orta" derinlik,
mevcut santral adları gizli (anonim kod + CSV yükleme), sıra H → I → J → K.

**Fazlar:**
- **Faz H — Bankaya sunulabilir verim (P50/P90) + proje finansmanı.** ✅ (2026-10-25) bkz. `docs/v4_H_finansman.md`. Modüller
  `src/finansman/` (verim: belirsizlik bütçesi; borc_lp: çok senaryolu borç LP'si + dualler; selale: DSRA/kilit/temerrüt
  şelalesi + PD hedefli boyutlandırma; motor: tam analize bağlantı). Config `v4.verim`, `v4.finansman`. Anahtar
  `KullaniciVarsayimlari(finansman=True)` (False = v3 aynen). Monte Carlo `mc_calistir(..., finans=True)`: `m_ges`, `m_disdeger`,
  gecikmesiz CFADS ve ortalama yollar. Arayüz `uygulama/v4_bolumler.py`. Betik `src/v4_H1_finansman.py` → `outputs/v4H/`.
  Testler `tests/test_v4_H.py`.
- **Faz I — Mevcut santrale hibrit/depolama ekleme.**
- **Faz J — YEKA teklif stratejisi.**
- **Faz K — Temel model (merit order) fiyat projeksiyonu.**
