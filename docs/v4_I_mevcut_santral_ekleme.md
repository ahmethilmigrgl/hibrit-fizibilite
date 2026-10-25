# v4 Faz I — Mevcut RES'e GES ve batarya ekleme (yardımcı kaynak)

**Soru:** Türkiye'deki mevcut bir rüzgâr santralinin bağlantısı zaten var ve rüzgâr onu çoğu saat doldurmuyor (86 kalibre
santralde medyan bağlantı kullanımı %33). Aynı bağlantıya ne kadar GES ve batarya eklemeli, ve bu ekleme ne kadar değer
yaratır?

Yeni bir sahaya göre farklar: şebeke bağlantısı, TEİAŞ kapasite bedeli, arazi ve RES maliyetleri zaten ödenmiştir. Asıl
kısıt bağlantı gücüdür (MWe). Rüzgâr ve güneş aynı saatlerde bağlantıyı aşarsa üretim kesilir.

Modüller: `src/ekleme/` (`santraller.py` anonim santral listesi, `analiz.py` ekleme analizi + hafif tarama). Arayüz:
`uygulama/sayfa_ekleme.py` (`/ekleme`). Config: `v4.ekleme`. Profil modu: `KullaniciVarsayimlari(kalibrasyon="santral:<id>")`.
Betik: `src/v4_I1_ekleme.py` → `outputs/v4I/`, `data/atlas/v4_ekleme_tarama.csv`. Testler: `tests/test_v4_I.py`.

---

## 1. Mevzuat çerçevesi (modelin varsayımları)

| Konu | Kural | Kaynak / güven |
|---|---|---|
| Yardımcı kaynak | Lisanslı tesise ana kaynak dışında kaynak eklenebilir ("birden çok kaynaklı üretim tesisi"); lisans tadili gerekir | Lisans Yönetmeliği ve YEK Destekleme Yönetmeliği, 08.03.2020 değişiklikleri; tanım RG 28.05.2021 |
| Güç | Mekanik kurulu güç (MWm) artar, elektriksel güç (MWe = bağlantı) aynı kalır | EPDK tadil örnekleri (ör. 19,51 → 22,966 MWm, 18,68 MWe sabit) |
| YEKDEM | Ana kaynak YEKDEM'deyse yardımcı kaynak, ana kaynağın kalan süresince ve tesisteki **en düşük** yenilenebilir fiyatından yararlanır | Aydem Yenilenebilir izahnamesi s. 69 (ikincil kaynak; madde metni doğrulanmadı → TAHMİN) |
| Eski YEKDEM fiyatı | Rüzgâr ve güneş 7,3 ABD doları sent/kWh, 10 yıl, nominal | 5346 sayılı Kanun I sayılı cetvel |
| Bütünleşik depolama | Üretim tesisine bütünleşik depolama tanımlı; 7189'daki depolamalı üretim fiyatı bütünleşik ünitelere uygulanmaz | Depolama Faaliyetleri Yönetmeliği, Aralık 2025 değişikliği (01.01.2026) |

Modellenmeyenler: lisans tadili süresi, ÇED, arazi, TEİAŞ/dağıtım şirketi görüşü, sayaç düzeni.

---

## 2. Profil: santralin kendi kalibrasyonu

Atlas her kalibre santral için gerçek EPİAŞ üretimine uydurulmuş 12 × 24 (ay × saat) bir hız katsayısı matrisi içerir.
Santral kendi türbin vekili ve göbek yüksekliğiyle bu matrisle modellenir (`genel.k_matrisi(..., "santral:<id>")`). Yeni bir
sahadaki gibi komşulardan aktarım yapılmaz.

**Doğrulama** (`outputs/v4I/I1_dogrulama.json`, 86 santral): model KF − gözlenen KF ortalaması −0,07 puan, mutlak medyan
0,59 puan, en büyük 1,86 puan.

### 2.1 Kullanıcının üretim verisi (MCP)

İsteğe bağlı saatlik üretim CSV'si (`zaman` TSİ, `uretim_mw`) modelin ay × saat oranını düzeltir:

$$
r_{m,h} = \frac{\overline{u}_{m,h}}{\overline{\hat u}_{m,h}},\qquad \hat u'_t = r_{m(t),h(t)} \cdot \hat u_t
$$

