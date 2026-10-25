# v4 Faz H — Bankaya sunulabilir verim (P50/P90) ve proje finansmanı

Bu faz şu soruyu yanıtlar: **"Bu santrale bir banka ne kadar borç verir ve bu borç ne kadar risklidir?"** Önceki fazlar
projenin değerini (NPV) ölçüyordu. Bankanın sorusu farklıdır: borç her yıl, en kötü makul senaryoda bile ödenebilmelidir.
Bu yüzden ortalama değil, aşağı yön senaryoları (P90, P99) ve nakit akışının yıllık zamanlaması önemlidir.

Modüller: `src/finansman/` (`verim.py` belirsizlik bütçesi, `borc_lp.py` borç LP'si, `selale.py` nakit şelalesi ve
olasılık tabanlı boyutlandırma, `motor.py` tam analize bağlantı). Arayüz: `uygulama/v4_bolumler.py` (tam analiz sonucunda
"Proje finansmanı" bölümü). Config: `v4.verim`, `v4.finansman`. Anahtar: `KullaniciVarsayimlari(finansman=True)`
(varsayılan); `False` v3 davranışını aynen verir. Doğrulama: `src/v4_H1_finansman.py` → `outputs/v4H/`. Testler:
`tests/test_v4_H.py`.

---

## 1. Kavramlar (ilk kez görenler için)

