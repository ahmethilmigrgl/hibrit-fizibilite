# v3 Faz F — Portföy optimizasyonu ve performans izleme

Bu belge iki bölümden oluşur. §0 Faz F ön adımıdır (Ö1 v1 çift sayım etkisi, Ö2 bağlantı mesafesi belirsizliği). §1'den
itibaren Faz F gelir.

---

## 0. Ön adım

### 0.1 Ö1 — v1'de sigorta ve arazi kirası çift sayımı

Ayrıntı ve tüm tablolar: **[docs/v1_duzeltme_notu.md](v1_duzeltme_notu.md)**. Kod: `src/finans/model.py`
(`v1_cift_sayim_duzeltmesi`, `Varsayimlar.sigorta_res_haric`), `src/risk/degerleme.py`. Anahtar: config
`v1_duzeltme.cift_sayim` (varsayılan false) ya da `V1_CIFT_SAYIM=1`. Betikler `src/v3_O1_v1_duzeltme.py`,
`src/v3_O1_v2_kontrol.py` → `outputs/v3F/O1_*`, düzeltilmiş Monte Carlo `outputs/07/v1_cift_sayim/`.

| v1 nihai baz vaka (Ezine, YEKDEM opsiyonu + tüccar) | v1 | Düzeltilmiş |
|---|---|---|
| Beklenen NPV | −1,66 M$ | **+0,92 M$** |
| P(NPV > 0) | %42,4 | %48,7 |
| CVaR %5 | −28,0 M$ | −25,1 M$ |
| Azami edinim primi | 0 | 0,92 M$ |
| Durum tespiti bilgi değeri | 0 | 1,16 M$ |
| Karar (kural: E[NPV] > 0 ⇒ (a)) | (b) rafa kaldır | **(a) durum tespiti + ≤0,9 M$ teklif** |

- Excel modelinde düzeltilmiş senaryo seçilebilir. Senaryo sayısı 48'den 96'ya çıktı; 96/96 senaryo Python ile mutabık
  (azami fark 0), formül hatası yok.
- v2 motorunda aynı çift sayım var: Ezine, Gürün ve Susurluk'ta E[NPV] +2,4…+2,6 M$ iyileşiyor, karar değişmiyor. v3
  varsayılanında (FSA) çift sayım yok.

### 0.2 Ö2 — Bağlantı mesafesi belirsizliği

**Sorun.** Model en yakın uygun gerilimli trafo merkezine bağlanıldığını varsayıyor. TEİAŞ ise kapasitesi olan bir
merkezi ya da mevcut bir hatta girdi-çıktı bağlantısını atar. Lisanslı projeler için trafo merkezi kapasitesi
yayımlanmadığından atamayı önceden bilemeyiz; bu bir belirsizliktir.

**Veri.** YEKA RES-2025 (6) ve RES-2026 (8) bağlantı görüşleri: `data/atlas/teias_yeka_baglanti.csv`. Yarışma alanlarının
koordinatları yayımlanmadığı için "aynı yer" il düzeyinde yaklaşıklandı. Projenin ilindeki rüzgârlı ön tarama hücrelerinde
(il içi RES KF ≥ 75. yüzdelik) atanan gerilim sınıfına uygun en yakın trafo uzaklığının medyanı × güzergâh çarpanı 1,25
alındı (`src/v3_O2_baglanti_orani.py` → `data/atlas/baglanti_oranlari.csv`, `baglanti_orani.json`).

