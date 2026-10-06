# Değişiklik günlüğü

Proje aşamalar halinde geliştirildi. Her aşama bir commit; revizyonlar ve önerinin nasıl değiştiği aşağıda. Ayrıntılar
`docs/00–07`, `docs/RAPOR.md` ve `docs/MODEL_DOGRULAMA.md` içinde.

## Karar yolculuğu

| Adım | Ne değişti | Beklenen NPV | Öneri |
|---|---|---|---|
| Aşama 4 | Deterministik optimum: yalnız RES 58,8 MW | −1,6 M$ | Yatırım yapılamaz |
| Aşama 5 | Batarya + SFK (yan hizmet) geliri, Monte Carlo | +28,4 M$ | Güçlü evet |
| Aşama 6 | SFK piyasası doyum stres testi | +4,5 M$ | Koşullu onay (PPA, aşamalı batarya) |
| Aşama 7 | Gerçekçi takvim, sistem kesintisi, YEKDEM | +2,1 M$ | Koşullu onay (inşaata hazır + YEKDEM) |
| Tutarlılık 1 (Ö1–Ö2) | YEKDEM/PPA'da batarya arbitrajı kaldırıldı | −11,4 M$ | Yatırım önerilmez |
| Tutarlılık 2 | YEKDEM yıllık opsiyon, ortak batarya sürücüsü, inşaata hazır takvim | +1,5 M$ | Durum tespiti + ≤1,5 M$ teklif |
| **Nihai (Aşama 9 A)** | **Fiyat ortalaması: 58 $/MWh medyan değil beklenen değer** | **−1,7 M$** | **Rafa kaldır, tetikleyicileri izle** |

## [2.0.0-rc] — 2026-10-06 (dal `v2-genel`, yayınlanmadı)

Türkiye geneli saha tarama ve analiz uygulaması. Ayrıntı: `docs/v2_A_veri_altyapisi.md`, `docs/v2_B_analiz_motoru.md`,
`docs/v2_C_arayuz.md`.

### Faz C — Web uygulaması (yerel Streamlit)
- **Ön adım — atlas aktarımı düzeltildi** (`docs/v2_A §5b`):
  - Aktarım hız uzayındaydı; KF kopyalanmıyordu.
  - Ama santral GWA referansı sahanın moduna bağlıydı (türbin yerleşimi etkisizdi) ve santraller ortak bir vekil türbinle
    (E-92/80 m) kalibre ediliyordu.
  - Artık her santral OSM'den çıkarılan kendi türbin vekili ve gerçek türbin konumlarıyla kalibre ediliyor; talimat/arıza
    saatleri k'dan çıkarıldı.
  - Ezine (E-141/120 m): yerleşim 2 km %30,2 → %33,9 (v1 kalibre %37,8).
  - Güven seviyeleri ikiye indi: yüksek (≤ 30 km) medyan 3,8 / P90 9,8 puan; düşük 5,6 / 11,5.
  - Türbin yerleşimi varsayılan açık (çapraz doğrulamada RMSE 9,2 → 7,2).
- **Veri katmanı** (`src/veri_katmani.py`): Çalışma anında yalnız yerel paketler okunuyor. PVGIS GES KF gridi ve Copernicus DEM
  rakım ızgarası eklendi; uygulama hiçbir dış API'ye bağlanmıyor.
- **Ön tarama haritası:** 1.464 kara hücresi için başabaş fiyatları ve KF'ler (`data/atlas/on_tarama.parquet`).
- **Uygulama** (`app.py`, `uygulama/`):
  - Saha seçimi üç yoldan: harita, koordinat, il/ilçe adayları.
  - Hızlı tarama: başabaş fiyatı, Türkiye yüzdeliği ve "tam analize değer mi?" değerlendirmesi.
  - Tam analiz: sıra numarası, ilerleme, öneri, güven etkisi ve HTML/PDF rapor.
  - Paylaşım bağlantısı; vaka çalışması ve yöntem sayfaları; TR/EN.
  - İstek sınırları ve gizlilik notu.
- **Motor:**
  - Tam analiz sırası (sıra numarası, azami uzunluk) ve önbellekten okuma (`onbellekten`).
  - Hızlı taramada en iyi standart tasarımın başabaşı; tam analizde güven seviyesinin E[NPV]'ye etkisi.
  - Hızlı tarama metinlerinden karar dili çıkarıldı.
- **Testler:** AppTest (`tests/test_v2_uygulama.py`); Playwright ile masaüstü/390 px ekran görüntüleri ve taşma kontrolü
  (`src/v2_C8_tarayici.py`).

### Faz B — Analiz motoru (`58a6eeb`)
- `analiz_et(saha, hizli|tam, varsayımlar)`.
- Hızlı tarama ~2 s; tam analiz 2 çekirdekte ~4 dk.
- MILP'te SFK doyum beklentisi; sonuç önbelleği ve tek tam analiz kilidi.
- Ezine regresyonu v1 ile bir standart hata içinde.

### Faz A — Veri altyapısı (`9ba4f3f`, `6165d28` ve öncesi)
- Open-Meteo / ERA5 gridi, Global Wind Atlas (1 km, 250 m).
- 90 santrallik kalibrasyon atlası ve aktarım kuralı.
- Sahaya bağlı parametreler, ulusal piyasa paketi.

