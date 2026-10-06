# v2 Faz A — Veri altyapısı ve genelleştirme

Amaç: hattı (üretim → piyasa → finans → optimizasyon → risk) Türkiye'de herhangi bir saha için çalıştırmak ve bunu
herkese açık bir uygulamada kişisel kimlik bilgisi olmadan yapmak. Lisanslar ve atıflar: `DATA_SOURCES.md` (v2 bölümü).
Para birimi ve finansal varsayımlar v1 ile aynı (reel 2026 USD, %7 reel WACC).

## 1. Mimari

| Katman | Çalışma zamanı (uygulama) | Çevrimdışı (ön hesaplama, kişisel anahtar) |
|---|---|---|
| Rüzgâr | Open-Meteo ERA5 (anahtarsız) | CDS ERA5 (atlas için santral hücreleri) |
| Güneş | PVGIS API (anahtarsız) | — |
| Rüzgâr iklimi | GWA 1 km paketi (`data/atlas/gwa_tr_1km.npz`, 4,6 MB) | GWA 250 m rasterlerinden üretim |
| Kalibrasyon | Atlas (`kalibrasyon_atlasi.csv`, `kalibrasyon_matrisleri.npz`) + aktarım kuralı | EPİAŞ santral üretimi → atlas |
| İl/ilçe, kıyı | `sinirlar_tr.npz` (80 KB), `kiyi_tr.npz` (32 KB) | geoBoundaries, Natural Earth |
| Piyasa | `data/atlas/piyasa/` (2,9 MB) | EPİAŞ → `src/v2_A6_piyasa_paketi.py --guncelle` |
| Tarife | config `v2.teias_2026` | EPDK 14204 (taranmış PDF elle) |

**Saha nesnesi** (`src/saha.py`): ad, enlem, boylam, il, ilçe, bağlantı MW, RES/GES üst sınırları, türbin/göbek (yoksa
otomatik), kullanıcı varsayımları (config yolu → değer). `saha_cfg(saha)` sahaya özgü config kopyası üretir:
- GWA rüzgâr sınıfına göre türbin ve göbek seçer;
- tarife bölgesine göre TEİAŞ bedellerini ayarlar;
- bağlantıyı ve üst sınırları uygular.

`src/uretim/genel.py → profil_uret(saha, cfg, ruzgar_kaynagi, kalibrasyon)` v1 profil biçimini üretir. `Ortam(cfg, uretim)`
(Aşama 5 çekirdeği) artık sahayı dışarıdan alır. Sabit 50 MW bağlantı sahadan okunur. Ezine dışı profillerde işletme
tablosu önbellek anahtarına profil parmak izi eklenir.

## 2. A1 — Rüzgâr verisi: Open-Meteo ile CDS

Ezine ERA5 noktası (39,75; 26,25), 2014–2023, 87.648 saat. Open-Meteo `models=era5` aynı grid noktasını döndürdü.

| | Değer |
|---|---|
| 100 m hız: saatlik korelasyon / ortalama fark / RMSE | 0,9999 / −0,0004 m/s / 0,048 m/s |
| 10 m hız: korelasyon / ortalama fark | 0,9999 / −0,0004 m/s |
| Sıcaklık / yüzey basıncı farkı | −0,17 K / −3,4 hPa (Open-Meteo yüksekliği farklı alıyor; yoğunlukta ~%0,3) |
| RES KF (v1 modeli, kalibre): CDS / Open-Meteo / fark | %37,68 / %37,61 / −0,07 puan (yıllık en büyük fark 0,09 puan) |

**Karar:** Open-Meteo ana kaynak.

**Kısıt:** Ücretsiz katman ticari olmayan kullanım içindir ve günde 10.000 çağrıyla sınırlıdır. 10 yıllık saatlik bir
sorgu ~260 çağrı sayılır. Streamlit Cloud'da tüm kullanıcılar aynı IP'yi paylaştığı için bu, günde ~38 yeni sahaya denk
gelir. Bu yüzden sorgular önbelleklenir (`data/raw/open_meteo/`), uygulamada da paylaşımlı önbellek gerekecek (Faz C).

**Yedek: ön hesaplanmış Türkiye ERA5 grid veri seti (tasarım; indirme kullanıcı onayına bağlı)**
- Kapsam: Türkiye karasına değen 1.464 adet 0,25° ERA5 hücresi, 2014–2025 saatlik (105.192 saat).
- Nokta başına dosya:
  - 100 m hız: uint16, cm/s;
  - kayma üssü α: int8, ×200 (göbeğe taşıma için);
  - göbek yoğunluğu için ρ: int8, (ρ−1)×1000;
  - isteğe bağlı 100 m yön (uint8, 2°) ve 2 m sıcaklık.
- Boyut: sıkıştırılmış .npz nokta başına 0,24 MB (asgari) / 0,37 MB (yön + sıcaklık). Toplam **0,35–0,54 GB**: Hugging
  Face veri deposunda ücretsiz barındırılabilir.
- Üretim: CDS ile ~75 s/hücre, 4 paralel ≈ 7–8 saat.
- Lisans: C3S CC-BY, "Contains modified Copernicus …" atfıyla.

