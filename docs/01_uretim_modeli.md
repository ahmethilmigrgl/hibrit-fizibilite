# Aşama 1 — Saha Seçimi ve Üretim Modeli

**Amaç:** Seçilen saha için optimizasyon modelinin doğrudan kullanabileceği, çok yıllı **saatlik
kapasite faktörü** profilleri üretmek: 1 MW AC kurulu GES ve 1 MW RES her saat kaç MW üretir?
Optimizasyon (Aşama 4) bu profilleri kapasite değişkenleriyle çarparak kullanacak.

| | |
|---|---|
| Kodlar | `src/uretim/gunes.py`, `src/uretim/ruzgar.py`, `src/uretim/profil.py`, `src/uretim/hibrit.py`, `src/uretim/degiskenlik.py` |
| Çalıştırma | `src/01_saha_taramasi.py` (4 saha, 2021–2023), `src/01_uretim_profilleri.py` (Ezine, 2014–2023) |
| Çıktı verisi | `data/processed/ezine_profiller_2014_2023.parquet` (87.648 saat, eksik/tekrar yok) |
| Grafikler | `outputs/01_saha_taramasi/`, `outputs/01_uretim_modeli/` |
| Varsayımlar | `config.yaml` → `aday_sahalar`, `saha`, `uretim` |

**Parquet sütunları:** `zaman_utc` (UTC, saat başı), `ges_kf`, `res_kf` (E-141), `res_kf_e126`
(duyarlılık), `v100_ham` ve `v_gobek_ham` (kalibrasyonsuz ERA5 hızları, m/s), `hava_yogunlugu` (kg/m³).
Kapasite faktörleri 0–1 arasında, AC tarafında ve tüm kayıplar düşülmüştür.

> **Aşama 2 güncellemesi (2026-10-03):** Rüzgâr modeli Ezine'deki gerçek santral üretimiyle kalibre
> edildi: `ruzgar_hiz_kalibrasyon_katsayisi` = **1,065** (bkz. `docs/02_piyasa_analizi.md`, bölüm 6).
> Bu belgedeki RES ve hibrit sayıları **kalibrasyon öncesi (k = 1)** değerlerdir. Güncel değerler:
> - RES KF %34,5 → %38,1
> - RES P50 3.060 → 3.378 MWh/yıl, P90 2.766 → 3.080 MWh/yıl
> - Hibrit P50 4.620 → 4.880 MWh/yıl, P90 4.316 → 4.582 MWh/yıl
> - Hibrit kesinti %5,4 → %6,1
>
> Güncel tablolar `outputs/01_uretim_modeli/` altında; kalibrasyon öncesi P50/P90 tablosu
> `p50_p90_ozet_k1.csv`. Ayrıca Aşama 2'de ERA5'in Ezine'deki öğleden sonra rüzgâr pikini
> yakalayamadığı görüldü. Gözlenen gün içi şekille GES–RES saatlik korelasyonu −0,11 yerine +0,17,
> hibrit kesinti %6 yerine %13 çıkıyor. Aşağıdaki "saatlik tamamlayıcılık" yorumları bu nedenle
> iyimserdir; mevsimsel tamamlayıcılık geçerlidir.

---

## 1. Veri kaynakları

| Veri | Kaynak | Çözünürlük | Kullanım |
|---|---|---|---|
| Güneş ışınımı (eğik düzlem, direkt/yaygın/yansıyan) | **PVGIS 5.3**, ışınım veritabanı **PVGIS-SARAH3** (uydu), AB Ortak Araştırma Merkezi (JRC) — `re.jrc.ec.europa.eu/api/v5_3/` | Saatlik, ~5 km | GES modeli girdisi |
| Hava sıcaklığı, 10 m rüzgâr (GES için) | PVGIS içinden ERA5 | Saatlik | Modül sıcaklığı |
| Rüzgâr u/v bileşenleri (10 m, 100 m), 2 m sıcaklık, yüzey basıncı | **ERA5** yeniden analiz, Copernicus İklim Veri Deposu (CDS), veri seti `reanalysis-era5-single-levels-timeseries` | Saatlik, 0,25° (~25 km) | RES modeli girdisi |
| Türbin güç eğrileri | **windpowerlib** türbin kütüphanesi (Open Energy Platform) | 0,5–1 m/s adımlı | Güç dönüşümü |
| Doğrulama | PVGIS'in kendi PV hesabı (`pvcalculation`); Türkiye RES filosu üretim istatistikleri | Yıllık | Kıyaslama |

