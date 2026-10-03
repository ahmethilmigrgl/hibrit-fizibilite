# Aşama 2 — Piyasa Analizi ve Rüzgâr Kalibrasyonu

**Amaç:** (1) Ezine'de üretilecek güneş, rüzgâr ve hibrit enerjinin piyasada hangi fiyatı
"yakaladığını" ve bunun zamanla nasıl değiştiğini ölçmek; (2) bataryanın değerini gösterecek ön
göstergeleri çıkarmak; (3) Aşama 1'deki ERA5 rüzgâr modelini Ezine'deki gerçek santral üretimiyle
kalibre etmek.

| | |
|---|---|
| Kodlar | `src/piyasa/epias.py` (API istemcisi), `src/piyasa/veri.py` (çekme + UTC dönüşümü), `src/piyasa/analiz.py` (yakalanan fiyat, batarya göstergeleri) |
| Çalıştırma | `src/02_piyasa_verisi.py` → `src/02_ruzgar_kalibrasyonu.py` → `src/01_uretim_profilleri.py` → `src/02_piyasa_analizi.py` |
| İşlenmiş veri | `data/processed/ptf_2014_guncel.parquet`, `uretim_turkiye_2014_guncel.parquet`, `ezine_res_santralleri.parquet`, `auf_2022_2023.parquet` |
| Çıktılar | `outputs/02_piyasa/` (grafikler ve CSV tabloları) |

---

## 1. Veri kaynakları

| Veri | Kaynak | Dönem | Not |
|---|---|---|---|
| Saatlik PTF (TL, USD, EUR) | EPİAŞ Şeffaflık Platformu, `POST /v1/markets/dam/data/mcp` | 2014-01 → 2026-09 | USD/EUR karşılığını EPİAŞ, TCMB gösterge döviz alış kuruyla hesaplıyor; ayrı bir kur serisi gerekmedi |
| Kaynak bazında saatlik gerçek zamanlı üretim (Türkiye) | `POST /v1/generation/data/realtime-generation` | 2014-01 → 2026-09 | Rüzgâr, güneş, toplam ve diğer kaynaklar |
| Santral bazında saatlik üretim | Aynı servis, `powerPlantId` ile | 2014-01 → 2026-09 | Ezine çevresinde 5 RES |
| Santral listesi | `GET /v1/generation/data/powerplant-list` | — | 1.830 santral, 307 RES |
| Azami Uzlaştırma Fiyatı (AUF) ve GÖP azami fiyatı | `POST /v1/markets/data/maximum-settlement-price` | 2022-04 → 2023-09 | Kaynak bazında aylık |
| YEKDEM kurulu güç | `POST /v1/renewables/data/new-installed-capacity` | — | Lisanslı/lisanssız kırılımı |
| Türkiye yıl sonu kurulu güç | TEİAŞ, IRENA, TÜREB, GENSED (`config.yaml → kurulu_guc_turkiye`) | 2014–2025 | Yalnızca trend yorumu için |

**API ayrıntıları (dokümantasyondan ve deneyerek doğrulandı, 2026-10-03):**
- **Kimlik doğrulama:** `POST https://giris.epias.com.tr/cas/v1/tickets` (form: kullanıcı adı, şifre) → `TGT-...` bileti.
  - Bilet her isteğe `TGT` başlığıyla eklenir ve 2 saat geçerlidir.
  - İstemci bileti 100 dakikada bir ya da 401/403 alınca otomatik yeniler.
  - Kimlik bilgileri yalnızca `.env`'de tutulur. EPİAŞ hata yanıtları kullanıcı adı ve IP içerdiği için istemci hata gövdesini olduğu gibi yazdırmaz, yalnızca hata mesajını gösterir.
- **Tarih aralığı limitleri:** PTF'de 1 yıllık istek sorunsuz çalıştı; üretim ve AUF servislerinde en fazla 3 ay ("tanımlanmış aralıktan (3 MONTH) fazla olamaz").
- **İstek düzeni:** İstekler yıllık ya da çeyreklik parçalara bölündü, aralarına 0,4 s bekleme kondu. 429/5xx yanıtlarında üstel bekleme ile yeniden deneniyor.
- **Önbellek:** Ham yanıtlar `data/raw/epias/<servis>/` altında önbelleklenir; tekrar çalıştırmada indirme yapılmaz.
- **Tuzak:** Santral filtresinin alan adı `powerPlantId`. Yanlış yazılırsa (`powerplantId`) API hata vermez, sessizce **Türkiye toplamını** döndürür.

## 2. Zaman: Türkiye yerel saatinden UTC'ye

EPİAŞ zaman damgaları yerel saattedir ve ofset içerir (ör. `2015-03-29T04:00:00+03:00`). Türkiye
**7 Eylül 2016'ya kadar yaz saati uyguluyordu** (kış UTC+2, yaz UTC+3), sonra sabit UTC+3'e geçti.
EPİAŞ her güne 24 satır verdiği için geçiş günlerinde şu durumlar oluşuyor:

| Durum | Ne oluyor | Nasıl ele alındı |
|---|---|---|
| İlkbahar, saat ileri (23 saatlik gün; ör. 29.03.2015, 27.03.2016) | Yaşanmamış 03:00 için **fiyatı/üretimi 0 olan yer tutucu satır** var; `date` alanı 04:00 ile çakışıyor | `hour` etiketi ile `date`'in yerel saati uyuşmayan satır atılır. Atılmasa sahte bir "sıfır fiyatlı saat" olurdu |
| Sonbahar, saat geri (25 saatlik gün; ör. 26.10.2014, 08.11.2015) | Yalnız 24 satır var; iki kez yaşanan saatin **ilki eksik** | UTC'ye çevrilince oluşan tek saatlik boşluk doğrusal enterpolasyonla doldurulur, `dolduruldu=True` diye işaretlenir |
| Diğer tüm saatler | `date` alanındaki ofset ile doğrudan UTC'ye çevrilir | — |

