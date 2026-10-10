# Veri kaynakları, lisanslar ve atıflar

Bu repodaki **kod MIT lisanslıdır** ([LICENSE](LICENSE)). Veriler ve veriden türetilen sonuçlar aşağıdaki kaynakların
koşullarına tabidir. Ham veri (`data/raw`, `data/processed`) repoya girmez. `results/` ve `outputs/` yalnızca türetilmiş,
toplulaştırılmış sonuçlar içerir: yıllık, aylık ve gün içi ortalamalar, model çıktıları, grafikler.

Atıf metinleri, lisans sayfalarından Ekim 2026'da doğrulanarak birebir kullanılmıştır.

## Zorunlu atıflar (README, rapor, memo, sunum eki ve dashboard altında aynen kullanılır)

**Copernicus / ERA5** — C3S lisansı; atıf biçimi "[Generated using/Contains modified] Copernicus Climate Change Service
information [year]" ve sorumluluk cümlesi
([ECMWF Copernicus Knowledge Base, "How to acknowledge and cite a CDS catalogue entry"](https://confluence.ecmwf.int/display/CKB/How+to+acknowledge+and+cite+a+Climate+Data+Store+%28CDS%29+catalogue+entry+and+the+data+published+as+part+of+it)).
ERA5 hız serileri kalibre edildiği (ay × saat katsayısı) için "Contains modified" biçimi kullanılır:

> Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is
> responsible for any use that may be made of the Copernicus information or data it contains.

Veri seti künyesi: *ERA5 hourly time-series data on single levels from 1940 to present*. Copernicus Climate Change
Service (C3S) Climate Data Store (CDS), DOI: [10.24381/1cf1ad76](https://doi.org/10.24381/1cf1ad76). Lisans: CC-BY
(CDS katalog kaydı). Erişim: 2026.

**PVGIS** — Kaynak gösterilmesi koşuluyla serbest kullanım
([JRC PVGIS veri indirme sayfası](https://joint-research-centre.ec.europa.eu/pvgis-photovoltaic-geographical-information-system/pvgis-data-download_en);
[kullanım koşulları](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/usage-conditions-data-protection_en)):

> PVGIS © European Communities, 2001-2026

Kullanılan veritabanı: PVGIS-SARAH3 (PVGIS 5.3, `seriescalc` API, pvlib `get_pvgis_hourly`).

**EPİAŞ Şeffaflık Platformu** — Platformdaki içerik ve veriler **kaynak gösterilmek suretiyle çoğaltılabilir ve
kullanılabilir**. EPİAŞ verilerden doğabilecek zararlardan sorumluluk kabul etmez
([Şeffaflık Platformu hakkında](https://seffaflik.epias.com.tr/transparency/about.xhtml)):

> Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)

## Kaynak listesi

| Kaynak | Ne için kullanıldı | Lisans / koşul | Repoda ne var |
|---|---|---|---|
| **ERA5** (C3S / ECMWF), CDS API (`cdsapi`) | 2014–2026 saatlik 10 m / 100 m rüzgâr, sıcaklık, basınç → RES üretim profili | CC-BY (C3S lisansı), atıf zorunlu | Yalnız kalibre edilmiş, toplulaştırılmış profiller ve grafikler |
| **PVGIS-SARAH3** (AB JRC) | 2014–2023 saatlik düzlem ışınımı → GES üretim profili (pvlib PVWatts) | Kaynak gösterilerek serbest kullanım | Toplulaştırılmış profiller |
| **EPİAŞ Şeffaflık Platformu** (API) | 2014–2026 saatlik PTF, santral bazında gerçek zamanlı üretim (kalibrasyon), YAT talimatları, SFK/PFK fiyatları, YEK-G | Kaynak gösterilerek çoğaltma ve kullanım | Yalnız türetilmiş ve toplulaştırılmış sonuçlar (yıllık yakalanma oranları, gün içi ortalama profiller, aylık yan hizmet özetleri); **ham saatlik EPİAŞ serisi yok** |
| **windpowerlib** (oemof, MIT) ve OEP türbin kütüphanesi | Enercon E-141/4200 ve E-126 güç eğrileri | Kod MIT; türbin veri seti OEP'te açık veri olarak yayımlanmış (veri kaydının lisans metni bu projede ayrıca doğrulanmadı) | Türbin verisi yeniden dağıtılmıyor |
| **pvlib** (BSD-3) | PVGIS indirme, PV modeli | BSD-3-Clause | — |
| **Pyomo** (BSD), **HiGHS** (MIT) | Optimizasyon modelleri ve çözücü | Açık kaynak | — |
| **TEİAŞ** | Kurulu güç istatistikleri, iletim/sistem kullanım tarifeleri, yan hizmet (SFK) usul ve esasları | Kamuya açık belgeler; sayılar config'te kaynakla | Yalnız config değerleri |
| **EPDK, ETKB, Resmî Gazete** (CK 7189, CK 9903, YEK Yönetmeliği), **GİB** | Lisans/takvim süreleri, YEKDEM koridoru, teşvikler, şebeke emisyon faktörü (ETKB 2024), vergi | Kamu mevzuatı ve resmî yayınlar | Yalnız config değerleri ve atıflar |
| **IRENA** (Renewable Power Generation Costs 2025), **Lazard** (LCOE+ / LCOS 2025), **BNEF**, **NREL** (ATB 2024, PVWatts) | CAPEX, OPEX, verim, bozunma varsayımları | Yayımlanmış raporlar; yalnız tek tek sayılar alıntılandı | Config değerleri + kaynak notu |
| **Damodaran** (Ocak 2026 ülke risk primi) | WACC | Kamuya açık veri seti | Config değeri |
| **İngiltere (Modo, Timera), Almanya (FCR), Avustralya** piyasa raporları | SFK doyum modelinin kalibrasyonu | Yayımlanmış piyasa analizleri | Config değerleri + kaynak notu |
| Sektör haberleri (Enerji Ajansı, Yeşil Haber, Dünya, TÜREB, EDEDER) | YEKDEM güncel fiyatı, depolama boru hattı, CAPEX referansları | Haber/sektör yayınları, alıntı | Config notları (TAHMİN olarak işaretli) |

Her bir varsayımın değeri, birimi, kaynağı ve notu `config.yaml` içindedir. Dashboard'da "Yöntem" sekmesindeki varsayım
tablosu bu alanları gösterir.

## EPİAŞ verisinin yeniden paylaşımı — kontrol

- `results/` içindeki 51 dosyanın hiçbiri 200 satırı aşmıyor. En büyük CSV'ler yıllık ve gün içi ortalama profiller,
  ham saatlik fiyat ya da üretim serisi değil (kontrol: `results/*.csv` satır sayıları, Ekim 2026).
- `outputs/` içindeki EPİAŞ türevleri grafikler ve özet tablolar: yıllık yakalanma oranları, ay × saat ortalama ısı
  haritaları, aylık YAT toplamları.
- Ham EPİAŞ yanıtları yalnız yerel önbellekte (`data/raw/epias/`) tutulur ve `.gitignore` ile repo dışındadır.
- EPİAŞ API kimlik bilgileri yalnız `.env` içindedir; hiçbir çıktıya yazdırılmaz.

---

## v2 (dal `v2-genel`) — Türkiye geneli kaynaklar

Koşullar Ekim 2026'da her kaynağın kendi sayfasından doğrulandı. Herkese açık, **ticari olmayan** (reklamsız,
aboneliksiz, eğitim/portföy amaçlı) bir web uygulamasında kullanımı engelleyen koşul bulunmadı. Uygulama çalışırken
kişisel kimlik bilgisi (CDS, EPİAŞ) kullanılmaz; bunlar yalnız çevrimdışı ön hesaplama betiklerindedir.

| Kaynak | v2'de kullanım | Lisans / koşul | İstek limiti | Atıf |
|---|---|---|---|---|
| **Open-Meteo** tarihsel hava API'si (`models=era5`) | Çalışma zamanı rüzgâr kaynağı (ERA5 0,25°) | Ücretsiz katman yalnız ticari olmayan kullanım (kişisel projeler, reklamsız/aboneliksiz siteler, eğitim); veri CC BY 4.0 ([koşullar](https://open-meteo.com/en/terms)) | 600/dk, 5.000/saat, 10.000/gün, 300.000/ay; 2 haftadan uzun ya da 10'dan fazla değişkenli istek kesirli çoklu çağrı sayılır → 10 yıl saatlik ≈ 260 çağrı ([fiyatlandırma](https://open-meteo.com/en/pricing)) | Verinin gösterildiği yerin yanında bağlantılı "Weather data by Open-Meteo.com", lisans bağlantısı (CC BY 4.0) ve değişiklik notu (göbek yüksekliğine taşındı, kalibre edildi) ([lisans](https://open-meteo.com/en/licence)) + Copernicus ERA5 atfı |
| **Open-Meteo** yükseklik API'si (Copernicus DEM GLO-90) | Santral/saha rakımı (aktarım kuralı) | Aynı koşullar | Aynı kota | Aynı |
| **Global Wind Atlas 3.0** (DTU, Dünya Bankası) | 100 m ortalama hız, Weibull A/k (1 km paket); GWA düzeltmesi, türbin sınıfı, ilçe adayları | CC BY 4.0 | — (bir kez indirildi) | "Global Wind Atlas 3.0, a free, web-based application developed, owned and operated by the Technical University of Denmark (DTU). The Global Wind Atlas 3.0 is released in partnership with the World Bank Group, utilizing data provided by Vortex, using funding provided by the Energy Sector Management Assistance Program (ESMAP). For additional information: https://globalwindatlas.info" |
| **OpenStreetMap** (Overpass API; `power=plant`, `plant:source=wind`) | Türkiye RES konumları ve kurulu güç (186 santral) → EPİAŞ eşleştirmesi | ODbL 1.0: atıf + türetilmiş **veritabanı** aynı lisansla paylaşılır. Atlasın konum içeren tablosu (`kalibrasyon_atlasi.csv`) ODbL ile yayımlanır | Overpass adil kullanım (bir kez sorgulandı) | "© OpenStreetMap katkıcıları, ODbL" |
| **Global Energy Monitor** Global Wind Power Tracker | (Alternatif konum kaynağı) | CC BY 4.0; **indirme ad/e-posta isteyen bir form** gerektiriyor → kullanıcı indirirse eklenecek, şimdilik kullanılmadı | — | "Global Wind Power Tracker, Global Energy Monitor, February 2026 release." |
| **geoBoundaries** gbOpen TUR (OSM kökenli) | İl (ADM1, 81) ve ilçe (ADM2, 973) sınırları → 1 km ızgara paketi | ADM1 CC BY-SA 2.0, ADM2 ODbL 1.0 | — | "geoBoundaries (Runfola et al. 2020), © OpenStreetMap katkıcıları" |
| **Natural Earth** 1:10m kıyı çizgisi | Kıyıya uzaklık | Kamu malı (atıf gerekmez) | — | (isteğe bağlı) "Made with Natural Earth." |
| **EPDK Kurul Kararı 14204** (30/12/2025) ve EK-2 | 2026 iletim tarife bölgeleri (15 bölge, 81 il) ve üretim tarifeleri | Kamu belgesi (TEİAŞ duyurusu eki, taranmış PDF elle aktarıldı) | — | Kaynak olarak anılır |
| **EPİAŞ** Şeffaflık Platformu | Ulusal piyasa paketi (saatlik PTF TL/USD, ulusal rüzgâr/güneş üretimi, SFK/PFK, SMF); santral bazında üretim → kalibrasyon atlası (yalnız türetilmiş katsayılar) | Kaynak gösterilerek çoğaltılabilir ve kullanılabilir | Uygulama EPİAŞ API'sine bağlanmaz | "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)" |
| **ERA5** (CDS, çevrimdışı) | Kalibrasyon atlası için santral hücreleri (2014–2025); olası yedek grid | CC-BY (C3S) | CDS kuyruğu | v1 ile aynı "Contains modified Copernicus Climate Change Service information 2026 …" |
| **ERA5 Türkiye nokta gridi** (CDS zaman serisi, çevrimdışı indirilir) | Çalışma zamanının **birincil** rüzgâr kaynağı: 1.464 kara hücresi, 2014–2023 saatlik, hız büyüklüğü uint16 (~0,7 GB). Hugging Face veri deposunda (`hf/README.md`) yeniden dağıtılır; uygulama yalnız sahanın tek dosyasını indirir. Yoksa Open-Meteo'ya düşer | CC-BY (C3S lisansı yeniden dağıtıma atıf ve değişiklik notuyla izin verir) | Uygulama CDS'e bağlanmaz; HF anonim indirme | Copernicus atfı + "değiştirildi: hız büyüklüğüne indirgenip kuantalandı" |
| **Global Wind Atlas 3.0, 250 m** | Türbin yerleşimi seçeneği (en rüzgârlı hücreler) ve nokta hızı: Türkiye kesiti 145 karo (17 MB, `data/grid/gwa_tr/`) + COG (21 MB), HF'te yeniden dağıtılır | CC BY 4.0 | — | Yukarıdaki GWA atfı + "Türkiye kesiti, uint16 kuantalama, 1° karolar" |
| **PVGIS Türkiye GES KF gridi** (PVGIS-SARAH3, çevrimdışı) | Çalışma anının güneş kaynağı: 1.464 kara hücresinin temsilî kara noktasında saatlik AC KF (2014–2023, uint16), `data/grid/pvgis_tr/v1` (~130 MB); ön tarama haritası | Kaynak gösterilerek serbest kullanım (JRC koşulları; türetilmiş KF yeniden dağıtılabilir) | Uygulama PVGIS'e bağlanmaz | "PVGIS © European Communities, 2001-2026" |
| **Copernicus DEM GLO-90** (AWS açık veri, COG) | Rakım ızgarası 0,02° (`data/grid/rakim_tr/v1`, 0,4 MB); komşu santral benzerliği | Ücretsiz, atıfla yeniden dağıtılabilir (Copernicus DEM lisansı) | Uygulama DEM'e bağlanmaz | "Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved." |
| **OpenStreetMap türbin düğümleri** (Overpass; `power=generator`, `generator:source=wind`; santral ilişki üyeleri) | Kalibre santrallerin türbin konumları, birim gücü, üretici, rotor, göbek → türbin vekili ve santral GWA'sı (`data/atlas/santral_turbinleri.csv`, `santral_turbin_konumlari.csv`) | ODbL 1.0 (türetilmiş veritabanı ODbL ile) | Overpass adil kullanım (bir kez sorgulandı) | "© OpenStreetMap katkıcıları, ODbL" |
| **OpenStreetMap harita karoları** (tile.openstreetmap.org) | Uygulamadaki harita altlığı (tarayıcı yükler) | OSM karo kullanım politikası: atıf zorunlu; yoğun trafik için uygun değil → herkese açık yayında bir karo sağlayıcısı seçilmeli (Faz yayın) | Politika gereği düşük hacim | "© OpenStreetMap contributors" (harita üzerinde) |

**Not (v1'den fark):** v1'de `results/` içinde ham saatlik EPİAŞ serisi tutulmuyordu. v2 piyasa paketi
(`data/atlas/piyasa/saatlik.parquet`) saatlik PTF ve ulusal üretim içerir; EPİAŞ'ın "kaynak gösterilerek çoğaltma"
koşuluna uygun olarak atıf metniyle dağıtılır. Santral bazında ham üretim dağıtılmaz; atlas yalnız türetilmiş katsayılar
(k, 12 × 24 matris, ay × saat ortalama KF) içerir.

## v3 (dal `v3-ie`) — Faz D: türbin yerleşimi, bakım ve güvenilirlik

Koşullar Ekim 2026'da kendi sayfalarından doğrulandı; herkese açık, ticari olmayan uygulamada kullanımı engelleyen koşul yok.

| Kaynak | v3'te kullanım | Lisans / koşul | Atıf |
|---|---|---|---|
| **ERA5 saatlik tek seviye, gridli** (`reanalysis-era5-single-levels`; u100, v100; Türkiye kutusu 0,25°, 2014–2023; CDS, çevrimdışı `src/v3_D0_era5_yon_grid.py`) | 100 m rüzgâr **yönü** → hücre başına 10°'lik sektör (uint8), `data/grid/era5_yon_tr/v1/` (git'e girmez); rüzgâr gülü ve saatlik iz verimi | CC-BY (C3S lisansı) | v1 Copernicus atfı + "değiştirildi: 100 m rüzgâr yönü 10°'lik sektörlere indirgendi" |
| **OpenStreetMap türbin düğümleri** (Türkiye, 4.122 düğüm; v2 Faz C0 indirmesi) | Komşu santral türbinleri (konum, birim güç, rotor, göbek) → `data/atlas/osm_turbinler.csv` | **ODbL 1.0** (türetilmiş veritabanı) | "© OpenStreetMap katkıcıları, ODbL" |
| **DTU PyWake 2.6** ([LICENSE](https://gitlab.windenergy.dtu.dk/TOPFARM/PyWake/-/blob/master/LICENSE)) | İz modeli referansı (Bastankhah Gauss, Jensen/NOJ), genel türbin CT eğrisi | MIT, © DTU Wind and Energy Systems 2018 | "PyWake (DTU Wind Energy), MIT lisansı" |
| **SimPy 4.1** ([PyPI](https://pypi.org/project/simpy/)) | Bakım ayrık olay simülasyonu | MIT | — |
| **Carroll, McDonald & McMillan (2016)**, *Failure rate, repair time and unscheduled O&M cost analysis of offshore wind turbines*, Wind Energy 19(6):1107–1119 ([açık erişim](https://strathprints.strath.ac.uk/54141/)) | Alt sistem × sınıf iş süreleri, malzeme maliyetleri, teknisyen sayıları; kara jeneratör/konvertör arıza oranları; sıfırlama oranı | Bilimsel yayın (değerler sayısal olarak alıntılandı) | Kaynak olarak anılır |
| **WMEP** (ISET/Fraunhofer IWES; Hahn, Durstewitz & Rohrig 2007; Faulstich vd. 2009, EWEC) | Kara RES'leri alt sistem arıza sıklıkları (grafikten yaklaşık) ve toplam 2,4 arıza/türbin/yıl | Bilimsel yayın | Kaynak olarak anılır |
| **NREL Cost of Wind Energy Review 2024** ([PDF](https://www.nrel.gov/docs/fy25osti/91775.pdf)) | Kara RES işletme gideri karşılaştırması (43 $/kW-yıl, 2023 $) | Kamu yayını | Kaynak olarak anılır |

## v3 (dal `v3-ie`) — Faz E: coğrafi katmanlar, çok kriterli seçim, lojistik

Koşullar Ekim 2026'da kendi sayfalarından doğrulandı. Tüm ağır CBS işi çevrimdışı; uygulama yalnız `data/atlas` altındaki
küçük türetilmiş tabloları ve `data/grid/cbs_tr` gridini okur, hiçbir dış servise bağlanmaz.

| Kaynak | Faz E'de kullanım | Lisans / koşul | Atıf |
|---|---|---|---|
| **OpenStreetMap — Geofabrik Türkiye PBF** ([download.geofabrik.de/europe/turkey.html](https://download.geofabrik.de/europe/turkey.html), 2026-10-08, 650 MB; `src/v3_E1_osm_katmanlar.py`, pyosmium) | Yollar (sınıflı; ağır nakliye ağı), iletim hatları ve trafo merkezleri (`voltage`), yerleşimler (yer düğümleri + `landuse=residential`), havalimanları, koruma alanları → `data/grid/cbs_tr/v1` mesafe gridleri, `data/atlas/trafo_merkezleri.csv`, `havalimanlari.csv`, `katman_*.geojson`, `cbs_hucre.parquet` | **ODbL 1.0** — atıf zorunlu; türetilmiş veritabanları ODbL ile paylaşılır (Geofabrik ek koşul koymaz) | "© OpenStreetMap katkıcıları, ODbL" (harita üstünde ve Yöntem sayfasında) |
| **WDPA / Protected Planet** (UNEP-WCMC, IUCN) | **Kullanılmadı.** Koşullar ([Terms of Use](https://www.protectedplanet.net/en/legal)) verinin yeniden dağıtımını ve ticari kullanımını izinsiz yasaklıyor; herkese açık uygulamaya türetilmiş katman gömmek bu koşula takılır | — | Alternatif: OSM `boundary=protected_area`, `boundary=national_park`, `leisure=nature_reserve` (477 alan; resmî listeden eksik olabilir — sınırlama) |
| **Copernicus DEM GLO-90** (AWS açık veri; `src/v3_E1_egim_grid.py`) | 250 m eğim (ortalama, azami) ve rakım → `data/grid/egim_tr/v1`; yol yokuş cezası | Copernicus DEM lisansı: ücretsiz, atıfla yeniden dağıtılabilir | "Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved." |
| **Liman ve üretici bilgileri** (liman işletmelerinin proje kargosu sayfaları: Aliağa, Bandırma/Çelebi, Gemlik, Samsunport, Port Akdeniz; TPI Composites, Nordex Türkiye, Ateş Wind Power, Gesbey; TÜREB/DARGEB tedarik zinciri yayınları) | `data/atlas/tedarik_kaynaklari.csv` (konum, bileşen, kapasite, doğrulama durumu ve kaynak bağlantısı) | Olgusal bilgi; içerik kopyalanmadı | Satır başına kaynak bağlantısı |
| **Kuş göç koridorları** (Doğa Derneği önemli kuş alanları; Jobson vd. 2021; Belen/Amanos RES izleme çalışmaları) | `data/atlas/goc_koridorlari.json`, `katman_goc.geojson`: yayınlardaki şekillerden elle sayısallaştırılmış **yaklaşık** eksen + tampon (risk 1/2) | Kendi yaklaşık sayısallaştırmam, CC BY 4.0; kaynak yayınlar anılır | Arayüzde "yaklaşık; ÇED kuş izleme çalışmasının yerini tutmaz" uyarısı |
| **ETKB — YEKA RES-2025 TEİAŞ bağlantı görüşleri** (enerji.gov.tr, 2025-09-09) | `data/atlas/teias_yeka_baglanti.csv`: 6 yarışma alanının bağlantı TM'si, gerilim ve hat uzunluğu → bağlantı maliyeti doğrulaması, gerilim kuralı | Kamu duyurusu | Kaynak olarak anılır |
| **YEKA RES-2026 bağlantı görüşleri** (Resmî Gazete 11.07.2026/33307 yarışma ilanı; aktaran Yeşil Haber, 2026-07-16 — ikincil kaynak) | `data/atlas/teias_yeka_baglanti.csv` (8 santral alanı): Faz F ön adım Ö2 bağlantı mesafesi oranı. Gerilim yalnız Manisa için yazılı, diğerleri TAHMİN (400 kV hatları) | Kamu duyurusu | Kaynak olarak anılır |
| **TEİAŞ ihale duyuruları** (154 kV hat ve TM yapım işleri yaklaşık maliyetleri, EKAP/teias.gov.tr) | `v3.baglanti` $/km ve TM birim maliyetleri | Kamu duyurusu | Kaynak olarak anılır |
| **TEİAŞ bağlantı kapasitesi** | **Bulunamadı (lisanslı RES için).** TEİAŞ yalnız lisanssız üretim için bölgesel bağlanabilir kapasite ve YEKA yarışmalarına özel görüş yayımlıyor; trafo merkezi bazında lisanslı kapasite tablosu yok | — | Ana sınırlama olarak raporlanır |
| **Cotrell vd. (2014)**, *Analysis of Transportation and Logistics Challenges Affecting the Deployment of Larger Wind Turbines*, NREL/TP-5000-61063 | Taşıma birim maliyeti (0,50 $/t/mil kule kesitleri) ve taşımanın kule maliyetindeki payı | ABD kamu yayını | Kaynak olarak anılır |
| **pyosmium 4.3** (BSD-2), **networkx** (BSD-3; kullanılmadı, scipy.sparse.csgraph tercih edildi) | Çevrimdışı OSM işleme | BSD | — |

## v3 (dal `v3-ie`) — Faz F: portföy ve performans izleme

Yeni bir dış veri kaynağı indirilmedi. Portföy, Faz A–E paketlerini ve motoru kullanır. Performans izleme, Faz A'da
önbelleğe alınmış EPİAŞ santral üretimini (kaynak gösterilerek kullanım koşulu) ve ERA5 hücre serilerini çevrimdışı
işler. Uygulamaya yalnız türetilmiş aylık ve günlük oranlar girer.

| Kaynak | Faz F'de kullanım | Lisans / koşul | Atıf |
|---|---|---|---|
| **EPİAŞ Şeffaflık Platformu — santral bazında gerçek zamanlı üretim** (önbellek, 2014–2026) | Performans izleme: günlük ve aylık gözlenen/beklenen oranı. Ham saatlik veri `data/raw` dışına çıkmaz | Kaynak gösterilerek kullanılabilir | "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr)" |
| **IRENA, Renewable Power Generation Costs** | Türbinin kara RES kurulum maliyetindeki payı %64–84 → toplu indirim hesabında %70 | Kamu yayını | Kaynak olarak anılır |
| **Çerçeve anlaşması duyuruları** (EDF Renewables–Vestas; VERBUND–Nordex 700 MW, 2026; EDF power solutions UK–Nordex ~900 MW) | Toplu türbin alımının fiyat avantajı sağladığı (oran yayımlanmıyor → TAHMİN %2/%3) | Basın duyurusu | Kaynak olarak anılır |
| **Montgomery (2019), *Introduction to Statistical Quality Control*; Sherbrooke (2004), *Optimal Inventory Modeling of Systems* (METRIC)** | EWMA/CUSUM parametre seçimi ve ARL; Poisson taban stok, beklenen bekleyen sipariş (EBO) | Ders kitapları | Kaynak olarak anılır |
| **Rockafellar & Uryasev (2000), "Optimization of conditional value-at-risk", *Journal of Risk* 2(3)** | Portföy MILP'inde CVaR doğrusallaştırması | Bilimsel yayın | Kaynak olarak anılır |
