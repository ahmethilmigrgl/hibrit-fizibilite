# v4 Faz K — Temel model (merit order) ile fiyat projeksiyonu

**Soru:** 2028–2057 boyunca Türkiye'de elektrik fiyatı ne olur ve güneş kendi fiyatını ne kadar düşürür (kanibalizasyon)?
v1–v3 bunu iki varsayımla geçiyordu: uzun dönem fiyat 58 $/MWh (beklenen değer) ve güneş yakalanma oranının 2033'e kadar
doğrusal olarak 0,60'a inmesi. Bu faz ikisini de saatlik bir arz yığını modelinden türetir.

Modüller: `src/merit/` (`veri.py` kalibrasyon verisi, `model.py` sevk ve arz eğrisi, `kalibrasyon.py`, `projeksiyon.py`,
`motor.py` v2 motoruna bağlantı). Arayüz: `uygulama/sayfa_fiyat.py` (`/fiyat`) ve saha analizinde "Fiyat görüşü". Config:
`v4.merit`. Betik: `src/v4_K1_merit_order.py` (~1 dk) → `outputs/v4K/`, `data/atlas/v4_merit.json`. Testler: `tests/test_v4_K.py`.
Kullanıcı kararı: "orta" derinlik (yakıt türü bazında toplulaştırılmış yığın; santral bazında değil).

---

## 1. Veri

EPİAŞ Şeffaflık Platformu, 2018–2025 saatlik: kaynak bazında gerçek zamanlı üretim (rüzgâr, lisanslı güneş, akarsu,
barajlı, jeotermal, biyokütle, linyit, ithal kömür, doğalgaz) ve PTF (USD). Toplam 70.128 saat, eksik yok. Veri çevrimdışı
kalibrasyonda kullanılır; uygulama yalnız sonuç paketini okur.

**Lisanssız güneş sorunu.** EPİAŞ verisi yalnız lisanslı güneşi görür; güneşin büyük kısmı (Ocak 2024: %86) lisanssızdır ve
dağıtım şebekesinde talebi düşürür. Toplam güneş = lisanslı profil × (TEİAŞ toplam kurulu / etkin lisanslı kurulu) alınır;
toplam talep = EPİAŞ toplamı + lisanssız güneş. Kalibrasyondaki termik artık yük bu ölçeklemeden etkilenmez (ikisi birbirini
götürür). 2024–25'te ulusal güneş KF'si 0,21 çıkıyor (makul).

**Kullanılabilir kapasite:** her yıl kaynağın saatlik üretiminin %99,5 yüzdeliği. 2025 değerleri: linyit 5,7, ithal kömür 10,1,
doğalgaz 17,3, barajlı 13,6 GW. Kurulu gücün altındadır (bakım, yakıt, kısıtlar).

---

## 2. Model (`src/merit/model.py`)

### 2.1 Sevk sırası (her saat)

1. **Net yük:** $N_t$ = talep − rüzgâr − güneş − akarsu − jeotermal − biyokütle − nükleer.
2. **Barajlı hidro, su doldurma (water-filling):** aylık su bütçesi tepe saatlere gider:

$$
H_t = \operatorname{clip}(N_t - \lambda_m,\ H_{\min},\ H_{\max}),\qquad \textstyle\sum_{t \in m} H_t = \text{bütçe}_m
$$

   λ_m ikiye bölmeyle bulunur. Fiyat net yükte artan olduğundan bu, sabit su değeriyle gelir enbüyüklemenin yaklaşığıdır.
3. **Depolama, günlük arbitraj:** en düşük artık yük saatlerinde şarj, en yükseklerde deşarj ($\sum D = \eta \sum S \le E$,
   güç ≤ P). Throughput, tepe eşiği taban eşiğinin üstünde kaldıkça büyütülür (iç içe ikiye bölme, günler boyunca vektörize).
4. **Termik artık yük:** $RL_t = N_t - H_t - D_t + S_t$. $RL_t < 0$ ise yenilenebilir fazlası kesilir ve fiyat 0 olur.

### 2.2 Arz eğrisi

