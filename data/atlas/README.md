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