## 3. A2 — Global Wind Atlas ve GWA düzeltmesi

- GWA 3 Türkiye rasterleri (100 m ortalama hız, Weibull A ve k; 250 m) 4 × 4 blokla ~1 km'ye indirgendi.
  Blok içi **en yüksek** hız ayrı katman olarak tutuldu, çünkü blok ortalaması sırt tepelerini yumuşatır.
- **GWA düzeltmesi:** c = GWA 100 m ortalaması / ERA5 100 m ortalaması (aynı nokta, sınır 0,5–3,2). Saatlik ERA5 hızı c ile
  ölçeklenir. Ortalama düzelir; gün içi ve mevsimsel şekil düzelmez.
- **Karmaşık arazide fark neden büyür?**
  - ERA5, ~25 × 28 km'lik bir hücrenin alan ortalamasıdır. Model orografisi bu ölçekte yumuşatılmıştır: sırtlar alçak,
    vadiler sığdır, pürüzlülük hücre ortalamasıdır.
  - GWA ise mezo ölçek modeli WAsP ile 250 m'ye indirger. Böylece tepe üstü hızlanmayı, pürüzlülük geçişlerini ve
    vadilerde yavaşlamayı içerir.
  - Türbinler bilerek sırtlara kurulur. Hücre ortalaması bu noktaların hızını sistematik olarak düşük gösterir.
  - Sonuç: santral noktalarında GWA/ERA5 oranı kıyı ve düzlükte ~1,1–1,4, iç ve dağlık kesimde 2–3'tür.

## 4. A3 — Türkiye RES kalibrasyon atlası

**Konum kaynağı:** OpenStreetMap (186 RES, ODbL). GEM tracker CC BY 4.0, ama indirmesi kişisel bilgili form istiyor;
kullanıcı indirirse eşleştirmeye eklenecek.

**Eşleştirme** (`src/v2_A3_santral_eslestirme.py`):
- Yöntem: ad normalizasyonu + difflib benzerliği + ortak kelime oranı.
- Sonuç: **120 eşleşme** (113 otomatik: puan ≥ 0,90 ve ikinci adaydan ≥ 0,05 farklı; 7 manuel kabul).
- 15 kayıt reddedildi: belirsiz çoklu aday (Karadağ, Urla, Mordoğan, Seferihisar, Kıyıköy), yanlış aday, yinelenen
  OSM kaydı. 51 kayıt eşleşmedi.
- Manuel kararlar: `data/atlas/eslestirme_manuel.csv`. Eşleşme kalitesi ayrıca OSM–EPİAŞ kapasite oranıyla sınanır
  (medyan 1,04).

**Kalibrasyon** (`src/atlas/kalibrasyon.py`; v1 Ezine yöntemi):
- Vekil türbin: tüm santrallerde ortak E-92/2350, 80 m. Bu, k değerlerini karşılaştırılabilir kılar.
- Gözlenen KF: kapasite artırımlarına göre yıllık kapasite (%99,9 yüzdelik); ≥ 48 saatlik duruşlar hariç.
- Veri: 2014–2025 (ERA5 CDS, santral hücresi).
- Katsayılar: sabit k ve ay × saat (TSİ) matrisi.
- Arama aralığı: Türkiye genelinde k 3'e kadar çıktığı için sabit k 0,4–3,5'te aranır. Matris hücreleri ise santralin
  kendi k'sine göre görece aralıkta aranır (0,5k–1,8k). Mutlak geniş aralıkta zayıf rüzgârlı hücreler sınıra kaçıyordu;
  Enerjisa'da korelasyon 0,85'ten 0,64'e düşmüştü.

**Kalite sınıfı:**

| Sınıf | Koşullar |
|---|---|
| temiz | korelasyon ≥ 0,70; ≥ 3 veri yılı; talimat şüphesi ≤ %2; kapasite oranı 0,7–1,3; R = k / (GWA/ERA5) 0,75–1,35 |
| kullanılabilir | korelasyon ≥ 0,60; ≥ 2 yıl; talimat şüphesi ≤ %5; R 0,6–1,6 |

**Sonuç:** 120 eşleşmeden **90 santral kalibre edildi** (57 temiz, 33 kullanılabilir; OSM kurulu gücü 4.377 MW, 659
santral-yılı). Kalanlar: 19 veri yetersiz (< 2 yıl), 6 dışarıda (düşük korelasyon ya da talimat şüphesi), 5 k sınır dışı.

**Kontrol:** Enerjisa Çanakkale k = 1,068, korelasyon 0,845 (v1: 1,065). Sares 1,23, Çamseki 0,98, ikisi de temiz.

**Ürün:** `data/atlas/kalibrasyon_atlasi.csv` ve `kalibrasyon_matrisleri.npz`. Ham EPİAŞ verisi içermez; yalnız katsayılar
ve ay × saat ortalama KF vardır.

**k'nin Türkiye geneli dağılımı** (`outputs/v2/A3_k_haritasi.png`, `A3_k_bolgesel.csv`):

