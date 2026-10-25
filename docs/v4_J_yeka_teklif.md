# v4 Faz J — YEKA RES teklif stratejisi (açık artırma teorisi)

**Soru:** 2 Kasım 2026'daki YEKA RES-2026 yarışmalarında (7 proje, 1.500 MWe) her proje için katkı payı ne olur ve bir
istekli nerede çekilmeli?

Modüller: `src/yeka/` (`deger.py` lot değerlemesi, `muzayede.py` rakip değer modeli, en çok olabilirlik, strateji, fiyat
aşaması). `src/motor/mc.py`'ye `sozlesme` yapısı eklendi (tüccar dönem + sabit fiyatlı alım dönemi). Arayüz:
`uygulama/sayfa_yeka.py` (`/yeka`). Config: `v4.yeka`. Betik: `src/v4_J1_yeka.py` → `outputs/v4J/`,
`data/atlas/v4_yeka.json`. Testler: `tests/test_v4_J.py`.

---

## 1. Mekanizma ve veri

| | 2024 (5 yarışma) | 2025 (6) | 2026 (7, 2 Kasım) |
|---|---|---|---|
| Fiyat | 5,50 → 3,50 ABD $-sent/kWh | 5,50 → 3,50 Avro-sent/kWh | 5,50 → 3,50 Avro-sent/kWh |
| Sonuç | Hepsi tabanda | Hepsi tabanda | ? |
| Katkı payı | 60–148 bin $/MW | 56–312 bin €/MW | 10 bin €/MW'den artırma |
| Proje başına teklif | 14–26 | ~12 (75/6, TAHMİN) | 4–5 (29 teklif, 12 firma) |
| Sözleşme | — | — | 72 ay tüccar, sonra 20 yıl alım |

Kaynaklar config `v4.yeka.kaynak`'ta. Belirsiz olanlar: 2024 projelerinin il eşleşmesi (Edirne ve Gürün dışında), 2025'te
proje başına teklif sayısı, alım fiyatının endekslenip endekslenmediği (nominal sabit varsayıldı) ve tek bir kaynakta geçen
serbest dönem 4,75 €c tabanı (modellenmedi).

**Mekanizma:**
1. Önce kapalı fiyat teklifi verilir, sonra fiyat açık eksiltmeyle iner.
2. Tabanda iki ya da daha fazla istekli kalırsa yarışma katkı payında İngiliz artırmasına döner.

---

## 2. Lot değerlemesi (`src/yeka/deger.py`)

Yarışma alanı koordinatları yayımlanmadığından lotun ilindeki rüzgârlı ön tarama hücrelerinin (RES KF ≥ il 75. yüzdeliği)
medyan KF'sine en yakın hücre temsilî nokta alınır. Değerleme temsilî 100 MW RES içindir (v2 motoru). Bağlantı maliyeti TEİAŞ
görüşünden hesaplanır (TM + fider + hat km × birim maliyet); görüş yoksa en yakın uygun trafo kullanılır.