Hava yılları ve GES ile eşzamanlılık korunur. **Ölçüm–korelasyon–tahmin (MCP) ayrıntısı:** ölçüm model dönemiyle
(2014–2023) en az 300 gün örtüşüyorsa oran **aynı saatler** üzerinden hesaplanır. Böylece ölçüm yılları rüzgârlı ya da sakin
geçtiyse bu santral farkı sanılmaz; uzun dönem düzeltmesi kendiliğinden yapılır. Örtüşme yoksa ölçümün ortalaması modelin
10 yıllık ortalamasıyla kıyaslanır ve bu bir uyarıyla belirtilir.

Bu kural doğrulamada bulunan bir hatadan geldi. İlk sürüm her zaman 10 yıllık ortalamayla kıyaslıyordu. Modelin kendi
profili %10 artırılıp 2021–22 için "ölçüm" diye verildiğinde oranı 1,146 buldu, çünkü 2021–22 ortalamadan rüzgârlıydı.
Aynı saatler üzerinden kıyaslayınca oran tam 1,100 çıkıyor (test: `test_csv_mcp_ruzgarli_yillari_santral_farki_sanmaz`).

---

## 3. Artımsal ekonomi ve optimizasyon

### 3.1 Artımsal maliyetler

İki durumda da ortak olan kalemler sıfırlanır: RES CAPEX, O&M, arazi, söküm, şebeke CAPEX'i ve TEİAŞ kapasite bedeli
(`artimsal_cfg`). İnşaat 1 yıl, ilk işletme yılı 2027. RES'in analiz ufku boyunca çalıştığı varsayılır (ömür uzatma ya da
yenileme iki durumda da aynıdır, farkta söner).

$$
\Delta\mathrm{NPV} = \mathrm{NPV}(\text{RES} + \text{ekleme}) - \mathrm{NPV}(\text{yalnız RES})
$$

### 3.2 Kapasite MILP'i

Mevcut kapasite modeli (`docs/04_optimizasyon.md`) iki değişiklikle kullanılır:

- Santral tek bir "türbin" olarak temsil edilir: `turbin_gucu` = kurulu güç, $N = 1$ sabit. Böylece RES tamsayı değişkeni
  sabitlenir, kalan karar değişkenleri GES gücü $G$, batarya gücü $P$ ve enerjisi $E$ olur.
- Bağlantı kısıtı santralin MWe'sidir; GES üst sınırı varsayılan olarak 1,5 × MWe (arazi/izin).

RES sabit olduğundan toplam NPV'yi büyütmek artımsal NPV'yi büyütmekle aynıdır. Amaç ve saatlik kısıtlar (enerji dengesi,
şebeke sınırı $x_t \le \mathrm{MWe}$, batarya SoC dinamiği, SFK rezervi) değişmez.

### 3.3 GES başabaş CAPEX'i

Bataryasız durumda artımsal NPV, GES CAPEX'inde doğrusaldır (amortisman vergi kalkanı dahil):

$$
\Delta\mathrm{NPV}(c) = a - b\,c \quad\Rightarrow\quad c^\* = a / b
$$

$a$, GES CAPEX'i sıfırken artımsal NPV'dir; $b$ iki noktadan bulunan eğimdir. $c^\*$, "GES eklemesi hangi kurulum
maliyetinde kâra geçer?" sorusunun yanıtıdır. GES boyutu büyüdükçe $c^\*$ düşer: kesinti artar, güneş kendi fiyatını düşürür
(kanibalizasyon).

---

## 4. Monte Carlo: ortak rastgele sayılar

İki tasarım (RES + ekleme, yalnız RES) **aynı** senaryolarla değerlenir: fiyat yolu, hava yılı, SFK doyumu, kesinti ve
CAPEX/OPEX çekilişleri ortaktır (aynı tohum). Artımsal NPV senaryo başına farktır.

$$
\operatorname{Var}(X - Y) = \operatorname{Var}X + \operatorname{Var}Y - 2\operatorname{Cov}(X, Y)
$$

İki NPV aynı fiyat ve havayla güçlü biçimde birlikte hareket ettiğinden kovaryans büyüktür ve farkın varyansı, bağımsız
örneklemeye göre küçülür. Bu, benzetimde klasik bir **varyans azaltma** tekniğidir. Örnek santrallerde varyans %10–79
azaldı (`I1_ornekler.csv`, arayüzde "Varyans azaltma" sütunu). Aynı standart hata için gereken simülasyon sayısı
$1/(1 - \text{azaltma})$ kat azalır.

Kontrol: ekleme sıfırken artımsal NPV her senaryoda tam olarak 0'dır (`test_ekleme_analizi_kucuk`).

---

## 5. Sonuçlar

### 5.1 Türkiye taraması (86 santral; `data/atlas/v4_ekleme_tarama.csv`)

