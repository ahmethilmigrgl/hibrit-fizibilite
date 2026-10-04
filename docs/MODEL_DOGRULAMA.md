# Model doğrulama ve sınırlamalar

Kısa ve dürüst bir özet: neyi neyle doğruladım, neyi doğrulayamadım, sonuç en çok neye duyarlı.

## 1. Doğrulananlar

| Parça | Neyle doğrulandı | Sonuç | Kaynak |
|---|---|---|---|
| GES üretim modeli (pvlib PVWatts) | PVGIS `pvcalculation` (%14 kayıp, aynı tanım) | Yıllık verim 1.583 / 1.523 kWh/kWp: **+%4,0** | `outputs/01_uretim_modeli/ges_dogrulama.csv` |
| RES üretim modeli (ERA5 + güç eğrisi) | Üç komşu RES'in EPİAŞ saatlik üretimi; ay × saat hız katsayısı | Saatlik korelasyon 0,76 → **0,85**; ay × saat RMSE 10,6 → 0,9 KF puanı | `outputs/02_piyasa/kalibrasyon_metrikler.csv` |
| Kalibrasyonun aşırı uyumu | Çapraz doğrulama (2014–18 ile kur, 2019–23'te test ve tersi) | Test döneminde ay × saat RMSE 10–11 → **2,5–2,8** KF puanı; yıllık KF hatası ~1,8 puan | `kalibrasyon_capraz_dogrulama.csv` |
| Finansal model (Python) | Formüllü Excel modeli (FAST benzeri), LibreOffice ile yeniden hesap | 48/48 senaryoda NPV, IRR, öz kaynak IRR, DSCR, LCOE farkı **0**; 0 formül hatası | `outputs/08/excel_mutabakat.csv` |
| Finansal temel fonksiyonlar | Birim testleri (el hesabı) | NPV/IRR, vergi ve 5 yıllık zarar mahsubu, LCOE, batarya SOC, DST dönüşümü, CPM | `tests/` (18 test) |
| Temsilî günler | Tam yıl MILP (2 × 8.760 saat) | 24 temsilî gün 1 türbin eksik buluyor, NPV'yi ~0,7 M$ düşük tahmin ediyor → ana sonuçlar tam yılla | `outputs/04_optimizasyon/b3_temsili_vs_tam.csv` |
| Monte Carlo ara değerlemesi (dispatch tabloları) | Rastgele simülasyonlarda tam LP çözümü | Fark −0,1 ile −0,5 M$ (NPV'nin ~%1'i, hep aşağı yönlü) | `outputs/05_risk/b_yaklasim_hatasi.csv` |
| Dashboard tasarım gezgini | Tam model | Fark +0,5 / −0,8 M$ | `results/gezgin_hata.csv` |
| Deterministik baz ↔ Monte Carlo | Bileşen bileşen ayrıştırma; iki uç birebir | Fark açıklandı; fiyat ortalaması hatası bulunup düzeltildi (58 medyan → beklenen değer) | `docs/07` Güncelleme 3, `src/07_fark_ayristirma.py` |
| Kod kalitesi | ruff (lint + format), GitHub Actions CI | Ham veri olmadan temiz ortamda: ruff temiz, 17 test geçti (1 veri testi atlandı) | `.github/workflows/ci.yml` |

## 2. Doğrulanamayanlar (varsayım; config'te TAHMİN olarak işaretli)

- **YEKDEM USD koridorunun endekslenmesi:** 7189 sayılı karardaki taban/tavanın ABD enflasyonuyla güncellenip
  güncellenmeyeceği belirsiz. Kararı değiştirebilen tek kalem: nominal −1,7 M$, endeksli +0,4 M$.
- **Sistem kesintisinde tazmin oranı:** YAT talimatlarının ne kadarının DGP'den (tazminli) geldiği kamuya açık değil.
  Düzgün %0–100 varsayıldı.
- **Yan hizmet (SFK) parametreleri:** 2026 SFK fiyatı gerçek, ama doyum hızı, senaryo olasılıkları, bataryaların SFK'ya
  uygun payı (θ) ve fırsat maliyeti tabanı İngiltere/Almanya deneyiminden kalibre edildi. Türkiye'de SFK'ya fiilen
  katılan batarya verisi yok. TEİAŞ'ın hibrit tesisteki bataryayı kabul edip etmeyeceği belirsiz.
- **PPA iskontosu** (%10), **CAPEX dağılımları**, **kriz olayı** (yıllık %3, ×1,6) ve **ornitoloji** kaybı:
  kamuya açık Türkiye verisi bulunamadı.
- **Rüzgâr kaynağı:** saha ölçümü yok; ERA5 komşu santrallerle kalibre edildi. İz (wake) kaybı toplam kayıp oranıyla
  yaklaşıklandı.
- **Dispatch:** mükemmel öngörülü; gerçek arbitraj geliri daha düşük olur. Gelirin çoğu kapasite ödemesi olduğundan
  etkisi sınırlı.
- **Tarihsel sayılar:** Aşama 5–6 çıktıları (`outputs/05_risk`, docs/05) fiyatın medyan tanımıyla üretildi ve karar
  yolculuğunun parçası olarak bırakıldı. Hat yeniden çalıştırılırsa düzeltilmiş tanımla yeniden üretilir.

## 3. Sonuçlar en çok neye duyarlı?

1. **Uzun vadeli fiyat seviyesi.** NPV varyansının yarısından fazlası. Deterministik eğim ~1,35 M$ / ($/MWh);
   başabaş beklenen fiyat ≈ 59 $/MWh, baz varsayımın yalnız ~%2 üstü. Tornado: 45 / 72 $/MWh → NPV aralığı ~40 M$.
2. **SFK piyasasının doyum hızı.** Batarya değerinin neredeyse tamamı SFK'dan geliyor. Senaryo karışımı ile
   deterministik baz yol arasındaki fark tek başına +2,7 M$. Bu belirsizliğin bilgi değeri 2,0 M$.
3. **CAPEX** (±%20 → ~27 M$ aralık) ve **WACC** (%5,5–8,5 → ~18 M$ aralık).
4. **Takvim:** COD 2030 sonrasına kayarsa YEKDEM hakkı kaybolur; geliştirme aşamasındaki proje için COD P50 2032.
5. **Fiyat sürecinin tanımı:** 58 medyan yerine ortalama alındığında baz vaka +1,5'ten −1,7 M$'a döndü. Bu bir
   duyarlılık değil, düzeltilen bir hata. Ama ne kadar küçük bir tanım farkının kararı çevirdiğini gösteriyor.

**Sonuç:** Model, üretim ve finans tarafında bağımsız kaynaklarla tutarlı. Kararı belirleyen girdiler (fiyat seviyesi,
SFK doyumu, YEKDEM endekslemesi) ise doğrulanamayan varsayımlar. Bu yüzden öneri kesin bir "hayır" değil: gözlenebilir
tetikleyicilere bağlı bir "şimdilik hayır".