| Bant | Termik artık yük $x$ | Fiyat |
|---|---|---|
| Zorunlu çalışma altı | $[0, M)$ | $f(M)\,(x/M)^\alpha$ — fiyat sıfıra iner; $M$ = must_oran × (linyit + kömür) |
| Linyit | $[M, K_L)$ | $MC_L + e_L \cdot CO_2$ |
| İthal kömür | $[K_L, K_L+K_C)$ | $C_y + e_C \cdot CO_2$ |
| Doğalgaz | $[K_L+K_C, K)$ | $v + (G_m + e_G\cdot CO_2)\,HR(q)$, $\;HR(q) = HR_{\min}(1 + (r-1)q^\kappa)$ |
| Kıtlık | $\ge K$ | tavan |

$q$ gaz filosundaki konumdur (verimli santraller önce). Gözlenen fiyat basamaklı değildir (kullanılabilir kapasite, ithalat,
teklif davranışı). Bu yüzden eğri bir belirsizlikle düzgünleştirilir: $p = \mathbb E[f(RL + \varepsilon)]$,
$\varepsilon \sim \mathcal N(0, \sigma_{RL}^2)$ (9 düğümlü Gauss–Hermite).

**Döngü indirimi.** Termik santraller öğle çukurunda, akşam tepesi için devrede kalmak üzere (kalkış maliyeti, asgari çalışma
süresi) marjinal maliyetin altında satar:

$$
p_t \leftarrow p_t \cdot (1 - \beta\, d_t),\qquad d_t = \frac{\max_{\text{gün}} RL - RL_t}{K}
$$

Bu terim olmadan model 2025 güneş yakalanma oranını 6,7 puan iyimser buluyordu; terimle fark 2,1 puana indi (§4).

**Doğrusallık.** Fiyat $C_y$ ve $G_m$'de doğrusaldır: $p = A + C\cdot B + G\cdot\Gamma$. Kalibrasyonun iç problemi bu yüzden
doğrusal en küçük karelerdir.

---

## 3. Kalibrasyon (`src/merit/kalibrasyon.py`)

**İç problem (doğrusal):** θ verilince aylık gaz yakıt maliyeti $G_m$ (96 ay) ve yıllık kömür bandı $C_y$ (8 yıl) sınırlı
doğrusal en küçük kareler ile bulunur (seyrek tasarım matrisi, `lsq_linear`). Bunlar fiyatın **seviyesini** taşır; bir anlamda
modelin "gözlediği yakıt fiyatlarıdır". Örneğin 2022 krizinde gaz maliyeti 85–90 $/MWh_th'ye çıkar, 2025'te 24–33'tür.

**Dış problem (doğrusal değil):** θ = (MC_L, r, κ, v, σ_RL, must_oran, α, β) eğrinin **şeklini** taşır. Nelder–Mead ile aylık
ortalamaya göre bağıl saatlik RMSE küçültülür. Mutlak RMSE'de 2022'nin yüksek fiyatları şekli bastırıyordu. $HR_{\min}$ = 1,75
sabittir; G·HR ölçek belirsizliğini kaldırır.

| θ (2018–2023) | Değer | Yorum |
|---|---|---|
| r = HR_max / HR_min | 1,56 | en verimsiz gaz santrali ~%35 daha az verimli |
| σ_RL | 3.100 MW | kullanılabilirlik + ithalat belirsizliği |
| must_oran, α | 0,43, 7,5 | ~6,8 GW altında fiyat hızla sıfıra iner |
| β | 1,32 | güçlü döngü indirimi |
| v | 17,9 $/MWh | gaz bandında sabit bileşen (VOM + kâr payı) |
| MC_L | ≈ 0 | **tanımlanamıyor**: linyit bandı nadiren marjinal |

**Tanımlanabilirlik.** Kalibrasyon dönemi 2020–2023'e kısaltılınca MC_L 0 → 55 $/MWh değişiyor. Örneklem dışı metrikler ise
neredeyse aynı kalıyor (R² 0,68 / 0,74; güneş yakalanma 0,947 / 0,854). Yani MC_L sonuçları etkilemeyen, veriden öğrenilemeyen
bir parametre. Mülakatta "her parametreye anlam yüklenmez" diye anlatılabilir.

---

## 4. Doğrulama (`outputs/v4K/K1_dogrulama.csv`)

θ 2018–2023'te kalibre edildi. 2024–2025'te yalnız $G_m$ ve $C_y$ yeniden tahmin edildi (seviye bilgisi); şekil dışarıdan
sınanıyor.

