# v2 Faz B — Analiz motoru

Faz A, rüzgâr/güneş verisini ve kalibrasyonu Türkiye'nin herhangi bir noktası için üretilebilir hale getirdi. Faz B, v1'in
Ezine hattını (üretim → piyasa → finans → MILP → Monte Carlo → karar) **tek bir çağrıya** dönüştürüyor. Web uygulaması
(Faz C) yalnız bu çağrıyı kullanacak:

```python
from src.motor import analiz_et, KullaniciVarsayimlari
s = analiz_et({"ad": "Kangal", "enlem": 39.08, "boylam": 37.40}, "hizli", KullaniciVarsayimlari(baglanti_mw=50))
s.ozet, s.tablolar, s.grafikler, s.nedenler, s.uyarilar   # JSON özet, DataFrame'ler, grafik verisi, gerekçeler
s.kaydet(Path("cikti/"))                                  # sonuc.json + tablolar/*.parquet
```

## 1. Mimari

| Modül (`src/motor/`) | Görev |
|---|---|
| `varsayimlar.py` | `KullaniciVarsayimlari` (hepsi varsayılanlı), `dogrula()` sınır/tutarlılık kontrolü, iki dilli `MotorHatasi` ve `Uyari` |
| `ortak.py` | Saha nesnesi + kara kontrolü, kullanıcı varsayımlarının config'e uygulanması (WACC, CAPEX çarpanları, kanibalizasyon), profil önbelleği, güven bilgisi, `sfk_milp_carpani` |
| `hizli.py` | Hızlı tarama (§2) |
| `tablolar.py` | Çalışma zamanı işletme (dispatch) tabloları, 2 süreçli havuz, disk önbelleği (§4) |
| `mc.py` | Azaltılmış Monte Carlo ve yakınsama kuralı (§3) |
| `tam.py` | Tam analiz: tasarım seçimi, gelir yapıları, karar kuralı, tetikleyiciler, başabaş fiyat |
| `rapor.py` | Saha raporu HTML + PDF (Chrome headless) |
| `onbellek.py` | Sonuç önbelleği, tek tam analiz kilidi, zaman aşımı (§5) |
| `sonuc.py` | `Sonuc` nesnesi: `.json()`, `.kaydet()` |
| `motor.py` | `analiz_et(saha, mod, kullanici_varsayimlari, ilerleme_geri_cagirimi)` |

**Kullanıcı varsayımları:**

| Grup | Varsayımlar |
|---|---|
| Kapasite | bağlantı MW (5–300); azami RES/GES MW |
| Rüzgâr | türbin yerleşimi (açık/kapalı, yarıçap 0,5–10 km) |
| Fiyat | fiyat senaryosu (düşük/baz/yüksek) ya da serbest seviye (20–150 $/MWh); kanibalizasyon (devam/durur) |
| Finans | WACC (%3–15); RES/GES/BESS CAPEX çarpanları (0,5–2) |
| Proje | proje aşaması (ön lisans / inşaata hazır) |
| Gelir | gelir yapıları (tüccar, yıllık YEKDEM opsiyonu, PPA); SFK katılımı |
| İleri düzey | sabit tasarım; kalibrasyon modu; rüzgâr kaynağı |

**Doğrulama:** Bütün mesajlar Türkçe ve İngilizce verilir.
- Hata verilen durumlar: sınır dışı değer, deniz ya da Türkiye karası dışı nokta, bilinmeyen gelir yapısı, kurulacak kapasite yok.
- Uyarı verilen durumlar: veri boşluğu (> 48 saat), çok düşük rüzgâr (KF < %15) ya da güneş, düşük güven seviyesi, bağlantının yarısından küçük RES sınırı.

**İlerleme geri çağırımı:** `ilerleme(oran, mesaj)` aşama başlarında çağrılır, örneğin "Monte Carlo n = 4000, standart hata 0,24 M$". Web arayüzü bunu ilerleme çubuğuna bağlar.

## 2. Hızlı tarama (`mod="hizli"`, hedef ≤ 90 s)

1. **Profiller.**
   - Rüzgâr: ERA5 grid noktası, yoksa Open-Meteo; atlas kalibrasyonu ve türbin yerleşimi uygulanır.
   - Güneş: PVGIS.
   - 10 yıllık saatlik KF profilleri sha1 anahtarlı diskte önbellekte tutulur.