| | k medyanı (P10–P90) |
|---|---|
| Tümü (90) | 1,70 (1,11–2,66) |
| Kıyı < 20 km | 1,41 |
| Kıyıya yakın 20–80 km | 1,85 |
| İç > 80 km | 2,34 |
| Rakım < 300 m / 300–800 m / > 800 m | 1,29 / 1,59 / 2,35 |
| Arazi karmaşıklığı düşük / orta / yüksek | 1,42 / 1,75 / 2,20 |

Spearman korelasyonları:
- k ile GWA/ERA5: 0,90;
- k ile ERA5 100 m ortalaması: −0,96;
- k ile rakım: 0,70;
- k ile kıyıya uzaklık: 0,59;
- k ile karmaşıklık: 0,51.

**Yorum:**
- ERA5 iç ve dağlık Türkiye'de rüzgârı ciddi düşük gösteriyor. Santral noktasında ERA5 100 m ortalaması 2,7 m/s'ye kadar
  iniyor, gerçek ise ~7–8 m/s.
- k'nin büyük kısmını GWA açıklıyor. Arta kalan **R = k / (GWA/ERA5)** dar bir aralıkta: medyan 1,07 (P10–P90 0,91–1,30).
- Gün içi şekil düzeltmesi iç kesimde daha büyük. Matrisin gün içi genliği kıyıda ~0,3, iç ve yüksek kesimde ~0,7–0,8.
  Bu, ERA5'in kararlı gece sınır tabakasını ve dağ–vadi rüzgârlarını yakalayamamasıyla tutarlı.

## 5. A4 — Aktarım kuralı ve güven seviyeleri

**Ayrıştırma:** K_s = c_s · R_s (GWA düzeltmesi × artık). Yeni saha x için kural (`src/atlas/aktarim.py`):
- **Yüksek güven:** ≤ 30 km içinde **benzer** santral var. Benzerlik: rakım farkı ≤ 400 m, karmaşıklık farkı ≤ 0,04,
  aynı kıyı sınıfı. K_x = c_x · Σ w_i R_i (en fazla 3 santral, ters mesafe karesi ağırlığı). Komşuların gün içi şeklini
  ve artığını alır; ortalamayı sahanın kendi GWA düzeltmesiyle kurar.
- **Orta / düşük güven:** komşu yok. K_x = c_x · ulusal medyan R matrisi (GWA'nın sistematik düşük sapması + ortalama
  şekil). Arazi karmaşıklığı ≤ 0,083 (atlasın alt üçte biri) ise orta, değilse düşük.

**Birini dışarıda bırak çapraz doğrulaması** (90 santral; vekil türbin, santralin kendi ERA5 hücresi;
`outputs/v2/A4_capraz_dogrulama.csv`, `A4_ozet.csv`):

| Yöntem | KF ortalama hata [puan] | Medyan mutlak | RMSE | P90 mutlak | Gün içi RMSE (medyan) | Korelasyon |
|---|---|---|---|---|---|---|
| Düzeltmesiz ERA5 | −20,7 | 21,4 | 22,7 | 31,0 | 21,9 | 0,68 |
| Yalnız GWA (sabit c) | −3,6 | 5,7 | 8,1 | 13,7 | 8,9 | 0,76 |
| Doğrudan komşu k matrisi | −2,9 | 6,2 | 8,5 | 13,9 | 8,2 | 0,77 |
| **Kural (GWA ölçekli)** | **−0,7** | **4,8** | **7,8** | 14,4 | **6,3** | **0,78** |

**Kural nasıl kesinleşti:**
- İlk sürümde 30–80 km'deki komşular da kullanılıyordu. Bu santrallerde RMSE 9,1 çıktı; ulusal medyan artık (7,7) daha
  iyiydi. Uzak komşular bilgi değil gürültü katıyor, bu yüzden komşu yarıçapı 30 km'ye indirildi.
- Komşusuz durumda yalnız GWA kullanmak −4,6 puanlık sistematik sapma veriyordu. Ulusal medyan artık bunu −1,1'e indirdi.

