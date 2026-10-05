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
| `piyasa/saatlik.parquet` | **Ulusal** saatlik PTF (TL, USD), Türkiye geneli rüzgâr/güneş üretimi, SFK/PFK/SMF | EPİAŞ Şeffaflık Platformu | EPİAŞ koşulu: kaynak gösterilerek çoğaltılabilir ve kullanılabilir. Atıf: "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)" |
| `piyasa/yillik.csv`, `ozet.json` | Yıllık özetler, kurulu güç (TEİAŞ) | EPİAŞ, TEİAŞ | Aynı |
| `piyasa/parametreler.json` | Fiyat senaryosu ve Monte Carlo parametreleri | config.yaml (kendi varsayımlarım) | CC BY 4.0 |

**ODbL bildirimi:** ODbL 1.0 ile işaretli dosyalar OpenStreetMap verisinden türetilmiş veritabanlarıdır ve Open Database
License 1.0 (https://opendatacommons.org/licenses/odbl/1-0/) ile paylaşılır. Bu dosyaları kullanan ya da değiştiren
herkes aynı lisansla paylaşmalı ve "© OpenStreetMap katkıcıları" atfını yapmalıdır.

**Ham veri kontrolü:**
- Klasörde **santral bazında ham saatlik EPİAŞ verisi yoktur**. Santral tarafında yalnızca türetilmiş katsayılar ve
  12 × 24 ay × saat ortalamaları bulunur.
- `piyasa/saatlik.parquet` ulusal düzeyde saatlik piyasa verisi içerir. Bu, v2 Faz A6'da uygulamaya gömülmesi istenen
  pakettir; EPİAŞ'ın "kaynak gösterilerek çoğaltma" koşuluyla dağıtılır.