2. **Üretim özeti.**
   - KF'ler ve 1 yıllık P50/P90.
   - RES belirsizlik bandı: güven seviyesinin medyan ve P90 hatası (§6).
   - Gün içi ve aylık profil, RES–GES korelasyonu (tamamlayıcılık).
3. **Piyasa.** Yakalanan fiyat ve yakalanma oranı (ulusal piyasa paketi, kanibalizasyon yolu ile).
4. **Standart tasarımlar.** v1 `proje_degerle` ile deterministik NPV, IRR, kesinti, LCOE ve teknoloji bazında başabaş fiyat. Tasarımlar:
   - RES = bağlantı;
   - RES %30 fazla kurulum;
   - RES + %50 GES;
   - yalnız GES.
5. **Temsilî gün MILP'i.** 24 gün; v1 kapasite modeli; SFK geliri doyum beklentisiyle çarpılır (§3.1).
6. **Kural tabanlı "neden" metinleri** (sayılarla). Örnekler:
   - "GES eklemek kesintiyi +3,3 puan artırıp NPV'yi −4,3 M$ değiştiriyor (güneş yakalanma oranı 0,72)";
   - "Hiçbir tasarım pozitif NPV vermiyor: en iyi karar yatırım yapmamak".

**Kapsam dışı:** Monte Carlo, gelir yapıları ve takvim yalnız tam analizde.

## 3. Tam analiz (`mod="tam"`, hedef ≤ 10 dk)

1. **Tasarım: tam yıl (8760 × 10 yıl) kapasite MILP'i.**
   - MIP boşluğu %0,5. v1 %0,1 kullanıyordu; Susurluk'ta süre 164 → 70 s; amaç değeri en fazla %0,5 kayıp.
   - MILP "kurulum yok" derse, standart tasarımların en iyisi değerlenir ve gerekçeye yazılır. Monte Carlo böylece "kursak ne olur?" sorusunu yanıtlar.
2. **Çalışma zamanı işletme tabloları.** Ayrıntı §4'te.
3. **Monte Carlo.** v1 07 hattı sahaya genellendi. Belirsizlikler:
   - fiyat (log-AR(1), ortalama tanımlı, kriz/tavan);
   - hava yılı;
   - kanibalizasyon;
   - SFK doyum senaryoları + ortak batarya sürücüsü;
   - sistem kaynaklı kesinti;
   - CAPEX/OPEX;
   - bozunma;
   - YEKDEM yıllık opsiyon (30 Kasım kararı);
   - PPA finansal fark sözleşmesi.

   v2 farkları:
   - **Rüzgâr model belirsizliği sahanın güven seviyesinden:** m ~ LogNormal(−σ²/2, σ). σ = 1,4826 × medyan mutlak KF hatası / atlas ortalama KF. Değerler: yüksek ≈ %10, orta ≈ %23, düşük ≈ %27. Kalibre (v1) modda v1 üçgen dağılımı korunur.
   - **COD, proje aşamasının takvim dağılımından** (v1 CPM + Monte Carlo örnekleri) simülasyon başına çekilir. COD 31.12.2030'dan sonraysa YEKDEM hakkı yoktur.
   - **n yakınsamayla seçilir.** n = 2000'den başlar ve ikiye katlanır. En iyi yapının E[NPV] standart hatası ≤ 0,25 M$ olunca durur; üst sınır 16.000. SE raporda gösterilir.
4. **Karar kuralı:**

   | Koşul | Karar |
   |---|---|
   | E[NPV] > 0, P(NPV > 0) ≥ 0,65 ve CVaR5 ≥ −0,25 × CAPEX | **Yatırım yap** |
   | E[NPV] > 0 (ama yukarıdaki koşullardan biri sağlanmıyor) | **Sınırlı teklif** (durum tespiti + ≤ E[NPV] prim) |
   | Diğer | **Rafa kaldır, tetikleyicileri izle** |

   Tetikleyiciler:
   - Monte Carlo başabaş fiyatı: L − E[NPV]/eğim. Eğim, deterministik NPV'nin fiyat seviyesine türevidir (L ± 1).
   - SFK doyum hızına koşullu E[NPV].
   - Rüzgâr ölçümü (güven seviyesi düşükse öncelikli).
   - YEKDEM katılım yılları.
