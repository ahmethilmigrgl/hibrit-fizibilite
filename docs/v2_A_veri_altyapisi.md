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