| Terim | Anlamı |
|---|---|
| **P50 / P90 / P99** | Yıllık üretimin aşılma olasılığı. P90: üretimin %90 olasılıkla bu değeri aşacağı seviye. P50 beklenen değere yakındır. |
| **1 yıllık / 10 yıllık P90** | Tek bir yılın mı, 10 yıllık ortalamanın mı P90'ı. Kötü hava yılları ortalamada telafi edildiği için 10 yıllık P90 P50'ye daha yakındır. |
| **CFADS** | Cash flow available for debt service: borç servisine esas nakit akışı (FAVÖK − vergi − yatırım harcamaları). |
| **DSCR** | Debt service coverage ratio = CFADS / borç servisi. Banka her yıl için bir alt sınır ister (ör. P50'de 1,35). |
| **Heykelsi (sculpted) geri ödeme** | Her yılın borç servisi o yılın CFADS'sine göre ayarlanır: DSCR her yıl aynı kalır. |
| **LLCR** | Loan life coverage ratio: vade boyunca CFADS'nin bugünkü değeri / borç. |
| **DSRA** | Debt service reserve account: kötü bir yılda kullanılmak üzere tutulan rezerv (burada 6 aylık servis). |
| **Dağıtım kilidi (lock-up)** | DSCR eşiğin (1,10) altına düşerse kâr payı dağıtılamaz; nakit projede kalır. |
| **Temerrüt** | DSRA da tükendikten sonra borç servisinin ödenememesi. |

---

## 2. Enerji verimi belirsizlik bütçesi (`src/finansman/verim.py`)

### 2.1 Bileşenler

Her bileşen yıllık enerjiye göre bağıl standart sapmadır (σ/P50). İki tür vardır:

- **yıllık:** her yıl yeniden çekilir, T yıllık ortalamada σ/√T'ye iner.
- **kalıcı:** proje ömrü boyunca sabit kalan tahmin hatası.

| Bileşen | Tür | RES | GES | Kaynak |
|---|---|---|---|---|
| Yıllar arası değişkenlik (IAV) | yıllık | sahanın 2014–2023 yıllık üretimi | aynı | veriden |
| Referans dönem (σ_IAV/√10) | kalıcı | ≈ %2 | ≈ %1 | veriden |
| İklim temsiliyeti | kalıcı | %2 | %2 | TAHMİN (endüstri %1–3) |
| Model ve kalibrasyon | kalıcı | atlas güven seviyesinden (`res_sigma`) | — | v2 atlas |
| Işınım veri seti / PV modeli | kalıcı | — | %4 / %2 | PVGIS-SARAH; TAHMİN |
| Yıllık kullanılabilirlik | yıllık | %1,5 | %0,5 | MC ile aynı; TAHMİN |

**Çift sayımdan kaçınma.** Atlas model hatası, mevcut santrallerin *ölçülen* üretimiyle tahmin arasındaki farktır. İz
kaybı, elektrik kayıpları ve ortalama kullanılabilirlik bu farkın içindedir. Bu yüzden ayrıca iz/kayıp belirsizliği
eklenmez; yalnız atlasın göremediği yıllık dalgalanma ve gelecek iklimin geçmişe benzememe payı eklenir.

### 2.2 Birleştirme

$$
\sigma(T)^2 = \sum_{j \in \text{yıllık}} \frac{\sigma_j^2}{T} + \sum_{j \in \text{kalıcı}} \sigma_j^2,
\qquad P_x(T) = P50 \cdot \bigl(1 - z_x\, \sigma(T)\bigr),\quad z_{0,90} = 1{,}2816
$$

Hibritte bileşenler MWh cinsinden toplanır. IAV ve referans dönem terimleri RES ile GES arasında veriden ölçülen ρ ile
ilişkili, model hataları bağımsızdır:

$$
\operatorname{Var} = (E_r \sigma_r)^2 + (E_g \sigma_g)^2 + 2\rho\, E_r E_g\, \sigma_r \sigma_g
$$

ρ < 1 ise hibritin bağıl belirsizliği tek teknolojilerin ağırlıklı ortalamasından küçüktür (test:
`test_butce_hibrit_cesitlendirme`). Ezine'de yıllık RES–GES korelasyonu ρ ≈ 0,80 olduğundan bu kazanç küçük kalır.

### 2.3 Simülasyonla karşılaştırma

Monte Carlo (tam analiz) her senaryoda şebeke kısıtı, batarya ve sistem kesintisi sonrası **satılan** enerjiyi üretir;
simülasyon P değerleri bunun yüzdelikleridir (`verim.simulasyon_p`).

| Ezine, 50,4 MW RES | P90 (1 yıl) | P99 (1 yıl) | P90 (10 yıl) | P99 (10 yıl) |
|---|---|---|---|---|
| Analitik (brüt, normal) | 0,781 | 0,602 | 0,798 | 0,634 |
| Simülasyon (satılan) | 0,799 | 0,655 | 0,823 | 0,694 |
| Saha ölçümü sonrası (analitik) | 0,875 | 0,774 | 0,910 | 0,836 |

**Fark neden var?** P90'da ikisi yakın. P99'da simülasyon daha iyimser, çünkü Monte Carlo model hatasını log-normal
çeker ($m \sim \text{LogNormal}(-\sigma^2/2, \sigma)$). Log-normalin sol kuyruğu normalinkinden incedir: σ = %15,3'te
%1'lik dilim log-normalde 0,69, normalde 0,64. Ayrıca şebeke kesintisi üst kuyruğu kırpar ve P50'yi aşağı çeker. Banka
pratiği normal yaklaşımdır; borç boyutlandırmada analitik oranlar kullanılır, yani ihtiyatlı taraf.

**Baskın bileşen.** Ezine'de RES model belirsizliği σ = %15,3 (atlas, yüksek güven). Yıllar arası değişkenlik (%6,9)
bunun yarısından azdır. Kalıcı olduğu için 10 yıllık ortalamada da sönmez. Bu yüzden 10 yıllık P90 (0,80) 1 yıllığa
(0,78) çok yakın. Ölçülmemiş bir sahanın asıl belirsizliği hava değil, tahminin kendisidir.

---

## 3. Çok senaryolu borç boyutlandırma LP'si (`src/finansman/borc_lp.py`)

### 3.1 Formülasyon

**Kümeler**
- $k \in \{1, \dots, V\}$: vade içindeki işletme yılları ($V$: borç vadesi)
- $c \in C$: kredi veren senaryoları (P50, P90-1y, P99-1y, Aşağı yön)

**Parametreler**
- $\mathrm{CFADS}_{c,k}$: senaryo $c$'de yıl $k$'nın CFADS'si (nominal USD)
- $\mathrm{DSCR}_{c,k}$: harmanlanmış asgari DSCR (§3.2)
- $i$: nominal faiz (%8)
- $g$: azami borç/CAPEX (%75)
- $\mathrm{CAPEX}$: nominal yatırım

**Karar değişkenleri**
- $D \ge 0$: COD'daki borç
- $s_k \ge 0$: yıl $k$'nın borç servisi
- $B_k \ge 0$: yıl sonu bakiye ($B_0 = D$, $B_V = 0$)

**Amaç**

$$\max\; D$$

**Kısıtlar**

$$
\begin{aligned}
&\text{(bakiye)} && B_k = (1+i)\,B_{k-1} - s_k && \forall k\\
&\text{(DSCR)} && s_k \le \mathrm{CFADS}_{c,k} / \mathrm{DSCR}_{c,k} && \forall c, k\\
&\text{(anapara)} && s_k \ge i\, B_{k-1} && \forall k:\ \min_c \mathrm{CFADS}_{c,k} > 0\\
&\text{(kaldıraç)} && D \le g \cdot \mathrm{CAPEX}
\end{aligned}
$$

**Sezgi.** Bakiye kısıtları zincirlenince $D = \sum_k s_k (1+i)^{-k}$ olur: borç, gelecekteki servislerin bugünkü
değeridir. Amaç borcu büyütmek olduğundan her yılın servisi, o yılın **en sıkı** DSCR kısıtına kadar çıkar. Anapara
kısıtı bakiyenin büyümesini (negatif amortisman) engeller. CFADS ≤ 0 olan yıllarda (ör. batarya yenileme) uygulanmaz;
uygulansaydı LP borcu o yıldan önce kapatmak zorunda kalırdı (test: `test_lp_negatif_cfads_yili_vadeyi_kisaltmaz`).

**Doğrulama.** Tek senaryo ve anapara kısıtı yokken LP, v1'in kapalı form heykelsi borcuyla birebir aynıdır (göreli fark
0; `outputs/v4H/H1_ozet.json`, `test_lp_tek_senaryo_kapali_form`).