**Yıl aralığı:** PVGIS-SARAH3 2005–2023 arasını destekliyor (API 2004 ve 2024'ü reddediyor;
kontrol 2026-10-03). En güncel 10 yıl **2014–2023** kullanıldı. Saha taramasında indirme süresini
kısaltmak için son 3 yıl (2021–2023) kullanıldı; GES ve RES için hep aynı yıllar alındı, böylece
saatlik korelasyonlar aynı hava koşullarını yansıtıyor.

**Neden ERA5 nokta zaman serisi?** Bu veri seti gereken altı değişkenin hepsini içeriyor ve
istenen noktaya en yakın grid hücresinin serisini doğrudan CSV olarak veriyor. Klasik yol (alan
kesip yıl yıl NetCDF indirmek, en yakın hücreyi seçmek) gereksiz kaldı. 4 saha × 3 yıl yaklaşık
4 dakikada indi. Ham dosyalar `data/raw/era5/` ve `data/raw/pvgis/` altında önbelleklenir; ikinci
çalıştırmada indirme yapılmaz.

## 2. Zaman kuralı: her şey UTC

- PVGIS ve ERA5 zaman damgaları UTC'dir; tüm profiller **UTC** olarak saklanır (`zaman_utc`).
- PVGIS zaman damgaları `HH:10` gibi kayıktır (uydu taramasının anı). Güneş konumu bu gerçek
  anlarda hesaplanır, sonra indeks saat başına (`HH:00`) yuvarlanır.
- ERA5 rüzgâr değerleri `HH:00` anındaki anlık değerlerdir.
- **EPİAŞ verisi Türkiye saatindedir (TSİ).** Türkiye **7 Eylül 2016'dan beri sabit UTC+3**
  kullanıyor; ondan önce kışın UTC+2, yazın UTC+3 (yaz saati) uygulanıyordu. Bu yüzden Aşama 2'de
  2014–2016 verisi birleştirilirken sabit "+3" değil, saat dilimi veritabanı (`Europe/Istanbul`)
  ile dönüşüm yapılmalı.
- Grafiklerde saat ekseni okunabilirlik için **TSİ = UTC+3** olarak gösterilir ve eksende belirtilir.

## 3. Güneş modeli (PVGIS + pvlib, PVWatts yaklaşımı)

Sistem: sabit montaj, güneye bakan (azimut 180°), **optimum eğim** (PVGIS her saha için yıllık
ışınımı maksimize eden eğimi hesaplar; Ezine için 33°). 1 MW AC başına 1,2 MWp panel.

Saatlik hesap zinciri:

1. **Düzlem ışınımı (POA):** PVGIS'ten direkt, yaygın ve yerden yansıyan bileşenler ayrı gelir
   (ufuk gölgesi dahil).
2. **Yansıma kaybı (IAM):** Işığın geliş açısı büyüdükçe camdan yansıyan pay artar. ASHRAE modeli
   (b₀ = 0,05) direkt bileşene uygulanır.
3. **Hücre sıcaklığı:** SAPM modeli (açık raf, cam-polimer modül), ışınım + hava sıcaklığı + rüzgârdan.
4. **DC güç (PVWatts):** `P_dc = P_dc0 · (G_etkin / 1000) · [1 + γ · (T_hücre − 25)]`, γ = −0,37 %/°C.
5. **Sistem kayıpları %14** (PVWatts tanımı: kirlenme, gölge, uyumsuzluk, kablo, LID, nominal değer,
   kullanılabilirlik; inverter hariç).
