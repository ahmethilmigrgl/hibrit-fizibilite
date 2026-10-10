# v3 Faz D — Türbin yerleşimi optimizasyonu, bakım ve güvenilirlik

**Amaç:** Tam analizin iki kaba varsayımını endüstri mühendisliği modelleriyle değiştirmek:
1. **Toplu %12 kayıp** (iz + kullanılabilirlik + elektrik) → sahaya özgü **türbin yerleşimi** ve **iz (wake) kaybı**
   (komşu santraller dahil) + **ayrık olay simülasyonundan** kullanılabilirlik.
2. **Sabit O&M (35.000 $/MW-yıl)** → arıza, onarım kuyruğu, ekip/vinç kısıtı, hava pencereleri, önleyici bakım çizelgesi ve
   yedek parça stoku içeren **aşağıdan yukarı O&M modeli**.

| | |
|---|---|
| Kod | `src/yerlesim/` (yerleşim), `src/bakim/` (bakım), `src/motor/v3.py` (motor bağlantısı), `uygulama/v3_bolumler.py` (arayüz) |
| Betikler | `src/v3_D0_era5_yon_grid.py` (yön gridi), `v3_D1_osm_turbinler.py`, `v3_D1_atlas_iz.py`, `v3_D1_yontem_karsilastirma.py`, `v3_D2_hizli_tablolar.py`, `v3_D2_bakim_analizi.py`, `v3_D3_once_sonra.py` |
| Çıktılar | `outputs/v3D/` |
| Config | `v3.kayip`, `v3.yerlesim`, `v3.bakim` (her değerin kaynağı ve notu config'te) |
| Kütüphaneler | DTU **PyWake 2.6** (iz modeli, MIT), **SimPy 4.1** (ayrık olay simülasyonu, MIT), HiGHS (MILP) |
| Testler | `tests/test_v3_D.py` (23 test) |

Motor seçenekleri (`KullaniciVarsayimlari`): `yerlesim_bakim` (varsayılan açık; kapalıysa v2 davranışı birebir),
`yerlesim_yontemi` (sa / ga / milp / izgara / acgozlu), `bakim_modeli` (yeni / sabit), `bakim_stratejisi`
(duzeltici / takvim / durum). Ezine v1 regresyon modu (`kalibrasyon="v1"`) v3'ü her zaman kapatır.

---

## 1. Veri

### 1.1 Rüzgâr gülü: ERA5 100 m yönü
v2'nin ERA5 nokta gridi yalnız hız büyüklüğünü saklıyordu. Yön için CDS'in **gridli** ERA5 ürününden Türkiye kutusunun
u100, v100 alanları (2014–2023, saatlik, 20 yarım yıllık istek) çevrimdışı indirilir ve her kara hücresi için saatlik
10°'lik sektör (uint8) olarak paketlenir (`data/grid/era5_yon_tr/v1/`, git'e girmez; `src/v3_D0_era5_yon_grid.py`,
devam ettirilebilir).

**Bu fazın analizlerinde kullanılan yön verisi:** grid indirmesi CDS kuyruğunda ~13 dk/istek sürdüğü için commit anında
tamamlanmamıştı. Bütün analiz sahaları (Ezine, Gürün, Susurluk, hızlı tablo örnek sahaları, 85 atlas santrali) aynı
ERA5 u100/v100 verisini CDS zaman serisi ürününden (`data/raw/era5_hucre/`, hücre başına) aldı; Gürün hücresi bu iş için
indirildi. Kaynak sırası `era5_yon.saatlik_yon`: yön gridi → ham hücre → 0,5° içindeki komşu hücre → tek biçimli (bayraklı).
Grid tamamlanınca diğer sahalar da kendi hücrelerinin yönünü kullanır; yukarıdaki sahaların sonuçları değişmez (aynı ERA5
verisi; 10°'lik sektörleme iz hesabının kendi 36 yönlü kutulamasıyla aynı). Meteorolojik yön:
θ = (270° − atan2(v, u)) mod 360 (rüzgârın **estiği** yön).

**Hız, profilin kalibre hızıdır:** rüzgâr gülünün ve iz hesabının hızı, üretim profilini üreten hızın aynısıdır
(ERA5 100 m → saatlik kayma üssüyle göbek → atlas ay × saat katsayısı K). Yoğunluk eşdeğeri:
v_eş = v · (ρ/1,225)^(1/3). Böylece yerleşim, atlas kalibrasyonuyla aynı rüzgârı görür.

### 1.2 Saha içi mekânsal değişim: GWA 250 m
Aday konum i'nin hız çarpanı **m_i = GWA_i / GWA_ref**. GWA_ref, profilin kalibre edildiği GWA hızıdır (v2 kuralı:
yarıçaptaki en rüzgârlı hücrelerin ortalaması). m_i = 1 olan bir konum tam olarak profildeki rüzgârı görür; bu,
yerleşimin atlas kalibrasyonuyla tutarlı olmasını sağlar.

### 1.3 Komşu santral türbinleri
v2'de indirilen 4.122 OSM türbin düğümünden küçük bir paket (`data/atlas/osm_turbinler.csv`, ODbL):
konum + iz hesabı için birim güç, rotor çapı, göbek.
- 1.798 türbin atlas santrallerine bağlı → santralin türbin vekili (windpowerlib),
- 675 türbinde OSM etiketi,
- kalanlarda güç sınıfı varsayılanı (D = √(4P / (π·SP_sınıf))).

İz hesabında 10 km içindeki en yakın 150 türbin kullanılır. Yeni türbinler mevcut türbinlere 3D'den yakın konamaz
(dışlama katmanı).

---

## 2. Saha alanı ve kısıtlar

**Alan:** seçilen nokta çevresinde yarıçap R (varsayılan 2 km = v2 türbin yerleşimi yarıçapı).

**Dışlama katmanı arayüzü** (`src/yerlesim/alan.py`):
```python
class DislamaKatmani(Protocol):
    ad: str
    def maske(self, enlem, boylam) -> np.ndarray: ...   # True = türbin konamaz
```
Şimdilik `MevcutTurbinTamponu` ve `KaraMaskesi`. **Faz E'de** yol, yerleşim, koruma alanı ve eğim katmanları aynı
arayüzle `SahaAlani(dislama=[...])` listesine eklenecek; yerleşim kodu değişmeyecek.