**Güven seviyeleri** (`data/atlas/guven_seviyeleri.csv`; Faz B'de Monte Carlo RES model belirsizliği):

| Seviye | Tanım | Santral | KF medyan mutlak hata | RMSE | P90 | Göreli RMSE | Gün içi RMSE |
|---|---|---|---|---|---|---|---|
| Yüksek | Benzer santral ≤ 30 km | 36 | **2,4 puan** | 6,6 | 11,9 | %20 | 4,6 |
| Orta | Komşu yok, düz arazi | 14 | **5,9 puan** | 6,6 | 9,3 | %20 | 7,3 |
| Düşük | Komşu yok, karmaşık arazi | 40 | **7,2 puan** | 9,0 | 15,0 | %27 | 9,0 |

Yüksek seviyede RMSE'yi birkaç uç değer büyütüyor (medyan 2,4); Monte Carlo için medyan ve P90 birlikte kullanılmalı.

**Ezine özel karşılaştırma** (aynı E-141/120 m; `outputs/v2/A4_ezine_gwa.csv`, `A4_ezine_gwa_tamyil_milp.csv`,
`A4_ezine_atlas.csv`):

| | v1 kalibre (Enerjisa matrisi) | Yalnız GWA | Atlas kuralı (3 komşu, yüksek) |
|---|---|---|---|
| RES KF | %37,7 | %33,4 | %32,1 |
| Gün içi genlik | 21,5 puan | 7,3 puan | 8,6 puan |
| 14–18 TSİ KF | %48,3 | %32,6 | %36,5 |
| Tam yıl MILP tasarımı | RES 58,8 + BESS 40,0/70,0 | RES 58,8 + BESS 40,1/69,5 | — |
| Tam yıl MILP kesinti | %5,2 | %2,9 | — |
| Tam yıl MILP NPV tahmini | 26,4 M$ | 23,5 M$ | — |
| Yalnız RES 58,8 NPV @58 | −1,6 M$ | −6,2 M$ | — |
| RES 58,8 + 30/60 NPV @58 (SFK dahil) | 25,2 M$ | 21,1 M$ | — |

**Yorum:**
- Yalnız GWA düzeltmesi meltem kaynaklı öğleden sonra tepesini kaybediyor.
- Bunun sonucunda kesinti yarıya iniyor: tepe saatleri bağlantıyı daha az zorluyor.
- Ama ortalama üretim de düşüyor ve NPV ~3–5 M$ azalıyor. Tasarım (RES + ~40 MW batarya) değişmiyor; bataryanın değeri
  çoğunlukla SFK'dan geliyor.
- 24 temsilî günlük MILP bu karşılaştırmada ters işaretli sonuç verdi. Temsilî günler profile göre değişiyor; karşılaştırma
  tam yılla yapılmalı.
- Atlas kuralı Ezine'de v1'den düşük çıkıyor. Neden: v1, Enerjisa santralinin katsayısını ilçe koordinatına aynen
  taşımıştı. GWA'ya göre bu nokta santral sırtlarından daha az rüzgârlı (GWA/ERA5 noktada 0,98, Enerjisa'da 1,09). Üç
  santralin gün içi şekillerinin ortalanması da meltem genliğini sönümlüyor (Enerjisa matris genliği 0,52, Sares 0,09).
- Yani v1, sahayı fiilen "santral sırtı kadar iyi" varsaymıştı. v2'de bu varsayım görünür hale geliyor: kullanıcı santral
  benzeri bir sırt noktası seçerse sonuç v1'e yaklaşır.

## 5a. Ön adım güncellemesi (Ö3–Ö4): 250 m GWA, türbin yerleşimi ve güven seviyeleri

> **Güncellendi (Faz C ön adımı, §5b):** Bu bölümdeki güven seviyeleri ve yerleşim karşılaştırması ortak vekil türbinle
> (kapalı döngü) ölçülmüştü. Güncel tanım ve sayılar §5b'de.

> Bu bölüm §5'teki güven seviyesi tablosunun yerini alır.

**250 m GWA:**
- Türkiye 100 m ortalama hız rasterı (7.767 × 3.713, uint16 cm/s, deflate) Cloud Optimized GeoTIFF olarak **20,8 MB**.
- 1° × 1° karolara bölündüğünde toplam **17,1 MB** (145 karo, karo başına ~100–200 KB).
- Uygulama GDAL gerektirmeden yalnızca sahanın düştüğü karoları indiriyor (`src/kaynaklar/gwa250.py`, `hf_veri.py`).
- 1 km paketi yedek olarak kalıyor.

**Türbin yerleşimi** (`gwa250.turbin_yerlesimi`; Saha alanları `turbin_yerlesimi`, `yerlesim_yaricap_km`, varsayılan 2 km):
- Seçilen noktanın çevresinde, yarıçap içindeki en rüzgârlı 250 m hücreler türbin konumu kabul edilir.
- Türbinler birbirinden en az 500 m uzak (~4 rotor çapı); sayı ≈ 1,3 × bağlantı / türbin gücü.
- Sahanın GWA hızı bu hücrelerin ortalaması olur. Seçenek kapalıyken noktanın 250 m hücresi kullanılır.
- Atlas tarafında santrallerin c'si de aynı yöntemle hesaplanır: kurulu güç / 3 MW türbin, 3 km yarıçap.
- **Modellenmeyenler:** iz (wake) kayıpları (yalnız toplam kayıp oranıyla), erişim yolu ve eğim, arazi kullanımı ve mülkiyet,
  koruma alanları, izinler, hücre içi türbulans ve yükler. Sonuç "uygun bir sırt varsa" potansiyelidir, mikro yerleşim
  değildir.

**Çapraz doğrulama (GWA modu × yöntem, 90 santral, KF puanı):**

| GWA modu | Yöntem | Ort. hata | Medyan mutlak | RMSE | P90 mutlak | Gün içi RMSE |
|---|---|---|---|---|---|---|
| 1 km nokta | GWA ölçekli kural | −0,7 | 4,8 | 7,8 | 14,4 | 6,3 |
| 250 m nokta | GWA ölçekli kural | −0,8 | 5,4 | 9,0 | 16,3 | 7,5 |
| **Yerleşim** | **GWA ölçekli kural** | **−0,6** | **4,6** | **7,0** | **11,4** | **6,3** |
| Yerleşim | Yalnız GWA | +3,3 | 5,7 | 7,7 | 12,0 | 8,6 |
| Yerleşim | Doğrudan komşu | +1,4 | 5,5 | 7,8 | 12,8 | 7,8 |