| Gösterge | Medyan | Aralık |
|---|---|---|
| Bağlantı kullanımı (RES KF) | %33 | %21–45 |
| Bağlantının yarısından azının dolu olduğu saatler | %70 | %54–89 |
| Saatlik RES–GES korelasyonu | −0,09 | −0,26…+0,15 |
| GES başabaş CAPEX (GES = bağlantının %25'i) | 437 bin $/MWac | P10–P90 374–485 |
| Batarya öneren santral (MILP, SFK dahil) | 85 / 86 | — |

**Bulgu 1: Bugünkü GES maliyetiyle (620 bin $/MWac) hiçbir santralde GES eklemesi tek başına kârlı değil.** Bağlantı boş
ve korelasyon negatif, yani teknik uyum iyi. Sorun fiyat: güneşin yakalanan fiyatı (kanibalizasyon sonrası) ~43 $/MWh'lik
LCOE'nin altında. Başabaş için GES CAPEX'inin %20–40 düşmesi gerekiyor.

**Bulgu 2: Batarya hemen her santralde değer yaratıyor**, ama değerin çoğu SFK (yan hizmet) gelirinden. Bu gelir doyuma
açık ve bankalanabilir değil (Faz H).

### 5.2 Örnek santraller (tam analiz; `outputs/v4I/I1_ornekler.csv`)

GES'e en yatkın (S015), medyan (S041) ve en az yatkın (S054) santral, GES CAPEX çarpanı 0,6 / 0,8 / 1,0:

| Santral | GES CAPEX | Önerilen GES | Batarya | En iyi yapı | Artımsal E[NPV] | P(>0) |
|---|---|---|---|---|---|---|
| S015 (Muğla, 42 MW) | ×0,6 | 48,9 MW | 32 MW | PPA | +18,3 M$ | %96 |
| | ×0,8 | 23,6 MW | 31 MW | Tüccar | +13,7 M$ | %87 |
| | ×1,0 | 0 | 32 MW | Tüccar | +10,9 M$ | %74 |
| S041 (Adıyaman, 25 MW) | ×0,6 | 30,8 MW | 30 MW | PPA | +13,2 M$ | %85 |
| | ×0,8 | 9,4 MW | 30 MW | Tüccar | +10,3 M$ | %71 |
| | ×1,0 | 0 | 31 MW | Tüccar | +9,2 M$ | %66 |
| S054 (Kahramanmaraş, 29 MW) | ×0,6 | 15,2 MW | 30 MW | Tüccar | +11,1 M$ | %75 |
| | ×0,8–1,0 | 0 | 31 MW | Tüccar | +10,0 M$ | %69 |

**Yorum.** Önerilen GES boyutu CAPEX'e çok duyarlı: S015'te %20'lik maliyet düşüşü 0'dan 24 MW'a, %40'lık düşüş 49 MW'a
(bağlantının %116'sı) çıkarıyor. Optimal tasarımda GES bağlantıyı aşacak kadar büyük olabiliyor, çünkü batarya öğle
fazlasını akşama kaydırıyor. GES büyüdükçe PPA öne geçiyor: güneşin kanibalize olan tüccar geliri yerine sabit fiyat. Eski
YEKDEM'in 2029'da bitmesi (3 yıl kalan) sonucu değiştirmiyor; kısa süre ve sabit nominal fiyat tüccarı geçmiyor.

---

## 6. Sınırlamalar

- **Yardımcı kaynak YEKDEM kuralı** ikincil kaynaktan. Birincil madde metni doğrulanmadı.
- **Kesinti önceliği:** bağlantı aşıldığında hangi kaynağın kesileceği LP'de serbest (değere göre); gerçekte sözleşme ve
  sayaç düzeni belirleyebilir.
- **SFK yaklaşımı:** batarya önerisi SFK'ya katılım için asgari 30 MW eşiğine yakın kümeleniyor (ikili katılım kuralı,
  `gelir_yigini.yan_hizmet.asgari_guc`). Batarya değeri SFK doyum varsayımına duyarlı (Faz H ve v1 Aşama 6).
- **MILP ve Monte Carlo farkı:** taramadaki MILP artımsal NPV tahmini (medyan +5,1 M$) Monte Carlo'dan (~+10 M$) düşük, çünkü
  MILP SFK'yı Aşama 5 azalma yoluyla, Monte Carlo doyum senaryolarıyla değerliyor. Tarama sıralama içindir; karar için tam
  analiz kullanılmalı.
- RES'in ömrü ve yenileme kararı modellenmez (ortak varsayılır).