5. **Saha raporu.** HTML + PDF. İçerik: özet ve karar, tasarım, gelir yapıları tablosu, NPV histogramı, üretim profilleri, gerekçeler, varsayımlar, veri atıfları.

### 3.1 SFK doyumu ve boyutlandırma tutarlılığı (Faz B'de bulunan tutarsızlık)

İlk beş sahalık taramada temsilî gün MILP'i her sahada aynı sonucu verdi: "RES 0 / GES 0 / BESS 30 MW, NPV +11…+21 M$". Bu, sahadan bağımsız tek başına bir bataryaydı.

**Neden.**
- MILP, SFK gelirini Aşama 5'in azalma yoluyla (%15/yıl, 2026 seviyesinin %25'inde taban) değerliyordu.
- Monte Carlo ise Aşama 6 doyum senaryolarını kullanıyor: SFK ihtiyacı ~1 GW, sırada GW'larca depolama var.
- Sonuç olarak boyutlandırma, değerlemenin varsaymadığı bir geliri kovalıyordu. Bu, v1'in stres testi dersinin motorda unutulmuş haliydi.

**Düzeltme.** `ortak.sfk_milp_carpani(o)` MILP'e `yh_carpan` olarak verilir:

$$
c_{SFK} = \frac{\sum_t DF_t\, \sum_s \pi_s\, a^{doyum}_{s,t}}{\sum_t DF_t\, a^{MILP}_t}
$$

Burada π_s doyum senaryolarının olasılıklarıdır ("katılamama" dahil, a = 0). Böylece MILP, Monte Carlo'nun beklediği SFK gelirini görür. Ezine için c = 0,32: MILP eskiden beklenen SFK değerinin ~3 katını varsayıyordu.

**Düzeltme sonrası.** Beş sahanın üçünde MILP hiçbir kapasiteyi kârlı bulmuyor. İki sahada 30 MW batarya, sabit maliyetleri en az kayıpla karşılayan seçenek olarak kalıyor (NPV < 0). Tarama artık "Yatırım yok" diyor (§7.3).

## 4. Çalışma zamanı işletme tabloları: doğruluk / süre ödünleşimi

v1'de Monte Carlo, önceden hesaplanmış işletme tablolarını okuyordu: her (kanibalizasyon H, RES model çarpanı M, SFK fiyat çarpanı A, hava yılı) için yıllık gelir ve enerji kalemleri, batarya için LP ile. Yeni bir sahada bu tablolar çalışma zamanında üretilmeli. Bu, tam analizin en pahalı adımı.

| Izgara | H × M × A × hava | Süre (2 çekirdek, tüccar) | E[NPV] farkı (v1 ızgarasına göre) | Karar |
|---|---|---|---|---|
| v1 | 4 × 3 × 6 × 10 | ~10 dk (+ YEKDEM) | — | Yalnız regresyon |
| **hafif** | 2 × 3 × 4 × 10 | **93 s** | **−0,01 M$** | **Varsayılan** |
| hızlı (5 hava yılı) | 2 × 3 × 4 × 5 | ~½ | −1,6 M$ (yanlı) | Reddedildi |

Ayrıntılar:
- **Hafif ızgara.** H = {0,55; oran₀}. M = {1−2σ; 1; 1+2σ}, [0,5; 1,5] ile kırpılır; aralık sahanın güven seviyesine göre genişler. A = {0; 0,05; 0,25; 1}.
- **Hava yılı seçimi yanlılık üretiyor.** 5 hava yılının ortalama KF sırasına göre eşit aralıklı seçimi, kuyruk yıllarını eksik temsil etti. Hava boyutu bu yüzden kırpılmadı.
- **YEKDEM tablosunun φ = 0 kesiti** tüccar tablosuyla aynı (göreli fark 2·10⁻⁹). YEKDEM tablosu yalnız φ = 1 için üretilir.
- **Paralellik.** `fork` bağlamlı 2 süreçli havuz (`MOTOR_CEKIRDEK`). macOS'ta `spawn` önyükleme hatası verdiği için `fork` kullanılır.
- **Disk önbelleği.** `data/onbellek/tablolar/`, anahtar = tasarım + ızgara + saha profili sha1. Aynı tasarımın ikinci analizi tabloyu yeniden üretmez.

