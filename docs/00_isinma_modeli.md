# Aşama 0 — Isınma Modeli: GES/RES Kapasite Seçimi (LP)

Kod: [`src/00_kurulum_testi.py`](../src/00_kurulum_testi.py)

## 1. Problem
Elimizde 50 MW'lık bir şebeke bağlantı hakkı, 45 milyon $ yatırım bütçesi ve en fazla 40 MW
GES kurulabilecek arazi var. Yıllık geliri en yüksek yapmak için kaç MW GES ve kaç MW RES kurmalıyız?

## 2. Matematiksel formülasyon

**Kümeler**
- $T = \{\text{GES}, \text{RES}\}$ — teknolojiler

**Parametreler**

| Sembol | Anlamı | GES | RES | Birim |
|---|---|---|---|---|
| $c_t$ | CAPEX | 0.6 | 1.2 | milyon $/MW |
| $r_t$ | Yıllık gelir | 0.096 | 0.180 | milyon $/MW/yıl |
| $G$ | Şebeke bağlantı kapasitesi | | 50 | MW |
| $B$ | Bütçe | | 45 | milyon $ |
| $A$ | GES arazi limiti | | 40 | MW |

**Karar değişkenleri**
- $x_t \ge 0$ — $t$ teknolojisinden kurulacak kapasite [MW] (sürekli → model bir **LP**)

**Amaç fonksiyonu**
$$\max \; Z = \sum_{t \in T} r_t \, x_t = 0.096\,x_{GES} + 0.180\,x_{RES}$$

**Kısıtlar**
$$
\begin{aligned}
\text{(K1) Şebeke:}\quad & x_{GES} + x_{RES} \le 50 \\
\text{(K2) Bütçe:}\quad & 0.6\,x_{GES} + 1.2\,x_{RES} \le 45 \\
\text{(K3) Arazi:}\quad & x_{GES} \le 40 \\
& x_{GES},\, x_{RES} \ge 0
\end{aligned}
$$

## 3. Sonuç
| | Değer |
|---|---|
| GES | **25 MW** |
| RES | **25 MW** |
| Yıllık gelir | **6.90 milyon $** |

| Kısıt | Kullanım / Limit | Bağlayıcı mı? | Gölge fiyat |
|---|---|---|---|
| Şebeke | 50 / 50 MW | **Evet** | 0.012 milyon $/MW |
| Bütçe | 45 / 45 milyon $ | **Evet** | 0.14 $/$ |
| Arazi | 25 / 40 MW | Hayır (15 MW boşluk) | 0 |

## 4. Neden iki teknolojinin karışımı çıktı?

İki teknolojiyi **iki farklı "kıt kaynak" açısından** karşılaştırmak gerekiyor:

| | MW başına gelir (şebeke açısından) | $ başına gelir (bütçe açısından) |
|---|---|---|
| GES | 0.096 | 0.096 / 0.6 = **0.160** ✅ |
| RES | **0.180** ✅ | 0.180 / 1.2 = 0.150 |

- **Şebeke kıtsa** her MW'ın değerli olduğu durumda RES daha iyi: MW başına daha çok kazandırıyor.
- **Bütçe kıtsa** her doların değerli olduğu durumda GES daha iyi: dolar başına daha çok kazandırıyor.

Tek bir teknolojiye gitmek bir kaynağı boşa harcıyor:
- **Sadece RES:** bütçe 45 / 1.2 = 37.5 MW'ta biter → gelir 6.75 M$, ama şebekenin 12.5 MW'ı boş kalır.
- **Sadece GES:** arazi 40 MW'ta durdurur → gelir 3.84 M$; bütçenin 21 M$'ı ve şebekenin 10 MW'ı boş kalır.

En iyi çözüm **iki kaynağı da sonuna kadar kullanan** noktadır. Şebeke ve bütçe kısıtlarını
eşitlik olarak birlikte çözersek:

$$x_{GES} + x_{RES} = 50,\qquad 0.6\,x_{GES} + 1.2\,x_{RES} = 45 \;\Rightarrow\; x_{RES} = 25,\; x_{GES} = 25$$

Geometrik olarak: LP'nin optimumu her zaman uygun bölgenin bir **köşe noktasındadır**; bu köşe,
şebeke ve bütçe doğrularının kesiştiği noktadır. Amaç doğrusunun eğimi (0.096/0.180 = 0.53) iki
kısıt doğrusunun eğimleri (şebeke: 1, bütçe: 0.6/1.2 = 0.5) arasında kaldığı için optimum tam bu
kesişimdedir. Gelirler değişip oran 0.5'in altına düşerse sadece RES, 1'in üstüne çıkarsa
GES ağırlıklı (arazi limitine kadar) çözüm optimal olur.

Arazi kısıtı **bağlayıcı değil**: 25 MW GES, 40 MW limitinin altında. Bu yüzden gölge fiyatı 0;
daha fazla arazi bulmak sonucu değiştirmez.

## 5. Gölge fiyatların yorumu (mülakatta sorulabilir)
Gölge fiyat (dual değer): bir kısıtın limiti 1 birim gevşetilirse amaç fonksiyonunun ne kadar
iyileşeceğidir.

- **Bütçe: 0.14** → 1 milyon $ ek bütçe yıllık geliri 0.14 milyon $ artırır (%14 getiri).
  Ek para geldiğinde model GES'i azaltıp RES'i artırarak (şebekeyi dolu tutarak) kullanır.
- **Şebeke: 0.012** → 1 MW ek bağlantı hakkı yıllık geliri sadece 0.012 milyon $ artırır.
  Ek MW'ı doldurmak için yine bütçe gerekir, o yüzden şebekenin marjinal değeri düşük.
- **Arazi: 0** → bağlayıcı olmayan kısıtın gölge fiyatı her zaman sıfırdır.

Doğrulama (dual sistem): $y_{şebeke} + 0.6\,y_{bütçe} = 0.096$ ve $y_{şebeke} + 1.2\,y_{bütçe} = 0.180$
→ $y_{bütçe} = 0.14$, $y_{şebeke} = 0.012$. Ayrıca $50 \times 0.012 + 45 \times 0.14 = 6.9$ — dual amaç
değeri primal ile eşit (güçlü dualite).

**Gerçek projeye bağlantı:** Bu mantık Aşama 4'te de geçerli olacak. Şebeke bağlantı hakkı
Türkiye'de kıt bir kaynak; şebeke kısıtının gölge fiyatı, "bir MW ek bağlantı kapasitesi için
ne kadar ödemeye değer?" sorusunun cevabıdır. Hibrit (GES+RES+BESS) tasarımın temel motivasyonu da
aynı bağlantı noktasını farklı saatlerde üreten teknolojilerle daha verimli kullanmaktır.

## 6. Bu basit modelin eksikleri (sonraki aşamalarda giderilecek)
- Gelir sabit varsayıldı; gerçekte saatlik üretim × saatlik fiyat ile hesaplanır (Aşama 1–2).
- Kurulu güç toplamı ≤ şebeke kısıtı çok tutucu: GES ve RES aynı anda tam güçte üretmediği için
  saatlik bazda "üretim − curtailment ≤ şebeke" yazılır ve aşırı kapasite (overbuilding) mümkün olur (Aşama 4).
- Amaç yıllık gelir değil, CAPEX/OPEX ve zaman değerini içeren NPV olacak (Aşama 3–4).