6. **İnverter:** PVWatts verim eğrisi (nominal %96) ve 1 MW AC'de **kırpma (clipping)**.
7. **Ek kırpma kaybı %1** (aşağıda, Sınırlamalar 5. maddeye bakın).

Kapasite faktörü = P_ac / 1 MW AC.

## 4. Rüzgâr modeli (ERA5 + windpowerlib)

1. **Hız:** `v = √(u² + v²)`, 10 m ve 100 m için.
2. **Saatlik kayma üssü (shear exponent):** Rüzgâr yükseldikçe hızlanır; bunu kuvvet yasası anlatır:
   `v(h) = v_ref · (h / h_ref)^α`. α her saat iki yükseklikten hesaplanır:
   `α = ln(v₁₀₀ / v₁₀) / ln(100 / 10)`. 10 m hızı 1 m/s'nin altındaysa (oran anlamsızlaşır) sahanın
   medyan α'sı kullanılır; α [0, 0,5] aralığına kırpılır. Ezine medyan α ≈ 0,16.
3. **Göbek yüksekliğine taşıma:** `v₁₂₀ = v₁₀₀ · (120/100)^α`. Ezine 10 yıllık ortalama 6,90 m/s.
4. **Kalibrasyon katsayısı:** `v_kalibre = k · v₁₂₀`, şimdilik k = 1,0
   (`ruzgar_hiz_kalibrasyon_katsayisi`). Aşama 2'de EPİAŞ'tan Ezine çevresindeki gerçek RES'lerin
   saatlik üretimiyle kalibre edilecek. Katsayıyı değiştirip `src/01_uretim_profilleri.py`'yi
   yeniden çalıştırmak yeterli (indirme yapılmaz, ~1 dk); ham hızlar parquet'te de saklanır.
5. **Hava yoğunluğu:** Türbin aynı hızda yoğun havada daha çok güç üretir. İdeal gaz yasası
   `ρ = p / (R·T)`; sıcaklık göbek yüksekliğine −6,5 K/km ile, basınç hipsometrik denklemle taşınır.
   Ezine ortalama 1,187 kg/m³ (standart 1,225).
6. **Güç eğrisi + yoğunluk düzeltmesi:** IEC 61400-12 yöntemi (windpowerlib
   `power_curve_density_correction`): güç eğrisi her saatin yoğunluğuna göre kaydırılır.
7. **Kayıplar %12:** iz etkisi (wake) + kullanılabilirlik + elektriksel; brüt üretime uygulanır.
   Bu yüzden RES kapasite faktörü en fazla 0,88 olabilir.

