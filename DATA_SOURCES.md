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

**Not (v1'den fark):** v1'de `results/` içinde ham saatlik EPİAŞ serisi tutulmuyordu. v2 piyasa paketi
(`data/atlas/piyasa/saatlik.parquet`) saatlik PTF ve ulusal üretim içerir; EPİAŞ'ın "kaynak gösterilerek çoğaltma"
koşuluna uygun olarak atıf metniyle dağıtılır. Santral bazında ham üretim dağıtılmaz; atlas yalnız türetilmiş katsayılar
(k, 12 × 24 matris, ay × saat ortalama KF) içerir.