## 5. Önbellek ve eşzamanlılık

- **Sonuç önbelleği** (`data/onbellek/sonuc/`). Anahtar: sha1 [0,01° yuvarlatılmış enlem/boylam, mod, tüm kullanıcı varsayımları, veri sürümü `v2.motor.veri_surumu`]. Toplam boyut `onbellek_azami_mb`'yi (500 MB) aşınca son erişimi en eski kayıtlar silinir (LRU, erişimde `touch`). Bozuk kayıt sessizce silinip yeniden hesaplanır.
- **Profil ve tablo önbellekleri** ayrı. Aynı sahada farklı finansal varsayımlar profili yeniden indirmez.
- **Tek tam analiz.** Aynı anda en fazla bir tam analiz çalışır: süreç içi kilit + süreçler arası `flock` (çok işçili sunucu için). Diğerleri sıraya girer. Hızlı tarama kilitsiz çalışır.
- **Zaman aşımı** (`tam_zaman_asimi_s` = 900 s; bekleme + çalışma). Süre dolunca kullanıcıya hemen iki dilli mesaj döner. Python iş parçacığı zorla durdurulamadığı için kilit, arka plandaki iş gerçekten bitince bırakılır; böylece yeni bir tam analiz onunla üst üste binmez. İlk sürümde bir hata vardı: `with ThreadPoolExecutor` çıkışı iş parçacığını beklediği için mesaj ancak iş bitince dönüyordu. Test bunu yakalıyor: `tests/test_v2_motor.py`.

## 6. Güven seviyeleri ve rüzgâr belirsizliği

> **Güncellendi (Faz C ön adımı):** Atlas aktarımı düzeltildi; güven artık iki seviye (yüksek ≤ 30 km: medyan 3,8 / P90 9,8
> puan; düşük: 5,6 / 11,5). Beş saha ve tutarlılık tabloları yeniden üretildi: `docs/v2_C_arayuz.md §2`. Aşağıdaki tablolar Faz B anındadır.

Güven seviyeleri Faz A Ö4'ten gelir; bkz. `docs/v2_A_veri_altyapisi.md §5a`, `data/atlas/guven_seviyeleri.csv`. Değerler bırakılan-dışarı çapraz doğrulama ile ölçülen mutlak KF hatasıdır (puan); parantez içinde bootstrap %90 güven aralıkları:

| Seviye | Tanım | n | Medyan | P90 |
|---|---|---|---|---|
| Yüksek | benzer komşu ≤ 15 km | 28 | 2,1 (1,7–3,7) | 7,5 (4,4–8,3) |
| Orta | komşu 15–30 km | 8 | 5,2 (4,0–7,9) | 11,8 (6,0–20,4) |
| Düşük | komşu yok (GWA × ulusal artık) | 54 | 5,9 (4,7–7,1) | 13,6 (10,7–15,0) |

Motor bu tabloyu iki yerde kullanır:
- hızlı taramada RES KF bandı;
- tam analizde Monte Carlo'nun σ'sı.

**Sınırlama: tek komşu.** Yüksek güvenli bir tahmin tek bir komşu santrale dayanabilir. Örnek: Karaburun'da yalnız Yaylaköy RES, 7 km.
- O santralin GWA artığı (R = 0,78) ulusal medyandan (0,92) belirgin düşükse sahaya aynen aktarılır.
- Karaburun noktasında KF %22 çıktı; komşu santralin gözlenen KF'si %32,5.
- Fark kısmen gerçek: seçilen nokta sırtta değil, GWA 7,4 m/s; santral hücreleri ~9 m/s.
- Kısmen de tek santralin artığının taşınmasından geliyor.
- Faz C'de rapor, komşu sayısı 1 ise bunu ayrıca belirtmeli.

## 7. Doğrulama

### 7.1 Ezine regresyonu (tam analiz vs v1 nihai baz vaka)

Koşullar: kalibre (v1) mod; CDS ERA5; türbin yerleşimi kapalı; v1 nihai tasarımı (RES 58,8 MW + BESS 30/60) sabit; v1 tablo ızgarası; inşaata hazır takvim. Kaynak: `src/v2_B5_regresyon.py` → `outputs/v2B/B5_regresyon.csv`.