| Yıl | Dönem | R² | RMSE | Gün içi korelasyon | Güneş yakalanma (göz. / model) | Rüzgâr yakalanma |
|---|---|---|---|---|---|---|
| 2018 | kalibrasyon | 0,61 | 5,9 | 0,93 | 1,08 / 1,09 | 0,99 / 1,00 |
| 2021 | kalibrasyon | 0,78 | 9,1 | 0,96 | 1,04 / 1,04 | 1,00 / 1,01 |
| 2022 | kalibrasyon | 0,79 | 26,6 | 0,90 | 1,03 / 1,06 | 0,95 / 0,96 |
| 2023 | kalibrasyon | 0,85 | 16,6 | 0,88 | 0,90 / 0,95 | 0,96 / 0,97 |
| **2024** | **test** | **0,68** | **11,0** | **0,91** | **0,91 / 0,95** | **0,97 / 0,97** |
| **2025** | **test** | **0,73** | **10,3** | **0,93** | **0,83 / 0,86** | **0,99 / 0,99** |

**Değerlendirme:**
- Rüzgâr yakalanma oranı neredeyse birebir tutuyor.
- Güneş yakalanma oranında model 2–4 puan iyimser: öğle çukurunu biraz eksik açıklıyor. Bu, projeksiyondaki kanibalizasyonun
  alt sınır olarak okunması gerektiği anlamına gelir.
- Model sıfır fiyatlı saatleri üretmiyor (gözlenen %0,6–1).

---

## 5. Projeksiyon (`src/merit/projeksiyon.py`)

**Şekil yılları:** 2024 ve 2025. Talep, rüzgâr/güneş kapasite faktörü ve akarsu profilleri buradan alınır; talep 2025 düzeyine
ölçeklenip büyür. Barajlı hidro bütçesi 2018–2025 ay ortalamasıdır (ortalama hidroloji). Gaz maliyeti 2025'in aylık profili ×
senaryo çarpanı, kömür 2025 seviyesi; karbon her yakıtın emisyon yoğunluğuyla eklenir.

| Senaryo | 2035 güneş / rüzgâr / nükleer / depolama | Talep | Karbon 2035 | Kaynak |
|---|---|---|---|---|
| Baz | 52,9 / 29,6 / 7,2 / 7,5 GW (2 sa) | %3/yıl | 23 $/t | ETKB Ulusal Enerji Planı (2023) |
| Hızlı dönüşüm | 77 / 43 / 7,2 / 15 GW (4 sa) | %3,5 | 46 $/t | ETKB 2035 rüzgâr + güneş 120 GW hedefi (Ekim 2024) |
| Yavaş | 40 / 23 / 4,8 / 3 GW | %2 | 6 $/t | TAHMİN |

### 5.1 Sonuçlar (`outputs/v4K/K1_projeksiyon.csv`)

| | 2030 | 2035 | 2040 | 2050 |
|---|---|---|---|---|
| **Baz** — fiyat $/MWh | 58,6 | 61,8 | 69,3 | 81,6 |
| güneş yakalanma | 0,62 | 0,48 | 0,36 | 0,22 |
| rüzgâr yakalanma | 0,98 | 0,97 | 0,95 | 0,98 |
| sıfır fiyatlı saat | %3,0 | %7,3 | %11,2 | %23,9 |
| **Hızlı dönüşüm** — fiyat | 61,8 | 62,7 | 75,1 | 102,7 |
| güneş yakalanma | 0,55 | 0,34 | 0,33 | 0,31 |
| **Yavaş** — fiyat | 67,3 | 66,0 | 71,5 | 85,2 |
| güneş yakalanma | 0,73 | 0,63 | 0,55 | 0,40 |

**Yorum:**
1. **Fiyat seviyesi önce düşer, sonra yükselir.** 2030'a kadar nükleer ve yenilenebilir gazı iter (baz 58,6). Sonra talep
   büyümesi ve karbon fiyatı gazı yeniden marjinal yapar. Seviyelendirilmiş fiyat (2028–2057, %7) baz 67,3, hızlı dönüşüm 73,9,
   yavaş 71,2 $/MWh; hepsi v1'in 58'inin üstünde.
2. **Güneş kanibalizasyonu v1 varsayımından çok daha derin.** v1: 2033'te 0,60'ta durur. Merit order (baz): 2035'te 0,48,
   2040'ta 0,36. Güneşin yakaladığı fiyat 2030'da 36 $/MWh, 2040'ta 25 $/MWh; rüzgârınki 58 → 66.