**Yorum:**
- Yerleşim hatayı azaltıyor: RMSE 7,8 → 7,0, P90 14,4 → 11,4.
- 250 m tek nokta, 1 km'den bile kötü. OSM koordinatı santral poligonunun merkezi; çoğu zaman sırtın kendisi değil, yamaç
  ya da vadi hücresine düşüyor.
- Bu, santrallerin sırtlarda olduğu yorumunu destekliyor. Sabit kuralın varsayılanı `gwa_modu = yerlesim` yapıldı.
- Yerleşimle ulusal medyan artık R 0,92'ye iniyor: seçilen en iyi hücreler santrallerin ortalama türbin konumundan daha
  rüzgârlı. Saha tarafı da aynı yöntemle hesaplandığı için bu iç tutarlılığı bozmuyor.

**Ö4 — Güven seviyelerinin yeniden tanımı:**
- Eski tanımda "yüksek" seviyenin P90'ı (11,9) "orta"nınkinden (9,3) kötüydü.
- Kuyruk incelemesi: yüksek seviyedeki en kötü santral Söke RES (−20 puan), komşusu 26 km uzakta ve 200 m rakım farkında.
  Diğer kuyruk santralleri 12–29 km mesafede.
- Komşusuz santrallerde hatayı **arazi karmaşıklığı ayırt etmiyor** (Spearman 0,01). Eski karmaşıklık tabanlı orta/düşük
  ayrımının dayanağı olmadığı için kaldırıldı.
- Denenen dört tanım arasında (mesafe; rakım farkı; ikisi birlikte; komşu sayısı) hem medyanda hem P90'da en net sıralanan,
  mesafe tabanlı tanım oldu.

| Seviye | Tanım | Santral | Medyan mutlak hata [puan] (%90 GA) | P90 mutlak hata (%90 GA) | RMSE | Göreli RMSE | Gün içi RMSE |
|---|---|---|---|---|---|---|---|
| **Yüksek** | Benzer santral ≤ 15 km | 28 | **2,1** (1,7–3,7) | **7,5** (4,4–8,3) | 4,1 | %12 | 4,2 |
| **Orta** | En yakın benzer santral 15–30 km | 8 | **5,2** (4,0–7,9) | **11,8** (6,0–20,4) | 8,9 | %27 | 7,0 |
| **Düşük** | 30 km içinde benzer santral yok | 54 | **5,9** (4,7–7,1) | **13,6** (10,7–15,0) | 7,8 | %24 | 7,6 |

- GA: 4.000 örnekli bootstrap; `outputs/v2/A4_guven_bootstrap.csv`, `data/atlas/guven_seviyeleri.csv`.
- Orta seviyenin örneklemi küçük (n = 8); P90 aralığı çok geniş. Seviyeler nokta tahminlerinde sıralı ama orta ile düşüğün
  medyan aralıkları örtüşüyor.
- Monte Carlo'da her seviyenin medyan ve P90 hatası birlikte kullanılacak (Faz B).

**Ezine (Ö3):** v1 kalibre KF %37,7 (E-141/120 m; `outputs/v2/O3_ezine_yerlesim.csv`).

| | Yerleşim kapalı (250 m nokta) | Yerleşim 2 km | Yerleşim 3 km |
|---|---|---|---|
| GWA hızı | 6,44 m/s | 6,98 m/s | 7,18 m/s |
| Yalnız GWA düzeltmesi | %32,4 (−5,3) | **%37,1 (−0,6)** | %38,7 (+1,0) |
| Atlas kuralı (3 komşu, yüksek) | %30,2 (−7,5) | %30,2 (−7,5) | %31,7 (−5,9) |