| Gelir yapısı | v1 E[NPV] | v2 E[NPV] | Fark | v2 SE | v1 P(NPV>0) | v2 P(NPV>0) | v1 CVaR5 | v2 CVaR5 |
|---|---|---|---|---|---|---|---|---|
| YEKDEM opsiyonu | −1,66 | −1,43 | +0,23 | 0,24 | %42,4 | %43,2 | −28,0 | −28,4 |
| Tüccar | −2,11 | −1,88 | +0,23 | 0,24 | %42,0 | %42,8 | −30,4 | −30,7 |
| PPA | −6,05 | −5,93 | +0,12 | 0,18 | %28,0 | %27,8 | −26,0 | −26,3 |

**Karar aynı:** "Rafa kaldır, tetikleyicileri izle".

**Tolerans.** Fark, iki tahminin birleşik standart hatası içinde: √(0,24² + 0,15²) ≈ 0,28 M$ (v1: σ ≈ 15 M$, n = 10.000). P ve CVaR farkları < 1 puan / < 0,4 M$.

**Farkın kaynağı.** Kalan +0,2 M$ büyük ölçüde örnekleme gürültüsü (n = 4000 vs v1 10.000). İki yapısal etken de var:
- COD v2'de simülasyon başına takvim dağılımından çekilir (v1: erteleme yılı kesikli ağırlıklarla).
- v2 yakınsama kuralı n = 4000'de durdu.

Sistematik bir sapma olsaydı üç yapıda farklı işaretler ya da > 2 SE görülürdü.

### 7.2 Hızlı ↔ tam tutarlılığı (3 saha)

`src/v2_B5_dogrulama.py tutarlilik` → `outputs/v2B/B5_tutarlilik.csv`.

| Saha | Güven | Hızlı (24 temsilî gün) tasarım | Hızlı det. NPV | Tam (tam yıl) tasarım | Tam MILP det. NPV | Tam E[NPV] (en iyi yapı) | Hızlı sonuç | Tam karar | Tam süre |
|---|---|---|---|---|---|---|---|---|---|
| Çanakkale-Ezine | yüksek | kurulum yok | −6,1 | RES 8,4 + BESS 30/60 | −4,9 | −7,6 (YEKDEM opsiyonu) | Yatırım yok | Rafa kaldır | 260 s |
| Sivas-Gürün | yüksek | RES 58,8 + BESS 30/57 | −1,6 | RES 58,8 + BESS 32/60 | +1,2 | −3,8 (YEKDEM opsiyonu) | Yatırım yok | Rafa kaldır | 325 s |
| Balıkesir-Susurluk | yüksek | RES 58,8 + BESS 31/60 | +4,9 | RES 58,8 + BESS 32/60 | +4,2 | −3,1 (YEKDEM opsiyonu) | Optimum pozitif | Rafa kaldır | 309 s |

Gözlemler:
- **Gürün ve Susurluk: tasarımlar aynı.** RES 58,8 MW (14 türbin, %18 fazla kurulum) ve ~30 MW / 60 MWh batarya. Temsilî gün ile tam yıl MILP'inin deterministik NPV'leri 0,7–2,8 M$ farklı. Fark, temsilî günlerin kesinti ve fiyat kuyruklarını yumuşatmasından geliyor.
- **Ezine (atlas kalibrasyonu, KF %30): iki mod da pozitif NPV'li tasarım bulmuyor.** Tam yıl MILP'i yatırım zorunluyken en az kayıplı seçenek olarak 2 türbin + batarya seçiyor. Bu, aynı kararın dejenere bir köşe çözümü. Ezine'nin v1'den (KF %37,7, kalibre) farkı Faz A §5a'da açıklandı.
- **Tutarsız görünen tek nokta: Susurluk.** Deterministik optimum pozitif (+4,2…+4,9), Monte Carlo ise negatif (−3,1). Bu, v1'deki deterministik → Monte Carlo köprüsünün aynısı: fiyat ortalama tanımı, YEKDEM'e giriş zamanı, takvim gecikmesi, kesinti, SFK doyum dağılımının kuyruğu (`src/07_fark_ayristirma.py`). Hızlı tarama bu yüzden karar vermez; "deterministik optimum pozitif → tam analize değer" der.
- **Karar yönü uyumlu.** Hızlı taramanın "yatırım yok" dediği hiçbir sahada tam analiz yatırım önermedi.