### 3.2 Gelir türüne göre DSCR

Bankalar her gelir türüne aynı güveni duymaz. Yıllık gelir üç paya ayrılır: sözleşmeli $p_s$ (YEKDEM/PPA), batarya
$p_b$ (arbitraj + SFK) ve tüccar enerji $p_t$. Harmanlanmış eşik:

$$
\mathrm{DSCR}_{c,k} = \Bigl(\tfrac{p_{s,k}}{\mathrm{DSCR}^s_c} + \tfrac{p_{b,k}}{\mathrm{DSCR}^b_c} + \tfrac{p_{t,k}}{\mathrm{DSCR}^t_c}\Bigr)^{-1}
$$

| Senaryo | Enerji | Fiyat | SFK | Tüccar | Sözleşmeli | Batarya |
|---|---|---|---|---|---|---|
| P50 | P50 | beklenen | beklenen | 1,35 | 1,20 | 1,75 |
| P90-1y | P90 (1 yıl) | beklenen | beklenen | 1,20 | 1,10 | 1,50 |
| P99-1y | P99 (1 yıl) | beklenen | beklenen | 1,00 | 1,00 | 1,20 |
| Aşağı yön | P50 | × 0,80 | × 0,50 | 1,00 | 1,00 | 1,00 |

Eşikler TAHMİN'dir (Türkiye için kamuya açık kredi koşulu yok; kaynaklar config'de). Vade tüccar 15, PPA 18, YEKDEM 12 yıl.

**Kredi veren senaryosunun girdileri.** Monte Carlo'nun gecikmesiz ortalama yollarından gelir: fiyat (tavanlı kriz yılları
hariç), kanibalizasyon, SFK fiyatı, sistem kesintisi ve YEKDEM katılım olasılığı. Hava yılları ortalanır. Enerji oranı
$P_x/P50$ hem RES hem GES çarpanına uygulanır. İşletme tablosunun ızgarası dışına düşen RES çarpanı ızgara sınırında
okunur, kalan oran üretime orantılı uygulanır (`m_disdeger`). P50 senaryosunun vade içi CFADS'si Monte Carlo ortalamasının
%100–102'si çıkar (`kredi_p50_mc_orani`). Kalan küçük fark vergideki doğrusal olmayan etkiden gelir.

### 3.3 Dual değerler: hangi kısıt bağlıyor?

