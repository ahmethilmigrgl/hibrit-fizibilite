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