**Yorum:**
- Yerleşim açıkken yalnız GWA düzeltmesi v1'e 0,6 puan yaklaşıyor. v1'in örtük varsayımı ("saha, santral sırtları kadar
  rüzgârlı") yerleşimle büyük ölçüde açıklanıyor.
- Atlas kuralı ise daha düşük, çünkü komşu santraller GWA'nın sırt potansiyelinin altında üretiyor. Yerleşimle artık R
  değerleri: Enerjisa 0,95, Çamseki 0,92, Sares 0,84.
- Atlas, Ezine'de "yakın santraller gibi üretir" diyor; v1 ise Enerjisa'nın katsayısını aynen taşımıştı. İkisi arasındaki
  ~7 puan, Ezine sahası için gerçek bir belirsizlik. Yüksek güvenin P90'ı (7,5 puan) bu farkı kapsıyor.

## 5b. Faz C ön adımı: atlas aktarımı kontrolü ve düzeltme

**Şüphe (kullanıcı):**
- Ezine'de atlas KF'si %30,2. Bu, Enerjisa Çanakkale RES'in gözlenen KF'siyle aynı. Ancak o santral 80 m'de E-92 kullanıyor, tasarım ise 120 m'de E-141.
- Türbin yerleşimi açılınca GWA hızı 6,44'ten 6,98 m/s'ye çıkıyor, KF ise değişmiyor.
- Aktarım hız yerine doğrudan KF üzerinden yapılıyor olabilir.

**Kontrol** (`src/v2_C0_ezine_kontrol.py`, aynı Open-Meteo ERA5 verisi):

1. **Aktarım hız uzayında; KF kopyalanmıyor.**
   - K matrisi, sahanın ERA5 hızının göbek yüksekliğine taşınmış hâlini çarpar. Sonra hız seçilen türbinin güç eğrisinden geçer (`ruzgar.ruzgar_kapasite_faktoru`).
   - Aynı atlas K'sı (ort. 0,927) E-92 / 80 m ile %22,7, E-141 / 120 m ile %30,2 veriyor.
   - %30,2'nin Enerjisa'nın gözlenen %30,4'üne yakın olması tesadüf.
   - Şüphenin bu kısmı yanlış.
2. **Hata 1 — yerleşim oranda yok oluyordu.**
   - Santral düzeltmesi c_i = GWA_i / ERA5_i, sahanın GWA moduyla birlikte hesaplanıyordu (`santral_c(gmod)`).
   - Yerleşim açılınca hem sahanın hem santrallerin GWA'sı yükseliyor, K = c_saha × R değişmiyordu: Ezine'de c +%8,4, K 0,927 → 0,928.
   - Doğrusu: santralin gözlenen performansı türbinlerinin durduğu yerin rüzgârını yansıtır. c_i her zaman gerçek türbin konumlarından alınmalı, sahanın seçeneğinden bağımsız olmalı.
3. **Hata 2 — vekil türbin.**
   - Santral k matrisleri tüm santraller için ortak bir vekille (E-92/2350, 80 m) çıkarılıyordu.
   - Eski/küçük türbinli bir santralin düşük verimi "düşük rüzgâr" olarak k'ya giriyor ve yeni sahaya taşınıyordu.
   - Önceki çapraz doğrulama bunu göremezdi: kalibrasyon ve test aynı vekille yapıldığı için hata kendini götürüyordu (kapalı döngü).
4. **Kesinti ve kullanılabilirlik.**
   - Talimat (YAT) ya da arıza şüpheli saatler (model KF > 0,5 iken gözlenen < 0,1 × model) k uydurmasına giriyordu.
   - Sistem kesintisi finans modelinde ayrıca uygulandığı için bu bir çift sayımdı.

**Düzeltmeler:**

| Düzeltme | Uygulama |
|---|---|
| **Santral türbinleri** | `src/v2_C0_santral_turbinleri.py`. OSM'den 4.122 rüzgâr türbini düğümü alındı. Santral ilişki üyeliği ve poligonuyla 95/96 santrale atandı. Birim güç OSM etiketinden (26 santral), yoksa EPİAŞ kapasitesi / türbin adedinden (65); makul dışıysa (> 4,5 MW, eksik haritalama) etiketli medyandan (5). Kütüphane eşlemesi `src/atlas/turbinler.py`: özgül güç (rotor varsa ondan, yoksa güç sınıfından) ve birim güce en yakın windpowerlib eğrisi; üretici biliniyorsa ve özgül güç ±%16 içindeyse onun türbini. Göbek OSM'den ya da sınıftan (`config v2.santral_turbin`). |
| **Kesik eğri** | Kütüphanedeki V90/2000 güç eğrisi 16,5 m/s'de bitiyor (kesme hızı 25). Rüzgârlı santrallerde k aranan aralığın dışına çıkıyordu. 20 m/s'den önce biten eğriler aday listesinden çıkarıldı (V90/2000/GS kullanılıyor). |
| **Kalibrasyon** | Santralin kendi türbini ve göbeğiyle; şüpheli saatler iki geçişte çıkarıldı (`kalibre_et`). Kullanılabilir santral sayısı yine 90. |
| **c_i** | Gerçek türbin konumlarındaki 250 m GWA ortalaması / ERA5 (`gwa_turbin`, `c_turbin` sütunları; `santral_c()` mod parametresi kaldırıldı). |
| **Çapraz doğrulama** | Dışarıda bırakılan santral **kendi türbini ve göbeğiyle** tahmin ediliyor. Saha GWA'sı üç şekilde: nokta (santral noktasındaki 250 m hücre), yerleşim (2 km, santralin türbin adedi kadar en rüzgârlı hücre), gerçek türbin konumları (kâhin, alt sınır). |

**Ezine önce/sonra** (E-141/4200 @ 120 m, aynı veri):

| Durum | GWA [m/s] | K ort. önce → sonra | KF önce → sonra |
|---|---|---|---|
| Yerleşim kapalı (nokta) | 6,44 | 0,927 → 0,914 | %30,2 → **%29,3** |
| Yerleşim 2 km | 6,98 | 0,928 → 0,991 | %30,2 → **%33,9** |
| Yerleşim 3 km | 7,18 | — → 1,019 | — → **%35,5** |
| v1 kalibre matris | — | 1,074 | %37,8 (v1 nihai %37,7) |

**v1 ile kalan fark** (2 km'de 3,9 puan) bir hata değil:
- v1 sahayı komşu santrallerin üzerindeymiş gibi doğrudan kalibre ediyordu.
- Atlas, seçilen noktanın 2 km içindeki en iyi hücrelerinin daha az rüzgârlı olduğunu görüyor:
  - Enerjisa türbinlerinden %2 daha az (7,12 m/s);
  - Sares türbinlerinden %18 daha az (8,56 m/s).
- 3 km'lik yerleşimde fark 2,3 puana iniyor.
- Komşu santrallerin R değerleri: Sares 0,93, Enerjisa 1,01, Çamseki 0,92 (ulusal medyan 0,96).

**Çapraz doğrulama önce/sonra** (GWA ölçekli kural, 90 santral, mutlak KF hatası, puan):

| Saha GWA modu | Önce (vekil, kapalı döngü): RMSE / P90 | Sonra (kendi türbini): RMSE / P90 / ort. hata |
|---|---|---|
| Nokta 250 m | 9,00 / 16,3 | 9,18 / 14,8 / −4,1 |
| **Yerleşim 2 km** | 6,99 / 11,4 | **7,17 / 11,4 / −1,1** |
| Gerçek türbin konumları (kâhin) | — | 6,66 / 10,5 / −0,9 |

**Varsayılan türbin yerleşimi: açık.**
- Yerleşim, noktaya göre RMSE'yi 2,0 puan, yanlılığı 3,1 puan düşürüyor.
- Kâhin alt sınırına (gerçek türbin konumları) 0,5 puan yaklaşıyor.
- Sezgisi: geliştiriciler türbinleri sırtlara koyar; noktanın kendisi genellikle sırtta değildir.

**Güven seviyeleri yeniden tanımlandı.** "Orta" seviye (komşu 15–30 km) gerçek aktarım altında n = 9 ile yüksekten iyi çıktı (medyan 2,1 vs 4,1; bootstrap GA 1,6–7,5). Denenen hiçbir mesafe eşiği medyanda sıralamayı korumadı. İki seviye:

| Seviye | Tanım | n | Medyan (GA) | P90 (GA) | Ort. hata |
|---|---|---|---|---|---|
| Yüksek | benzer kalibre santral ≤ 30 km | 37 | 3,8 (2,9–6,9) | 9,8 (8,0–12,8) | −1,3 |
| Düşük | yok (GWA × ulusal medyan R) | 53 | 5,6 (4,6–7,8) | 11,5 (10,6–12,6) | −0,8 |

**Eski "yüksek" seviyenin daha iyi görünmesinin nedeni.** Eski yüksek seviyenin medyanı 2,1 puandı. Bu kapalı döngüden geliyordu: vekil türbin hatası hem kalibrasyonda hem testte vardı ve birbirini götürüyordu. Yeni sayılar, farklı türbine aktarımın gerçek hatasıdır.

**Rakım.** Uygulama çalışırken Open-Meteo'ya bağlanmamak için 0,02°'lik Copernicus DEM GLO-90 ızgarası kullanılıyor (`src/v2_C1_rakim_grid.py`). API değerlerine göre medyan fark 39 m, P90 100 m; benzerlik eşiği 400 m.

**Yeniden üretilen tablolar** (beş saha, tutarlılık): bkz. `docs/v2_C_arayuz.md §2`.

## 6. A5 — Sahaya bağlı parametreler

- **İl/ilçe:** geoBoundaries ilçe sınırları 1 km ızgaraya rasterize edildi (973 ilçe, 81 il). Nokta → il/ilçe ve "Türkiye
  karası mı" kontrolü (deniz, ada dışı ve komşu ülke noktaları reddedilir).
- **TEİAŞ 2026:** 15 tarife bölgesi, üretim sistem kullanım bedeli 123.430 (1. bölge, Trakya) – 273.224 TL/MW-yıl (15. bölge,
  Van/Muş). Enerji bileşeni tüm bölgelerde 170,39 TL/MWh. 45 TL/USD ile reel USD'ye çevrilir. Ezine (2. bölge)
  3.471,9 USD/MW-yıl; v1'in yuvarlanmış 3.470 değeri regresyonda korunur.
- **Türbin seçimi** (config `v2.turbin_secimi`), GWA 100 m ortalamasına göre:
  - < 6,5 m/s: E-141/4200 @135 m;
  - 6,5–7,5 m/s: E-141 @120 m;
  - 7,5–8,5 m/s: E-126/4200 @105 m;
  - ≥ 8,5 m/s: V112/3450 @94 m.
  - Gerekçe: düşük rüzgârda büyük rotor ve düşük özgül güç (~269 W/m²), yüksek rüzgârda IEC I sınıfı (~350 W/m²).
  - Sınırlama: windpowerlib'de güncel 5–7 MW platformlar yok.
- **İlçe adayları:** İlçe içinde GWA ortalaması en yüksek, birbirinden ≥ 3 km uzak 5 hücre (ilçe merkezi değil).
- **Arazi kısıtları:** Kullanıcı girdisi (azami RES/GES MW). Otomatik arazi kullanımı ve koruma alanı analizi **kapsam
  dışı** (sınırlama).

## 7. A6 — Ulusal piyasa paketi

`src/v2_A6_piyasa_paketi.py` (`--guncelle` ile önce EPİAŞ'tan yeni aylar çekilir) → `data/atlas/piyasa/` (2,9 MB):

| Dosya | İçerik |
|---|---|
| `saatlik.parquet` | PTF TL/USD 2014–Eylül 2026; ulusal rüzgâr ve güneş üretimi; SFK/PFK ve SMF (2023+) |
| `yillik.csv` | Yıllık PTF, rüzgâr/güneş yakalanma oranı, kurulu güç (TEİAŞ) |
| `parametreler.json` | Fiyat senaryoları, Monte Carlo, stres testi, gelir yığını, YEKDEM, kesinti, ortak sürücü |
| `ozet.json` | Kapsam, son veri tarihi, atıf ve koşul |

EPİAŞ koşulu: kaynak gösterilerek çoğaltma serbest. Santral bazında ham üretim pakette yok.

## 8. A7 — Genelleştirilmiş hattın doğrulanması

**Ezine regresyonu** (`tests/test_v2_regresyon.py`; kalibre mod: CDS ERA5 + v1 matrisi):
- Sahaya özgü config, v1 config'inin tüm anahtarlarıyla aynı.
- Profil v1'le birebir: 87.648 saat, GES ve RES KF farkı < 1e-12.
- Yalnız RES 58,8 NPV'si iki `Ortam`'da aynı (fark < 1 USD).
- Kapasite MILP'i (24 gün; yan hizmet + dengesizlik + YEK-G) aynı tasarım ve amaç değerini veriyor.
- 4 testin hepsi geçti.

### 8.1 İki bölgede uçtan uca çalıştırma

Kalibre santrallerin 12–25 km uzağında, santral üstünde olmayan iki nokta seçildi (`src/v2_A7_bolge_dogrulama.py`,
`outputs/v2/A7_bolge_dogrulama.csv`). Hat: Open-Meteo ERA5 + atlas kuralı → profil → kapasite MILP'i (24 gün) → yalnız RES NPV.

| | Sivas-Gürün (iç Anadolu, 1.665 m) | Balıkesir-Susurluk (Marmara içi) |
|---|---|---|
| Tarife bölgesi | 11 (252.829 TL/MW-yıl) | 2 (156.234 TL/MW-yıl) |
| GWA 100 m / GWA düzeltmesi c | 6,97 m/s / 1,56 | 6,89 m/s / 1,58 |
| Güven / komşular | yüksek / Kangal RES (14 km) | yüksek / Susurluk, Balıkesir, Şamlı RES (12–25 km) |
| Türbin (otomatik) | E-141/4200 @120 m | E-141/4200 @120 m |
| RES KF (E-141) / GES KF | %35,8 / %20,6 | %39,9 / %19,1 |
| **Kontrol: vekil türbinle model KF / komşuların gözlenen KF'si** | **%27,0 / %30,1 (−3,1 puan)** | **%31,4 / %34,4 (−2,9 puan)** |
| MILP tasarımı | RES 58,8 + BESS 40, GES 0 | RES 58,8 + BESS 41, GES 0 |
| MILP kesinti | %2,9 | %1,4 |
| Yalnız RES 46,2 MW NPV @58 $/MWh | −3,9 M$ | +4,4 M$ |

**Makullük:**
- Vekil türbinle hesaplanan model KF'si, komşuların gözlenen KF'sinden ~3 puan düşük. Bu, yüksek güvenin tipik hatası
  (medyan 2,4, P90 11,9 puan) içinde ve GWA'ya göre beklenen yönde: noktalar santral sırtlarından biraz daha az rüzgârlı.
- E-141/120 m ile KF'nin ~5 puan yükselmesi büyük rotorun beklenen etkisi.
- İki sahada GES yine elenmiş; batarya yine SFK sınırında (~40 MW).
- Gürün'ün daha düşük değeri, rüzgârdan çok tarife bölgesinden geliyor: 11. bölge üretim bedeli 2. bölgenin 1,6 katı.

## 9. Sınırlamalar

- **Vekil türbin:** k, ERA5 sapmasıyla birlikte gerçek türbin ve göbek farkını da taşır. Santral türbin bilgisi yok.
  Aktarımda aynı vekille kurulduğu için hatalar kısmen birbirini götürür, ama yeni nesil büyük rotorlarda yanlılık olabilir.
- **OSM kapsamı ve doğruluğu:** 186 santralin 51'i eşleşmedi. OSM kurulu güçleri bazen güncel değil (kapasite oranı > 1,3).
- **Talimat ve kesinti:** 2024 sonrası sistem kaynaklı kesinti gözlenen KF'yi düşürür. Talimat şüphesi bayrağı ile
  sınırlandı ama tamamen ayrıştırılamaz.
- **Güven seviyeleri:** Vekil türbin ve santral noktası için ölçüldü. Farklı türbin ve göbekte hata dağılımı değişebilir.
- **GWA dönemi:** GWA 3 dönemi (2008–2017) ile ERA5 dönemi (2014–2025) farklı. Uzun dönem ortalaması varsayılıyor.
- **Open-Meteo kotası:** paylaşımlı IP'de günde ~38 yeni saha. Önbellek ve gerekirse yedek grid gerekli.
- **Arazi:** Arazi kullanımı ve koruma alanları otomatik değil; kullanıcı girdisi.