HiGHS her kısıt için bir dual değer (gölge fiyat) döndürür. Bağlayıcı bir DSCR kısıtında dual $(1+i)^{-k}$'dir: o yılın
izin verilen servisini 1 $ artırmak borcu bugünkü değeriyle artırır. Arayüz, yıl başına bağlayan senaryoyu sayar:

| Ezine | Bağlayan senaryo (yıl sayısı) | Yorum |
|---|---|---|
| 50,4 MW RES, tüccar | P99-1y: 15 | Model belirsizliği büyük (σ %15): en kötü %1'lik yıl her yılı bağlıyor |
| Hibrit (RES 25 + batarya 30 MW), tüccar | P99: 7, Aşağı yön: 4, P50: 2, P90: 2 | İlk yıllarda SFK geliri yüksek → aşağı yön senaryosu bağlıyor |

---

## 4. Nakit şelalesi ve olasılık tabanlı boyutlandırma (`src/finansman/selale.py`)

### 4.1 Şelale

Borç FID'de boyutlanır; servis planı sabittir. Monte Carlo'nun her senaryosu yıllık şelaleden geçer:

1. Kullanılabilir nakit = CFADS + faiz vergi kalkanı
2. Borç servisi (önceki yıldan gecikmiş servis varsa faiziyle birlikte)
3. Açık varsa DSRA'dan çekilir; DSRA da yetmezse **temerrüt** (gecikmiş servis birikir)
4. DSRA hedefine tamamlanır (sonraki yılın servisinin 6/12'si)
5. DSCR < 1,10 ya da gecikmiş servis varsa nakit kilit hesabında kalır; test geçilince serbest kalır
6. Kalan nakit öz kaynağa dağıtılır. DSRA'nın ilk dolumu COD'da öz kaynakla yapılır.

Çıktılar: P(temerrüt), P(DSRA kullanımı), P(dağıtım kilidi), asgari DSCR dağılımı, öz kaynak IRR'ının P10/P50/P90'ı.
Hesap vektörizedir: 2.000 senaryo × 30 yıl birkaç milisaniyede biter.

### 4.2 Olasılık tabanlı boyutlandırma

DSCR kuralları yalnız seçilmiş birkaç senaryoya bakar. Monte Carlo ise fiyat, SFK doyumu, hava ve model hatasının tüm
birleşimlerini görür. İkinci bir boyutlandırma tanımlanır:

$$
\max_{a \in [0, \bar a]}\ a \quad \text{s.t.}\quad \Pr\bigl[\text{temerrüt} \mid a \cdot s\bigr] \le \mathrm{PD}_{\text{hedef}} = \%5
$$

LP'nin servis profili $s$ şekli korunarak $a$ ile ölçeklenir. Her senaryoda servis büyüdükçe açık büyüdüğü için temerrüt
olasılığı $a$'da monotondur; bu yüzden ikiye bölme yöntemi yeterlidir (test: `test_pd_hedefli_monoton`). Bu bir
**şans kısıtlı** (chance-constrained) boyutlandırmadır.

### 4.3 Sonuçlar (Ezine; `outputs/v4H/H1_borc.csv`)

| Tasarım | Yapı | Borç, DSCR kuralları | P(temerrüt) | Borç, PD ≤ %5 | Saha ölçümü sonrası |
|---|---|---|---|---|---|
| Hibrit (RES 25,2 + BESS 30/60) | Tüccar | 25,8 M$ (%59) | %43 | 5,9 M$ (%13) | 28,0 M$ |
| | YEKDEM opsiyonu | 23,1 M$ (%53) | %39 | 7,3 M$ (%17) | 25,2 M$ |
| | PPA | 23,6 M$ (%54) | %40 | 10,1 M$ (%23) | 29,1 M$ |
| 50,4 MW RES | Tüccar | 22,0 M$ (%35) | %22 | 9,1 M$ (%14) | 33,5 M$ |
| | YEKDEM opsiyonu | 18,6 M$ (%29) | %15 | 10,5 M$ (%17) | 29,2 M$ |
| | PPA | 20,5 M$ (%32) | %12 | 12,5 M$ (%20) | 32,4 M$ |

Temerrüt olasılığı – borç oranı eğrisi: `outputs/v4H/H1_pd_egrisi.png`.

### 4.4 Yorum (mülakatta anlatılacak)

1. **Kurallar riski kaçırıyor.** DSCR kurallarıyla boyutlanan borçta vade boyunca temerrüt olasılığı %12–43. Kredi veren
   senaryoları enerji riskini (P90/P99) iyi temsil ediyor. Tüccar projede asıl risk ise fiyat seviyesinin yıllarca düşük
   kalması ve SFK fiyatının doyumla çökmesi; bunlar tek bir aşağı yön senaryosuyla yakalanamıyor. SFK geliri en kötü
   %10'luk dilimde beklenen değerin üçte birine iniyor (CFADS 1. yıl P10 2,2 M$, ortalama 7,3 M$).
2. **Batarya, borç kapasitesini SFK'ya bağlıyor.** Hibritte ilk 5 yılın gelirinin %44'ü bataryadan. Kurala göre borç
   yüksek (%59), ama PD hedefine göre en düşük (%13). SFK'ya dayalı tüccar batarya, sözleşmesiz haliyle
   bankalanabilir değil. Çözüm sözleşmeleştirmek (tolling, kapasite sözleşmesi) ya da öz kaynakla finanse etmek.
3. **Sözleşme borç riskini düşürüyor.** RES'te temerrüt olasılığı tüccar %22 → YEKDEM %15 → PPA %12. PD hedefli borç da
   aynı sırayla artıyor (%14 → %17 → %20). Sözleşmenin değeri NPV'den çok finansman kapasitesinde görünüyor.
4. **Saha ölçümünün değeri büyük.** Ölçüm sonrası RES model belirsizliği %15'ten %6'ya inince P99 0,60 → 0,77 ve kural
   tabanlı borç 22 → 33,5 M$ (+%52). Ölçüm belirsizliğine duyarlılık (`H1_olcum_degeri.csv`): σ = %4 → 34,3 M$, %8 → 31,5,
   %10 → 29,3. Bir ölçüm kampanyası (~0,3–0,5 M$) borç kapasitesini 7–12 M$ artırıyor; bu, öz kaynak ihtiyacını aynı
   tutarda düşürür.
5. **Projenin kendisi zayıf.** İki tasarımda da E[NPV] negatif (−1,6 / −9,5 M$). Temerrüt olasılığının yüksekliği kısmen
   bundan; ekonomisi güçlü bir projede aynı kurallar daha düşük risk verir. Borç oranının Türkiye RES pratiğindeki
   %70–75'in altında kalması da bununla tutarlı.

---

## 5. Sınırlamalar

- **COD gecikmesi şelalede yok.** Borç metrikleri COD'a koşulludur. NPV dağılımı gecikmeyi içerir.
- **Profil şekli sabit.** PD hedefli boyutlandırma LP profilini ölçekler; profil şeklinin de seçildiği bir stokastik program
  (servis profili + şans kısıtı) daha fazla borç bulabilir. Bu bir iyileştirme olarak açık.
- **Temerrüt tanımı katı.** Tek bir yılın ödenemeyen servisi temerrüttür. Gerçekte sponsor desteği, yeniden yapılandırma
  ve kredi verenin feragati vardır; olasılıklar üst sınır olarak okunmalı.
- **GES model belirsizliği kesinti etkileşimini ihmal eder.** `m_ges` üretime orantılı uygulanır.
- **Eşikler TAHMİN.** DSCR, DSRA, kilit ve PD hedefi kamuya açık Türkiye kredi koşullarından değil, genel proje finansmanı
  pratiğinden. Hepsi config'de değiştirilebilir.

## 6. v3 ile tutarlılık

`finansman=True` (varsayılan) NPV Monte Carlo'suna yalnız GES model belirsizliğini (`m_ges`, ortalaması 1) ve ızgara dışı
RES çarpanının orantılı okunmasını ekler (önceden ızgara sınırında kırpılıyordu). Ezine'nin hibrit tasarımında E[NPV]
−1,67 → −1,62 M$, P(NPV > 0) %39,0 → %39,2 (`finansman=False` ile karşılaştırma); fark yalnız ızgara dışı RES çarpanlarından,
çünkü tasarımda GES yok. Tüm mevcut testler geçer. `finansman=False` v3 davranışını aynen verir.