**Aday konumlar:** alan içindeki GWA 250 m hücre merkezleri (2 km'de ≈ 208 aday; `aday_alt_bolme: 2` ile 125 m).

**Asgari aralık (elips):** i ve j çatışır ⇔ (u/(a·D))² + (v/(b·D))² < 1.
- u: hâkim eksen boyunca uzaklık, v: ona dik uzaklık.
- a = 5D (hâkim yönde), b = 3D (dik yönde).
- Kaynak: Manwell, McGowan & Rogers (2009) "genelde 5–9D rüzgâr yönünde, 3–5D dik".
- Hâkim eksen, enerji ağırlıklı yön dağılımının ikinci momentinden bulunur: θ_eksen = ½·atan2(Σ e·sin2θ, Σ e·cos2θ).
  Çift yönlü rüzgârda (Ege'de kuzey–güney gibi) doğru ekseni verir.

---

## 3. İz modeli

### 3.1 Referans: PyWake
`PropagateDownwind` + `BastankhahGaussianDeficit` + karelerin toplamı süperpozisyonu.

Bastankhah & Porté-Agel (2014) Gauss izi, j türbininin i'deki bağıl hız açığı:

δ_ij = min(1, 2·a(CT_j·D_j² / (8σ²))) · exp(−r²/(2σ²)),   σ = k*·x + ε·D_j,   ε = 0,2·√β,   β = ½(1+√(1−CT))/√(1−CT)

- x: rüzgâr yönünde uzaklık (x ≤ 0 ise δ = 0),
- r: dik uzaklık (göbek yüksekliği farkı dahil),
- a(·): Madsen (2020) CT → indüksiyon yaklaşımı.

**Genişleme katsayısı:** k* = 0,38·TI + 0,004 (Niayifar & Porté-Agel 2016). TI = %10 → k* = 0,042 (kara için tipik ortam
türbülansı %8–12, TAHMİN).

**Süperpozisyon:** WS_eff,i = m_i·U − √(Σ_j (δ_ij · m_j·U)²).

**Duyarlılık:** Jensen/Park (NOJ, k = 0,075 kara).

**CT eğrisi:** windpowerlib kütüphanesinde yok; PyWake `GenericWindTurbine` aynı D, göbek ve anma gücüyle üretir
(kısmi yükte CT ≈ 0,8).

### 3.2 Hızlı vekil (optimizasyon için)
Optimizasyon binlerce yerleşimi değerlendirir; PyWake'i her seferinde çağırmak yavaş. Vekil, **PyWake'in formülünün
aynısını** iki basitleştirmeyle kullanır:
1. Kaynak türbinin CT'si kendi yerel serbest hızında (izli hızında değil) değerlendirilir.
2. Açıklar aday çiftleri için **bir kez** hesaplanır: A[i, j, w, s] = (δ_ij(w, s)·m_j)².

Bir yerleşim S'nin enerjisi: WS_eff = ws·(m_i − √(Σ_{j∈S} A[i,j,w,s])), güç eğrisi, P(w, s) ile ağırlık. Değerlendirme ~0,3 ms.

**Doğrulama** (`tests/test_v3_D.py`):
- İki türbinli durumda PyWake ile **1e-6 m/s** içinde aynı etkin hız.
- Rastgele yerleşimlerde yıllık enerji PyWake'e **%1,5** içinde. Ezine 12 türbinde vekil–referans farkı %0,35.

**Önemli bir bulgu: yön ayrıklaştırması.** İlk sürümde vekil 12 yön (30°) kullanıyordu. MILP, 30°'lik yön ızgarasının
**arasına düşen boşlukları** sömürdü: vekil enerjisi PyWake'in 36 yönlü (10°) referansından %2,1 iyimser çıktı. Bu
klasik bir "optimizasyon modelin hatasını bulur" örneği. Vekil 36 yöne çıkarıldı (hız kutuları kabalaştırıldı); fark
%0,35'e indi.

### 3.3 Saatlik iz verimi ve profil
Seçilen yerleşim PyWake'le (komşularla) 36 yön × 1 m/s ızgarada çözülür → çiftlik güç tablosu T(yön, hız). Her saat
için η_t = T(yön_t, v_t) / (N · P_ref(v_t)). P_ref, GWA çarpanı 1 olan izsiz tek türbindir.

Çiftlik profili = taban profil × η_t. Kesme hızı altında referans üretmezken yüksek çarpanlı konumların ürettiği
saatlerde doğrudan T/(N·P_n). İz kaybı orta hızlarda büyük, anma hızı üstünde sıfıra yakındır. Bu yüzden saatlik
uygulama, sabit bir yüzdeden daha doğru gelir zamanlaması verir.

---

## 4. Yerleşim optimizasyonu — formülasyon

### 4.1 Problem: ikili seçim (kuadratik)

| | |
|---|---|
| **Küme** | I: olurlu aday konumlar (n ≈ 208) |
| **Parametreler** | E_i: i'nin izsiz yıllık enerjisi [MWh] (GWA çarpanıyla) · a_ij ≥ 0: yalnız j varken i'nin j yüzünden kaybettiği enerji (ikili kayıp, vekil modelden) · C_ij ∈ {0,1}: elips çatışması · N: türbin sayısı |
| **Karar değişkeni** | x_i ∈ {0,1}: i'ye türbin konur |
| **Amaç** | maks Σ_i E_i·x_i − Σ_i Σ_j a_ij·x_i·x_j |
| **Kısıtlar** | Σ_i x_i = N · x_i + x_j ≤ 1 (C_ij = 1) |

Bu bir **ikinci dereceden ikili problem** (QUBO benzeri, kardinalite kısıtlı); amaçtaki x_i·x_j çarpımı doğrusal değil.

### 4.2 (a) MILP: Glover doğrusallaştırması
Her i için sürekli w_i ≥ 0 eklenir; w_i, "i seçilirse komşularından yediği toplam kayıp" olur:

```
w_i ≥ Σ_j a_ij x_j − M_i (1 − x_i),   w_i ≥ 0
M_i = i'nin en büyük N−1 ikili kaybının toplamı
maks Σ_i E_i x_i − Σ_i w_i
```

**Neden kesin?**
- x_i = 1 ⇒ w_i ≥ Σ_j a_ij x_j. Maksimizasyon w_i'yi bu değere indirir.
- x_i = 0 ⇒ sağ taraf ≤ 0 olur (en fazla N−1 komşu seçilebilir ve M_i onların en büyük toplamıdır), w_i = 0.

Yani w_i = x_i · Σ_j a_ij x_j.

**Neden Glover?** Standart doğrusallaştırma her çift için y_ij ≥ x_i + x_j − 1 ekler: O(n²) ≈ 21.000 değişken.
Glover O(n) değişkenle aynı modeli kurar. Bedeli, LP gevşetmesinin zayıf olmasıdır (büyük-M). HiGHS dal-sınır
ağacında binlerce düğüm açar.

**Sınırlılık:** MILP, ikili kayıpların **doğrusal toplamını** en iyiler. Gerçek model (karelerin toplamı) birden çok iz
üst üste geldiğinde daha az kayıp verir. Bu yüzden MILP'in "en iyisi" gerçek modelde en iyi olmayabilir. Sonuç
PyWake'le yeniden değerlendirilir.

### 4.3 (b) Sezgiseller
Sezgiseller doğrudan **gerçek vekil modeli** (karelerin toplamı) en iyiler.

**Genetik algoritma:**
- Birey: N adaylık küme.
- Seçim: turnuva (3).
- Çaprazlama: iki ebeveynin ortak genleri korunur, kalan genler havuzdan olurlu açgözlü sırayla eklenir.
- Mutasyon: 1–2 türbini 4D içindeki olurlu bir adaya taşı.
- Olursuz çocuk onarılır; 2 elit.
- Nüfus 40, 120 nesil.

**Benzetimli tavlama + yerel arama:**
- Hamle: bir türbini olurlu bir adaya taşı (%70 olasılıkla 4D içine).
- Kabul: Metropolis (kötüleşen hamle exp(Δ/T) olasılıkla kabul).
- Soğutma: T₀ = 0,1 · E/N, geometrik 0,997; 3.000 adım.
- Sonunda **en iyi iyileştirme yerel araması**: her türbinin 6D içindeki tüm tek taşımaları, iyileşme kalmayana dek.
- **3 başlangıç**, en iyisi seçilir.

### 4.4 (c) Referanslar
- **Düzenli ızgara:** satırlar hâkim rüzgâra dik; satır arası 7D, satır içi 4D. Izgara kaydırmaları denenir.
- **v2 GWA açgözlü kuralı:** en rüzgârlı hücreler, 500 m aralık.
- **Açgözlü (yardımcı):** her adımda E_i − Σ_{j∈S}(a_ij + a_ji) en büyük olurlu aday. İç içe yerleşimler üretir, bu yüzden
  N'ye göre iz kaybı eğrisini **tek geçişte** verir (kapasite MILP'ine girdi).

### 4.5 Karşılaştırma (3 saha × N ∈ {12, 20}; sezgiseller 5 tohum; hepsi aynı PyWake referansıyla)

| Yöntem | En iyiye fark, ort. | En kötü | İç iz (ort.) | Konum kazancı | Süre ort. / azami [s] | Tohumlar arası CV | Elips kısıtı |
|---|---|---|---|---|---|---|---|
| (a) MILP (Glover, 60 s sınırı) | %-0,09 | %-0,36 | %4,5 | 0,984 | 50,4 / 60,0 | – | sağlanıyor |
| (b) SA + yerel arama (3 başlangıç) | %-0,13 | %-0,48 | %4,5 | 0,984 | 1,9 / 2,7 | %0,10 | sağlanıyor |
| (b) Genetik algoritma | %-0,33 | %-0,58 | %4,6 | 0,982 | 1,1 / 1,6 | %0,05 | sağlanıyor |
| Açgözlü (yardımcı) | %-0,66 | %-1,30 | %4,7 | 0,980 | 0,0 / 0,0 | – | sağlanıyor |
| (c) v2 GWA açgözlü (500 m) | %-0,92 | %-2,27 | %6,9 | 1,000 | 0,0 / 0,0 | – | **ihlal** |
| (c) Düzenli ızgara 7D × 4D | %-7,67 | %-15,06 | %6,6 | 0,929 | 0,0 / 0,0 | – | sağlanıyor |

Saha × N ayrıntısı (PyWake Bastankhah yıllık enerji, GWh; parantezde en iyiye fark %):

| Saha | N | MILP | SA | GA | Açgözlü | v2 GWA | Izgara | Jensen iç iz (SA) |
|---|---|---|---|---|---|---|---|---|
| Balıkesir-Susurluk | 12 | 172,4 (0,00) | 172,1 (-0,14) | 171,9 (-0,28) | 171,9 (-0,28) | 170,4 (-1,11) | 158,1 (-8,25) | %2,5 |
| Balıkesir-Susurluk | 20 | 270,7 (0,00) | 270,1 (-0,22) | 269,4 (-0,48) | 269,4 (-0,48) | 269,3 (-0,51) | 229,9 (-15,06) | %5,6 |
| Sivas-Gürün | 12 | 172,6 (0,00) | 172,6 (0,00) | 171,8 (-0,42) | 171,5 (-0,63) | 171,4 (-0,66) | 166,6 (-3,47) | %3,1 |
| Sivas-Gürün | 20 | 267,7 (-0,36) | 268,4 (-0,09) | 268,0 (-0,26) | 265,2 (-1,30) | 267,7 (-0,35) | 260,8 (-2,95) | %6,4 |
| Çanakkale-Ezine | 12 | 165,6 (-0,13) | 165,7 (-0,08) | 165,7 (-0,10) | 165,4 (-0,28) | 162,1 (-2,27) | 152,6 (-8,00) | %3,8 |
| Çanakkale-Ezine | 20 | 255,1 (-0,04) | 254,6 (-0,23) | 254,0 (-0,45) | 252,7 (-0,98) | 253,7 (-0,60) | 234,1 (-8,26) | %6,4 |

MILP durumu: Çanakkale-Ezine N=12: Optimal (boşluk %0,1, 24 s); Çanakkale-Ezine N=20: Time limit reached (boşluk %5,4, 60 s); Sivas-Gürün N=12: Time limit reached (boşluk %0,9, 60 s); Sivas-Gürün N=20: Time limit reached (boşluk %6,7, 60 s); Balıkesir-Susurluk N=12: Optimal (boşluk %0,1, 39 s); Balıkesir-Susurluk N=20: Time limit reached (boşluk %4,1, 60 s).

**Seçim (web uygulaması): çok başlangıçlı benzetimli tavlama + yerel arama.**
- **Kalite:** en iyiye ortalama farkı %0,13 (en kötü %0,48). Gürün N = 20'de süre sınırına takılan MILP'i geçiyor. MILP
  6 durumun 4'ünde 60 s sınırına çarptı (boşluk %1–7) ve ikili-kayıp yaklaşımını en iyilediği için gerçek modelde her
  zaman en iyi değil.
- **Süre:** 1,3–2,7 s (MILP 24–60 s). Tam analizin 60 s'lik yerleşim bütçesinin küçük bir kısmı; kalan süre bakım
  simülasyonuna kalıyor.
- **Tekrarlanabilirlik:** tohum sabit (0) olduğu için uygulamada her çalıştırma aynı sonucu verir. Tohumlar arası değişim
  %0,1 (CV), yani tohum seçimi sonucu anlamlı değiştirmiyor.
- **Neden MILP değil:** %0,1'lik enerji farkı rüzgâr tahmininin belirsizliği (KF ±3–4 puan, yani ±%10) yanında ihmal
  edilebilir; 60 s ise tam analizin bütçesinin tamamı.
- **v2 kuralının sorunu:** en rüzgârlı hücreleri seçtiği için konum kazancı yüksek (1,01–1,02), ama türbinleri aynı sırta
  hâkim yön boyunca dizdiği için iz kaybı iki katı ve **elips kısıtını ihlal ediyor** (500 m < 5D = 705 m).

### 4.6 Bağlayıcı kısıtlar ve sezgisel yorum
- **Asgari aralık (elips) en sıkı kısıt.**
  - 2 km'lik alana en fazla ~26–28 E-141 sığıyor.
  - N = 20'de iç iz kaybı %6–7'ye çıkıyor; N = 12'de %2,5–3,5.
- **Konum kazancı ile iz kaybı arasında ödünleşim var.**
  - v2 GWA kuralı en rüzgârlı hücreleri seçiyor (konum kazancı 1,01–1,02) ama türbinleri hâkim yön boyunca dizdiği için
    iz kaybı iki katına çıkıyor (%7,5).
  - Optimum, biraz daha az rüzgârlı ama hâkim yöne dik dizilmiş konumları seçiyor.
- **Düzenli ızgara en kötü sonuç** (−%3,5 … −%15). Karmaşık arazide GWA'nın en iyi hücreleri ızgara düğümlerine denk
  gelmiyor. Türkiye'deki sırt yerleşimlerinde ızgara mantığı geçerli değil.

---

## 5. Komşu iz etkisi ve atlas hipotez testi

### 5.1 Kalibre santrallerin iz kaybı
85 santral (OSM yerleşimi, kendi türbin vekili, kendi kalibre rüzgârı, ERA5 hücre yönü; komşular 10 km)
→ `data/atlas/santral_iz_kaybi.csv`.

| | Ortalama | P10 | Medyan | P90 | En yüksek |
|---|---|---|---|---|---|
| İç iz | %4,7 | %1,2 | %4,1 | %8,6 | %14,5 (Uşak RES, 50 türbin, en yakın komşu ort. 3,0D) |
| Dış (komşu) iz | %0,45 | %0 | %0,06 | %0,6 | %11,7 (Çamseki, Ezine: Enerjisa ve Sares arasında) |
| Toplam | %5,1 | %1,5 | %4,7 | %9,4 | %14,9 |

Gerçek bir Türk santrali için makullük:
- **Kangal RES** (Gürün, 70 türbin, ort. en yakın komşu 4,1D): %6,1.
- **Geycek** (Kırşehir, 70 türbin, 2,2D): %8,0.
- **Balıkesir RES** (52 türbin, 60 komşu türbin): %3,8 (+ dış %0,2).

Kara santrallerinde yıllık iz kaybı enerji verimi değerlendirmelerinde tipik olarak tek hanelidir. Açık denizde bile
yerleşim optimizasyonuyla ≤ %10 hedeflenir (Fraunhofer IWES). Kara ortam türbülansı izi daha hızlı karıştırır.

### 5.2 Hipotez: "Balıkesir–Biga'da atlas rüzgârı yüksek gösteriyor çünkü kümelenme iz kaybı yaratıyor"
Faz A'da Balıkesir ve Biga santrallerinin GWA sonrası artığı R = K/c düşük çıkmıştı (0,84–0,98; Trakya 1,02–1,18).
Hipotez: bölge Türkiye'nin en yoğun kümesi; santraller arası iz gözlenen üretimi düşürüyor ama GWA'da yok.

**Test** (`outputs/v3D/D1_hipotez_ozet.json`, n = 85):

| Test | Sonuç |
|---|---|
| ln R ~ ln(1 − W) regresyonu | eğim 0,12 (SH 0,38, t = 0,30), R² = 0,001; kontrollü (karmaşıklık, rakım, kıyı) 0,11 (t = 0,28); bootstrap %90 GA −0,54 … 0,67 |
| ln q ~ ln(1 − W) (q = gözlenen KF / GWA-düzeltmeli model KF) | eğim 0,33 (t = 0,55), R² = 0,004; GA −0,72 … 1,20 |
| Spearman (W, ln R) | −0,06 |
| Balıkesir–Biga (n = 19) ile diğerleri (n = 66) | iz kaybı %5,4 ile %5,0: fark **0,34 puan**, permütasyon p = 0,70 |
| Bölgenin enerji artığı farkı | ln q: −0,120 ile −0,044 → fark −0,076 (≈ %7,3); iz farkının açıkladığı pay **%5** |

**Sonuç: hipotez çürütüldü.**
- Biga kümesinin dış iz kaybı diğerlerinden yüksek (%0,84 ile %0,34). Ama iç iz kaybı benzer olduğu için toplam fark
  yalnız 0,34 puan.
- Bölgenin artığı (~%7 enerji) iz kaybıyla açıklanamıyor.
- Kalan olası nedenler: GWA'nın bu bölgedeki sistematik yüksek tahmini (mezoölçek model), santrallerin yaşlı/küçük filosu
  için vekil türbin hatası, ERA5 hücre ortalamasının kıyı/sırt karışımı.

### 5.3 Birini dışarıda bırak doğrulaması: önce/sonra

| Durum | RMSE | Medyan mutlak | P90 mutlak | Ort. hata | Komşulu RMSE |
|---|---|---|---|---|---|
| Önce (v2: K, toplu %12) | 6,87 | 4,44 | 11,10 | −0,52 | 6,05 |
| Sonra-1: izden arındırılmış K' + sahanın kendi izi | 7,00 | 4,91 | 11,30 | −0,54 | 6,06 |
| **Sonra-2: K + göreli iz η/(1 − W̄)** (seçilen) | **6,77** | **4,11** | 11,12 | −0,53 | **5,83** |

KF puanı; bootstrap RMSE farkı (4.000): sonra-1 −0,09 … +0,34; sonra-2 −0,31 … +0,09.

**İzden arındırma** (K'_p = s_p·K_p, ort[brüt(sKv)·η_p] = ort[brüt(Kv)]·(1 − W_ref)) iz farklarını katsayıdan çıkarıp
ayrıca modellemeyi dener. Doğrulamayı **kötüleştirdi**, çünkü iz farkları gürültünün yanında küçük. Arındırma iz
modelinin kendi hatasını ekliyor. Bu yüzden **atlas matrisleri güncellenmedi** (`atlas_iz_arindirma: false`;
`kalibrasyon_matrisleri_izsiz.npz` yalnız kayıt için saklandı).

**Çift sayımı önleyen kural (göreli).** Atlas katsayısı K, kalibre santrallerin **gerçek** iz ve kısa duruş kayıplarını
zaten içeriyor. Yeni sahada iz ve kullanılabilirlik bu yüzden **ortalamaya göre** uygulanır:

KF(t) = brüt(K·v_t) · 0,88 · η_iz(t)/(1 − W̄) · A/A_k
     = brüt(K·v_t) · (1 − λ) · η_iz(t) · A,   λ = 1 − 0,88 / ((1 − W̄)·A_k) ≈ %6,3

| Parametre | Değer | Kaynak |
|---|---|---|
| W̄ | %5,1 | atlas santrallerinin hesaplanan ortalama iz kaybı |
| A_k | 0,99 | kalibrasyona gömülü yalnız kısa (< 48 saat) duruş kullanılabilirliği. Atlas ≥ 48 saatlik duruşları dışarıda bıraktığı için; D2 DES'inden 0,990–0,992 |
| A | sahanın simüle edilen tam kullanılabilirliği | D2 |

λ'nın içinde elektrik kaybı (~%3) ve atlasın açıklanmayan ortalama sapması var.

**v2'deki zımni iz:** Toplu %12 kayıp, A_k = 0,99 ve %3 elektrikle W_ref = 1 − 0,88/(0,97·0,99) ≈ %8,4 iz ima ediyordu.
Hesaplanan atlas ortalaması %5,1. v2'nin toplu kaybı izi biraz yüksek, diğer kayıpları düşük tutuyordu; toplamda tutarlı.

---

## 6. Analiz motoruna entegrasyon

### 6.1 Tam analiz
1. **Taban profil:** iz ve kullanılabilirlik hariç, λ ≈ %6,3 (önbellekli).
2. **MILP öncesi** (~1 s):
   - aday konumlar + vekil → açgözlü iç içe yerleşimlerle **çiftlik verimi eğrisi** η(N) = konum kazancı(N) ×
     (1 − iç iz(N)), N = 1..N_sığan;
   - açgözlü yerleşimde PyWake ile komşu izi;
   - kullanılabilirlik ve O&M tablodan.
3. **Kapasite MILP'i** (Aşama 4 modeli) η(N) ile. N tamsayı olduğundan parçalı doğrusal fonksiyon ikili seçimle **kesin**:
   ```
   λ_n ∈ {0,1},  Σ_n λ_n = 1,  N = Σ_n n·λ_n,  N_etkin = Σ_n n·η_n·λ_n
   üretim dengesi:  y_t + k_t + c_t = G·g_t + m·N_etkin·r_t     (maliyetler anma gücüyle: m·N)
   ```
   Böylece MILP her ek türbinin azalan marjinal üretimini (artan iz, düşen konum kalitesi) görür. Türbin üst sınırı alana
   sığan sayıdır.
4. **Seçilen N için yerleşim** (çok başlangıçlı SA, ~2 s) → PyWake (komşular dahil) → saatlik çiftlik profili.
5. **Bakım** (§7, ~8–10 s): çizelge MILP'i → stok → üç strateji DES (60 tekrar, ortak rastgele sayılar).
6. **Değerleme:** profil × A, OPEX = simüle O&M; Monte Carlo'nun kullanılabilirlik gürültüsü DES'ten
   (tekrar sd, yıllık sd).

### 6.2 Hızlı tarama
Önceden hesaplanmış tablolar (`data/atlas/v3_hizli_tablolar.csv`, `src/v3_D2_hizli_tablolar.py`): 12 örnek saha, N = 1..24.
- Medyan iç iz kaybı W(N).
- Kullanılabilirlik ve O&M/MW (N'ye göre).
- Standart tasarımların her biri kendi N'sine göre (1 − W(N)) ile ölçeklenir; hızlı MILP aynı eğriyi kullanır.

| N | İç iz kaybı medyan (P10–P90) | Kullanılabilirlik | O&M bin $/MW-yıl |
|---|---|---|---|
| 4 | %0,6 (%0,3–%1,3) | %97,4 | 31,2 |
| 8 | %2,0 (%0,9–%2,8) | %97,4 | 31,4 |
| 10 | %2,7 (%1,8–%3,8) | %97,4 | 29,2 |
| 12 | %3,2 (%2,4–%4,7) | %97,4 | 27,0 |
| 14 | %4,0 (%2,5–%5,0) | %97,5 | 27,6 |
| 16 | %4,7 (%3,4–%5,4) | %97,5 | 28,2 |
| 20 | %6,4 (%4,6–%7,6) | %97,6 | 26,1 |
| 24 | %8,0 (%6,0–%9,3) | %97,9 | 27,5 |

O&M/MW, ekip sayısının türbin sayısıyla basamaklı artmasından (her 7 türbine bir ekip) dalgalı; küçük santrallerde sabit ekip gideri MW başına daha ağır.

### 6.3 Arayüz
Tam analiz sonucunda iki yeni bölüm ("Eşik" bileşenleri, renkler yalnız `tokenlar.py`):

**Türbin yerleşimi:**
- KPI'lar: türbin, iç/komşu iz, konum kazancı, çiftlik verimi.
- Harita: saha dairesi; türbinler yıllık üretime göre viridis; komşu santral türbinleri gri; ipucunda türbin başına
  üretim, KF, iz kaybı.
- Rüzgâr gülü (12 sektör × 6 hız aralığı), iz kaybı eğrisi, türbin tablosu.

**İşletme ve bakım:**
- KPI'lar: kullanılabilirlik, O&M, kayıp gelir, çizelge kazancı.
- Strateji karşılaştırma tablosu, kullanılabilirlik dağılımı, aylara göre bakım takvimi (MILP ile bahar kampanyası).
- Arızanın mevsimine göre hava beklemesi, önerilen yedek parça stoku, O&M kalemleri.

---

## 7. Bakım ve güvenilirlik

### 7.1 Veri (config `v3.bakim`; kaynaklar config'te)

| Alt sistem | λ küçük / büyük / değişim [1/türbin/yıl] | İş süresi [saat] | Malzeme [€] | Vinç | β | Tedarik [gün] |
|---|---|---|---|---|---|---|
| Kanat/rotor | 0,20 / 0,070 / 0,005 | 9 / 21 / 288 | 170 / 1.500 / 90.000 | ✓ (≤ 8 m/s) | 1,5 | 120 |
| Dişli kutusu | 0,060 / 0,025 / 0,015 | 8 / 22 / 231 | 125 / 2.500 / 230.000 | ✓ | 2,5 | 120 |
| Jeneratör | 0,091 / 0,030 / 0,006 | 7 / 24 / 81 | 160 / 3.500 / 60.000 | ✓ | 2,0 | 90 |
| Ana yatak | 0,020 / 0,020 / 0,006 | 8 / 22 / 160 | 150 / 2.500 / 80.000 | ✓ | 2,5 | 120 |
| Güç elektroniği | 0,069 / 0,037 / 0,001 | 7 / 14 / 57 | 240 / 5.300 / 13.000 | – | 1 | 30 |
| Elektrik | 0,380 / 0,070 / 0,010 | 4 / 19 / 24 | 260 / 2.300 / 13.500 | – | 1 | 30 |
| Kontrol + sensör | 0,620 / 0,060 / 0 | 8 / 14 / – | 200 / 2.000 / – | – | 1 | 14 |
| Pitch/hidrolik | 0,170 / 0,055 / 0,005 | 9 / 19 / 25 | 210 / 1.900 / 14.000 | – | 1 | 30 |
| Yaw | 0,120 / 0,050 / 0,010 | 5 / 20 / 49 | 140 / 3.000 / 12.500 | – | 1 | 45 |
| Diğer (fren, yapı) | 0,180 / 0,040 / 0 | 5 / 21 / 36 | 110 / 2.400 / 10.000 | – | 1 | 30 |
| Sıfırlama | 7,5 | 4 (duruş) | – | – | – | – |

**Kaynaklar:**
- **Toplam arıza oranı 2,43/türbin/yıl.** Kara RES'leri için WMEP (1.500 türbin, Hahn vd. 2007) alt sistem sıklıkları
  grafikten **yaklaşık** okundu. Toplamları Faulstich vd. (2009) Tablo 2'deki WMEP ortalaması 2,4 ile tutarlı (kara
  veritabanları 0,8–2,4).
- **Jeneratör ve konvertör kara oranları, iş süreleri ve malzeme maliyetleri:** Carroll, McDonald & McMillan (2016),
  açık deniz, 350 türbin, Şekil 11–15. İş süresi teknisyenin türbinde geçirdiği süredir; lojistik ve hava beklemesi
  modelde ayrıca eklenir.
- **TAHMİN:** büyük değişim oranlarının bölünmesi, Weibull şekilleri, tedarik ve lojistik süreleri, hava sınırları,
  ekip, ücret, önleyici bakım etkisi, CMS tespit olasılıkları ve P-F aralığı, vinç maliyeti, stok tutma oranı.

**Yaşlanma:** değişim süreçleri Weibull(β > 1) yenileme süreci. Ölçek η, ömür boyu beklenen değişim sayısı
(yenileme fonksiyonu) M(T) = λ·T olacak şekilde sayısal bulunur. İlk denemede H(T) = (T/η)^β = λT kullanıldı; yenileme
ve kesilme yüzünden dişli için 0,0127 < 0,015 verdi ve düzeltildi.

### 7.2 Ayrık olay simülasyonu (SimPy)

| Öğe | Model |
|---|---|
| Varlıklar | N türbin (her biri PyWake'ten gelen üretim payıyla) |
| Kaynaklar | **Teknisyen ekipleri** (simpy.Resource; her 7 türbine bir 2 kişilik ekip) · **büyük vinç** (kapasite 1; mobilizasyon 14 gün) · **kritik parça stokları** (simpy.Container; baz stok) |
| Olaylar | Küçük/büyük onarım: Poisson · değişim: Weibull yenileme · sıfırlama: Poisson · yıllık önleyici bakım: çizelge günü |
| Onarım akışı | arıza → müdahale (4 saat) / parça (48 saat) → ekip kuyruğu → **tırmanma koşullu iş** (v < 15 m/s, 08–18 TSİ) |
| Değişim akışı | arıza → parça (stok ya da 90–120 gün) → vinç kuyruğu + mobilizasyon → ekip → **6 saatlik ardışık kaldırma penceresi** (v < 10 m/s; kanatta 8) → kalan iş |
| Hava | Sahanın saatlik kalibre göbek hızı; 30 yıllık ömür için hava yılları her tekrarda 10 ERA5 yılından çekilir. Birikimli uygun saat dizileriyle her sorgu O(log n) |
| Çıktılar | zaman ve **enerji** bazlı kullanılabilirlik (duruş aralıklarının birleşimi × türbinin saatlik üretimi), kayıp gelir (saatlik fiyat), O&M kalemleri, arıza sayıları, beklemeler; tekrar dağılımı |

**Stratejiler:**
- **Yalnız düzeltici:** önleyici bakım yok. Küçük/büyük onarım oranları × 1,4, Weibull ölçeği × 0,8 (TAHMİN).
- **Takvim bazlı önleyici:** yılda bir 30 iş saatlik bakım, çizelge MILP'inin günlerinde; temel oranlar.
- **Durum bazlı (CMS):** takvim + titreşim izleme. Aktarma organı değişimleri P-F aralığında (30–120 gün önce) tespit
  edilir. Tespit olasılığı: dişli 0,8, jeneratör 0,7, ana yatak 0,6, kanat 0,3. Tespitte parça siparişi ve vinç
  planlaması başlar. İş arızadan önce yapılırsa malzeme × 0,7 ve duruş yalnız iş süresi. CMS 1.200 $/türbin-yıl.

### 7.3 Önleyici bakım çizelgesi — zaman indeksli MILP

| | |
|---|---|
| **Kümeler** | I türbinler, D = {0, …, 364} günler |
| **Parametreler** | p_d: d'de (08:00) başlayan 30 iş saatlik bakımın beklenen takvim süresi [gün] (hava + vardiya, 10 yıl) · c_d: aynı bakımın beklenen kayıp geliri [$] (yalnız çalışılan saatlerde duruş; saatlik üretim × saatlik fiyat) · π_i: türbin üretim payı · K: bakım ekibi sayısı |
| **Değişken** | x_{i,d} ∈ {0,1}: i'nin bakımı d'de başlar (d + p_d ≤ 365) |
| **Amaç** | min Σ_i Σ_d π_i·c_d·x_{i,d} |
| **Kısıtlar** | Σ_d x_{i,d} = 1 ∀i (yılda bir) · Σ_i Σ_{d: d ≤ t < d+p_d} x_{i,d} ≤ K ∀t (ekip kapasitesi) |

N = 14'te ~5.000 ikili değişken; HiGHS'ta 0,1 s, %0 boşluk.

Karşılaştırma kuralları:
- **Bahar kampanyası:** 1 Nisan'dan ardışık (yaygın saha pratiği).
- **Eşit dağıtım:** yıla yayılmış.

### 7.4 Yedek parça stoku — baz stok (S−1, S), simülasyon tabanlı optimizasyon
**Politika:** her çekişte bir parça sipariş edilir, L gün sonra gelir. FIFO bekleyen siparişlerle klasik özdeşlik:
k'ıncı talep (k−S)'inci siparişle karşılanır → hazır_k = d_{k−S} + L (k > S).

**Ek duruş:** max(0, hazır_k − max(t_arıza, d_k + vinç mobilizasyonu)). Vinç zaten beklenirken gelen parça kayıp yaratmaz.

**Amaç:** min_S E[kayıp gelir(S)] + S × parça değeri × %15/yıl.

**Ortak rastgele sayılar:** tüm S değerleri, DES ile aynı örnekleme yordamı ve tohumlarla üretilen **aynı talep
akışlarında** değerlendirilir. Farkların varyansı düşer; "S = 1, S = 0'dan iyi" kararı gürültüden etkilenmez.

**Doğrulama:** kapalı form, olay bazlı stok benzetimiyle aynı bekleme sürelerini veriyor (`test_baz_stok_ozdesligi`).

**Faz F genişlemesi:** sahalar arası havuzlama, talep akışlarının birleştirilip transfer süresiyle aynı fonksiyona
verilmesidir (`havuz_transfer_h` parametresi).

### 7.5 Sonuçlar (N = 14, SA yerleşimi, 200 tekrar; `outputs/v3D/D2_*`)

| Saha | Strateji | Kullanılabilirlik zaman / enerji | Enerji P10–P90 | Kayıp üretim GWh/yıl | Kayıp gelir bin $/yıl | O&M bin $/MW-yıl | Toplam bin $/yıl (P10–P90) |
|---|---|---|---|---|---|---|---|
| Ezine | Düzeltici | %96,3 / %96,2 | 95,8–96,6 | 6,7 | 402 | 24,9 | 1.866 (1.768–1.969) |
| Ezine | Takvim | %97,0 / %97,0 | 96,6–97,4 | 5,2 | 302 | 25,1 | 1.776 (1.684–1.874) |
| Ezine | **Durum (CMS)** | **%97,4 / %97,4** | 97,1–97,7 | 4,5 | 261 | 25,5 | **1.761** (1.679–1.838) |
| Gürün | Durum | %97,4 / %97,3 | 97,0–97,6 | 4,9 | 278 | 25,5 | 1.778 |
| Susurluk | Durum | %97,4 / %97,4 | 97,1–97,7 | 4,8 | 275 | 25,5 | 1.776 |

**Strateji kararı:**
- Durum bazlı bakım toplam maliyette en iyi ama takvime üstünlüğü küçük: ~15 bin $/yıl, P10–P90 aralıkları örtüşüyor.
- Düzeltici strateji ~105 bin $/yıl daha pahalı ve değişkenliği yüksek (yıllık kullanılabilirlik sd %2,2; durumda %1,3).
- CMS'nin değeri ortalamadan çok **kuyruk riskini** azaltmakta. Kayıp gelirin ana kaynağı 90–120 günlük tedarik süresi;
  CMS bu süreyi arızadan önceye çekiyor.

**Çizelge kazancı** (yıllık önleyici bakımın kayıp geliri):

| Saha | MILP | Bahar kampanyası | Eşit dağıtım | Kazanç (bahara göre) |
|---|---|---|---|---|
| Ezine | 4,4 bin $ (338 MWh) | 10,1 bin $ (449 MWh) | 25,7 bin $ | **5,7 bin $/yıl (%56)** |
| Gürün | 7,3 bin $ (469 MWh) | 14,6 bin $ (639 MWh) | 26,5 bin $ | **7,3 bin $/yıl (%50)** |
| Susurluk | 6,3 bin $ (452 MWh) | 11,5 bin $ (511 MWh) | 28,9 bin $ | **5,3 bin $/yıl (%46)** |

- MILP bakımları Nisan–Haziran'a yayıyor (Ezine 4/6/4).
- Bahar kampanyası hepsini Nisan'a yığdığı için ekip sırası bazı türbinleri yine rüzgârlı günlere itiyor.
- Ege'de yazın meltem güçlü; "yaz bakımı" sezgisi burada yanlış. MILP en düşük rüzgâr × fiyat penceresini buluyor.
- Mutlak kazanç küçük (O&M'nin ~%0,4'ü). Değeri kural olarak sıfır maliyetli olması ve büyük portföyde ölçeklenmesi.

**Stok** (S* ve toplam maliyet bin $/yıl, S = 0 / 1):

| Kalem | Ezine 14 türbin | Ekonomik eşik |
|---|---|---|
| Dişli kutusu | S* = 0 (25,0 / 38,1) | 28+ türbinde S* = 1 |
| Kanat | S* = 0 (13,0 / 14,7) | sınırda; Gürün ve Susurluk'ta 14 türbinde bile S* = 1 |
| Jeneratör | S* = 0 (6,2 / 9,8) | 28+ türbinde 1 |
| Ana yatak | S* = 0 (11,7 / 13,1) | 28+ türbinde 1 |

Tek bir 14 türbinlik santral için kritik parça stoğu tutmak ekonomik değil: tutma maliyeti, nadir değişimlerde (dişli
~0,2/yıl) bekleme kaybını aşıyor. Aynı stok 28+ türbine hizmet ettiğinde dört kalemin hepsinde 1 adet ekonomik. Bu,
**Faz F'deki havuzlamanın** doğrudan gerekçesi.

**Arızanın mevsimine göre hava beklemesi** (vinçli dişli değişimi, Ezine):

| | Ara | Oca | Şub | Mar | Nis | May | Haz | Tem | Ağu | Eyl | Eki | Kas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gün | 1,09 | 1,45 | 1,06 | 1,04 | 0,34 | 0,14 | 0,14 | 0,32 | 0,64 | 0,53 | 0,47 | 0,78 |

Simülasyonda bu fark seyreliyor: 14 günlük vinç mobilizasyonu ve aylarca süren tedarik, işin başladığı mevsimi arızanın
mevsiminden ayırıyor.

### 7.6 O&M mutabakatı: model ile v1 sabit varsayımı (35.000 $/MW-yıl)

> **Güncelleme (v3 Ö1, `docs/v3_E_cbs_cok_kriterli_lojistik.md` §0.1):** bu bölümdeki 25,5 bin $/MW-yıl bir kapsam farkı içeriyordu. Mutlak O&M artık işletme modelinden (varsayılan FSA, 34 $/kW-yıl); genel gider çarpanı ve "diğer sabit giderler" kaldırıldı. Aşağıdaki tablo tarihsel kayıttır.

| Kalem (Ezine, 14 × 4,2 MW, durum stratejisi) | bin $/yıl | $/MW-yıl |
|---|---|---|
| Teknisyen ekipleri (2 × 2 kişi, 2.000 saat, 45 $/saat) × 1,30 genel gider | 468 | 7.959 |
| Düzeltici malzeme × 1,30 | 129 | 2.186 |
| Vinç işleri × 1,30 | 67 | 1.145 |
| Önleyici bakım malzemesi × 1,30 | 109 | 1.857 |
| Durum izleme (CMS) × 1,30 | 22 | 371 |
| Stok tutma | 0 | 0 |
| Diğer sabit giderler (saha yönetimi, BOP, SCADA, güvenlik, yol) | 706 | 12.000 |
| **Toplam (model)** | **1.501** | **25.519** |
| v1 sabit varsayım | 2.058 | 35.000 |

**Fark −9.500 $/MW-yıl (−%27). Açıklama:**
1. **Kapsam:** 35 bin, Lazard'ın 24,5–40 $/kW-yıl bandının üst ucundan "tam kapsamlı servis sözleşmesi" fiyatıydı. NREL 2024
   kara OpEx'i 43 $/kW-yıl, ama bu sigorta, arazi kirası ve vergi içeriyor. Bu modelde sigorta (CAPEX oranı), arazi ve
   TEİAŞ bedeli ayrı kalemler.
2. **Maliyet ile fiyat:** aşağıdan yukarı model **maliyeti** ölçüyor. Servis sözleşmesi fiyatı, OEM'in risk primini (büyük
   bileşen değişimini garanti etmesi) ve kârını içerir. Genel gider çarpanı (1,30) yalnız organizasyon giderini taşıyor.
3. **Türkiye işçiliği:** 45 $/saat (TAHMİN) Avrupa'nın yarısı civarı.
4. **Carroll maliyetleri yalnız malzeme:** lojistik ve tamir atölyesi işçiliği yok. Vinç ayrıca eklendi.

**Karar:** model varsayılan (config `bakim_modeli: yeni`), ama finansal sonucun bu farka duyarlılığı önce/sonra
tablosunda ayrıca gösteriliyor (§8.3). Gerçek projede bir OEM servis teklifi (fiyat + kullanılabilirlik garantisi)
alınmalı. Model, teklifin "makul maliyet + risk primi" ayrıştırması için bir taban veriyor.

**Kullanılabilirlik ile sektör:**
- Simüle edilen %97,0–97,4 (takvim/durum), sektörün kara için tipik %95–98'i (Faulstich vd. 2009: %95–99) içinde.
- WMEP'in yıllık duruşu 137–156 saat (≈ %98,3 zaman); modelde 230–330 saat. Fark modern büyük rotorlu türbinlerin
  vinçli değişimlerinden ve uzun tedarik sürelerinden.

**Arıza sayıları ile girdi:** 29 alt sistem × sınıfta simüle oran / girdi oranı 0,96–1,10 (değişimler 0,96–1,10,
onarımlar 0,97–1,03; 200 tekrar × 14 türbin × 30 yıl). `outputs/v3D/D2_ariza_dogrulama.csv`.

---

## 8. D3 — Doğrulama ve önce/sonra

### 8.1 İz kaybı makullüğü
- Optimum yerleşimlerde iç iz %2,5–3,7 (N = 12) ve %5,1–6,6 (N = 20).
- Atlas santrallerinde medyan %4,7, P90 %9,4; büyük santrallerde %4–8.
- Jensen/Park ile Bastankhah arasındaki fark ±0,5 puan (yöntem sıralamasını değiştirmiyor).

**Gerçek Türk santralleri** (OSM yerleşimi, `src/v3_D3_gercek_santral.py` → `outputs/v3D/D3_gercek_santral.csv`), iç iz kaybı:

| Santral | Türbin | Ort. en yakın komşu | Bastankhah TI %8 / %10 / %12 | Jensen |
|---|---|---|---|---|
| Kangal (Sivas-Gürün) | 70 | 4,1D | %7,0 / %6,1 / %5,4 | %6,2 |
| Geycek (Kırşehir) | 70 | 2,2D | %8,4 / %8,0 / %7,7 | %7,5 |
| Şah (Bursa) | 36 | 2,9D | %7,4 / %6,3 / %5,6 | %6,4 |
| Yahyalı (Kayseri) | 45 | 3,3D | %6,4 / %5,6 / %5,0 | %6,1 |
| Enerjisa Çanakkale (Ezine) | 13 | 4,0D | %5,6 / %5,0 / %4,4 | %5,1 |
| Balıkesir RES | 52 | 2,4D | %4,1 / %3,6 / %3,2 | %3,8 |
| Soma (Manisa) | 46 | 3,7D | %3,1 / %2,8 / %2,6 | %3,0 |

Büyük santrallerde %3–8, iki model arasında ±0,5 puan, türbülans varsayımına ±1 puan duyarlı. Bu, kara santralleri
için tipik tek haneli aralıkla tutarlı.

### 8.2 Kullanılabilirlik ve arıza sayıları
§7.6.

### 8.3 Üç sahada önce/sonra (tam analiz, 2 çekirdek)

| Saha | Durum | Tasarım RES / BESS | Türbin | İç iz | Kullanılabilirlik | O&M bin $/MW-yıl | RES KF | P50 MWh/MW | E[NPV] M$ | P(NPV>0) | Başabaş $/MWh | Karar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ezine | Önce (v2) | 58,8 / 31 MW | 14 | toplu %12 | toplu | 35,0 | %34,0 | 2.982 | **-6,30** | %33 | 62,6 | rafa kaldır |
| Ezine | v3 modelleri, v2 tasarımı | 58,8 / 31 MW | 14 | %3,9 | %97,4 | 25,5 | %33,4 | 2.926 | **-3,39** | %39 | 60,5 | rafa kaldır |
| Ezine | v3 yerleşim, sabit O&M (35 bin, A_k) | 29,4 / 30 MW | 7 | %2,9 | %99,0 | 35,0 | %37,0 | 3.237 | **-1,40** | %41 | 59,8 | rafa kaldır |
| Ezine | **Sonra (v3)** | 42,0 / 30 MW | 10 | %3,1 | %97,5 | 28,7 | %35,0 | 3.069 | **-0,82** | %44 | 58,8 | rafa kaldır |
| Gürün | Önce (v2) | 54,6 / 32 MW | 13 | toplu %12 | toplu | 35,0 | %34,6 | 3.030 | **-5,71** | %34 | 62,4 | rafa kaldır |
| Gürün | v3 modelleri, v2 tasarımı | 54,6 / 32 MW | 13 | %3,4 | %97,3 | 26,2 | %34,7 | 3.036 | **-1,90** | %43 | 59,5 | rafa kaldır |
| Gürün | v3 yerleşim, sabit O&M (35 bin, A_k) | 42,0 / 30 MW | 10 | %2,5 | %99,0 | 35,0 | %36,0 | 3.158 | **-2,62** | %39 | 60,5 | rafa kaldır |
| Gürün | **Sonra (v3)** | 46,2 / 31 MW | 11 | %2,7 | %97,3 | 27,7 | %35,2 | 3.081 | **-1,30** | %43 | 59,2 | rafa kaldır |
| Susurluk | Önce (v2) | 58,8 / 31 MW | 14 | toplu %12 | toplu | 35,0 | %34,9 | 3.056 | **-5,04** | %36 | 61,6 | rafa kaldır |
| Susurluk | v3 modelleri, v2 tasarımı | 58,8 / 31 MW | 14 | %3,4 | %97,5 | 25,8 | %34,9 | 3.053 | **-1,22** | %44 | 58,9 | rafa kaldır |
| Susurluk | v3 yerleşim, sabit O&M (35 bin, A_k) | 50,4 / 31 MW | 12 | %2,6 | %99,0 | 35,0 | %36,0 | 3.150 | **-2,09** | %42 | 59,7 | rafa kaldır |
| Susurluk | **Sonra (v3)** | 54,6 / 31 MW | 13 | %3,1 | %97,4 | 26,2 | %35,0 | 3.067 | **-0,36** | %47 | 58,3 | rafa kaldır |

**E[NPV] değişiminin ayrıştırması** (M$; en iyi gelir yapısı YEKDEM opsiyonu):

| Saha | Önce | Aynı tasarımda v3 modelleri | Tasarımın yeniden optimize edilmesi | Sonra | O&M modeli yerine sabit 35 bin olsaydı |
|---|---|---|---|---|---|
| Ezine | -6,30 | 2,91 | 2,57 | -0,82 | -1,40 |
| Gürün | -5,71 | 3,81 | 0,60 | -1,30 | -2,62 |
| Susurluk | -5,04 | 3,82 | 0,86 | -0,36 | -2,09 |

**Yorum.**
- **Aynı tasarımda** v3 modelleri E[NPV]'yi 2,9–3,8 M$ artırıyor. Enerji neredeyse aynı (Ezine KF %34,0 → %33,4:
  iç iz %3,9 ve kullanılabilirlik %97,4 göreli kurala göre ortalamadan biraz kötü; Gürün ve Susurluk ±%0,3). Farkın
  neredeyse tamamı O&M'den: 35 → ~25,5 bin $/MW-yıl, 58,8 MW'ta yılda ~0,56 M$, 30 yılda vergi sonrası ~3–4 M$.
- **Tasarımın yeniden optimize edilmesi** +0,6 … +2,6 M$ ekliyor. Kapasite MILP'i artık her ek türbinin daha az
  ürettiğini görüyor (artan iz, daha az rüzgârlı hücre) ve santrali 10–13 türbine küçültüyor. v2'nin düz MW başı
  profiliyle MILP her zaman üst sınıra (14 türbin) gidiyordu; deterministik NPV'si sıfıra yakındı ama Monte Carlo'da
  negatifti. Küçük proje, negatif NPV'yi küçültüyor.
- **O&M'e duyarlılık:** O&M modeli yerine v1'in 35 bin $'ı kullanılsaydı (yerleşim yine açık) E[NPV] −1,4 / −2,6 /
  −2,1 M$ olurdu. MILP bu durumda daha da küçük bir santral seçiyor (7–12 türbin).
- **Karar değişmedi:** üç sahada da "rafa kaldır". P(NPV > 0) %33–36'dan %43–47'ye, Monte Carlo başabaş fiyatı
  61,6–62,6'dan 58,3–59,2 $/MWh'e iniyor; senaryo fiyatı 58. Yani v3 projeyi eşiğe yaklaştırıyor ama geçirmiyor.
  O&M fiyatı kararı tek başına çevirmiyor: tam kapsamlı servis teklifi 35 bin $ olsa bile (yerleşim açık) E[NPV]
  −1,4 … −2,6 M$; v2'nin −5 … −6 M$'ına dönmüyor, çünkü tasarım küçülüyor.

### 8.4 Süreler (2 çekirdek benzetimi)

| Saha | Hızlı tarama önce / sonra (profil sıcak) [s] | Tam analiz önce / sonra [s] | v3 eki: iz eğrisi + yerleşim + bakım [s] | İşletme tabloları önce / sonra [s] |
|---|---|---|---|---|
| Ezine | 3,3 / 7,4 | 64 / 65 | 1,0 + 1,2 + 7,8 = **9,9** | 55 / 48 |
| Gürün | 2,5 / 3,1 | 62 / 73 | 0,9 + 1,3 + 8,5 = **10,7** | 53 / 54 |
| Susurluk | 3,1 / 3,3 | 77 / 110 | 0,9 + 1,5 + 10,8 = **13,2** | 60 / 84 |

- 2 çekirdek benzetimi (`MOTOR_CEKIRDEK=2`, OMP/VECLIB tek iş parçacığı), soğuk işletme tabloları ve sonuç önbelleği.
- v3'ün doğrudan eki 10–13 s; bütçe 60 s (yerleşim) + 30 s (bakım).
- Tam analiz süresindeki asıl fark tasarıma bağlı işletme tablolarından (batarya LP ızgarası) geliyor, v3 hesaplarından
  değil.
- Hızlı taramada Ezine'nin MILP'i ikili seçim değişkenleriyle 2 → 6 s uzadı. Diğer sahalarda değişmedi. Hedef (≤ 90 s)
  korunuyor.

---

## 9. Sınırlamalar
- **İz modeli:** mühendislik modeli (Gauss + karelerin toplamı). Arazi akışı (sırt hızlanması GWA'dan statik olarak var),
  derin dizi etkisi, yön değişkenliği ve atmosferik kararlılık yok. Türbülans yoğunluğu sabit %10 (TAHMİN).
- **Komşu türbinler:** OSM eksik olabilir; birim güç bilinmeyenlerde sınıf varsayılanı.
- **Bakım verisi:** Carroll açık deniz verisi (iş süreleri, maliyetler) kara için uyarlandı. WMEP alt sistem oranları
  grafikten okundu. Büyük değişim oranları, Weibull şekilleri, CMS etkileri TAHMİN. Bunlar için duyarlılık D2 çıktılarında
  strateji düzeyinde var; parametre bazında ayrı bir duyarlılık analizi yapılmadı.
- **Önleyici bakım etkisi** (oranlar × 1,4) literatürde tek bir değere bağlanamadı; strateji farkının büyüklüğü bu varsayıma duyarlı.
- **Dışlama katmanları** (yol, yerleşim, koruma alanı, eğim) yok. Faz E'de arayüz hazır.
- **Hızlı tarama** tablo medyanını kullanır. Sahanın rüzgâr gülü yönlülüğü ve alanı (2 km dışı) dikkate alınmaz.

---

## 10. Mülakatta anlatım (kısa)
- **Problem:** "Hangi N konuma türbin koyayım?" bir ikili seçim problemi. İz etkileşimi amacı kuadratik yapıyor.
- **(a) MILP:** Glover'la O(n) değişkenle kesin doğrusallaştırdım. **(b) Sezgiseller** gerçek modeli doğrudan en iyiliyor.
  **(c) Referanslar:** ızgara ve v2 kuralı.
- **Sonuç:** MILP en iyi ama süre sınırına çarpıyor (6 durumun 4'ünde). Çok başlangıçlı SA ortalamada MILP'ten
  ~%0,04 geride, bir sahada MILP'i geçiyor ve ~2 s sürüyor. Web için SA'yı seçtim. Bir doğrulama hatası (yön ayrıklaştırması) MILP'in modeli sömürmesiyle ortaya çıktı.
- **Hipotez:** "Biga'da iz kaybı atlası şaşırtıyor" hipotezini veriyle çürüttüm (fark 0,34 puan, p = 0,70). Atlası
  değiştirmedim; çift sayımı göreli kuralla önledim.
- **Bakım:** SimPy ile kuyruk + hava + vinç + stok simülasyonu. Zaman indeksli MILP çizelgesi bahar kampanyasının kayıp
  gelirini yarıya indiriyor. Baz stok özdeşliğiyle simülasyon tabanlı stok optimizasyonu: tek santralde stok ekonomik
  değil, 28+ türbinde ekonomik (havuzlama).