**Türbin seçimi: Enercon E-141 EP4 (4,2 MW, 141 m rotor).** windpowerlib kütüphanesinde güç eğrisi
olan 4–5 MW sınıfı türbinler AD116/5000 (deniz üstü), E-126/4200 ve E-141/4200. E-141'in spesifik
gücü (~269 W/m²) bugün Türkiye'de kurulan büyük rotorlu türbinlere (V150-4.2, N149-4.5, SG 4.5-145)
en yakın olanı; Enercon'un Türkiye'de de büyük bir kurulu tabanı var. E-141 düşük rüzgâr sınıfında
(IEC IIIA) olduğu için, yüksek rüzgârlı sahalar için tasarlanmış **E-126 EP4** (IEC IIA, ~332 W/m²)
duyarlılık sütunu olarak tutuldu. Ezine'de E-126, E-141'den 4 puan düşük kapasite faktörü veriyor
(%30,5'e karşı %34,5).

## 5. Saha taraması (2021–2023)

| | Çanakkale-Ezine | Balıkesir-Bandırma | İzmir-Aliağa | Konya-Karapınar |
|---|---|---|---|---|
| Optimum eğim | 33° | 32° | 33° | 33° |
| GES kapasite faktörü | 20,6% | 19,2% | 21,8% | **22,1%** |
| RES kapasite faktörü (E-141) | **35,4%** | 24,2% | 20,7% | 11,5% |
| 120 m ortalama hız | **7,0 m/s** | 5,6 | 5,4 | 4,2 |
| Saatlik GES–RES korelasyonu | **−0,12** | −0,03 | −0,04 | −0,09 |
| Günlük GES–RES korelasyonu | **−0,28** | −0,24 | −0,16 | −0,18 |
| 1+1 MW / 1 MW bağlantı: satılan [MWh/yıl] | **4.642** | 3.636 | 3.586 | 2.891 |
| Aynı düzende kesinti | 5,4% | 4,5% | 3,7% | 2,0% |
| Bağlantı kullanım oranı | **53,0%** | 41,5% | 40,9% | 33,0% |

**Hibrit göstergesi:** 1 MW GES + 1 MW RES aynı 1 MW bağlantıyı paylaşırsa her saat
`satılan = min(GES + RES, 1)` ve `kesilen = (GES + RES) − satılan` olur. Bu bir optimizasyon değil,
sahaları aynı düzende karşılaştırmak için basit bir göstergedir.

**Neden Ezine?**
- **Rüzgâr kaynağı açık ara en iyi** ve hibrit değerini asıl belirleyen bu. Aynı 1 MW bağlantı,
  ikinci sıradaki sahadan ~%28 daha fazla enerji satıyor.
- **Tamamlayıcılık en güçlü:** Korelasyon en negatif. Rüzgâr kışın ve gece güçlü, güneş yazın ve
  öğlen. Bu da batarya ve bağlantı boyutlandırmasını tartışmak için iyi bir zemin.
- **Güneşte biraz geride:** Karapınar'dan ~1,5 puan düşük, ama rüzgârdaki fark bunu fazlasıyla kapatıyor.
- Karapınar'ın rüzgârı (%11,5) hibriti anlamsız kılıyor; orası saf GES sahası.
- **Gerçek projede riskler:** Biga yarımadasında RES yoğunluğu yüksek, bu da şebeke kapasitesi
  kıtlığı ve TEİAŞ bağlantı görüşü riski demek. Ayrıca tarım arazisi kısıtları GES alanını
  sınırlayabilir. Bunlar Aşama 4'teki şebeke kısıtı tartışmasının gerçek dünyadaki karşılığı.

Saha seçimi 2026-10-03'te onaylandı.

## 6. Ezine sonuçları (2014–2023)

### 6.1 Yıllık üretim

| Yıl | GES KF | GES [MWh/MW] | RES KF | RES [MWh/MW] | Hibrit satılan [MWh] | Hibrit kesinti |
|---|---|---|---|---|---|---|
| 2014 | 19,5% | 1.711 | 28,9% | 2.533 | 4.085 | 3,8% |
| 2015 | 20,7% | 1.817 | 35,3% | 3.092 | 4.641 | 5,5% |
| 2016 | 21,0% | 1.836 | 34,6% | 3.029 | 4.600 | 5,5% |
| 2017 | 21,0% | 1.843 | 33,6% | 2.942 | 4.521 | 5,5% |
| 2018 | 19,8% | 1.736 | 34,3% | 3.001 | 4.503 | 4,9% |
| 2019 | 20,7% | 1.812 | 35,9% | 3.143 | 4.654 | 6,1% |
| 2020 | 21,0% | 1.838 | 36,3% | 3.179 | 4.710 | 6,1% |
| 2021 | 20,5% | 1.794 | 35,4% | 3.100 | 4.643 | 5,1% |
| 2022 | 21,1% | 1.847 | 37,2% | 3.255 | 4.789 | 6,1% |
| 2023 | 20,3% | 1.775 | 33,5% | 2.938 | 4.485 | 4,8% |

Yıllık üretim = yıllık ortalama KF × 8760 h. Artık yılların fazladan 24 saati değişkenliğe sahte
gürültü eklemesin diye 8760 ile normalize edildi. Hibrit düzeni: 1 MW GES + 1 MW RES, 1 MW bağlantı.

### 6.2 P50 / P90 (MWh/yıl)

| | 1 MW GES | 1 MW RES | 1+1 MW, sınırsız bağlantı | 1+1 MW / 1 MW bağlantı |
|---|---|---|---|---|
| Ortalama | 1.801 | 3.021 | 4.822 | 4.563 |
| Standart sapma (σ) | 47 | 199 | 236 | 193 |
| **Değişkenlik katsayısı (σ / ort.)** | **2,6%** | **6,6%** | **4,9%** | **4,2%** |
| P50 (ampirik medyan) | 1.815 | 3.060 | 4.880 | 4.620 |
| P90 (ampirik, 10. yüzdebirlik) | 1.733 | 2.897 | 4.666 | 4.445 |
| P90 (normal: ort. − 1,282σ) | 1.741 | 2.766 | 4.519 | 4.316 |
| P90 / P50 (normal) | 96,6% | 91,6% | 93,7% | 94,6% |

**Yöntem:**
- **P50:** Yılların yarısında aşılması beklenen yıllık üretim. **P90:** Yılların %90'ında aşılması
  beklenen üretim; yani 10 yılda yaklaşık 1 yıl bunun altına düşülür. Bankalar borç kapasitesini
  genelde P90 (bazen P99) üzerinden boyutlandırır.
- **Ampirik P90:** 10 yıllık değerlerin 10. yüzdebirliği (doğrusal enterpolasyon). Dağılım
  varsayımı gerektirmez, ama 10 gözlemle en kötü iki yılın arasına düşer.
- **Normal P90:** `P90 = P50 − 1,282 · σ`. Burada 1,282 standart normal dağılımın %10 kantili,
  P50 = ortalama, σ = örneklem standart sapması (n − 1). Küçük örneklemde daha kararlıdır ve
  sektörde standart yaklaşımdır.
- **RES'te iki yöntem 130 MWh ayrışıyor.** Nedeni 2014: tek bir çok zayıf yıl (%28,9) σ'yı
  şişiriyor. Normal yöntem bunu tüm dağılıma yayıp daha muhafazakâr bir P90 veriyor; ampirik yöntem
  ise sadece en kötü iki yıl arasına bakıyor. Dağılım sola çarpık (bir kötü yıl, birçok normal yıl).
- **Kapsam:** Bunlar yalnızca **hava kaynaklı yıllar arası değişkenliği** gösteren 1 yıllık
  P90'lardır. Model belirsizliği (ERA5 sapması, güç eğrisi, kayıplar) ve çok yıllık ortalamanın
  P90'ı (σ/√N ile daralır) Aşama 5'te Monte Carlo ile eklenecek. Gerçek bir enerji raporunda
  toplam belirsizlik bu yüzden daha büyük olur.

### 6.3 Portföy etkisi: hibrit değişkenliği azaltıyor mu?

Kısa cevap: **Evet, ama sanıldığı kadar çeşitlendirmeyle değil.**

- **Saatlik ve mevsimsel ölçekte güçlü tamamlayıcılık var.** Saatlik korelasyon −0,12; rüzgâr
  kışın (%41–43) ve Ağustos meltemiyle (%42) güçlü, güneş Nisan–Eylül'de güçlü. Bu, aynı bağlantının
  daha çok saatte dolu kullanılmasını sağlıyor (bağlantı kullanım oranı %52, tek RES'te %34).
- **Yıllar arası ölçekte çeşitlendirme yok denecek kadar az.** Yıllık GES ve RES üretimlerinin
  10 yıllık korelasyonu **+0,74**: iyi yıllar ikisi için de iyi, kötü yıllar ikisi için de kötü.
  Bu değer kısmen 2014'ün etkisi (2014 hariç +0,45), ve 10 gözlemle %95 güven aralığı geniş
  (0,21–0,93), ama işareti açıkça pozitif. Sınırsız bağlantıda toplam üretimin σ'sı 236 MWh;
  iki kaynak bağımsız olsaydı √(47² + 199²) ≈ 205 MWh olurdu, tam ilişkili olsaydı 246 MWh.
  Yani gerçekleşen değer "tam ilişkili" uca çok yakın.
- **Değişkenlik katsayısındaki düşüş (RES %6,6 → hibrit %4,9) çoğunlukla seyreltmeden geliyor.**
  Çok kararlı bir kaynak (GES, %2,6) oynak olana eklenince oransal oynaklık düşüyor; bu
  çeşitlendirme değil, karışım etkisi.
- **Şebeke sınırı ek bir doğal sigorta gibi çalışıyor** (%4,9 → %4,2). Rüzgârlı yıllarda kesinti
  artıyor (yıllık RES üretimi ile kesinti oranı korelasyonu +0,91: 2022'de %6,1, 2014'te %3,8).
  Bağlantı iyi yılların fazlasını kırpıyor, kötü yılları neredeyse hiç etkilemiyor; sonuçta P90/P50
  oranı RES'te %91,6'dan hibritte %94,6'ya çıkıyor. Bunun bedeli ortalama üretimin %5,4'ünün kesilmesi.
- **Sonuç (finansman açısından):** Hibrit, tek RES'e göre P90'ı P50'ye yaklaştırıyor; yani borç
  kapasitesi açısından daha "bankalanabilir" bir üretim profili veriyor. Ama asıl kazanç yıllar
  arası çeşitlendirmeden değil, kıt bağlantı kapasitesinin daha verimli kullanılmasından geliyor.
  Batarya (Aşama 4), kesilen enerjinin bir kısmını kurtarabilir.

## 7. Doğrulama

### 7.1 GES: PVGIS'in kendi hesabıyla karşılaştırma (Ezine, 2014–2023, kWh/kWp/yıl)

| Hesap | kWh/kWp/yıl | PVGIS'e göre |
|---|---|---|
| PVGIS `pvcalculation` (crystSi, %14 toplam kayıp **inverter dahil**, kırpma yok) | 1.523 | — |
| Model, PVGIS-eşdeğer tanım (DC/AC = 1, %14 toplam kayıp, inverter ayrıca yok) | 1.583 | **+4,0%** |
| Model, proje tasarımı (DC/AC 1,2; %14 + %96 inverter), ek kırpma öncesi | 1.517 | −0,4% |
| Model, proje tasarımı, %1 ek kırpma kaybı sonrası (kullanılan) | **1.502** | −1,4% |

Taramadaki dört sahada da eşdeğer tanımla fark +3,6% ile +4,3% arasındaydı.

**Fark makul ve açıklanabilir.** Aynı ışınım verisini kullanmamıza rağmen PVGIS bazı etkileri
daha ayrıntılı modelliyor:
- düşük ışınımda modül veriminin düşmesi (PVWatts doğrusal varsayar),
- yansıma kaybının yaygın ışınıma da uygulanması (biz sadece direkte uyguluyoruz),
- spektral düzeltme,
- farklı bir sıcaklık modeli.

Bunların her biri %1–2'lik etkiler ve hepsi bizim modeli yukarı itiyor. Proje tasarımında ek %4
inverter kaybı ve %1 kırpma kaybı modelin sonucunu PVGIS'in %1,4 altına çekiyor. Farklı PV
simülasyon modelleri arasında aynı girdiyle birkaç yüzdelik fark olağandır; burada farkın yönü ve
nedenleri de açıklanabilir durumda.

### 7.2 RES: Türkiye filosuyla kıyas

- **Türkiye RES filosunun 2024 kapasite faktörü yaklaşık %33–35** (kendi hesabım): 2024'te elektrik
  üretiminin %11,34'ü rüzgârdan geldi ([AA](https://www.aa.com.tr/tr/ekonomi/turkiyenin-ruzgari-2024te-guclu-esti/3426477)),
  yıl sonu kurulu güç 13,8 GW ([Yeşil Haber / TÜREB](https://yesilhaber.net/turkiye-ruzgar-enerjisi-2024-raporu/)).
  Bu filo, ortalama daha küçük ve eski türbinlerden oluşuyor.
- **Ezine modeli %34,5** (2014–2023) ile filo ortalamasında. Taramada Bandırma (%24) ve Aliağa (%21)
  ise filo ortalamasının belirgin şekilde altında kaldı; bu bölgelerde yıllardır ticari RES işletildiği
  düşünülürse bu, ERA5'in düşük tahminine işaret ediyor (santral bazında henüz doğrulanmadı).
- **Yorum:** Ezine ve Çanakkale, Türkiye'nin en iyi rüzgâr bölgelerinden. Modern 4 MW'lık bir
  türbinin burada filo ortalamasının üstünde üretmesi beklenir. Bu yüzden %34,5'i **muhafazakâr
  (düşük tahmin)** sayıyorum. Gerçek değer Aşama 2'de EPİAŞ santral üretim verisiyle kalibrasyonla
  belirlenecek.

## 8. Sınırlamalar

1. **ERA5 karmaşık arazide rüzgârı düşük tahmin eder.** 0,25°'lik (~25 km) hücre araziyi
   yumuşatır. Ezine hücresinin ERA5 rakımı 134 m görünüyor, oysa santraller daha yüksek sırtlara
   kurulur ve sırtlarda rüzgâr hızlanır. Ayrıca ERA5 türbülans ve yerel kanalizasyon etkilerini
   yakalayamaz. Mutlak RES kapasite faktörleri muhafazakârdır; saha sıralaması için güvenilirdir.
   Telafi: `ruzgar_hiz_kalibrasyon_katsayisi` (Aşama 2).
2. **10 UTC süreksizliği.** ERA5 veri asimilasyonu 12 saatlik pencerelerle (09–21 UTC ve 21–09 UTC)
   yapılır ve pencere sınırlarında bilinen bir süreksizlik oluşur. Profillerimizde her sahada 10 UTC'de
   (13:00 TSİ) rüzgârda sahte bir kırılma görülüyor (ısı haritasında dikey çizgi). Yıllık enerjiye
   etkisi ihmal edilebilir, ama saatlik dispatch'te o saatte rüzgâr biraz düşük görünür. Gerekirse
   bu saat komşu saatlerden enterpole edilebilir.
3. **Kıyı hücreleri.** ERA5 kara/deniz maskesine göre Ezine hücresinin %71'i, Bandırma'nınkinin %76'sı,
   Aliağa'nınkinin %78'i kara (Karapınar %99). Deniz yüzeyi daha pürüzsüz olduğu için kısmen deniz
   olan hücreler rüzgârı kara içine göre farklı (genelde daha güçlü ve daha az türbülanslı) gösterebilir.
   Üç kıyı sahasında etki benzer olduğundan Ezine'nin üstünlüğünü açıklamıyor, ama mutlak değerlerde
   bir belirsizlik kaynağı.
4. **Nokta veriden santral üretimine geçiş.** Tek grid noktası tüm santrali temsil ediyor; türbinler
   arası mekânsal çeşitlilik ve gerçek iz kayıpları yerine sabit %12 kayıp varsayıldı.
5. **Saatlik veri inverter kırpmasını düşük gösterir.** Saatlik ortalama ışınım, bulut kenarı etkisi
   gibi dakikalık tepeleri yumuşatır. Model DC/AC 1,2'de yalnızca %0,01 kırpma hesapladı; literatürde
   bu oran için tipik değer %0,5–2. **Telafi:** config'teki `kirpma_kaybi` (%1) AC üretime tek tip
   uygulandı. Gerçekte kırpma yalnız yüksek üretimli saatlerde olur; tek tip uygulama yıllık enerjiyi
   doğru verir ama saatlik profilin en tepesini çok hafif fazla gösterir.
6. **UTC ↔ TSİ dönüşümü.** Profiller UTC'de. EPİAŞ fiyatları TSİ'de; 7 Eylül 2016 öncesinde yaz
   saati uygulaması vardı. Birleştirmede `Europe/Istanbul` saat dilimi kullanılmalı. Ayrıca PVGIS
   (HH:10 anlık) ve ERA5 (HH:00 anlık) değerleri saatlik ortalama gibi kullanılıyor; EPİAŞ saatleri
   ise "saat başı–saat sonu" dönemleri. Bu yarım saate kadar bir hizalama belirsizliği yaratır.
7. **10 yıl kısa bir iklim örneği.** P90 tahminleri, özellikle rüzgârda, tek bir yıla (2014)
   duyarlı. Sektörde genelde 20+ yıllık uzun dönem düzeltme (MCP) yapılır.
8. **Degradasyon yok.** Panel yaşlanması ve türbin performans düşüşü burada modellenmedi; finansal
   modelde (Aşama 3) yıllık oran olarak eklenecek.

## 9. Grafikler

| Dosya | İçerik |
|---|---|
| `outputs/01_uretim_modeli/aylik_kapasite_faktoru.png` | Aylık ortalama KF, GES ve RES (gölge: yıllar arası aralık) |
| `outputs/01_uretim_modeli/ay_saat_isi_haritasi.png` | Ay × saat (TSİ) ısı haritası, iki teknoloji |
| `outputs/01_uretim_modeli/yillik_kapasite_faktoru.png` | Yıllara göre KF, P50/P90 çizgileri (GES, RES, hibrit) |
| `outputs/01_uretim_modeli/sure_egrileri.png` | Süre eğrileri ve 1 MW bağlantı üstündeki kesinti alanı |
| `outputs/01_saha_taramasi/*.png` | Saha karşılaştırması: KF, hibrit göstergeleri, gün içi ve aylık profiller |

---

## Mülakat özeti

> Türkiye'de dört aday sahayı hibrit güneş-rüzgâr projesi için taradım. Güneş tarafında AB'nin
> PVGIS uydu verisini, rüzgâr tarafında ERA5 yeniden analiz verisini kullanıp pvlib ve gerçek bir
> 4,2 MW türbin güç eğrisiyle 10 yıllık saatlik üretim profilleri çıkardım. Çanakkale-Ezine'yi
> seçtim, çünkü rüzgâr kapasite faktörü %35 civarında, en iyiydi ve güneşle en güçlü
> tamamlayıcılığı gösteriyordu: rüzgâr kışın ve gece, güneş yazın ve öğlen üretiyor. Bu sayede
> 1 MW'lık aynı şebeke bağlantısına 1 MW güneş ve 1 MW rüzgâr bağladığımda üretimin sadece %5'i
> kesiliyor ve bağlantı tek başına rüzgâra göre çok daha dolu kullanılıyor. Modelimi PVGIS'in kendi
> hesabıyla %4 içinde doğruladım. ERA5'in karmaşık arazide rüzgârı düşük tahmin ettiğini bildiğim
> için bir kalibrasyon katsayısı bıraktım; bunu EPİAŞ'taki gerçek santral üretimiyle ayarlayacağım.
> İlginç bir bulgu da şuydu: saatlik ölçekte iki kaynak birbirini tamamlıyor, ama yıllar arasında
> birlikte iyi ya da birlikte kötü gidiyorlar. Yani hibritin P90'ı iyileştirmesi çeşitlendirmeden
> çok, şebeke sınırının iyi yılların fazlasını kırpmasından geliyor.