### 7.3 Beş saha tipi — hızlı tarama

`src/v2_B5_dogrulama.py tarama` → `outputs/v2B/B5_bes_saha.csv`. Ayarlar: varsayılanlar (50 MW bağlantı, baz fiyat 58 $/MWh, türbin yerleşimi 2 km, SFK katılımı açık).

| Saha tipi | Nokta | GWA 100 m [m/s] | Güven | RES KF | GES KF | RES yakalanma | GES yakalanma | LCOE RES / GES [$/MWh] | Başabaş RES / GES [$/MWh] | NPV RES / GES / RES+GES [M$] | MILP optimumu | Sonuç | Süre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Kıyı rüzgârlı | İzmir-Karaburun (38,63; 26,51) | 7,38 | yüksek | %22,1 | %20,9 | 1,04 | 0,72 | 84 / 50 | 95 / 88 | −28,4 / −14,9 / −32,2 | BESS 30 (−5,6) | Yatırım yok | 2,2 s |
| İç Anadolu rüzgârlı | Sivas-Kangal (39,08; 37,40) | 7,15 | düşük | %31,0 | %20,7 | 1,05 | 0,72 | 62 / 52 | 69 / 91 | −11,9 / −16,3 / −16,1 | kurulum yok | Yatırım yok | 2,0 s |
| Güneşli güney | Karaman (37,18; 33,22) | 4,86 | düşük | %16,2 | %21,8 | 1,06 | 0,72 | 113 / 49 | 126 / 85 | −40,2 / −14,0 / −43,4 | kurulum yok | Yatırım yok | 1,9 s |
| Düşük rüzgârlı | Ankara-Polatlı (39,58; 32,15) | 5,03 | düşük | %18,3 | %20,4 | 1,10 | 0,72 | 101 / 51 | 107 / 90 | −33,7 / −15,4 / −37,8 | BESS 30 (−4,4) | Yatırım yok | 2,0 s |
| Dağlık | Erzurum-Palandöken (39,86; 41,27) | 7,80 | düşük | %27,6 | %19,1 | 1,00 | 0,72 | 69 / 56 | 82 / 99 | −21,6 / −18,6 / −26,9 | kurulum yok | Yatırım yok | 2,0 s |

(Süreler profil önbellekteyken. Soğuk ilk çağrı PVGIS + rüzgâr indirmesiyle ~13 s, §7.4.)

Yorum:
- **Sıralama sezgiyle uyumlu.** RES maliyeti rüzgâra göre sıralanıyor: Kangal (LCOE 62) < Palandöken (69) < Karaburun (84) < Polatlı (101) < Karaman (113). Güneş KF'si güneyde en yüksek (Karaman %21,8).
- **Hiçbir tip 58 $/MWh baz fiyatta pozitif değil.** En yakın aday Kangal: başabaş 69 $/MWh, yani baz fiyatın %19 üstü. Bu, v1'in Ezine sonucuyla ("rafa kaldır, başabaş ~59–61") ve Susurluk tam analiziyle (başabaş 61) tutarlı.
- **Güneşin sorunu maliyet değil, değer.** LCOE ~50 $/MWh baz fiyatın altında. Ama 0,72 yakalanma oranıyla güneşin eline geçen fiyat ~42 $/MWh, başabaş 85–99 $/MWh. Kanibalizasyon her sahada aynı, çünkü fiyat ulusal.
- **Dağlık saha.** Palandöken'in GWA'sı yüksek (7,8 m/s), bu yüzden türbin seçim kuralı yüksek rüzgâr sınıfı türbini seçiyor: E-126, 105 m göbek. Buna rağmen KF %27,6'da kalıyor. İki neden var: ~2.000 m rakımda güç eğrisi yoğunluk düzeltmesi (hava ~%20 daha seyrek) ve komşu santral olmadığı için uygulanan ulusal artık (medyan R = 0,92). Güven "düşük" (komşu santral yok); ±13,6 puanlık P90 hatası kararı tek başına değiştirebilecek büyüklükte.
- **Karaburun "yüksek" güvenli ama tek komşulu** (§6 sınırlama).

### 7.4 Süreler (2 çekirdek)

Taze bir sahada ölçüldü: Geyikli, 39,80 / 26,18. Önce profil, tablo ve ham indirme önbellekleri silindi. Kaynak: `src/v2_B5_dogrulama.py sure` → `outputs/v2B/B5_sure.csv`.