Sonuç: PTF'de 111.743 UTC saati, yalnızca 2 saat dolduruldu (2014 ve 2015 sonbahar geçişleri;
2016'da geri dönüş yapılmadı). Üretim verisinde 3 saat dolduruldu.

> 2015'te Türkiye yaz saati bitişini seçim nedeniyle 25 Ekim'den 8 Kasım'a ertelemişti; veri bunu
> doğru yansıtıyor. Bu yüzden dönüşüm sabit kurallarla değil, kaydın kendi ofsetiyle yapıldı.

**Dönem hizalaması:** EPİAŞ'ın "12:00" değeri 12:00–13:00 yerel saat dilimini kapsıyor (dönem başı
etiket). Bunu ulusal güneş üretiminin tepe saatiyle doğruladım: tepe UTC 09:00 dilimine düşüyor,
Türkiye'nin ağırlık merkezinde (~34°D) güneş öğlesi ise ≈ 09:44 UTC. ERA5 ise saat başındaki anlık
değeri verir. Bu yüzden saatlik karşılaştırmalarda ERA5 bir saat ileri kaydırılarak (−1) hizalandı.
Yıllık ve aylık toplamlar bundan etkilenmez.

## 3. Fiyat verisi kalitesi ve fiyat limitleri

**Genel kontroller:**
- Eksik ya da tekrar eden saat yok (dönüşüm sonrası). USD karşılığı her saat mevcut.
- **Negatif fiyat yok.** GÖP'te asgari limit 0 TL/MWh.

**Sıfır fiyatlı saat sayısı:** Yıllara göre çok değişken.

| Yıl | Sıfır fiyatlı saat | Yıl | Sıfır fiyatlı saat |
|---|---|---|---|
| 2015 | 42 | 2023 | 10 |
| 2016 | 91 | 2024 | 4 |
| 2019 | 52 | 2025 | 42 |
| 2020 | 34 | **2026 (Ocak–Eylül)** | **395** |
| 2022 | 5 | | |

2015–2016 ve 2019–2020'de nedenler bol hidroloji ve düşük talepti. 2026'daki sıçrama ise bahar öğlelerindeki güneş fazlasından geliyor.

