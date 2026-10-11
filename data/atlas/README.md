# data/atlas — uygulamaya gömülen türetilmiş veri paketleri

Bu klasör, repodaki "veri commit edilmez" kuralının **tek istisnasıdır** (CLAUDE.md). İçindekiler küçük, türetilmiş ve
yeniden dağıtımı kaynaklarının lisanslarına uygun paketlerdir. **Kod MIT lisanslıdır; bu klasördeki veriler aşağıdaki
kendi lisanslarına tabidir** (MIT'in kapsamında değildir). Ayrıntılı kaynak ve atıf metinleri: `../../DATA_SOURCES.md`.

| Dosya | İçerik | Kaynak | Lisans |
|---|---|---|---|
| `santral_eslestirme.csv` | Türkiye RES konumları (OSM), kurulu güç, EPİAŞ santral adı/kimliği eşleşmesi | OpenStreetMap (Overpass), EPİAŞ santral listesi | **ODbL 1.0** (OSM'den türetilmiş veritabanı) |
| `eslestirme_manuel.csv` | Elle gözden geçirilmiş eşleşme kararları (OSM kimliği → EPİAŞ kimliği) | Kendi çalışmam, OSM kimlikleri | **ODbL 1.0** |
| `kalibrasyon_atlasi.csv` | Santral başına konum, kalibrasyon katsayıları, kalite bayrakları, saha tanımlayıcıları | OSM konumları + EPİAŞ üretiminden türetilmiş katsayılar + ERA5 + GWA | **ODbL 1.0** (OSM konumlarını içerdiği için türetilmiş veritabanı aynı lisansla) |
| `kalibrasyon_matrisleri.npz` | Santral başına 12 × 24 hız katsayısı matrisi ve ay × saat ortalama kapasite faktörü | EPİAŞ (türetilmiş ortalamalar), ERA5 | CC BY 4.0 (atıf: EPİAŞ Şeffaflık Platformu; "Contains modified Copernicus Climate Change Service information 2026") |
| `guven_seviyeleri.csv` | Aktarım kuralı güven seviyeleri ve hata istatistikleri | Kendi çapraz doğrulamam | CC BY 4.0 |
| `gwa_tr_1km.npz` | Global Wind Atlas 3 Türkiye 100 m ortalama hız, blok içi en yüksek hız, Weibull A/k (~1 km) | Global Wind Atlas 3.0 (DTU, Dünya Bankası) | **CC BY 4.0** (atıf metni DATA_SOURCES.md'de) |
| `sinirlar_tr.npz` | İl/ilçe kimlik ızgarası (~1 km) ve adları | geoBoundaries gbOpen TUR (OSM kökenli) | İlçeler **ODbL 1.0**, iller **CC BY-SA 2.0** |
| `kiyi_tr.npz` | Türkiye ve çevresi kıyı çizgisi noktaları | Natural Earth 1:10m | Kamu malı |
| `altlik_tr.geojson` | Uygulama haritasının karosuz altlığı: Türkiye kara çokgeni, il sınır çizgileri (sadeleştirilmiş, ~800 m), bölge kıyıları (`src/v2_tasarim_altlik.py`) | geoBoundaries gbOpen TUR ADM1 (OSM kökenli), Natural Earth 1:10m | İl sınırları **CC BY-SA 2.0**; kıyılar kamu malı |
| `piyasa/saatlik.parquet` | **Ulusal** saatlik PTF (TL, USD), Türkiye geneli rüzgâr/güneş üretimi, SFK/PFK/SMF | EPİAŞ Şeffaflık Platformu | EPİAŞ koşulu: kaynak gösterilerek çoğaltılabilir ve kullanılabilir. Atıf: "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)" |
| `piyasa/yillik.csv`, `ozet.json` | Yıllık özetler, kurulu güç (TEİAŞ) | EPİAŞ, TEİAŞ | Aynı |
| `piyasa/parametreler.json` | Fiyat senaryosu ve Monte Carlo parametreleri | config.yaml (kendi varsayımlarım) | CC BY 4.0 |
| `santral_turbinleri.csv` | Kalibre santral başına OSM türbin adedi, birim güç, üretici, rotor/göbek ve eşlenen windpowerlib türbin vekili | OpenStreetMap türbin düğümleri ve santral ilişkileri (Overpass), EPİAŞ kapasitesi, windpowerlib/OEP | **ODbL 1.0** |
| `santral_turbin_konumlari.csv` | Kalibre santrallerin türbin konumları (OSM) | OpenStreetMap | **ODbL 1.0** |
| `on_tarama.parquet` | Türkiye ön tarama haritası: 0,25° kara hücresi başına RES/GES KF, güven, başabaş fiyatları, standart tasarım NPV'leri (uygulama açılış haritası) | ERA5 + PVGIS gridleri, GWA, atlas, piyasa paketi ile kendi modelim | CC BY 4.0 (atıflar: Copernicus/ERA5, PVGIS, GWA, EPİAŞ; komşu santral adları OSM/EPİAŞ) |
| `osm_turbinler.csv` | v3 D1: Türkiye OSM türbin düğümleri (4.122) — konum, atlas santrali, iz hesabı için birim güç / rotor / göbek (`src/v3_D1_osm_turbinler.py`) | OpenStreetMap; türbin vekilleri windpowerlib/OEP; eksikler sınıf varsayılanı | **ODbL 1.0** |
| `santral_iz_kaybi.csv` | v3 D1: kalibre santrallerin hesaplanan iç/dış iz kaybı (`src/v3_D1_atlas_iz.py`) | OSM konumları + ERA5 + PyWake ile kendi hesabım | **ODbL 1.0** (OSM konumlarından türetildiği için) |
| `kalibrasyon_matrisleri_izsiz.npz` | v3 D1: izden arındırılmış hız katsayısı matrisleri (hipotez testi; birini dışarıda bırak doğrulamasında kötüleştirdiği için **kullanılmıyor**, `v3.yerlesim.atlas_iz_arindirma: false`) | Türetilmiş (EPİAŞ, ERA5, OSM) | CC BY 4.0 (EPİAŞ + Copernicus atfı) |
| `v3_hizli_tablolar.csv` | v3 D1/D2: hızlı tarama için türbin sayısına göre medyan iç iz kaybı, kullanılabilirlik ve O&M (`src/v3_D2_hizli_tablolar.py`) | Kendi modelim (12 örnek saha) | CC BY 4.0 |

**ODbL bildirimi:** ODbL 1.0 ile işaretli dosyalar OpenStreetMap verisinden türetilmiş veritabanlarıdır ve Open Database
License 1.0 (https://opendatacommons.org/licenses/odbl/1-0/) ile paylaşılır. Bu dosyaları kullanan ya da değiştiren
herkes aynı lisansla paylaşmalı ve "© OpenStreetMap katkıcıları" atfını yapmalıdır.

**Ham veri kontrolü:**
- Klasörde **santral bazında ham saatlik EPİAŞ verisi yoktur**. Santral tarafında yalnızca türetilmiş katsayılar ve
  12 × 24 ay × saat ortalamaları bulunur.
- `piyasa/saatlik.parquet` ulusal düzeyde saatlik piyasa verisi içerir. Bu, v2 Faz A6'da uygulamaya gömülmesi istenen
  pakettir; EPİAŞ'ın "kaynak gösterilerek çoğaltma" koşuluyla dağıtılır.
| `trafo_merkezleri.csv` | v3 E1: OSM trafo merkezleri (4.231; 2.320'sinin gerilimi biliniyor) — konum, ad, operatör, azami kV | OpenStreetMap (Geofabrik PBF) | **ODbL 1.0** |
| `havalimanlari.csv` | v3 E1: OSM havalimanları (79) | OpenStreetMap | **ODbL 1.0** |
| `cbs_hucre.parquet` | v3 E2/E4: 1.464 ön tarama hücresi için bağlantı (hedef TM, kV, uzaklık, maliyet), 2 km alan özeti (dışlama payları, eğim, koruma, göç), lojistik (maliyet, teslim süresi, kaynaklar), hücrede mevcut RES (`src/v3_E2_hucre_tablosu.py`) | OSM türevleri + Copernicus DEM + kendi modelim | **ODbL 1.0** (OSM'den türetilmiş) |
| `katman_agir_yol.geojson`, `katman_hat.geojson`, `katman_koruma.geojson` | v3 E5: harita katmanları (sadeleştirilmiş; `src/v3_E5_harita_katmanlari.py`) | OpenStreetMap | **ODbL 1.0** |
| `katman_goc.geojson`, `goc_koridorlari.json` | v3 E1/E5: yaklaşık kuş göç koridorları (eksen + risk tamponları) | Yayınlardan elle sayısallaştırma (Doğa Derneği, Jobson vd. 2021, Belen izleme çalışmaları) | CC BY 4.0 — **yaklaşık**, ÇED çalışmasının yerini tutmaz |
| `tedarik_kaynaklari.csv` | v3 E4: proje kargosu limanları ve yerli bileşen üreticileri (konum, bileşen, kapasite, doğrulama, kaynak) | Şirket ve liman sayfaları, TÜREB/DARGEB | CC BY 4.0 (olgusal bilgi) |
| `teias_yeka_baglanti.csv` | v3 E2: YEKA RES-2025 TEİAŞ bağlantı görüşleri | ETKB duyurusu | Kamu bilgisi; kaynak anılır |
| `lojistik_referans.json` | v3 E4: mevcut santral hücrelerinin medyan lojistik maliyeti ve teslim süresi (CAPEX referansı) | Kendi modelim | CC BY 4.0 |
| `v3_cok_kriterli_dogrulama.json` | v3 E3: AHP profilleri, ilk 10'lar, ROC/AUC doğrulaması (`src/v3_E3_cok_kriterli.py`) | Kendi modelim (OSM türbin konumlarıyla etiket) | **ODbL 1.0** |
| `baglanti_oranlari.csv`, `baglanti_orani.json` | v3 F ön adım Ö2: YEKA RES-2025/2026 santral alanlarında TEİAŞ'ın atadığı hat uzunluğu / modelin en yakın trafo hat uzunluğu oranı ve log-normal parametreleri (`src/v3_O2_baglanti_orani.py`) | ETKB/RG bağlantı görüşleri + OSM trafo merkezleri ile kendi hesabım | **ODbL 1.0** (OSM'den türetilmiş) |
| `portfoy/adaylar.csv`, `portfoy/tasarimlar.csv` | v3 F1: 40 portföy adayı (hücre temsil noktası, bölge, bağlantı trafosu, türbin) ve 148 tasarım seçeneğinin özetleri (`src/v3_F1_adaylar.py`) | Kendi modelim (ERA5, PVGIS, GWA, atlas, OSM trafo adları) | **ODbL 1.0** (OSM trafo adları) |
| `portfoy/npv.npz` | v3 F1: tasarım × 2.000 ortak senaryo NPV matrisi (M$) ve ortak sürücü özetleri | Kendi modelim | CC BY 4.0 |
| `portfoy/lojistik.parquet`, `portfoy/parametreler.json` | v3 F2: aday × bileşen × kaynak teslim maliyeti; sinerji parametreleri | Kendi modelim (OSM yol ağı türevi) | **ODbL 1.0** |
| `portfoy/analiz.json`, `portfoy/korelasyon.json` | v3 F3: etkin sınır, sinerji/çeşitlendirme ayrıştırması, duyarlılıklar, doğrulama; bölgeler arası korelasyon (`src/v3_F3_portfoy.py`) | Kendi modelim | CC BY 4.0 |
| `izleme/aylik.parquet`, `izleme/gunluk.parquet` | v3 F4: kalibre santrallerin aylık akran düzeltmeli performans oranı, kontrol kartı değerleri, alarmlar; günlük oran ve ayıklama bayrakları (yalnız türetilmiş oranlar; ham saatlik üretim yok) (`src/v3_F4_performans.py`) | EPİAŞ santral üretiminden türetilmiş oranlar + ERA5 | CC BY 4.0 (atıf: EPİAŞ Şeffaflık Platformu; Copernicus) |
| `izleme/durum.csv`, `izleme/dogrulama.json` | v3 F4: santral başına durum, tahmini kayıp, kart parametreleri, yapay arıza testi | Kendi modelim (santral adları atlas/OSM'den; uygulamada varsayılan gizli) | **ODbL 1.0** (OSM adları) |
| `portfoy/lanet.json` | v3 kapanış: optimize edicinin lanetine karşı Bayesçi büzülme — aday başına KF düzeltme çarpanı q ve ağırlık w, tasarım başına κ, bölgesel öncül (`src/v3_G1_optimizer_laneti.py`); uygulamanın varsayılanı | Kendi modelim (Faz A çapraz doğrulama hataları, ön tarama) | CC BY 4.0 |
| `portfoy/analiz_duzeltmesiz.json` | v3 kapanış: büzülmesiz (saf tahmin) portföy analizi, önce/sonra karşılaştırması için | Kendi modelim | CC BY 4.0 |