| Mod | Durum | Duvar [s] | CPU [s] | Adımlar |
|---|---|---|---|---|
| Hızlı | soğuk (PVGIS + Open-Meteo indirmesi) | **13,5** | 3,0 | hazırlık 11,4 (ağ) · tasarımlar 1,1 · MILP 0,9 |
| Hızlı | ılık (profil önbellekte) | **1,9** | 2,0 | tasarımlar 1,1 · MILP 0,6 |
| Hızlı | sıcak (sonuç önbelleği) | 0,03 | 0,03 | — |
| Tam | soğuk | **249** | 419 | MILP 87 · işletme tabloları 160 · Monte Carlo 0,3 · rapor ~1 |
| Tam | ılık (tablolar önbellekte) | **90** | 101 | MILP 88 |
| Tam | sıcak (sonuç önbelleği) | 0,03 | 0,03 | — |

Değerlendirme:
- **Hedefler sağlandı.** Hızlı tarama ≤ 90 s (soğukta 13,5 s). Tam analiz ≤ 10 dk (soğukta 4,2 dk); tutarlılık testindeki üç sahada da 260–325 s.
- **CPU / duvar oranı.** Soğuk tam analizde 1,68 (≤ 2), yani 2 çekirdek sınırı tutuyor.
- **Darboğazlar ve yapılanlar.**
  - İşletme tabloları (%64): hafif ızgara ve YEKDEM φ = 0 kesitinin tüccar tablosundan alınması (§4).
  - Tam yıl MILP'i (%35): MIP boşluğu %0,1 → %0,5.
  - Kalan seçenek: MILP'i 48 temsilî günle çözmek (~10 s). Doğruluk kaybı §7.2'deki 0,7–2,8 M$ farkına benzer olacağı için yapılmadı.
- **Monte Carlo ucuz** (< 1 s): vektörize nakit akışı. n yakınsama kuralıyla 2000–4000'de duruyor.

**2 çekirdek benzetimi.** macOS'ta `taskset` ya da cgroup yok. Kısıtlama şöyle yapıldı:
- Motorun süreç havuzu `MOTOR_CEKIRDEK=2` ile sınırlandı.
- BLAS/HiGHS iş parçacıkları `OMP_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1` ile tek iş parçacığına indirildi.
- Böylece aynı anda en fazla 2 çekirdek hesap yapar.
- Ölçüm için duvar saati ile süreç + çocuk CPU süresi (`resource.getrusage`) birlikte raporlandı: CPU / duvar ≤ 2 olmalı.
- Gerçek 2 vCPU'lu bir sunucuda (Faz C) tek iş parçacığı başarımı daha düşük olabilir. Buradaki süreler alt sınır sayılmalı.

## 8. Sınırlamalar

- **Hızlı taramanın kapsamı.** Hızlı tarama deterministik, gelir yapısı ve takvim yok. Kararı tam analiz verir; hızlı tarama yalnız "bakmaya değer mi" sorusunu yanıtlar.
- **Temsilî gün MILP'i.** 24 gün, tam yıl MILP'inden farklı tasarım verebilir (§7.2). Tam analiz tam yılı kullanır.
- **Hafif ızgara.** Ayrıştırma, Ezine ve Susurluk tasarımlarında doğrulandı (−0,01 M$). Çok farklı tasarımlarda (ör. büyük GES + batarya) ızgara enterpolasyon hatası ölçülmedi.
- **Doyum çarpanı.** `sfk_milp_carpani` beklenen değeri kullanır; doyum senaryolarına göre optimum tasarımın değişebileceğini (esnek/aşamalı batarya, v1 Aşama 6) motor modellemez.
- **Türbin yerleşimi.** Yerleşim, en rüzgârlı GWA hücrelerini seçer. İz kaybı, erişim, eğim ve izinler modellenmez; bkz. `docs/v2_A §5a`.
- **Güneş belirsizliği.** Güneş belirsizliği sabit %4 (PVGIS model hatası); saha ölçümüyle kalibre edilmedi.
- **Piyasa varsayımları ulusal.** Bölgesel fiyat ya da sistem kaynaklı kesinti farkı yok. Kesinti v1 referans santrallerinden ulusal oranla uygulanır.