**Azami fiyat limitleri ve 2022'deki azami uzlaştırma fiyatı:**
- **Varsayılan limitler:** Asgari 0, azami 2.000 TL/MWh (DUY geçici md. 30). 6 Ocak – 1 Mart 2017 arasında geçici olarak 500 TL/MWh tavanı uygulandı ([Enerji Uzmanları Derneği](https://www.enerjiuzmanlari.org.tr/dergi/organize-toptan-elektrik-piyasalarinda-fiyat-limitleri/)).
- **2021 ortasından itibaren** azami limit aylık, geçmiş fiyat ortalamasına bağlı bir formülle belirlenmeye başlandı. Ekim 2021'den sonra kural "son 12 ay ağırlıklı ortalama PTF × 3, en fazla 2.000 TL" oldu ([kaynak](https://www.afaenerji.com/blog/2022/02/23/mart-2022-azami-fiyat-limiti-1745-tl-mwh/)).
  - Enflasyon hızlanınca bu limit **çok sık bağlayıcı** oldu: Temmuz 2021 – Mart 2022 arasında her ay **300–490 saat** fiyat tam limitteydi.
  - Bu dönemde fiyatın tepesi yapay olarak kırpıldı ve gün içi fiyat farkı ile yakalanma oranları bastırıldı.
- **GÖP azami fiyatı sonrasında da birkaç kez değişti** (EPİAŞ AUF servisinden ve veriden ampirik olarak):
  - 2022: Nisan 2.500 → Mayıs 2.750 → Haziran 3.200 → Temmuz 3.750 → Ağustos 4.000 → Eylül–Aralık 4.800 TL/MWh
  - 2023: Ocak 4.200 → Şubat 3.650 → Mart 3.050 → Nisan 2.600 → Temmuz–Aralık 2.700 TL/MWh
  - 2024: Temmuz'dan itibaren 3.000 TL/MWh
  - 2025: Nisan'dan itibaren 3.400 TL/MWh
  - 2026: Nisan'dan itibaren 4.500 TL/MWh
- **Azami Uzlaştırma Fiyatı (AUF), 1 Nisan 2022 – 30 Eylül 2023** ([EPDK](https://www.epdk.gov.tr/Detay/Icerik/2-12999/azami-uzlastirma-fiyat-mekanizmasi-icin-uzatma-ka), [AA](https://www.aa.com.tr/tr/ekonomi/epdk-azami-uzlastirma-fiyat-mekanizmasinin-uygulama-suresini-6-ay-uzatti/2859391)):
  - **PTF'yi değil, üreticinin eline geçen fiyatı** kaynak bazında sınırladı. Aradaki fark "kaynak bazında destekleme bedeli" olarak bir havuza aktarıldı ve doğalgaz gibi maliyeti yüksek santralleri desteklemek için kullanıldı.
  - Yenilenebilirler için aylık AUF, Nisan 2022'de 1.200 TL/MWh'tan Eylül 2023'te 2.278 TL/MWh'a çıktı.
  - Bu dönemdeki saatlerin **%74,8'inde PTF, yenilenebilir AUF'unun üstündeydi.**
  - **Sonuç:** 2022–2023 için PTF ile hesaplanan yakalanan fiyat, YEKDEM dışı bir RES/GES'in fiilen aldığı fiyatı ciddi biçimde abartır (bkz. 5.3).

## 4. Tanımlar ve para birimi yaklaşımı

- **Yakalanan fiyat** = Σ(üretim × fiyat) / Σ(üretim): üretim ağırlıklı ortalama fiyat.
- **Ortalama fiyat (baz yük)** = Σ fiyat / saat sayısı.
- **Yakalanma oranı** = yakalanan fiyat / ortalama fiyat. 1'in altındaysa santral ortalamanın altında satıyor demektir.
- **Dönemler** Türkiye yerel saatine göre (yıl ve ay) belirlenir.

**TL mi USD mi?** Ana anlatı **USD** ve **yakalanma oranı** üzerinden kuruldu:
- **TL yıllar arası kıyaslanamaz.** 2014'te 164 TL/MWh olan ortalama PTF, 2025'te 2.620 TL/MWh; bunun büyük kısmı enflasyon ve kur.
- **Yıllık TL yakalanma oranı da yanıltıcı.** TL tek bir yılın içinde bile değer kaybettiği için (2022'de >%70 enflasyon) yılın son aylarının saatleri nominal olarak pahalı görünür, yani oran mevsimsel olarak çarpılır.
- **Çözüm:** TL için yakalanma oranı önce **her ay için** hesaplanıp sonra üretim ağırlığıyla yıllığa toplandı. Bir ay içinde enflasyon etkisi küçük olduğu için bu yaklaşım enflasyondan büyük ölçüde arınmış olur.
- **Sonuç tutarlı:** Bu "TL, aylık bazda" oranlar USD oranlarına çok yakın çıkıyor (ör. 2023 GES: TL 0,951, USD 0,924; 2025 güneş Yol B: TL 0,833, USD 0,834).
- **USD de reel değil.** USD fiyatları nominal; ABD enflasyonu 2014–2026'da yaklaşık %40 olduğu için mutlak USD seviyeleri de reel olarak karşılaştırılmamalı. Oranlar bundan etkilenmez.

## 5. Bulgular

### 5.1 Yol A — Ezine'nin kendi profilleriyle (2014–2023, aynı yılın fiyatıyla)

> Bu bölümdeki tablolar **Aşama 2 (sabit k = 1,065)** değerleridir ve tarihsel kayıt olarak korunmuştur. GES değerleri revizyondan etkilenmedi. RES ve hibrit için revizyon sonrası değerler bölüm 6.5'te, tam tablolar `outputs/02_piyasa/yol_a_*.csv` dosyalarında (önceki sürüm `outputs/revizyon_oncesi/`).

Profiller kalibre edilmiş Aşama 1 profilleri; hibrit = 1 MW GES + 1 MW RES, 1 MW
bağlantı, satılan üretim (min(GES + RES, 1)).

| Yıl | Ort. PTF [USD/MWh] | GES oranı | RES oranı | Hibrit oranı |
|---|---|---|---|---|
| 2014 | 75,1 | 1,13 | 0,97 | 1,02 |
| 2015 | 51,1 | 1,16 | 0,97 | 1,04 |
| 2016 | 46,3 | **1,21** | 0,98 | 1,05 |
| 2017 | 45,0 | 1,15 | 0,98 | 1,04 |
| 2018 | 47,4 | 1,04 | 1,00 | 1,01 |
| 2019 | 46,0 | 1,01 | 0,99 | 1,00 |
| 2020 | 40,1 | 0,99 | 0,97 | 0,98 |
| 2021 | 55,6 | 1,01 | 0,99 | 1,00 |
| 2022 | 147,5 | 1,01 | 0,94 | 0,97 |
| 2023 | 96,6 | **0,92** | 0,96 | 0,96 |

**2024–2026 uzantısı:** Ezine profilleri 2023'te bittiği için en güncel fiyat yıllarına 10 hava
yılının her biri (yerel ay-gün-saat eşleşmesiyle) uygulanıp ortalaması alındı.
- **Bu yöntem RES'i olduğundan iyi gösteriyor.** Hava yılları karıştırılınca Ezine rüzgârı ile Türkiye rüzgârının eşzamanlılığı (rüzgârlı saatte fiyatın düşmesi) kayboluyor ve RES yakalanma oranı ~5 puan yüksek çıkıyor. 2021–2023'te iki yöntem kıyaslandı: GES için fark ≈ 0, RES için +0,05, hibrit için +0,03.
- **Bu fark "eşzamanlılık düzeltmesi" olarak düşüldü:**

| Fiyat yılı | Ort. PTF [USD/MWh] | GES oranı | RES oranı (düzeltilmiş) | Hibrit oranı (düzeltilmiş) | GES yakalanan [USD/MWh] | Hibrit yakalanan [USD/MWh] |
|---|---|---|---|---|---|---|
| 2024 | 68,1 | 0,90 | 0,96 | 0,95 | 61 | 65 |
| 2025 | 66,4 | **0,82** | 0,97 | 0,93 | 55 | 62 |
| 2026 (Oca–Eyl) | 43,1 | **0,71** | 1,04 | 0,94 | 31 | 40 |

**Yorum:**
- **GES:** 2014–2017'de güneş **ortalamanın %13–21 üstünde** satıyordu. O yıllarda Türkiye'de neredeyse hiç GES yoktu ve öğle saatleri talebin tepesi olduğu için pahalıydı. 2018'den sonra oran 1'e indi, 2023'ten itibaren hızla düştü: 2025'te 0,82, 2026'nın ilk 9 ayında 0,71. Bu, kurulu güneş kapasitesinin kendi saatlerindeki fiyatı düşürmesi, yani **kanibalizasyon**.
- **RES:** Ezine rüzgârı istikrarlı biçimde ortalamanın biraz altında satıyor (0,94–1,00). Rüzgârlı saatlerde Türkiye geneli rüzgâr da yüksek olduğu için fiyat bir miktar düşüyor; bu, rüzgârın kendi küçük kanibalizasyonu. 2026'da RES'in 1'in üstüne çıkması, rüzgârın güneşin olmadığı saatlerde (akşam, gece, kış) üretmesinin artık **değerli** hâle gelmesi.
- **Hibrit:** Satılan üretim iki kaynağın karışımı olduğu için güneş kanibalizasyonunu kısmen telafi ediyor: 2025'te GES 0,82'ye karşı hibrit 0,93. Şebeke sınırı da en kalabalık (en ucuz) öğle saatlerinde üretimi kestiği için hibritin oranı basit ortalamadan biraz daha iyi.

### 5.2 Yol B — Türkiye geneli üretim şekilleriyle (piyasa trendi)

| Yıl | Ort. PTF [USD/MWh] | Rüzgâr oranı | Güneş oranı | Yıl sonu kurulu güneş [GW] |
|---|---|---|---|---|
| 2014 | 75,1 | 0,98 | — | 0,04 |
| 2016 | 46,3 | 1,00 | — | 0,8 |
| 2018 | 47,4 | 0,99 | — | 5,1 |
| 2019 | 46,0 | 1,00 | 1,02 | 6,0 |
| 2020 | 40,1 | 0,99 | 0,97 | 6,7 |
| 2021 | 55,6 | 1,00 | 1,04 | 7,8 |
| 2022 | 147,5 | 0,95 | 1,03 | 9,4 |
| 2023 | 96,6 | 0,96 | **0,90** | 11,3 |
| 2024 | 68,1 | 0,97 | **0,91** | 19,8 |
| 2025 | 66,4 | 0,99 | **0,83** | 25,1 |
| 2026 (Oca–Eyl) | 43,1 | 1,06 | **0,75** | ~27,5 (Temmuz) |

**Güneşin yakalanma oranı ve kurulu güç:**
- **2019–2022:** Kurulu güneş 6'dan 9,4 GW'a çıkarken oran 1 civarında kaldı. Bu dönemde öğle saatleri hâlâ talebin yüksek olduğu saatlerdi ve 2021–2022'de fiyat tavanı akşam pikini kırpıyordu.
- **2023 sonrası:** Kapasite 2023 sonunda 11 GW, 2025 sonunda 25 GW oldu; oran 0,90 → 0,83 → 0,75'e indi.
- **Doğrusal değil.** Bu veride kırılma ~10 GW civarında görülüyor; sonrasında kanibalizasyon hızlanıyor. Bu sezgisel olarak beklenen bir davranış: güneş üretimi öğle talebinin önemli bir kısmını karşılamaya başladığında öğle fiyatları belirgin biçimde düşüyor. 10 yıllık kısa seri ve 2021–2022 fiyat tavanları nedeniyle kesin bir eşik söylemek mümkün değil.
- **Yol A ve Yol B aynı hikâyeyi anlatıyor.** Ezine GES 2023'te 0,92 (Türkiye 0,90), 2025'te 0,82 (Türkiye 0,83).

**Rüzgâr:** Oran 0,95–1,00 bandında, trend yok. 2026'da 1,06'ya çıkması güneşin olmadığı saatlerin değer kazanmasıyla tutarlı.

**Sınırlama:**
- **EPİAŞ gerçek zamanlı güneş verisi yalnızca TEİAŞ'ın ölçtüğü lisanslı santralleri kapsıyor.** 2025'te ortalama 883 MW (üretimin %2,4'ü), oysa kurulu güneş ~25 GW.
- **Kurulu güneşin %86'sı lisanssız** (YEKDEM verisi, Ocak 2024) ve dağıtım şebekesinde talebi azaltarak görünüyor.
- **Bu yüzden ulusal güneş verisi yalnızca saatlik ŞEKİL olarak kullanıldı, mutlak miktar olarak değil.** Tüm GES'ler aynı güneşi gördüğü için şekil temsil gücü yüksek.
- **2016–2018 dışarıda bırakıldı.** Bu yıllarda veri birkaç MW'lık santrallerden oluşuyordu; Yol B güneşi 2019'dan başlıyor.

### 5.3 AUF dönemi duyarlılığı (Yol A, 2022–2023)

Yenilenebilir üreticinin fiilen aldığı fiyat ≈ min(PTF, aylık yenilenebilir AUF):

| | 2022 PTF ile | 2022 AUF sonrası | 2023 PTF ile | 2023 AUF sonrası (Oca–Eyl AUF) |
|---|---|---|---|---|
| Ortalama PTF [USD/MWh] | 147,5 | — | 96,6 | — |
| GES yakalanan [USD/MWh] | 148,7 | **83,6** | 89,2 | **73,9** |
| RES yakalanan [USD/MWh] | 138,3 | **82,9** | 92,7 | **74,9** |
| Hibrit yakalanan [USD/MWh] | 142,8 | **83,3** | 92,4 | **75,0** |

**Ders:** 2022'deki rekor fiyatlar YEKDEM dışı yenilenebilir üreticilere neredeyse hiç yansımadı;
gelirleri yaklaşık %44 kırpıldı. Finansal modelde (Aşama 3) bu, **düzenleyici risk** için somut
bir örnek: fiyat çok yükseldiğinde devletin müdahale edip tavan koyma ihtimali.

### 5.4 Batarya için ön göstergeler

**Ördek eğrisi (gün içi fiyat profili):**

| Yıl | Öğle (11–15 TSİ) / yıl ort. | Akşam (18–22 TSİ) / yıl ort. | Akşam / öğle |
|---|---|---|---|
| 2015 | 1,20 | 1,06 | 0,89 |
| 2018 | 1,05 | 1,07 | 1,02 |
| 2020 | 1,00 | 1,13 | 1,14 |
| 2023 | 0,92 | 1,18 | 1,29 |
| 2024 | 0,85 | 1,18 | 1,39 |
| 2025 | 0,75 | 1,20 | **1,60** |
| 2026 (Oca–Eyl) | 0,66 | 1,53 | **2,33** |

2015'te günün en pahalı saatleri öğle saatleriydi. 2025'te öğle fiyatları yıl ortalamasının %25
altına indi, akşam piki ortalamanın %20 üstünde. 2026'da bu fark daha da açıldı. **Ördek eğrisi
belirgin şekilde oluştu.** 2025 ısı haritasına göre en derin çukur Mart–Haziran ve Eylül–Ekim
öğlelerinde (bol güneş, düşük klima talebi), en pahalı saatler Nisan–Ağustos 19:00–22:00.

**Günlük fiyat farkı (spread):**

| Yıl | Medyan spread (maks − min) [USD/MWh] | Medyan "en pahalı 4 saat − en ucuz 4 saat" [USD/MWh] | Medyan spread / ort. PTF |
|---|---|---|---|
| 2017 | 27,3 | 23,8 | 0,61 |
| 2020 | 17,8 | 13,9 | 0,44 |
| 2021 | 27,9 | 22,7 | 0,50 |
| 2022 | 94,0 | 76,5 | 0,64 |
| 2023 | 58,9 | 48,8 | 0,61 |
| 2024 | 45,5 | 36,2 | 0,67 |
| 2025 | 44,7 | 34,5 | 0,67 |
| 2026 (Oca–Eyl) | **61,9** | **48,0** | **1,44** |

- **USD bazında spread doğrusal artmıyor.** 2022'deki kriz zirvesinden sonra 45 $/MWh civarına indi.
- **Ama fiyat seviyesine oranla belirgin şekilde büyüyor:** 2020'de ortalamanın 0,44'ü, 2026'da 1,44'ü.
- **4 saatlik bir batarya için kaba gösterge:** 2025'te günde ~34 $/MWh brüt fark, 2026'da ~48 $/MWh. Bu, gidiş-dönüş verimi (~%85–88) ve yıpranma maliyeti düşülmeden önceki üst sınır. Gerçek değer Aşama 4'teki optimizasyonla ölçülecek.

**Çok ucuz saatler:**

| Yıl | ≤ 1 $/MWh | ≤ 10 $/MWh |
|---|---|---|
| 2015 | 103 | 305 |
| 2016 | 271 | 521 |
| 2019 | 257 | 491 |
| 2021 | 0 | 7 |
| 2023 | 25 | 85 |
| 2024 | 57 | 231 |
| 2025 | 87 | 292 |
| 2026 (Oca–Eyl) | **431** | **1.564** |

- **Geçmişteki ucuz saatlerin nedeni farklıydı.** 2015–2016 ve 2019–2020'deki ucuz saatler bol yağışlı yıllar ve gece/bayram düşük talebinden geliyordu.
- **2026'nın ilk 9 ayında 1.564 saat (her 4 saatten biri) 10 $/MWh'ın altında.** Bunlar ağırlıkla bahar öğleleri.
- **Batarya için anlamı:** Neredeyse bedava şarj imkânı ve aynı zamanda GES/RES için **"sıfır fiyatta üretme"** riski.

**Bataryaya dair genel değerlendirme:** Gün içi fiyat şekli bataryanın lehine dönüyor: öğle ucuz,
akşam pahalı ve bu fark büyüyor. Ezine gibi bir hibrit sahada batarya üç değer kaynağına sahip:
1. Kesilen enerjiyi kurtarmak
2. Ucuz öğle üretimini pahalı akşama kaydırmak
3. Şebeke bağlantısını daha dolu kullanmak

Aşama 4'te bu üçü birlikte optimize edilecek.

## 6. Rüzgâr kalibrasyonu

### 6.1 Yöntem
- **Referans santral: Enerjisa Çanakkale RES** (Ezine-Mahmudiye, 13 × Siemens 2,3 MW, 29,9 MW, 2011). Seçilme nedenleri:
  - Ezine ilçesinde, ERA5 hücremize en yakın santrallerden biri.
  - **Kapasite 2014–2023 boyunca sabit:** Her yıl %99,9 yüzdelik üretimi 29,6–29,7 MW. Diğer santrallerde kapasite artırımları var.
  - Tek tip türbin, yani güç eğrisi vekili seçmek kolay.
  - Yalnızca iki uzun duruş var (2017'de 49 saat, 2021'de 87 saat). Bunlar arıza/bakım sayılıp dışarıda bırakıldı (≥ 48 saat ardışık sıfır üretim).
- **Elmayla armut karşılaştırmamak için** santral kendi türbinine yakın bir güç eğrisiyle modellendi:
  - windpowerlib'de Siemens SWT-2.3-93 yok. En yakın spesifik güç Enercon **E-92/2350** (354 W/m², SWT-2.3-93 için 339 W/m²).
  - Göbek yüksekliği 80 m (2011 dönemi için tipik; varsayım). Kayıplar %12, Aşama 1 ile aynı.
- **Hız kalibrasyon katsayısı k:** 2014–2023'te modellenen ortalama kapasite faktörü gözlenene (%30,2) eşit olacak şekilde kök bulma (Brent yöntemi) ile bulundu.
- **Neden k hızı ölçekliyor?** k bir hız katsayısı olduğu için (ERA5'in hız sapması), aynı k proje türbinine (E-141, 120 m) taşınabilir. KF'yi doğrudan ölçeklemek bunu yapamazdı, çünkü güç eğrisi doğrusal değil.

### 6.2 Sonuç: **k = 1,065** (ERA5, Ezine'de hızı ~%6,5 düşük tahmin ediyor)

| Yıl | Gözlenen KF | Model, k = 1 | Model, k = 1,065 |
|---|---|---|---|
| 2014 | 27,2% | 21,4% | 24,7% |
| 2015 | 31,6% | 27,4% | 31,0% |
| 2016 | 31,6% | 27,0% | 30,4% |
| 2017 | 29,9% | 26,2% | 29,6% |
| 2018 | 30,0% | 26,3% | 29,9% |
| 2019 | 31,0% | 27,9% | 31,5% |
| 2020 | 32,3% | 28,5% | 32,0% |
| 2021 | 30,7% | 27,8% | 31,4% |
| 2022 | 31,6% | 28,8% | 32,6% |
| 2023 | 26,5% | 25,6% | 29,1% |

**Uyum metrikleri (kalibrasyon sonrası):**

| Ölçek | Korelasyon |
|---|---|
| Saatlik | 0,76 |
| Günlük | 0,93 |
| Aylık | 0,95 |
| Yıllık | 0,79 |

Saatlik RMSE 0,21 (KF). 2023'te gözlenen değer modelden ~2,6 puan düşük. Bu fark santralin
kendisinden (arıza, bakım) ya da şebeke talimatlarından (YAT) veya kısıntılardan kaynaklanıyor
olabilir. Santral bazında YAT verisi kamuya açık olmadığı için ayrıştırılamadı.

**Duyarlılık (vekil türbin ve göbek):**

| Türbin vekili | Göbek | k |
|---|---|---|
| E-92/2350 | 80 m | **1,065** |
| E-92/2350 | 70 m | 1,088 |
| E-92/2350 | 100 m | 1,026 |
| E-82/2300 | 80 m | 1,119 |
| SWT113/2300 | 80 m | 0,907 |

En büyük belirsizlik vekil türbinin spesifik gücünden geliyor. Gerçek türbine en yakın vekil
(E-92) seçildi.

**Çapraz kontrol (diğer santraller, aynı vekil ile gösterge k):**

| Santral | İlçe | Kapasite değişimi | Gözlenen KF 2014–2023 | ERA5 ile saatlik korelasyon | Gösterge k |
|---|---|---|---|---|---|
| Enerjisa Çanakkale | Ezine | yok | 30,4% | 0,76 | 1,07 |
| Çamseki | Ezine | 21,7 → 63 MW (2018) | 30,5% | 0,80 | 1,07 |
| İntepe | Merkez | 31,5 → 56 MW (2016) | 31,0% | 0,83 | 1,08 |
| Sares | Ezine | 24 → 27,5 MW (2015) | 39,8% | 0,86 | 1,24 |
| Kocalar | Merkez | 26 → ~55 MW (2022–2025) | 46,7% | 0,73 | 1,41 |

- **Kapasite yönetimi:** Kapasitenin değiştiği santrallerde her yılın kapasitesi o yılın %99,9 yüzdelik üretimi alındı, geçiş yılları dışarıda bırakıldı.
- **Üç bağımsız santral (Enerjisa, Çamseki, İntepe) k ≈ 1,07 civarında birleşiyor;** bu kalibrasyonun sağlamlığını destekliyor.
- **Sares** muhtemelen çok iyi bir sırt konumunda (mikro yer seçimi).
- **Kocalar** güvenilmez: Kapasite neredeyse her yıl değişti ve listede 26 MW yazmasına rağmen veride ~55 MW görünüyor; türbinleri de çok daha yeni.
- **Mikro yer seçimi büyük fark yaratıyor.** Aynı ERA5 hücresinde santral verimleri %30 ile %40 arasında değişiyor. k = 1,065 "ortalama bir Ezine konumu" için muhafazakâr bir seçim; iyi bir sırtta k 1,2'ye çıkabilir.

### 6.3 Aşama 1'e etkisi (yeniden üretilen profiller, 2014–2023)

| | k = 1 (Aşama 1) | k = 1,065 (güncel) | Değişim |
|---|---|---|---|
| RES KF (E-141, 120 m) | 34,5% | **38,1%** | +3,6 puan |
| 1 MW RES P50 [MWh/yıl] | 3.060 | **3.378** | +10,4% |
| 1 MW RES P90 (normal) [MWh/yıl] | 2.766 | **3.080** | +11,4% |
| RES değişkenlik katsayısı | 6,6% | 6,1% | |
| Hibrit 1+1/1 P50 [MWh/yıl] | 4.620 | **4.880** | +5,6% |
| Hibrit 1+1/1 P90 (normal) [MWh/yıl] | 4.316 | **4.582** | +6,2% |
| Hibrit kesinti | 5,4% | 6,1% | |
| GES | değişmedi | | |

Önceki tablo: `outputs/01_uretim_modeli/p50_p90_ozet_k1.csv`, güncel tablo: `p50_p90_ozet.csv`.

### 6.4 ÖNEMLİ: ERA5 gün içi rüzgâr şeklini yakalayamıyor

Gözlenen Enerjisa üretimi **14:00–15:00 TSİ'de belirgin bir tepe** yapıyor (KF ~%45, gece ~%22).
Bu, Ege kıyısında tipik bir deniz meltemi / termal rüzgâr deseni. ERA5 modeli ise gün içinde
neredeyse düz ve hatta geceleri biraz yüksek (`kalibrasyon_aylik_gun_ici.png`). Hız katsayısı k
**ortalamayı** düzeltiyor ama **gün içi şekli** düzeltemiyor.

Etkisini ölçmek için gözlenen santral şekli, modelle aynı ortalamaya ölçeklenip RES profili yerine
kullanıldı (`gun_ici_sekil_duyarliligi.csv`):

| RES profili | GES–RES saatlik korelasyon | Hibrit kesinti (1+1 MW / 1 MW) | RES yakalanma oranı (10 yıl ort.) |
|---|---|---|---|
| ERA5 modeli (k = 1,065) | −0,11 | 6,1% | 0,974 |
| Gözlenen gün içi şekil | **+0,17** | **12,8%** | 0,990 |

- **Hibrit kesinti iki katına çıkıyor.** Gerçek rüzgâr öğleden sonra güneşle çakıştığı için saatlik tamamlayıcılık kayboluyor.
- **Bu, Aşama 1'deki "saatlik tamamlayıcılık" sonucunu zayıflatıyor.** Mevsimsel tamamlayıcılık (kış rüzgârı, yaz güneşi) ise geçerli kalıyor.
- **Yakalanma oranına etkisi küçük.**
- **Öneri:** Aşama 4'ten önce RES profiline gözlenen santralden türetilen ay × saat şekil düzeltmesi uygulanmalı. Bu, hibrit kesinti ve batarya boyutu için kritik. → **Uygulandı, bkz. 6.5.**

## 6.5 Revizyon: zaman hizalaması ve ay × saat şekil düzeltmesi

**Neden?** Bölüm 6.4'teki bulgu (ERA5 öğleden sonraki meltem pikini kaçırıyor) Aşama 4'teki batarya
ve kapasite kararlarını doğrudan etkileyeceği için düzeltildi.

**1) Zaman damgası uyumu** (`config.yaml → uretim.*.zaman_hizasi = "aralik"`)

| Kaynak | Değerin anlamı | Hedef tanıma ([t, t+1) UTC ortalaması) dönüşüm |
|---|---|---|
| EPİAŞ üretim/fiyat | Saat başı etiketli saatlik ortalama/dönem | Değişiklik yok (referans tanım) |
| ERA5 rüzgâr | HH:00 UTC anlık değer | Hız ve yoğunluk: (x_t + x_{t+1}) / 2, sonra güç eğrisi |
| PVGIS ışınım | ~HH:10 UTC anlık değer ([JRC kılavuzu](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/pvgis-user-manual_en)) | ⅔ · P(t) + ⅓ · P(t+1) (HH:30'a doğrusal enterpolasyon) |

- **Doğrulama:** Hizalamadan sonra gözlenen ile model arasındaki saatlik korelasyon 0,764 → 0,769'a çıktı. Bir saatlik ek kaymada korelasyon hâlâ marjinal olarak daha yüksek (0,769 vs 0,764); bu, ERA5'in meltem zamanlamasından gelen bir fark, etiketleme hatası değil.
- **14–15 TSİ tepesi hizalamadan sonra da duruyor.** Gözlenen tepe EPİAŞ verisinin kendisinde: Enerjisa 15 TSİ (KF %45 vs gece %22), Çamseki 14 TSİ (%42), İntepe 14–15 TSİ (%35, daha zayıf).

**2) Ay × saat hız katsayısı matrisi** (`ruzgar_kalibrasyon_yontemi = "ay_saat"`)
- Tek k yerine 12 × 24'lük bir k_ay,saat matrisi kuruldu. Her (ay, TSİ saati) hücresinde referans santral modelinin (E-92/2350, 80 m) ortalama KF'si gözlenene eşitlendi (kök bulma).
- Düzeltme yine KF'ye değil **hıza** uygulanıyor; bu yüzden matris proje türbinine taşınabiliyor.
- **Yumuşatma:** Komşu ay ve saatler arasında dairesel 3 × 3 ağırlıklı ortalama (Aralık↔Ocak, 23↔00), ardından toplam ortalama tek bir ölçekle yeniden eşlendi.
- **Matris değerleri:** 0,82 (yaz geceleri) – 1,73 (Haziran–Eylül, 13–15 TSİ).
- **Kayıt yeri:** Matris `data/processed/ruzgar_k_ay_saat.parquet` dosyasında, incelemek için kopyası `outputs/02_piyasa/ruzgar_k_ay_saat.csv`. Config yalnızca yöntemi seçiyor (`sabit` / `ay_saat`).

**3) Çapraz doğrulama** (`kalibrasyon_capraz_dogrulama.csv`): Matris bir dönemde kuruldu, diğer dönemde test edildi.

| Test dönemi | Yöntem | Saatlik korelasyon | Ay × saat RMSE [KF puanı] | Gün içi profil RMSE | Yıllık KF mutlak hata |
|---|---|---|---|---|---|
| 2019–23 (kurulum 2014–18) | Sabit k | 0,752 | 11,2 | 9,4 | 1,88 |
| | **Ay × saat (yumuşak)** | **0,841** | **2,7** | **2,1** | 1,88 |
| 2014–18 (kurulum 2019–23) | Sabit k | 0,775 | 10,3 | 8,6 | 1,81 |
| | **Ay × saat (yumuşak)** | **0,847** | **2,5** | **1,9** | 1,79 |

- **Matris örneklem dışında da çok daha iyi.** Hücre hatası ~4 kat azaldı, saatlik korelasyon +0,08 arttı.
- **Yıllık hata değişmiyor.** Bu hata iki 5 yıllık dönemin rüzgâr seviyesi farkından geliyor, şekilden değil.
- **Yumuşatma işe yarıyor:** Ham matristen biraz daha iyi sonuç veriyor, yani gürültüyü azaltıyor.

**4) Sonuçlara etkisi** (`revizyon_karsilastirma.csv`; üç durum aynı kodla üretildi)

| | Aşama 2: sabit k, anlık | Sabit k, aralık hizası | **Revizyon: ay × saat k** |
|---|---|---|---|
| RES KF | 38,1% | 38,1% | **37,7%** |
| RES tepe saati (TSİ) | 21 | 21 | **15** |
| GES–RES saatlik korelasyon | −0,11 | −0,11 | **+0,12** |
| Hibrit kesinti (1+1 MW / 1 MW) | 6,1% | 5,9% | **9,6%** |
| Hibrit P50 / P90 [MWh/yıl] | 4.880 / 4.582 | 4.889 / 4.591 | **4.652 / 4.390** |
| RES yakalanma oranı 2014–23 ort. | 0,974 | 0,975 | 0,988 |
| RES yakalanma oranı 2023 | 0,960 | 0,960 | 0,956 |
| RES yakalanma oranı 2025 (uzantı) | 0,966 | 0,966 | **0,940** |
| RES yakalanma oranı 2026 Oca–Eyl (uzantı) | 1,040 | 1,042 | **0,995** |
| Hibrit yakalanma oranı 2025 (uzantı) | 0,929 | 0,928 | **0,916** |

**Yorum:**
- **Zaman hizalaması tek başına önemsiz.** Etkinin tamamı gün içi şekilden geliyor.
- **RES'in yakalanma oranı dönemle birlikte yön değiştiriyor:**
  - 2014–2018'de öğleden sonra saatleri talebin tepesi olduğu için pahalıydı; meltem piki rüzgârı ortalamanın biraz üstüne çıkarıyor.
  - 2023'ten sonra güneş öğleden sonrayı ucuzlattıkça aynı pik **aleyhe** dönüyor: 2025'te 0,966 → 0,940, 2026'da 1,04 → 0,995.
  - Yani Ezine rüzgârı da güneş kanibalizasyonundan **kısmen etkileniyor**. Bu, ileriye dönük fiyat varsayımlarında (Aşama 3) önemli.
- **Kesinti belirgin büyüdü.** Matrisli model ortalama şekli düzeltse de saatlik oynaklığı tam yakalayamıyor; gözlenen şekille kesinti %12,2. Gerçek kesinti %10–12 aralığında olmalı.

## 7. Sınırlamalar

1. **Ulusal güneş verisi yalnızca lisanslı GES'leri kapsıyor.** Kurulu güneşin %86'sı lisanssız. Bu yüzden ulusal güneş yalnızca şekil olarak kullanıldı ve Yol B 2019'dan başlıyor.
2. **Gün içi rüzgâr şekli** ay × saat matrisiyle düzeltildi (bkz. 6.5). Ancak matris 80 m'de eski bir türbinle kuruldu ve 120 m'ye taşındı; saatten saate oynaklık tam yakalanamıyor (kesinti %9,6 model vs %12,2 gözlenen şekil).
3. **Gözlenen santral verisi saf rüzgâr kaynağı değil.** Şebeke talimatları (YAL/YAT), kısıntılar ve kısa arızalar da içinde. Yalnızca ≥ 48 saatlik duruşlar ayıklandı; santral bazında YAT verisi kamuya açık değil.
4. **Kalibrasyonda vekil türbin ve göbek yüksekliği varsayıldı.** Bunlardan kaynaklanan k belirsizliği 0,91–1,12.
5. **Mikro yer seçimi etkisi büyük.** Aynı hücrede santral KF'leri %30–40 arasında değişiyor; tek bir k bu çeşitliliği temsil etmez.
6. **Yarım saatlik hizalama belirsizliği.** EPİAŞ değerleri saat dilimi ortalaması, ERA5 ve PVGIS ise anlık değerler. Saatlik eşleşmelerde yarım saate kadar bir belirsizlik var.
7. **"Fiyat alıcı" varsayımı.** Ezine santrali fiyatı etkilemeyecek kadar küçük kabul edildi. YEKDEM ve ikili anlaşmalar (PPA) dikkate alınmadı; tüm satış spot PTF'den varsayıldı (AUF dönemi hariç duyarlılık).
8. **2026 yalnızca Ocak–Eylül.** Bahar ağırlıklı ilk 9 ay güneş kanibalizasyonunu yıllık değere göre biraz abartıyor olabilir.
9. **2024–2026 Ezine uzantısı.** Gerçek hava–fiyat eşzamanlılığını değil, 10 hava yılının ortalamasını ve 2021–2023'ten tahmin edilen bir düzeltmeyi kullanıyor.
10. **Kurulu güç serisi.** 2014–2017 değerleri ikincil kaynaklardan derlendi (yaklaşık) ve yalnızca trend yorumunda kullanıldı.

## 8. Grafikler (`outputs/02_piyasa/`)

| Dosya | İçerik |
|---|---|
| `yillik_fiyat_yakalanan_usd.png` | Yıllık ort. PTF ve Ezine GES/RES/hibrit yakalanan fiyat (USD) |
| `yakalanma_orani_trendi.png` | Yakalanma oranı: Yol A (Ezine + 2024–26 uzantı) ve Yol B (Türkiye) |
| `gunes_kapasite_ve_yakalanma.png` | Kurulu güneş gücü ve güneş yakalanma oranı ilişkisi |
| `gun_ici_fiyat_profili.png` | Yıllara göre normalize gün içi fiyat profili (ördek eğrisi) |
| `ay_saat_fiyat_isi_haritasi_2025.png` | Ay × saat ortalama PTF, 2025 |
| `gunluk_spread.png` | Günlük fiyat farkı dağılımı ve 4 saatlik spread trendi |
| `dusuk_fiyatli_saatler.png` | ≤ 1 ve ≤ 10 $/MWh saat sayıları |
| `kalibrasyon_yillik.png` | Referans santral: gözlenen ve model yıllık KF |
| `kalibrasyon_aylik_gun_ici.png` | Aylık KF serisi ve gün içi profil karşılaştırması |

---

## Mülakat özeti

> EPİAŞ Şeffaflık Platformu'nun API'siyle 2014'ten bugüne saatlik elektrik fiyatlarını ve üretim
> verilerini çektim; yaz saati geçişlerindeki çift ve eksik saatleri ele alıp her şeyi UTC'ye
> çevirdim. Sonra sahamda güneş, rüzgâr ve hibrit santralin piyasada ortalamaya göre hangi fiyatı
> yakaladığını hesapladım. En çarpıcı bulgu güneşin kanibalizasyonu oldu: 2016'da güneş ortalama
> fiyatın %20 üstünde satarken, kurulu güç 25 GW'a çıkınca 2025'te ortalamanın %18 altına,
> 2026'da %30 altına indi. Öğle ile akşam arasındaki fiyat farkı büyüdü, çok ucuz saatler patladı;
> bu da bataryanın değerinin arttığını gösteriyor. Rüzgâr modelimi Ezine'deki gerçek santral
> üretimiyle kalibre ederken ERA5'in öğleden sonraki deniz meltemi pikini kaçırdığını fark ettim.
> Bunu ay ve saat bazında bir hız düzeltmesiyle giderdim ve dönem bölerek çapraz doğruladım; hata
> dört kat azaldı. Bu düzeltmenin iki sonucu oldu: hibrit kesinti %6'dan %10'a çıktı ve rüzgârın
> son yıllardaki yakalanma oranı da düştü, çünkü rüzgâr da artık ucuzlayan öğleden sonra saatlerinde
> üretiyor.