3. **Rüzgâr korunuyor.** Rüzgâr yakalanma oranı 0,93–0,99'da kalıyor; üretimi akşam/gece ağırlıklı ve güneşle ters korelasyonlu.
4. **Hızlı dönüşümde paradoks:** daha fazla yenilenebilir, daha yüksek ortalama fiyat (2050: 103). Güneş öğle saatlerini
   sıfırlıyor; akşam saatleri daha yüksek talep ve karbonla gaza kalıyor. Ortalama fiyat yükselirken güneşin değeri düşüyor.

### 5.2 Duyarlılık (baz, 2035; `K1_duyarlilik.csv`)

| Değişiklik | Fiyat | Güneş yakalanma |
|---|---|---|
| Baz | 61,8 | 0,48 |
| Depolama yok / ×2 | 54,3 / 65,0 | **0,35 / 0,60** |
| Gaz −%30 / +%30 | 51,5 / 72,1 | 0,51 / 0,46 |
| Karbon yok / ×2 | 52,0 / 71,6 | 0,46 / 0,50 |
| Talep %2/yıl | 53,2 | 0,40 |

**Depolama, güneş kanibalizasyonunun en güçlü kaldıracı:** iki katı depolama 2035 yakalanma oranını 0,48'den 0,60'a çıkarıyor.
Gaz ve karbon ise seviyeyi taşıyor. Hibrit santral kararına doğrudan bağlanıyor: batarya hem kendi arbitraj gelirini hem de
GES'in yakaladığı fiyatı korur, ama sistem düzeyinde depolama arttıkça bu fark kapanır.

---

## 6. Motora aktarım (`src/merit/motor.py`)

`KullaniciVarsayimlari(fiyat_kaynagi="merit:<senaryo>")` (arayüzde Varsayımlar → Fiyat görüşü):
- **Fiyat:** `fiyat_senaryolari.seviye` (baz = seviyelendirilmiş fiyat; düşük/yüksek aynı oranla) ve
  `monte_carlo.fiyat_uzun_ortalama.seviye` (Monte Carlo'nun beklenen değeri).
- **Kanibalizasyon:** motorun "taban yılına kadar doğrusal iniş, sonra sabit" yolunun merit order güneş yolu üzerine iskonto
  ağırlıklı en küçük karelerle uydurulmuş taban oranı ve yılı. Baz: 0,25 / 2042 (uyum RMSE 0,03); hızlı: 0,33 / 2034; yavaş: 0,40 / 2047.
- **Monte Carlo kanibalizasyon tabanı:** üçgen(0,85 t; t; 1,2 t), TAHMİN.

**Motorda yapılan genelleştirmeler:**
- Fiyat şekli (`1 − d·g`) d > 1'e izin verecek ve negatif değerler sıfırda kırpılacak şekilde genişletildi. Eski şekil güneş
  yakalanma oranını ~0,45'in altına indiremiyordu.
- İşletme tablosu ızgarası gerektiğinde aşağı uzar (varsayılan config'de değişmez, 0,55).
- Varsayılan ayarlarda tüm sonuçlar birebir aynıdır (mevcut testler geçer).

**Ezine örneği (hızlı tarama):** yalnız RES NPV'si varsayılanda −4,5, merit order bazda +6,4 M$; RES + GES −8,7 → +0,8; GES
−14,8 → −18,8 (seviye yükselse de güneşin yakaladığı fiyat 42 → 40 $/MWh). Merit order görüşü rüzgâr ve batarya lehine.

---

## 7. Sınırlamalar

- **Toplulaştırılmış yığın:** santral bazında değil. İthalat/ihracat, iletim kısıtları ve bölgesel fiyat yok (Türkiye tek
  fiyat bölgesi, bu kabul edilebilir).
- **Hidroloji ortalama:** kurak/ıslak yıl belirsizliği projeksiyonda yok (Monte Carlo'nun fiyat süreci kısmen taşır).
- **Döngü indirimi indirgenmiş bir form:** birim taahhüdü (unit commitment) modeli değil. Yüksek güneş paylı gelecekte
  davranışın değişmesi mümkün.
- **Senaryo girdileri:** yakıt, karbon, kapasite ve depolama yolları varsayımdır (kaynaklar config `v4.merit.kaynak`'ta;
  ara noktalar TAHMİN).
- **Güneş kanibalizasyonu alt sınır:** doğrulamada model güneş yakalanma oranını 2–4 puan iyimser buluyor.