## [1.0.0] — 2026-10-04

### Aşama 9 — Yayın öncesi kalite turu
- **Bölüm A (tutarlılık):**
  - Monte Carlo log-fiyat süreci 58'i medyan alıyordu; simüle ortalama fiyat 61,8 $/MWh idi. Süreç beklenen değeri 58
    olacak şekilde düzeltildi (σ²/2 düzeltmesi, `monte_carlo.log_merkez`).
  - Deterministik baz → Monte Carlo farkı bileşenlerine ayrıldı (`src/07_fark_ayristirma.py`).
  - Baz vaka +1,5 → −1,7 M$; öneri "rafa kaldır, tetikleyicileri izle".
  - İkili bilgi değeri formülü negatif beklenen NPV için genelleştirildi.
- **Kod kalitesi:** ruff lint + format (`pyproject.toml`). Dışa açık fonksiyonlara tip ipuçları ve docstring eklendi.
  GitHub Actions CI (`.github/workflows/ci.yml`): ruff + ham veri gerektirmeyen testler; README rozetleri.
- **Veri ve lisanslar:** `DATA_SOURCES.md`. Copernicus/ERA5, PVGIS ve EPİAŞ atıfları README, rapor, memo, sunum eki ve
  dashboard altbilgisinde. MIT yalnız kod için.
- **Doğrulama:** `docs/MODEL_DOGRULAMA.md` (neyin neyle doğrulandığı, neyin doğrulanamadığı, duyarlılıklar).
- **Dashboard:**
  - Hakkında bölümü, favicon.
  - TR/EN sayı biçimi (tablolar ve grafikler), birim tutarlılığı (M$, $/MWh).
  - Markdown'da `$` kaçışı (uyarı metninde LaTeX hatası düzeltildi).
  - Mobil (390 px) kontrolü, README ekran görüntüleri ve GIF.

### Aşama 8 — Karar paketi (`cb14acd`)
- FAST benzeri formüllü Excel modeli: 48/48 senaryo Python ile mutabık, 0 formül hatası.
- Yatırım komitesi memosu (MD + PDF), 13 slaytlık sunum (karar yolculuğu grafiği), dashboard/README indirme bağlantıları.

### Tutarlılık 2 (`8da53ae`)
- YEKDEM 10 yıllık kilit değil, her 30 Kasım'da seçilen yıllık opsiyon (YEK Yön. md. 4/2, 5/1, 8/1).
- Kurulu batarya yayılımı SFK fiyatını, sistem kesintisini ve öğle kanibalizasyonunu birlikte sürüyor (ortak sürücü).
- İnşaata hazır proje takvimi (COD P50 Kasım 2029).

### Tutarlılık 1 — Ö1–Ö2 (`aca7120`)
- YEKDEM'de depolanıp verilen enerji de YEKDEM fiyatından ödenir: arbitraj yok. PPA finansal fark sözleşmesi olarak
  modellendi (batarya tüccar dispatch'i).
- `nihai_baz_vaka` tanımlandı.

### Aşama 7 — Tamamlayıcı analizler (`dc8e04a`)
- Sistem kaynaklı kesinti (EPİAŞ YAT talimatları + referans santraller), teşvik belgesi/KDV, YEKDEM, karbon ve CO2.
- CPM + Monte Carlo proje takvimi, 20 maddelik risk kaydı.

### Aşama 6 — Stres testi ve paketleme (`f113afb`, `d92058f`)
- SFK doyum arz-talep modeli (İngiltere/Almanya/Avustralya kalibrasyonu), fırsat penceresi, erteleme, esnek batarya.
- `calistir.py`, pytest, Streamlit dashboard (TR/EN), rapor PDF'i, README'ler.

### Aşama 5 — Gelir yığını ve risk (`d062808`)
- Yan hizmet (SFK ikili katılım ≥30 MW), dengesizlik, YEK-G, PPA.
- Önceden hesaplanmış dispatch tablolarıyla 10.000 senaryolu Monte Carlo, EVPI/EVPPI, Sobol.

### Aşama 4 — Optimizasyon (`38281c8`)
- Batarya ve hibrit dispatch LP'leri, tamsayı türbin ve ikili yatırım kararlı kapasite MILP'i (tam yıl, Pyomo + HiGHS),
  temsilî günler, pişmanlık analizi.

### Aşama 3 — Finansal model (`52c46cc`)
- Reel USD nakit akışı, vergi ve zarar mahsubu, P90 heykelsi borç, NPV/IRR/LCOE, tornado.

### Aşama 2 — Piyasa analizi (`f1e193c`, revizyon `79b6494`)
- EPİAŞ PTF 2014–2026, yakalanma oranı ve kanibalizasyon, ördek eğrisi.
- ERA5 rüzgârının üç santralle kalibrasyonu.
- Revizyon: zaman hizası ve ay × saat hız katsayısı (gün içi şekil düzeltmesi).

### Aşama 1 — Saha ve üretim (`a8124e8`)
- Dört aday saha taraması. Çanakkale-Ezine için 10 yıllık saatlik GES (PVGIS-SARAH3 + pvlib) ve RES (ERA5 +
  windpowerlib) profilleri.

### Aşama 0 — Kurulum (`cffc32e`)
- Klasör yapısı, Python 3.11 ortamı, ısınma LP modeli.