$$
r_i = \frac{\text{TEİAŞ'ın atadığı hat uzunluğu}_i}{1{,}25 \cdot \operatorname{medyan}_{c \in \text{il}_i} d_c^{\text{en yakın}}}
,\qquad \ln r \sim \mathcal{N}(\mu, \sigma^2)
$$

| | Değer |
|---|---|
| Gözlem | 14 santral alanı (4'ü mevcut hatta girdi-çıktı) |
| Medyan $e^{\mu}$ | 0,73 |
| Ortalama $e^{\mu + \sigma^2/2}$ | 1,14 |
| $\sigma$ (ln) | 0,94 (bootstrap %5–95: 0,61–1,14) |
| P10 / P90 | 0,22 / 2,45 |
| Gözlenen aralık | 0,13 (Sivas R26, girdi-çıktı) – 3,29 (Sivas R25, 210 km) |
| Girdi-çıktı hariç medyan | 1,10 |

**Yorum.** Atamalar ortalamada en yakın trafoya göre biraz daha uzun (×1,14) ama asıl özellik dağınıklık. TEİAŞ bazen çok
yakın bir hatta girdi-çıktı veriyor, bazen 200 km'lik yeni hat istiyor. Faz E'deki "2–12 kat uzun" yorumu, 400 kV
atamaları 154 kV'luk en yakın trafoyla kıyasladığı için yanlıştı; düzeltildi.

**Modele bağlantı** (`src/cbs/baglanti.belirsizlik`, `carpan_ornekle`; config `v3.baglanti.belirsizlik.aktif`):

$$
C(r) = C^{TM}_V + C^{fid}_V + r \cdot g\, d\, c^{hat}_V + C^{yol}, \qquad
\text{CAPEX}_{şebeke} = \mathbb{E}[C(r)] = C(e^{\mu + \sigma^2/2})
$$

- Deterministik kısımlar (MILP, hızlı tarama, başabaş) beklenen değeri kullanır.
- Monte Carlo'da her senaryoda $r_s$ çekilir ve şebeke CAPEX'i $C(r_s)/\mathbb{E}[C]$ ile çarpılır
  (`girdi["capex_sebeke"]`, `degerleme.nakit_akislari`). Çarpanın ortalaması 1.
- Hızlı taramada saha kartı beklenen değeri ve P10–P90 aralığını gösterir.
- Varsayım: oran 400 kV atamalarından ölçüldü (14'ün 12'si) ve 154 kV'luk 50 MW sahalara aktarıldı (iki 154 kV
  gözlemi 1,01 ve 1,23).

**Etki** (tam analiz, 2 çekirdek; `outputs/v3F/O2_once_sonra.csv`):

| Saha | Bağlantı, öncesi (M$) | Bağlantı, beklenen (P10–P90) | E[NPV] öncesi → sonrası | CVaR %5 öncesi → sonrası | Başabaş | Karar |
|---|---|---|---|---|---|---|
| Ezine | 5,59 | 5,64 (5,36–6,02) | −1,63 → −1,67 | −19,1 → −19,3 | 60,5 → 60,6 | rafa kaldır |
| Gürün | 10,30 | 10,76 (7,73–15,06) | −6,98 → −7,36 | −27,0 → −30,4 | 67,4 → 67,9 | rafa kaldır |
| Susurluk | 7,43 | 7,73 (5,76–10,51) | −3,34 → −3,58 | −28,4 → −29,7 | 61,3 → 61,5 | rafa kaldır |

Beklenen değerdeki etki küçük (−0,04…−0,37 M$), kuyruktaki etki büyük (CVaR −0,1…−3,3 M$). Trafoya yakın sahada
(Ezine 1,6 km) hat kalemi küçük olduğu için belirsizlik neredeyse önemsiz. Uzak sahada (Gürün 17,5 km) bağlantı tek
başına ±4 M$'lık bir risk kalemi.

---

## 1. Faz F özeti

| | |
|---|---|
| Portföy kodu | `src/portfoy/` — `adaylar.py` (aday seçimi, ortak senaryolarla değerleme), `sinerji.py` (işletme ölçeği, yedek parça havuzu, bugünkü değer çarpanları), `model.py` (iki aşamalı stokastik MILP), `analiz.py` (çeşitlendirme ayrıştırması, kaba kuvvet), `veri.py` |
| İzleme kodu | `src/izleme/` — `veri.py` (günlük gözlem/model), `analiz.py` (ayıklama, akran, taban, durum, kayıp), `spc.py` (Shewhart/EWMA/CUSUM, ARL kalibrasyonu, yapay arıza testi) |
| Çevrimdışı betikler | `src/v3_F1_adaylar.py` (40 aday × 2–4 tasarım × 2.000 senaryo, ~4 saat, 6 paralel), `src/v3_F3_portfoy.py` (korelasyon, etkin sınır, ayrıştırmalar, duyarlılıklar, doğrulama), `src/v3_F4_performans.py` (aylık güncelleme), `src/v3_F6_tarayici.py` |
| Uygulama paketi | `data/atlas/portfoy/` (adaylar, tasarımlar, NPV matrisi 148 × 2.000, lojistik, analiz ve korelasyon özetleri; ~1,2 MB), `data/atlas/izleme/` (aylık ve günlük oranlar, durum, doğrulama; ham saatlik EPİAŞ verisi yok) |
| Config | `v3.portfoy`, `v3.performans` |
| Arayüz | `uygulama/sayfa_portfoy.py` (`/portfoy`), `uygulama/sayfa_performans.py` (`/performans`) |
| Testler | `tests/test_v3_F.py` |

## 2. Aday sahalar ve ortak senaryolar (F1)

**Aday kümesi.** Ön tarama hücrelerinden Faz E dışlamaları (koruma, uygun alan < %10, ada) çıkarılır. Kalan hücreler
ekonomik sıra (başabaş fiyat) ile çok kriterli sıranın (dengeli profil, TOPSIS) ortalamasına göre sıralanır. Başabaşı
70 $/MWh'yi aşanlar elenir. Açgözlü seçim hücreler arası ≥ 60 km ve il başına ≤ 2 aday koşuluyla 40 adaya kadar sürer.
Sonuçta 7 coğrafi bölgenin hepsinden aday var.

**Tasarım seçenekleri.** Her aday için tam analiz motorunun adımları çalışır: hazırlık, iz verimi eğrisi ve MILP
tasarımı. Ardından 2–4 ayrık seçenek değerlenir:
- MILP tasarımı
- bataryasız
- küçük (türbin sayısının ~%60'ı)
- büyük (~%140, alana sığdığı kadar)

Her seçenek için yerleşim ve bakım simülasyonu (`tam_sonra`), işletme tabloları ve Monte Carlo yeniden yapılır. Toplam
148 tasarım üretildi.

**Ortak senaryolar (en kritik nokta).** Monte Carlo sabit 2.000 senaryoyla ve **tüm adaylarda aynı tohumla** çalışır:

| Belirsizlik | Tohum | Sonuç |
|---|---|---|
| Uzun vadeli fiyat yolu ve fiyat şekli | ortak | her senaryoda tüm sahalar aynı fiyatı görür |
| ERA5 hava yılı (her işletme yılı için 2014–2023'ten biri) | ortak | aynı senaryoda her saha **aynı takvim yılını** yaşar → sahalar arası rüzgâr korelasyonu ERA5'teki gibi korunur |
| Batarya yayılımı / SFK doyum senaryosu, kesinti | ortak | |
| CAPEX/OPEX çarpanları, YEKDEM koridoru | ortak | düzenleyici ve piyasa olayları |
| RES model hatası (atlas aktarımı), bağlantı mesafesi oranı (Ö2), COD | sahaya özgü (`tohum + crc32(kod)`) | bağımsız |

Saklanan veri, tasarım × senaryo NPV matrisidir (en iyi gelir yapısıyla: YEKDEM yıllık opsiyonu ya da tüccar). Ortak
sürücülerin senaryo özetleri de saklanır: ilk 10 yılın ortalama fiyatı L10, CAPEX çarpanı, SFK senaryosu.

## 3. Sinerjiler (F2)

Tek saha değerlemesi FSA işletme modelini ve her bileşenin en ucuz tedarik kaynağını varsayar. Portföy bunlara
deterministik bugünkü değer düzeltmeleri ekler. Çarpanlar:
- $\beta$: yıllık 1 $'ın vergi sonrası bugünkü değeri (= 8,13);
- $\kappa$: 1 $ CAPEX düşüşünün amortisman kalkanı sonrası değeri (= 0,85).

1. **İşletme modeli (ölçek ekonomisi).** $z$ = kendi bakımı. Tasarruf
   $\beta[\sum_{jd} q_{jd}\, n_{jd} P_{jd}(c^{FSA} - c^{kendi}) - O\,z - U \sum_r b_r - \Delta A\text{ kaybı}]$.
   - $c^{FSA}$ = 20 $/kW-yıl; $c^{kendi}$ = 10,8 $/kW-yıl (Faz D DES'inin ölçekteki değişken maliyeti).
   - $O$ = 0,6 M$/yıl organizasyon sabit gideri.
   - $U$ = 0,15 M$/yıl her aktif bölgedeki üs.
   - $q_{jd} = x_{jd} z$ ve $b_r \ge q_{jd}$ ($j \in r$): coğrafi yayılım kendi bakımını pahalılaştırır.
2. **Yedek parça havuzu** (yalnız kendi bakımında; FSA'da parça üreticinindir). Taban stok politikası, Poisson talep.
   Parça kalemi $i$'nin değişim oranı $\lambda_i$, etkin tedarik süresi $L_i$ (tedarik − vinç mobilizasyonu):
   $$\text{EBO}(S) = \sum_{x > S} (x - S)\, \frac{e^{-m} m^x}{x!},\quad m = N \lambda_i L_i / 365$$
   Yıllık maliyet = günlük gelir · 365 · EBO(S) + S · parça değeri · %15. Ayrı stoklarda her saha kendi $N_j$'siyle
   $\min_S$ alır. Havuzda tek depo (adayların medoidi) toplam $N$ ile $\min_S$ alır ve her talebe depo→saha transfer
   süresi eklenir: $\tau_j = 1{,}3 \cdot d_j / 400$ km/gün + 12 saat. Havuz maliyeti $N$'de içbükey olduğundan MILP'te
   $a + bN + c \sum N_j \tau_j$ doğrusal yaklaşımı kullanılır. Seçilen portföy için kesin değer ayrıca hesaplanır.
   Faz D'nin simülasyonuyla tutarlı: 8 türbinde $S = 0$, 15+ türbinde dişli kutusu ve jeneratör için $S = 1$.
3. **Toplu tedarik.**
   - (a) Toplam RES gücü 150 / 300 MW'ı aşınca türbin fiyatında %2 / %3 indirim (çerçeve anlaşmaları; oran yayımlanmaz,
     TAHMİN). Türbinin RES CAPEX payı %70 (IRENA %64–84).
   - (b) **Çok sahalı ulaştırma modeli:** Faz E LP'si genişletildi. $f_{ckj}$ = bileşen $c$'nin kaynak $k$'dan saha
     $j$'ye türbin seti akışı. Talep kısıtı $\sum_k f_{ckj} = \sum_d n_{jd} x_{jd}$. Kapasite kısıtı
     $\sum_j f_{ckj} \le C_{ck}$: yerli üretici (Gesbey kule 72 set/yıl) ve limanlar (bileşen başına 60 set/yıl, TAHMİN),
     2 yıllık inşaat penceresi için. Sinerji = tek saha en ucuz lojistiği − portföy ulaştırma maliyeti (≤ 0).
4. **Ortak kıt kaynak.** Aynı bölgedeki ya da aynı trafo merkezine bağlanacak sahalar bağlantı kapasitesi için yarışır:
   $\sum_{j \in r} 50\, x_{jd} \le K_r$, $\sum_{j \in t} 50\, x_{jd} \le K_t$. TEİAŞ lisanslı kapasite yayımlamadığı
   için $K_r$ = 150 MW ve $K_t$ = 100 MW parametredir; duyarlılık 50 MW–sınırsız.

## 4. Portföy optimizasyon modeli (F3)

Formülasyonun tamamı `src/portfoy/model.py` modül notunda. Özet:

**Kümeler:** $j$ adaylar; $d \in D_j$ tasarım seçenekleri; $s$ senaryolar (eşit olasılık); $r$ bölgeler; $t$ trafo
merkezleri; $(c, k)$ bileşen × kaynak.

**Karar değişkenleri.**
- Birinci aşama (yatırım): $x_{jd} \in \{0,1\}$; sinerji ikilileri $z, h, b_r, v_m$; doğrusallaştırma ikilileri
  $q_{jd}, g_{jd}, w_{jdm}$; akışlar $f_{ckj} \ge 0$.
- İkinci aşama: işletme kararları. Dispatch ve yıllık YEKDEM katılımı her senaryoda $V_{jds}$ içinde önceden en iyi
  biçimde çözüldü. Bu yüzden model, ikinci aşaması önceden hesaplanmış bir **deterministik eşdeğer** olarak kurulur.
  CVaR için $\eta$ ve $u_s \ge 0$ eklenir.

**Amaç (ortalama–CVaR).** $\Pi_s = \sum_{jd} V_{jds} x_{jd} + \Psi$, $\Psi$ = sinerjiler.
$$\max\ (1-\lambda)\,\frac{1}{|S|}\sum_s \Pi_s + \lambda\Big[\eta - \frac{1}{\alpha |S|}\sum_s u_s\Big],\qquad u_s \ge \eta - \Pi_s,\ u_s \ge 0$$

**Rockafellar–Uryasev doğrusallaştırması.** CVaR$_\alpha(\Pi) = \max_\eta \{\eta - \frac{1}{\alpha}\mathbb{E}[(\eta - \Pi)^+]\}$.
$(\cdot)^+$ yerine $u_s$ yardımcı değişkenleri yazılınca model doğrusal kalır. En iyi $\eta$, $\alpha$-yüzdeliktir (VaR).
Doğruluk kontrolü: çözümdeki doğrusal CVaR, seçilen portföyün senaryo vektöründen doğrudan hesaplanan en kötü %5
ortalamasıyla aynı (§6).

**Kısıtlar.**
- Saha başına en çok bir tasarım: $\sum_d x_{jd} \le 1$.
- Bütçe: $\sum I_{jd} x_{jd} \le B$.
- Bölge ve trafo kapasiteleri.
- Doğrusallaştırmalar: $q \le x$, $q \le z$, $q \ge x + z - 1$; $g$ ve $w$ benzer.
- $h \le z$ (havuz kendi bakımına bağlı).
- Toplu indirim kademeleri: $\sum G_{jd} x_{jd} \ge M_m v_m$.
- Ulaştırma talep ve kapasite kısıtları.
- "Hiç yatırım yapma" ($x = 0$) her zaman uygun.

**Etkin sınır (ε-kısıt).** $\max\ \mathbb{E}[\Pi]$ s.t. CVaR ≥ $c$, $c$ risk nötr portföyün CVaR'ından 0'a taranır.
λ ağırlıklı amaç arayüzdeki kaydırıcıdır. ε-kısıtı sınırın tamamını verir (λ yöntemi dışbükey olmayan bölgeleri atlayabilir).

**Çözücü.** HiGHS (scipy.optimize.milp). 148 tasarım, 2.000 senaryo: λ = 0'da ~1 s, ε-kısıtla ~55 s (tek iş parçacığı).
Arayüzde 1.000 senaryoluk sabit alt örnek: ≤ 16 s.

## 5. Performans izleme (F4)

Formülasyon `src/izleme/analiz.py` ve `src/izleme/spc.py` modül notlarında. Adımlar:
1. **Oran.** $PR = \sum$ gözlenen $/ \sum$ beklenen; beklenen = ERA5 hücresi + santralin türbin vekili + atlas
   ay × saat k matrisi × kapasite.
2. **Ayıklama.**
   - Bölgesel eşzamanlı düşüş: akranların (≤ 100 km, en az 3) yarısının PR'si aynı gün kendi 90 günlük medyanının
     %60'ının altında.
   - Ulusal YAT günleri: talimat özetinin %95 yüzdeliği; veri 2023 sonrası.
   - Kapasite artırımı ya da yenileme olayları: aylık %99,5 çıkışın geçmişe dönük en büyüğünde > %8 artış. Olay ayı ve
     sonraki 2 ay analiz dışı.
3. **Akran düzeltmesi.** $x = \ln PR - b \ln PR^{akran}$. $b = \mathrm{Cov}/\mathrm{Var}$, $[0, 1]$'e kırpılır (en
   küçük varyanslı birleşim).
4. **Kayan taban.** $\mu_t$ = medyan$\{x_{t-30}, \dots, x_{t-7}\}$; $\sigma_0$ = 1,4826 · MAD; $z_t = (x_t - \mu_t)/\sigma_0$.
5. **Kartlar.** Yalnız alt yönde (performans artışı alarm değildir):
   - Shewhart: $z < -L_s$
   - EWMA: $e_t = \lambda z_t + (1-\lambda)e_{t-1}$, alarm $e_t < -L_e\sqrt{\lambda/(2-\lambda)}$
   - CUSUM: $C_t = \max(0, C_{t-1} - z_t - k)$, alarm $C_t > h$

   $L_s, L_e, h$, gerçek $z$ serilerinden 12 aylık bloklarla durağan bootstrap yapılarak ARL0 = 48 ay olacak şekilde
   kök bulmayla seçilir. Böylece normal dağılım varsayımı gerekmez ve otokorelasyon korunur.
6. **Durum.**
   - Kalıcı sapma: son 6 ayın ≥ 3'ünde EWMA alarmı ve ortalama açık ≥ %3.
   - İzleniyor: son 3 ayda alarm.
   - Diğerleri: normal ya da veri yetersiz.
7. **Kayıp.** EWMA alarmlı aylarda (gözlenen / akran düzeltmeli oran − gözlenen) × aylık ortalama PTF (USD).

**Neden aylık?** Haftalık model/gözlem oranının doğal gürültüsü σ ≈ %17–19 çıktı. Model haftalık üretimle iyi korele
(r = 0,93), ama ERA5 sahaya özgü haftalık rüzgâr hatasını çözemiyor. Akranlarla en iyi birleşim gürültüyü yalnız ~%8
azalttı (b ≈ 0,5); 50 km'lik akranlar da yardım etmedi. Aylık σ ≈ %10.

**Ad gösterimi.** `v3.performans.santral_adlari_goster: false` varsayılandır. Sonuçlar modelden türetilir ve sapmanın
nedeni santral sahibinin verisi olmadan ayırt edilemez. Herkese açık bir sayfada ad göstermek doğrulanmamış bir iddiayı
belirli bir şirkete bağlar. Uygulama anonim kod + il gösterir. Atlas dosyalarında adlar zaten açık (OSM/EPİAŞ), ama
"sapma" etiketiyle birlikte sunulmazlar.

## 6. Sonuçlar

### 6.1 Adaylar ve korelasyon (`outputs/v3F/F1_*`, `data/atlas/portfoy/korelasyon.json`)

- **Adaylar.** 40 aday, 7 bölge, 148 tasarım. Hesaplama 4,2 saat sürdü (6 paralel; bazı adaylarda bilgisayar uykusu
  nedeniyle uzadı). 9 adayın en iyi tasarımı tek başına pozitif E[NPV]'ye sahip: en iyisi Çerkezköy A01, +9,6 M$.
- **Neden saha analizinden farklı?** Adaylar ön tarama hücrelerinin temsil noktalarıdır ve türbin otomatik seçilir
  (çoğunda V112/3,45 MW). Bu yüzden aynı ildeki saha analizinden (ör. Ezine noktası, E-141) farklı sonuç verirler.
- **Saatlik RES üretimi korelasyonu mesafeyle üstel azalıyor** ($\rho(d) = e^{-d/L}$):

  | | Saatlik | Aylık | Yıllık |
  |---|---|---|---|
  | Uzunluk ölçeği L | 293 km | 293 km | 232 km |
  | Ortalama (tüm çiftler) | 0,29 | 0,37 | 0,38 |
  | 100 km içi | 0,78 | 0,89 | 0,88 |
  | 500 km ötesi | 0,15 | 0,21 | 0,17 |

- **Bölgeler.** Marmara rüzgârı Akdeniz, Doğu ve Güneydoğu ile neredeyse ilişkisiz (aylık 0,05 / 0,05 / −0,17). İç
  Anadolu Karadeniz ve Doğu Anadolu ile güçlü korelasyonlu (0,86–0,87). Coğrafi çeşitlendirme rüzgâr açısından mümkün.
- **Sahalar arası NPV korelasyonu** (MILP tasarımları) ise ortalama 0,60 (0,10–0,82): NPV'yi ortak fiyat ve SFK
  senaryosu sürüklüyor.

### 6.2 Etkin sınır ve seçilen portföy (saf tahminlerle; büzülmüş — varsayılan — sonuçlar §8.1)

Bütçe 300 M$, bölge kapasitesi 150 M$, trafo 100 MW, tüm sinerjiler açık:

| CVaR alt sınırı (M$) | E[NPV] (M$) | CVaR %5 (M$) | CAPEX (M$) | Portföy |
|---|---|---|---|---|
| (yok; risk nötr) | **41,1** | −65,3 | 300 | A01 MILP, A02 küçük, A04 küçük, A05 küçük, A06 küçük |
| −58 | 36,4 | −56,5 | 260 | A01, A02, A04, A05 |
| −51 | 30,3 | −50,6 | 230 | A01, A02 MILP, A05 |
| −44 | 21,7 | −42,0 | 171 | A01, A04, A05 (küçükler) |
| −37 | 18,2 | −34,9 | 142 | A01 MILP, A05 küçük |
| −30 | 14,4 | −29,6 | 112 | A01, A05 (küçükler) |
| −23 | 7,3 | −16,0 | 55 | A01 küçük |
| ≥ −9 | 0 | 0 | 0 | yatırım yok |

- **Risk nötr portföy.** 5 saha, 49 türbin, P(NPV > 0) %72. Kendi bakımı, yedek parça havuzu (depo A18) ve 150 MW
  indirim kademesi seçili. Beş sahanın dördü "küçük" tasarım. Bütçe bağlayıcı olduğundan model sahaları küçültüp sayılarını
  artırıyor.
- **En iyi tek saha:** A01 MILP, E[NPV] 9,6 M$, CVaR −23,4 M$. **Aynı CVaR kısıtıyla optimal portföy bu tek sahanın
  kendisi.** Kuyruk riski ortak fiyattan geldiği için ikinci bir saha kuyruğu kötüleştiriyor. Portföy, aynı riskte daha
  fazla değer değil, daha fazla riske orantılı daha fazla değer ve sinerji sağlıyor.
- **Risk ağırlığıyla** (amaç (1 − λ)E + λ·CVaR, 2.000 senaryo):
  - λ ≤ 0,2: 5 saha;
  - λ = 0,3–0,35: 4 saha (E 39,8, CVaR −61,0);
  - **λ ≥ 0,40: yatırım yok.** Geçiş sert, çünkü CVaR negatif olduğundan amaç bir noktada tüm portföylerde sıfırın
    altına iniyor.

### 6.3 Sinerji ve çeşitlendirme ayrıştırması (`outputs/v3F/F3_sinerji.csv`, `F3_ozet.json`)

Sinerjiler (risk nötr, aynı bütçe). Katkı = kalem kapalıyken en iyi amaçtan fark:

| Kalem | Katkı (M$) | Not |
|---|---|---|
| İşletme ölçeği (kendi bakımı) | **+6,91** | 49 türbin > başabaş; organizasyon 0,6 M$/yıl + 2 bölge üssü (Marmara, Ege) |
| Toplu türbin alımı | +2,50 | 150 MW kademesi %2 (TAHMİN) |
| Yedek parça havuzu | +1,72 | kesin hesap 1,43 (doğrusal yaklaşım 0,29 fazla); ayrı stoklar 0,27 → havuz 0,10 M$/yıl |
| Çok sahalı ulaştırma | 0,00 | kapasiteler bağlayıcı değil |
| **Toplam** | **+9,36** | amaç 31,7 → 41,1 M$ |

Çeşitlendirme (aynı 5 saha):

| | Değer |
|---|---|
| Σ σ_j (tam korelasyon varsayımıyla) | 71,0 M$ |
| σ_portföy | 62,3 M$ (çeşitlendirme 8,7 M$) |
| Σ CVaR_j → CVaR_portföy | −92,6 → −65,3 M$ (**+27,4 M$**) |
| Varyans: ortak piyasa / hava korelasyonu / sahaya özgü | **%70 / %18 / %12** |
| Ortak sürücülerin tek tasarım NPV'sini açıklama gücü (R² medyan) | 0,54 |

**Çeşitlendirmenin sınırı.** Rastgele n sahalı portföylerde saha başına σ, n = 1'de 13,8 M$'dan n = 12'de 11,1 M$'a
iniyor. Ortak piyasa payı ise %49'dan %72'ye çıkıyor (`F3_cesitlendirme_egrisi.csv`). Fiyat, SFK ve CAPEX
belirsizliği her sahada aynı olduğundan saha eklemek bu kısmı azaltmaz. Çeşitlendirme yalnız hava ve sahaya özgü
riski (%30) seyreltebilir.

**Karşılaştırma.** Sinerjiler beklenen değeri +9,4 M$ artırıyor; çeşitlendirme beklenen değeri değiştirmiyor, kuyruğu
27 M$ iyileştiriyor. İkisi farklı birimler: λ = 0,2'deki amaçta çeşitlendirmenin değeri 0,2 × 27,4 ≈ 5,5 M$ eder;
sinerjilerinki 0,8 × 9,4 ≈ 7,5 M$.

### 6.4 Fiyat ve kapasite duyarlılığı

- **Uzun vadeli fiyat** (NPV(Δ) ≈ NPV + eğim·Δ; eğim, ilk 10 yılın fiyat ortalamasına regresyon katsayısı, medyan
  0,60 M$ per $/MWh):
  - Risk nötr portföy 48–68 $/MWh aralığında 5 saha.
  - **≤ 46 $/MWh'de hiç yatırım yapmamak optimal.**
  - 48 $/MWh'de seçilen 5 sahanın 4'ü tek başına negatif. Portföyü sinerjiler (~10 M$) pozitif yapıyor; sinerjisiz
    yalnız A01 kurulurdu (+0,36 M$).
  - CVaR ≥ −30 kısıtlı yatırımcı fiyat yükseldikçe 1 → 5 sahaya genişliyor.
- **Bölge bağlantı kapasitesi:** 50 MW'ta E[NPV] 29,1 M$ (4 saha, dört farklı bölgede), 100 MW'ta 40,7, 150 MW ve
  sınırsızda 41,1 M$. Kıt bağlantı kapasitesi portföyü coğrafi olarak yaymaya zorluyor.
- **Bütçe:** 150 M$ → 18,2 M$ (3 saha); 600 M$ → 69,4 M$ (8 saha, CVaR −124 M$).

### 6.5 Performans izleme (`data/atlas/izleme/dogrulama.json`, `durum.csv`)

- **90 santral.** Kart parametreleri (ARL0 = 48 ay): Shewhart L = 2,44, EWMA L = 2,22 (λ = 0,2), CUSUM h = 3,40 (k = 0,5).
- **Aylık gürültü** medyan σ0 = %10,6. Analiz dışı kalan günler: bölgesel eşzamanlı düşüş %7,0, ulusal YAT %0,07.
- **Gerçek "normal" santrallerde yanlış alarm** (santral-yıl): Shewhart 0,23, EWMA 0,28, CUSUM 0,28 (hedef 0,25).
- **Yapay arıza testi** (yakalama oranı, normal santrallerin izleme dönemi; 600 tekrar). Yakalama penceresi arıza süresi
  + 2 ay; bu pencerede yanlış alarm taban oranı ~%2/ay:

  | Düşüş | 1 ay | 3 ay | 6 ay | CUSUM gecikmesi (6 ay) |
  |---|---|---|---|---|
  | %3 | %18 | %27 | %36 | 1,5 ay |
  | %5 | %21 | %27 | %44 | 2 ay |
  | %10 | %24 | %50 | **%71** | 2 ay |

  EWMA CUSUM'a çok yakın; Shewhart küçük ve uzun düşüşlerde zayıf (6 ay %10: %43).
- **Durum** (son ay 2025-12): **60 normal, 16 izleniyor, 10 kalıcı sapma, 4 veri yetersiz.** Kalıcı sapmaların son 6 ay
  açığı %7–17. Tahmini kayıp toplamı ~30 M$; bu, modelden türetilmiş bir üst sınırdır ve iki santralde 11 M$'ı aşıyor.
- **Faz D'de aykırı çıkan santraller:**
  - Söke RES: **normal** (son 6 ay +%14 üstte; akran ağırlığı 0, çünkü akranlarıyla ilişkisiz; σ0 %13). Faz D'deki
    aykırılık, kalibrasyon katsayısının seviyesi ile ilgiliydi; izleme seviyeyi değil değişimi ölçtüğü için bu santral
    işaretlenmiyor.
  - Meryem RES: **izleniyor** (izleme dönemi boyunca 8 ay EWMA alarmı; son 3 ayda alarm var, ama son 6 ayın ortalaması tabanın
    %2 üstünde). İki kapasite olayı var.
- **Sınır.** Model tabanlı izleme %10 ve birkaç ay süren düşüşleri makul yakalıyor, %3'lük verim kayıplarını
  yakalayamıyor. Bunun için SCADA (türbin bazında rüzgâr hızı ve güç) gerekir.

### 6.6 Süreler (2 çekirdek benzetimi; `outputs/v3F/F6_tarayici_sure.csv`)

| Ölçüm | Süre | Bütçe |
|---|---|---|
| Portföy optimizasyonu, 1.000 senaryo, λ = 0 / 0,1 / 0,2 / 0,3 / 0,45 | 1,0 / 15,8 / 19,0 / 21,1 / 11,0 s | ≤ 30 s |
| Portföy sayfası tarayıcıda (λ = 0,2 çözümü dahil) | 18,5 s | ≤ 30 s |
| Performans izleme sayfası (masaüstü / mobil) | 1,6 / 1,4 s | ≤ 2 s |
| Çevrimdışı: aday değerleme / portföy analizleri / performans | 4,2 saat / 15 dk / 7 s | — |

16 ekran görüntüsünün (`docs/img/v3/F_*`) hiçbirinde yatay taşma yok.

### 6.7 Doğrulama (F6)

- **Kaba kuvvet.** 6 sahalık örnekte (179–1.800 kombinasyon × sinerji ikilileri) MILP üç ayarda da (λ = 0 / 0,2 / 0,05;
  bütçe 150 / 150 / 250 M$) aynı portföyü ve aynı amaç değerini buldu (fark < 1e-10). `tests/test_v3_F.py` sentetik bir
  örnekte aynı kontrolü 3 ayarda yapar.
- **CVaR doğrusallaştırması.** λ > 0 çözümlerinde doğrusal CVaR (η − Σu/(α|S|)) seçilen portföyün senaryo vektöründen
  doğrudan hesaplanan en kötü %5 ortalamasıyla aynı (−34,931 / −57,644 M$; fark < 1e-13).
- **Varyans ayrıştırması.** Parçaların toplamı portföy varyansına eşit (test).
- **SPC.** Normal dağılımlı sentetik seride kalibre edilen Shewhart sınırı ≈ 2,04 (P(z < −L) = 1/48) ve EWMA ARL0
  hedefin %15'i içinde (test). Gerçek veride yanlış alarm oranı hedefle uyumlu (yukarıda).

## 7. Sınırlamalar

1. **Adaylar hücre temsil noktalarıdır.** Arazi, imar ve izin durumu bilinmez. Tasarım seçenekleri ayrık ve sınırlıdır
   (2–4 seçenek).
2. **Sinerji parametrelerinin bir kısmı TAHMİN:**
   - toplu indirim oranları;
   - bölge üssü maliyeti;
   - liman elleçleme kapasitesi;
   - bölge ve trafo bağlantı kapasiteleri (TEİAŞ yayımlamıyor).

   Kendi bakımının ölçek maliyeti Faz D DES'inden gelir; literatür daha yüksek başabaş verir (Faz E §0.1). Bu durumda
   işletme sinerjisi daha düşük olur.
3. **Havuz maliyeti MILP'te doğrusal yaklaşımla** girer (seçilen portföyde kesin değerin 0,29 M$ üstünde).
4. **Fiyat duyarlılığı birinci derece yaklaşımdır** (NPV'nin L10'a doğrusal eğimi). YEKDEM opsiyonunun fiyatla doğrusal
   olmayan değeri yaklaşık temsil edilir.
5. **İzleme ERA5 çözünürlüğüyle sınırlı** (aylık σ ~ %10). Kalıcı sapma bir modelin çıktısıdır; neden santral
   verisi olmadan bilinemez. 2026 ayları ERA5 hücre serisi 2025 sonunda bittiği için izlenmedi.

## 8. Optimize edicinin laneti ve Bayesçi büzülme (v3 kapanış)

Kod `src/portfoy/lanet.py`, betik `src/v3_G1_optimizer_laneti.py` → `outputs/v3G/G1_*`, uygulama paketi
`data/atlas/portfoy/lanet.json`.

**Sorun.** Her adayın rüzgâr tahmini tek tek yansız olsa bile, 40 aday arasından en iyi görünenleri seçmek, tahmini
olduğundan iyi çıkmış adayları seçmek demektir (Smith & Winkler 2006). Seçilen portföyün tahmini değeri, gerçek
değerinden sistematik olarak yüksektir; aradaki fark **beklenen hayal kırıklığıdır**.

**Ampirik kanıt** (Faz A birini dışarıda bırak doğrulaması, 90 santral):
- Hata, tahmin düzeyiyle güçlü ilişkili (Spearman 0,77).
- En yüksek tahmin çeyreği ortalama %14 (log) fazla tahmin ediyor.
- ln gözlenen ~ ln tahmin kalibrasyon eğimi 0,36: tahminler gerçeklerden çok daha dağınık.

**Model** (log KF; bölge r; güven seviyesi g):
$$\ln c_j \sim \mathcal{N}(m_r, \tau_r^2),\qquad \ln \hat c_j = \ln c_j + e_j,\ e_j \sim F_g,\qquad
\mathbb{E}[\ln c_j \mid \hat c_j] = m_r + w_j(\ln \hat c_j - m_r),\quad w_j = \frac{\tau_r^2}{\tau_r^2 + \sigma_g^2}$$

- Öncül ampirik Bayes: $m_r$ ve $\tau_r^2 = \mathrm{Var}_r(\ln \hat c) - \bar\sigma^2$, bölgenin ön tarama hücrelerinden.
- $F_g$: birini dışarıda bırak göreli hataları, güven seviyesine göre güncel RMSE'ye (%18,2 / %22,5) ölçeklenir.
- **NPV düzeltmesi:** $V_{jds} + \kappa_{jd}(q_j - 1)$, $q_j = \hat c_j^{\text{büzülmüş}} / \hat c_j$.
- $\kappa_{jd}$ = NPV'nin sahanın KF çarpanına duyarlılığı. Sahanın Monte Carlo model çarpanı aynı tohumla yeniden
  üretilir ve ortak sürücülerle birlikte regresyona sokulur. Açıklanan varyans 0,46'dan 0,79'a çıkar; κ medyan
  ~1,2 M$/MW, 50 MW bağlantıda kırpılan büyük tasarımlarda daha düşük.

**Büzülme.** w = 0,67–0,88. Adayların KF tahmini %3–16 aşağı çekiliyor (q = 0,84–0,97, medyan 0,89). En çok büzülenler
düşük güvenli İç Anadolu adayları: Kırşehir %34,8 → %29,1.

**Simülasyon** (200 tekrar). Her tekrarda gerçek KF sonsaldan çekilir; yeni tahmin = gerçek + ampirik hata. Portföy
(λ = 0, bütçe 300 M$, tüm sinerjiler) ve en iyi tek saha (a) saf tahminle, (b) büzülmüş tahminle seçilir:

| | Tahmin edilen | Gerçek | **Beklenen hayal kırıklığı** (± SH) | P10–P90 |
|---|---|---|---|---|
| Saf seçim — portföy | 76,6 M$ | 30,2 M$ | **46,3 ± 1,5 M$** | 22–75 |
| Saf seçim — en iyi tek saha | 24,4 M$ | 8,7 M$ | **15,7 ± 0,8 M$** | 3–34 |
| Büzülmüş seçim — portföy | 40,6 M$ | **33,8 M$** | 6,8 ± 1,0 M$ | −10–27 |
| Büzülmüş seçim — en iyi tek saha | 13,4 M$ | **10,3 M$** | 3,1 ± 0,5 M$ | −5–12 |

- Büzülme beklenen hayal kırıklığını %85 azaltıyor ve **gerçekleşen değeri artırıyor**: portföyde +3,5 M$, tek sahada
  +1,6 M$. Daha iyi seçim yaptırıyor; tekrarların %54'ünde büzülmüş seçim gerçek değerde daha iyi, %28'inde aynı.
- Kalan 7 M$'lık hayal kırıklığının nedenleri: κ doğrusallığı, sinerjilerin sahaya göre değişmesi ve ampirik hata
  dağılımının kuyrukları.
- Simülasyondaki tahmin edilen değerler (76 M$) gerçek kararınkinden (41 M$) yüksek, çünkü her tekrarda tahmin
  gerçeğin üstüne yeni bir hata ekler. Bu, "40 aday yeniden değerlenseydi" dünyasıdır.

**Gerçek karar** (Faz F'nin saf seçimi, sonsal beklentiyle):

| | Tahmin (saf) | Sonsal (büzülmüş) |
|---|---|---|
| Faz F'nin seçtiği 5 sahalık portföy | 41,1 M$ | **19,3 M$** (−22 M$, %53) |
| Büzülmüş tahminle seçilen portföy (A01 MILP, A02 MILP, A04 küçük, A05 küçük) | – | **20,4 M$** |
| En iyi tek saha A01 MILP | 9,6 M$ | **4,9 M$** |

**Duyarlılık.** Çapraz doğrulama kalibrasyon eğimi 0,36, ampirik Bayes ağırlığından (~0,8) çok daha güçlü bir
büzülme ima ediyor. Ancak işletmedeki santraller iyi gözlenen rüzgârları için seçildiğinden gözlenen KF aralığı dar
ve bu eğimi aşağı çeker. Varsayılan olarak ihtiyatlı ampirik Bayes kullanılıyor; gerçek düzeltme daha büyük olabilir.

**Uygulama.** Portföy sayfasında "Optimize edicinin lanetine karşı düzeltme (önerilen)" anahtarı varsayılan açık ve
kısa bir notla açıklanıyor. Etkin sınır, seçilen portföy ve eşikler için önce/sonra karşılaştırması §8.1'de.

### 8.1 Önce / sonra (`outputs/v3F/F3_*_duzeltmesiz.*` ve `F3_*`; ERA5 yön gridiyle yeniden değerlenmiş adaylar)

| | Saf tahmin (önce) | Büzülmüş tahmin (sonra, varsayılan) |
|---|---|---|
| Risk nötr portföy | 5 saha (A01 MILP, A02/A04/A05/A06 küçük) | **4 saha** (A01 MILP, A02 MILP, A04 küçük, A05 küçük) |
| E[NPV] / CVaR %5 / P(NPV>0) | 41,1 / −65,3 M$ / %72 | **20,4 / −80,4 M$ / %60** |
| Sinerjiler | +9,4 M$ (işletme 6,9) | +10,6 M$ (işletme 8,1) |
| En iyi tek saha A01 MILP | 9,6 M$, CVaR −23,4 | 4,9 M$, CVaR −28,1 |
| Aynı CVaR'da optimal portföy | en iyi tek saha | en iyi tek saha (değişmedi) |
| **Yatırım yok — fiyat eşiği** | ≤ 46 $/MWh | **≤ 52 $/MWh** |
| **Yatırım yok — risk ağırlığı eşiği (58 $/MWh)** | λ ≥ 0,40 | **λ ≥ 0,25** |
| Eşikte sinerjinin rolü | 48 $/MWh'de 5 sahanın 4'ü tek başına negatif | 54 $/MWh'de 4 sahanın 2'si tek başına negatif |
| Varyans: ortak piyasa / hava / sahaya özgü | %70 / %18 / %12 | %69 / %17 / %14 |

**Etkin sınır** (ε-kısıt; CVaR alt sınırı → E[NPV], M$):

| CVaR ≥ | Önce | Sonra |
|---|---|---|
| risk nötr | 41,1 (CVaR −65) | 20,4 (CVaR −80) |
| ≈ −60 | 36,4 (4 saha) | 13,0 (3 saha, CVaR −63) |
| ≈ −45 | 21,7 (3 saha) | 9,6 (2 saha, CVaR −43) |
| ≈ −30 | 14,4 (2 saha) | 4,9 (A01, CVaR −28) |
| ≈ −16 | 7,3 (A01 küçük) | 0,7 (A10 küçük) |
| > −11 | 0 | 0 |

Sınır sola ve aşağı kayıyor: her kuyruk riski düzeyinde beklenen değer yarıya iniyor. Düzeltme bir sabit kayma
olduğundan CVaR da kötüleşiyor. Portföy yapısı az değişiyor (A01, A02, A04, A05 her iki durumda çekirdek), ama
yatırım kararı çok daha kırılgan. Risk nötr bir yatırımcı için bile uzun vadeli fiyat beklentisinin 52 $/MWh'nin
altına inmesi portföyü boşaltıyor (58'e karşı 6 $/MWh pay). Ilımlı risk kaçınması (λ = 0,25) da yatırımı durduruyor.