**Gelir:** 2026 sözleşmesi + 72 ay → alım 2033–2052 arası, 3,50 €c/kWh nominal (reel USD'ye kur ve avro enflasyonuyla).
Öncesi ve sonrası tüccar satıştır. Sözleşmeli yıllarda sistem kesintisi YEKDEM tazminiyle hesaplanır.

**Katkı payı:** sözleşmede peşin ödenir, 10 yılda itfa edilir:

$$
\mathrm{NPV}(K) = \mathrm{NPV}(0) - K \cdot \mathrm{MW} \cdot \text{kur} \cdot f,\qquad f = 1 - \tau \sum_{k=1}^{10} \tfrac{1}{10}(1+r)^{-k}
\quad\Rightarrow\quad \hat v = \frac{\mathrm{NPV}(0)}{\mathrm{MW}\cdot\text{kur}\cdot f}
$$

Her Monte Carlo senaryosu için bir başabaş katkı payı çıkar; $\hat v$ bunların ortalamasıdır.

**Sonuç:** bizim varsayımlarımızla (CAPEX 1,15 M$/MW, reel WACC %7, uzun dönem fiyat 58 $/MWh) her lotta $\hat v$ ≈ −590
ile −900 bin €/MW arasında. Yani bu varsayımlarla hiçbir YEKA lotu katkı payı ödemeye değmez. Nominal sabit 3,5 €c, 20 yılda
reel olarak ~%33 eriyor; tüccar dönem kısa.

---

## 3. Rakip değer modeli (`src/yeka/muzayede.py`)

### 3.1 İngiliz artırması ve sıra istatistiği

Katkı payı açık artırmasında baskın strateji, katkı payı kendi değerinize ulaşınca çekilmektir. En yüksek değerli istekli
kazanır ve ikinci en yüksek değer çekildiği anda ödemeyi yapar. Bu yüzden **gözlenen katkı payı, n istekli arasında ikinci
en yüksek değerdir.**

### 3.2 Model

$$
V_{ij} = \hat v_i + \delta + \gamma \ln(\mathrm{MW}_i/150) + s\,\varepsilon_{ij},\qquad \varepsilon_{ij} \sim \mathcal N(0,1)
$$

| Parametre | Anlamı |
|---|---|
| $\hat v_i$ | Bizim modelimizin değeri (yer, rüzgâr, bağlantı farklarını taşır) |
| $\delta$ | **Piyasa primi:** tipik istekli bizden ne kadar iyimser |
| $\gamma$ | Lot büyüklüğü etkisi (büyük lotta sermaye kısıtı, daha az ciddi istekli) |
| $s$ | İstekliler arası dağınıklık |

Rakip değerlerini bizim modele **oranla** değil **toplamsal** modelledik, çünkü $\hat v$ negatif.

### 3.3 Kesilmiş olabilirlik (seçilim yanlılığı)

İkinci en yüksek değerin yoğunluğu:

$$
f(y) = n(n-1)\,\Phi(z)^{n-2}\,(1-\Phi(z))\,\varphi(z)/s,\qquad z = (y-\mu_i)/s
$$

Katkı payı yalnız fiyat tabana inerse, yani ikinci en yüksek değer ≥ 10 bin € ise gözlenir. Tabana inmeyen bir yarışma
veride "katkı payı" olarak görünmezdi. Olabilirlik bu yüzden bu koşulla kesilir:

$$
\ell_i = \log f(y_i) - \log P\bigl(Y_{(n-1)} \ge 10^4\bigr),\qquad P = 1 - (1-S)^{n-1}(1+(n-1)S),\ S = 1 - F(10^4)
$$

Kuyrukta $P \approx \binom n2 S^2$ log-uzayda hesaplanır. İlk sürümde $P$ sıfıra kırpılıyordu ve optimizasyon bu açığı
istismar edip anlamsız bir çözüm buldu; kararlı hesapla düzeldi.

### 3.4 Tahmin (11 yarışma)

| | Büyüklük terimli | Terimsiz |
|---|---|---|
| δ (bin €/MW) | **804** (%90 GA 767–862) | — |
| γ (bin €/MW, ln birimi) | **−200** (GA −317…−160) | 0 |
| s (bin €/MW) | **116** (GA 61–151) | — |
| AIC | **272,6** | 284,9 |

Lot gücü iki katına çıkınca MW başına değer ~139 bin € düşüyor (γ·ln 2). En büyük lotlar (R25-Sivas 500 MW, R24-Edirne
410 MW) en düşük katkı paylarını gördü.

**Doğrulama** (birini dışarıda bırak; her yarışma kalan 10'la tahmin edilip tabana inme koşullu dağılımla karşılaştırıldı):
%80 aralığı 11 yarışmanın 7'sini kapsıyor (%64). 11 gözlemle dağınıklık biraz düşük tahmin ediliyor; tahmin aralıkları
dar okunmamalı. Sentetik veri testi parametreleri geri buluyor (`test_mle_parametreleri_geri_bulur`).

---

## 4. Piyasa primi neyi ifade ediyor? (`outputs/v4J/J1_model.json`)

Bizim varsayımlarımızı piyasanınkine yaklaştırınca δ'nın ne kadarı kapanıyor?

| Varsayım | δ (bin €/MW) | Kapanan |
|---|---|---|
| Bizim varsayımlarımız | 804 | — |
| CAPEX −%20 | 579 | %28 |
| CAPEX −%40 | 359 | %55 |
| Reel WACC %5 / %3 | 714 / 513 | %11 / %36 |
| Uzun dönem fiyat 70 / 85 $/MWh | 688 / 547 | %14 / %32 |
| Alım fiyatı avro enflasyonuna endeksli | 613 | %24 |
| Ömür 40 yıl | 738 | %8 |
| Bileşik: CAPEX −%20, WACC %5, fiyat 70 | 329 | %59 |
| Bileşik + endeks + 40 yıl | −220 | %127 |

**Yorum (mülakatta):** Tek bir varsayım farkı yetmiyor. Piyasanın ödediği katkı payları ancak beş iyimser varsayımın
**birlikte** alınmasıyla açıklanıyor: Çin türbinleriyle daha düşük CAPEX, daha ucuz sermaye, daha yüksek uzun dönem fiyat,
endeksli alım fiyatı ve uzun ömür. Ya piyasa bizden belirgin biçimde iyimser, ya da yarışmalar ortak değer bileşeni taşıyor
ve kazananlar aşırı ödüyor (**kazananın laneti**: en iyimser tahmine sahip olan kazanır). Bu, v3'teki "optimize edicinin
laneti" bulgusunun açık artırma versiyonu.

---

## 5. YEKA RES-2026 tahminleri (`outputs/v4J/J1_r26_tahmin.csv`)

Rakip ortalaması $\mu_j = \hat v_j + \delta + \gamma\ln(\mathrm{MW}_j/150)$. n = başvuru sayısı ile ikinci en yüksek değer
dağılımı benzetilir. **Fiyat aşaması:** ikinci en yüksek değer tabanda negatifse fiyat tabana inmez. İkinci istekli,
değerinin sıfır olduğu fiyatta çekilir: $p = 3{,}5 - Y_{(n-1)}/(\partial \hat v/\partial p)$. Eğim, lotu 4,5 €c ile yeniden
değerleyerek bulunur.

| Yarışma | MW | Teklif | P(tabana iner) | Fiyat medyanı | Katkı payı P10 / P50 / P90 (bin €/MW) | n = 12 olsaydı P50 |
|---|---|---|---|---|---|---|
| R26-Sivas | 320 | 4 | %10 | 4,16 €c | 10 / 26 / 75 | 37 |
| R26-Balıkesir-1 | 140 | 4 | %99 | 3,50 | 88 / 174 / 264 | 267 |
| R26-Balıkesir-2 | 235 | 4 | %99 | 3,50 | 76 / 161 / 251 | 253 |
| R26-Balıkesir-3 | 170 | 4 | %99 | 3,50 | 77 / 162 / 252 | 255 |
| R26-Balıkesir-4 | 140 | 5 | %100 | 3,50 | 156 / 237 / 321 | 308 |
| R26-Manisa | 235 | 4 | %91 | 3,50 | 30 / 101 / 188 | 187 |
| R26-Kütahya | 260 | 4 | %2 | 4,75 €c | 10 / 20 / 62 | 22 |

**Öngörüler:**
1. **Rekabet düştü.** Proje başına 4 teklif, 2025'in ~12'sine göre ikinci en yüksek değeri belirgin biçimde düşürüyor:
   Balıkesir lotlarında beklenen katkı payı ~260 bin yerine ~165 bin €/MW.
2. **Sivas ve Kütahya tabana inmeyebilir.** Bu iki ilde temsilî rüzgâr kaynağı zayıf (KF %31 ve %27) ve lotlar büyük. Değerler
   tabanda çoğunlukla negatif çıkıyor; yarışmanın fiyat aşamasında (~4,2 ve ~4,8 €c) bitmesi bekleniyor. 2024–25'te hiç
   görülmemiş bir sonuç.
3. **Teklif eğrisi** (arayüz): istekli kendi değer primini seçer (0 = bizim varsayımlarımız, δ = tipik istekli). Sayfa
   çekilme eşiğine göre kazanma olasılığını, beklenen ödemeyi, beklenen fazlayı ve "kazanınca değerimizin ödediğimizden
   düşük çıkma olasılığı"nı (kazananın laneti göstergesi) gösterir. Bizim varsayımlarımızla girmemek doğru karardır.

Bu tahminler yarışmadan önce (25 Ekim 2026) üretildi. 2 Kasım sonuçları modelin dışarıdan sınanması olacak.

---

## 6. Sınırlamalar

- **11 gözlem, il düzeyinde konum.** Temsilî nokta gerçek alanı temsil etmeyebilir (ör. R25-Kütahya: model düşük, gözlenen
  yüksek). Bu nedenle tahmin aralıkları geniş okunmalı.
- **Bağımsız özel değerler.** Ortak değer bileşeni (aynı fiyat görüşü) ve stratejik davranış (sinyal, firma sermaye kısıtı,
  portföy stratejisi) modelde yok. Açık artırmada çekilmeler gözlendiği için ortak değer etkisi kısmen azalır.
- **Teklif sayısı = istekli sayısı varsayıldı.** 2025 için ortalama.
- **Kapalı zarf aşaması** modellenmedi (açık eksiltme ve artırma ile aynı sonucu verdiği varsayıldı).
- Serbest dönem 4,75 €c tabanı ve alım fiyatının olası endekslenmesi değerlemeye girmedi (ikisi de değeri artırır; δ'nın bir
  kısmını açıklayabilir).
