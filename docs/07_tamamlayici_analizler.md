# Aşama 7 — Tamamlayıcı analizler: sistem kesintisi, teşvikler, gelir yapıları, çevresel etki, takvim riski, risk kaydı

Kod: `src/07_sistem_kesintisi.py`, `src/07_gelir_yapilari.py`, `src/07_takvim.py`, `src/07_risk_kaydi.py`.
Çıktılar: `outputs/07/`. Parametreler: `config.yaml → kesinti, yekdem, tesvik, karbon, takvim`.
Para birimi: reel 2026 USD, %7 reel WACC.

**Okuma notu:** Emin olmadığım her şey açıkça **TAHMİN** olarak işaretlendi ve config'te de öyle yazıldı. Her bölümün
sonunda o adımın nihai öneriye etkisi ayrıca raporlandı.

---

## Özet: önce / sonra

| | Aşama 6 önerisi | Aşama 7 sonrası |
|---|---|---|
| Tasarım | RES 58,8 MW + 30 MW / 52,5 MWh batarya (40 MW'a büyütülebilir) | **Aynı** |
| Gelir yapısı | PPA (P90'ın %70'i, 12 yıl) | **YEKDEM**, taban/tavan endeksliyse. Değilse PPA |
| Proje edinimi | Belirtilmemişti (model FID 2026, COD 2028 varsayıyordu) | **İnşaata hazır proje** (ÇED, imar, lisans tamam); geliştirme aşamasından başlamak önerilmez |
| Batarya siparişi | RES FID'inden ~12 ay sonra | **RES ile birlikte, FID'de.** Batarya kararı FID'de gözlenen doyuma göre verilir |
| Yeni koşullar | — | Teşvik belgesi (KDV istisnası); YEKDEM endekslemesinin hukuki teyidi; COD ≤ 31.12.2030 güvencesi |
| Beklenen NPV | +4,5 M$ (P %58) | Gerçekçi takvim ve kesintiyle: **+2,1 M$** (inşaata hazır + endeksli YEKDEM), −0,3 M$ (inşaata hazır + PPA), −1,5 M$ (geliştirmeden + PPA) |
| Karar | Koşullu onay | **Geliştirme aşamasındaki proje için ret. İnşaata hazır proje + endeksli YEKDEM için koşullu onay; edinim primi ≤ ~2 M$** |

**Öneri değişti. Neden?** Üç bulgu bir araya geldi:

1. **Takvim:** Gerçekçi takvimde COD 2028 değil, inşaata hazır projede 2030, geliştirme aşamasında 2032. Bu gecikme
   SFK penceresinin büyük kısmını kaçırıyor.
2. **Sistem kesintisi:** 2026'da başlayan kesinti, beklenen NPV'yi ~2 M$ azaltıyor.
3. **YEKDEM:** 2030 sonuna kadar devreye giren RES'lere hâlâ açık. Sınırları endeksliyse en iyi risk-getiri profilini
   veriyor, ama yalnızca inşaata hazır bir projeyle yetişilebiliyor.

---

## 1. Sistem kaynaklı kesinti (TEİAŞ / DGP YAT talimatları)

### 1.1 Veri ve bulgular

**Sistem geneli YAT hacmi** (EPİAŞ `/v1/markets/bpm/data/order-summary-down`, saatlik, 0/1/2 kodlu;
`outputs/07/kesinti_sistem_yat_yillik.csv`):

| Yıl | YAT toplam [GWh] | 1 kodlu (sistem kısıtı) [GWh] |
|---|---|---|
| 2023 | 2.509 | 162 |
| 2024 | 2.839 | 99 |
| 2025 | 2.925 | 54 |
| **2026 (Oca–Eyl)** | **9.482** | 117 |

2026'da YAT hacmi üç katına çıktı. Zirve aylar: Mayıs 3,1 TWh, Haziran 2,1, Nisan 1,8, Mart 0,9 TWh.

**EPİAŞ kaynak ya da santral bazında YAT miktarı yayımlamıyor**; yalnızca sistem toplamı var. Bu yüzden RES'lere
düşen payı doğrudan göremiyoruz.

**Nerede yoğunlaşıyor?** Bir saat tipinin YAT payının o tipin saat payına oranı (1 = ortalama;
`kesinti_yat_yogunluk.csv`):

| | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| Bahar öğle (Mar–Haz, 10–16) | 1,36 | 1,76 | 2,29 | **3,31** |
| Bayram / resmî tatil | 1,72 | 2,12 | **3,47** | 2,31 |
| Gece / akşam | 0,74 | 0,65 | 0,59 | 0,74 |

**Ezine'de talimat izi.** Yöntem:

- Kalibre ERA5 modeli (Aşama 2 ay × saat katsayısı) için 2024–2026 ERA5 verisi indirildi.
- Üç referans RES (Enerjisa Çanakkale, Çamseki, İntepe) için modelin yüksek üretim beklediği (KF > 0,3) saatlerde
  **en az iki santralin aynı saatte beklenenin yarısından az ürettiği** saatler işaretlendi.
- Tek bir santralin arızası eşzamanlı olmaz; eşzamanlı düşüş, sistem talimatının imzasıdır.
- 2016–2022 dönemi model hatası tabanı olarak kullanıldı (talimatın yaygın olmadığı dönem).

| Yıl | Eşzamanlı düşüş [saat] | Kaybolan enerji payı | Taban üstü (talimat tahmini) |
|---|---|---|---|
| 2016–2022 ort. | 199–428 | %3,5 (taban) | — |
| 2023 | 384 | %4,6 | %1,0 |
| 2024 | 166 | %2,5 | %0 |
| 2025 | 183 | %2,9 | %0 |
| **2026 (Oca–Eyl)** | **620** | **%13,0** | **~%9,5** |

2026'daki düşüşlerin 177 saati Mayıs'ta, 130'u Haziran'da, 89'u Nisan'da. Sistem YAT verisiyle aynı desen. Bayram
saatlerinde eşzamanlı düşüş sıklığı 2016–22'ye göre 4,8 kat, bahar öğlelerinde 1,9 kat
(`kesinti_referans_saat_tipi.csv`).

**Yorum:** 2023–2025'te Ezine RES'lerine düşen kesinti ihmal edilebilir düzeydeydi. 2026'da ise üretimin ~%9,5'i
(yıllıklandırılmış ~%7) talimatla kesilmiş görünüyor. Kaynaklar 2026'yı bir kırılma yılı olarak tanımlıyor: dolu
barajlar (HES üretimi yüksek), 25 GW güneş, düşük bahar talebi ([Yeşil Haber](https://yesilhaber.net/hesiad-hes-uretim-gelir-yat/)).
Saatlik mahsuplaşmaya geçiş de aynı sorunun işareti ([Turkey Recap](https://www.turkeyrecap.com/p/as-solar-and-wind-boom-grid-bottlenecks)).

**Sınırlama:** Eşzamanlı düşüşlerin bir kısmı bakım, yerel şebeke arızası ya da 2026 ERA5 hatası olabilir. Tahmin
"üst sınıra yakın" okunmalı.

### 1.2 Ücretlendirme
- DGP'de YAT talimatı alan dengeleme birimi, düşürdüğü enerjiyi **kendi YAT teklif fiyatından piyasadan geri alır**.
  Uzlaştırmada birimlerin kendi teklif fiyatları esas alınır (Elektrik Piyasası Dengeleme ve Uzlaştırma Yönetmeliği,
  değişiklik [RG 21.01.2025](https://resmigazete.gov.tr/eskiler/2025/01/20250121-3.htm); uzlaştırma dönemi 15 dk).
- Talimatlar 0 (dengeleme), 1 (sistem kısıtı) ve 2 (yan hizmet) kodlarıyla etiketlenir.
- **Sonuç:** GÖP'te PTF'den satış yapmış bir RES, YAT teklifini ~0'dan verdiyse talimat altında geliri neredeyse
  korunur (PTF'yi tutar, ~0 öder). Kaybı yalnızca teklif fiyatı kadardır.
- Ama talimat DGP dışından gelirse (acil durum, sistem güvenliği) ya da tesis YEKDEM kapsamındaysa (üretilmeyen enerji
  için YEKDEM ödemesi yapılmaz) kayıp tamdır.
- Hangi oranın tazmin edildiğini kamuya açık veriden ayıramadım. **TAHMİN:** tazmin oranı ~ Düzgün(0, 1).

### 1.3 Model
- **Yıllık oran:** $\kappa_y = \kappa_0 \cdot s_{\text{senaryo}} \cdot 1{,}04^{\,y-2026} \cdot \varepsilon_y$
  - $\kappa_0$ ~ Üçgen(%1; %5; %12): 2023–25 ~%0–1 ile 2026'nın ~%7'si arası (TAHMİN).
  - Güneş büyümesiyle yılda +%4.
  - Batarya kurulumuyla etkileşim: hızlı doyumda ×0,7, yavaşta ×1,3; bataryalar öğle fazlasını emer (TAHMİN).
  - $\varepsilon_y$: hidroloji / talep yılı oynaklığı, lognormal σ = 0,5.
- **Saatlik dağılım:** YAT yoğunluğuna göre 4 saatlik talimat blokları (bahar öğle, bayram).
- **Değer faktörü:** Talimat saatlerinde fiyat ortalamanın altında (50,5 $/MWh). Kesilen enerjinin değeri ortalamanın
  0,89'u.
- **Batarya kurtarma:** Şebeke sınırı talimat saatlerinde 0'a inen saatlik LP (`kesinti_batarya_kurtarma.csv`).

| %5 kesintide (temsilî yıl) | Kayıp gelir [M$/yıl] | Kayıp enerji [GWh] |
|---|---|---|
| Yalnız RES 58,8 | 0,52 | 9,3 |
| + 30 MW / 52,5 MWh batarya | 0,43 | 6,0 |

**Bataryanın kurtarabildiği:** kayıp enerjinin ~%35'i, kayıp gelirin **~%16'sı**. Bu bir üst sınır, çünkü SFK'ya
rezerv ayrılan saatlerde batarya şarj için boş değil. Değerin az olmasının nedeni, kurtarılan enerjinin de çoğunlukla
ucuz saatlere kayması.

### 1.4 Etki
Monte Carlo'da önerilen tasarım (F2P) için **E[NPV] 4,5 → 2,4 M$**, P(NPV>0) %58 → %52; yalnız RES için
−1,9 → −4,9 M$. **Öneriye etkisi:** Bataryanın göreli değeri biraz artıyor; projenin mutlak değeri düşüyor.

---

## 2. Teşvikler ve alternatif gelir yapıları

### 2.1 Yatırım teşvik belgesi
- **Mevzuat:** [9903 sayılı Cumhurbaşkanı Kararı](https://www.yatirimadestek.gov.tr/pdf/assets/upload/dosyalar/karar-yatirim_tesvik_uygulamalari.pdf)
  (RG 30.05.2025) ve 2025/1 Tebliğ. RES ve enerji depolama yatırımlarında teşvik belgesiyle **KDV istisnası** ve
  **gümrük vergisi muafiyeti** sağlanıyor. **Ticari elektrik üretiminde vergi indirimi uygulanmıyor**
  ([Sönmez Müşavirlik](https://www.sonmezmusavirlik.com.tr/ruzgar-enerjisi-res-yatirim-tesvikleri),
  [Atlas Nestor](https://atlasnestor.com/gunes-ges-ve-ruzgar-res-enerjisi-yatirimlarinda-tesvik-sistemi-ve-yerlilik-sartlari/)).
- **Model ne varsayıyordu?** Model KDV ve gümrüğü hiç içermiyordu, yani zımnen teşvik belgesi varsayıyordu. Bu yüzden
  doğru soru "belge olmazsa ne kaybedilir?" (`tesvik_etkisi.csv`):
  - İnşaatta ödenecek KDV: **14,0 M$**. Çıkış KDV'siyle mahsup edilir, ama TL devreden KDV bakiyesi USD cinsinden
    aşınır (yılda ~%20, TAHMİN).
  - Net bugünkü maliyet: **5,8 M$** (aşınmasız olsaydı 2,2 M$). Bu, projenin beklenen NPV'sinden büyük.
  - Batarya gümrük vergisi (Çin menşeli; oran belirsiz, %0–10): 0–0,6 M$ (TAHMİN).
- **Öneriye etkisi:** Teşvik belgesi FID'in **ön koşulu** oldu.

### 2.2 YEKDEM
- **Mevzuat:** [7189 sayılı Cumhurbaşkanı Kararı](https://yesilekonomi.com/2030a-kadar-uygulanacak-yeni-yekdem-fiyatlari-belirlendi/)
  (RG 01.05.2023). **01.07.2021–31.12.2030 arasında işletmeye girecek** YEK belgeli tesisler kapsamda.
  - Karasal RES: 106 TL kr/kWh, **taban 4,95 – tavan 6,05 USD ¢/kWh**, **10 yıl**.
  - Fiyat TL olarak aylık güncelleniyor, USD taban/tavanla sınırlı
    ([Paksoy](https://paksoy.av.tr/2023/06/yekdem-ve-yerli-katki-fiyati-guncellendi/)).
  - Aralık 2025'te uygulanan RES fiyatı 245,06 kr/kWh ≈ 5,8 ¢ ([Enerji Ajansı](https://enerjiajansi.com.tr/yekdem-fiyatlari/)).
  - [RG 29.12.2025](https://www.aa.com.tr/tr/enerjiterminali/elektrik/yekdemden-yararlanma-sartlarinda-degisiklige-gidildi/53716)
    değişikliği: şebekeden çekilen enerji YEK kapsamı dışında; resmî tatillerde KGÜP üstü üretime ödeme yok;
    depolamalı tesislere ayrı fiyat.
- **Erişilebilir mi?** Yeni bir RES için **evet, ama yalnızca COD ≤ 31.12.2030 olursa**. Bazı ikincil kaynaklar
  "yeni santrallere YEKDEM kapalı" diyor; resmî karar 2030'a kadar açık.
- **TAHMİN — kritik belirsizlik:** USD taban/tavanının ABD enflasyonuyla **endekslenip endekslenmediğini** resmî metinden
  doğrulayamadım. İki varyant modellendi:
  - **Nominal:** reel değer 10 yılda ~%22 aşınır; reel ortalama ~48 $/MWh.
  - **Endeksli:** reel ~57 $/MWh sabit.
  - Simülasyon başına nominal fiyat ~ Üçgen(4,95; 5,8; 6,05) ¢/kWh.
- **Diğer varsayımlar:** Banka koşulları DSCR 1,20, 12 yıl (TAHMİN). Dispatch tablosu PPA noktasından (yaklaşım).

### 2.3 Tüccar / PPA / YEKDEM karşılaştırması
Aynı Monte Carlo (10.000; doyum + sistem kesintisi dahil; model takvimi), `gelir_yapilari_metrikler.csv`:

| Seçenek | E[NPV] | P(NPV>0) | CVaR %5 | Borç kapasitesi (baz / muhafazakâr) [M$] | P(DSCR<1), muhafazakâr | Öz kaynak IRR P50 |
|---|---|---|---|---|---|---|
| Yalnız RES — tüccar | −4,9 | %35 | −32,8 | 42,6 / 28,7 | %47 | %6,5 |
| Yalnız RES — PPA | −8,0 | %19 | −25,2 | 47,6 / 40,3 | %39 | %6,1 |
| Yalnız RES — YEKDEM (nominal) | −12,5 | %6 | −28,2 | 34,5 / 32,9 | %35 | %5,0 |
| Öneri — tüccar | 3,7 | %55 | −30,4 | 52,6 / 33,0 | %41 | %8,5 |
| Öneri — PPA | 2,4 | %52 | −25,1 | 59,0 / 42,1 | %38 | %8,8 |
| Öneri — YEKDEM (nominal) | 0,8 | %48 | −24,9 | 48,4 / 36,1 | %25 | %7,7 |
| **Öneri — YEKDEM (endeksli)** | **5,5** | **%61** | **−20,1** | 53,0 / 41,1 | **%22** | **%9,0** |

![Gelir yapıları](../outputs/07/gelir_yapilari.png)

**Yorum:**
- **Endeksli YEKDEM her metrikte en iyisi.** Fiyat tabanı alt kuyruğu kesiyor, DSCR ihlalini yarıya indiriyor.
- **Nominal YEKDEM** riski azaltıyor (CVaR, DSCR) ama reel aşınma yüzünden beklenen değeri düşürüyor.
- **PPA**, tüccara göre ~1,3 M$ beklenen değerden vazgeçip kuyruğu ~5 M$ iyileştiriyor.
- **Yalnız RES** her gelir yapısında negatif. Projeyi pozitife çeviren hâlâ batarya + SFK.

**Öneriye etkisi:** YEKDEM yeni tercih edilen gelir yapısı oldu, ama iki koşula bağlı: hukuki endeksleme teyidi ve
2030 sonu COD. İkincisi takvim analizinde belirleyici çıktı (§4).

### 2.4 Karbon
- **Türkiye ETS:** İklim Kanunu (7552, 2025) ile kuruldu. Pilot dönem 2026–2027'de elektrik üretimi dahil, %100
  ücretsiz tahsisat, 2026'da yalnız raporlama, karbon fiyatı 2027'de fiyat koridoruyla başlıyor
  ([iklim.gov.tr](https://iklim.gov.tr/turkiye-emisyon-ticaret-sistemi-yonetmeligi-taslagi-yayimlandi-haber-4519),
  [Yeşil Haber](https://yesilhaber.net/turkiye-ets-pilotu-karbon-fiyati/)).
- **Elektrik fiyatına etkisi:**
  - Marjinal santral doğal gaz ise (~0,37 tCO2/MWh) €20/t → +~8 $/MWh.
  - Kömür ise (~0,95 tCO2/MWh) €20/t → +~20 $/MWh.
  - Ücretsiz tahsisatta bile fırsat maliyeti fiyata yansıyabilir.
- **Yüksek fiyat senaryosunun gerekçesi:** Yüksek senaryo (72 $/MWh, baza göre +14 $/MWh), gaz marjda iken €30–35/t ya
  da kömür marjda iken ~€15/t karbon fiyatıyla tutarlı. Bu artık gerekçeli bir senaryo.
- **ETS fiyat aralığı:** 2035 için €5–40/t (TAHMİN). Pilot dönemin fiyat koridoru belirsiz.
- **Gönüllü karbon kredisi:** Verra ve Gold Standard 2019'dan beri en az gelişmiş ülkeler (LDC) dışındaki ülkelerde
  şebekeye bağlı yeni yenilenebilir projeleri kabul etmiyor. ICVCM de 2024'te yenilenebilir kredilerini "yüksek
  bütünlük" etiketinden çıkardı ([Climate Home](https://www.climatechangenews.com/2024/08/07/renewable-energy-carbon-credits-rejected-by-high-integrity-scheme/)).
  Türkiye'deki eski RES kredileri hâlâ işlem görüyor ([Quantum Commodity Intelligence](https://www.qcintel.com/carbon/assessment/gs-wind-turkey-v24-20kt-GSWT24.html)),
  ama yeni proje için gerçekçi gelir **0**. Yalnızca YEK-G (~0,1 $/MWh) var; zaten modelde.
- **Öneriye etkisi:** Doğrudan yok. Yüksek fiyat senaryosuna dayanak sağlıyor.

---

## 3. Çevresel etki

Önerilen tasarım (P50, ilk 10 yıl ortalaması, kesinti dahil). Emisyon faktörü:
[ETKB Türkiye Ulusal Elektrik Şebekesi Emisyon Faktörü Bilgi Formu](https://enerji.gov.tr/Media/Dizin/EVCED/tr/%C3%87evreVe%C4%B0klim/%C4%B0klimDe%C4%9Fi%C5%9Fikli%C4%9Fi/TUESEmisyonFktr/Belgeler/TUESEF_Bilgi_Formu.pdf),
2024 birleşik marj, RES/GES için **0,6345 tCO2/MWh** (2023: 0,6242). `co2.csv`:

| | Değer |
|---|---|
| Satılan enerji | 174,6 GWh/yıl |
| Önlenen CO2, yıllık | **~111 bin t** |
| Önlenen CO2, 30 yıl (faktör sabit) | 3,3 milyon t |
| Önlenen CO2, 30 yıl (faktör yılda %2 azalır, TAHMİN) | **2,4 milyon t** |
| Eşdeğer hane | **~62 bin hane** (2.824 kWh/hane-yıl: EPDK 2024 mesken 75,1 TWh / TÜİK 26,6 milyon hane — [Türkinform](https://turkinform.com.tr/turkiyede-ortalama-bir-ev-yilda-ne-kadar-elektrik-harcar-4-bin-kwh-siniri-asiliyor-mu-tuketimi-ne-etkiler)) |

Birleşik marj, CDM Tool 07'ye göre "projenin yerini aldığı" üretimin emisyon yoğunluğu. Şebeke dekarbonize oldukça
gerçek önlenen emisyon azalır; azalan faktörlü değer daha dürüst.

---

## 4. Proje takvimi ve takvim riski

### 4.1 Aktivite ağı
Başlangıç Ekim 2026 (geliştirme kararı). Mevcut bir ön lisansın devri varsayılıyor: Ekim 2023'ten beri yeni başvuru
kısıtlı ve 2026'da RES başvuru kuralları değişti. Süreler ay cinsinden, üçgen (iyimser / olası / kötümser;
`config.yaml → takvim`).

| Kod | Aktivite | a / m / b | Öncüller | Gerekçe |
|---|---|---|---|---|
| ONL | Ön lisans devri | 3 / 5 / 9 | — | EPDK devir onayı; ön lisans 24 ay geçerli |
| OLC | Rüzgâr ölçümü | 12 / 12 / 15 | — | Banka kabulü için ≥ 12 ay yerinde ölçüm |
| KUS | Ornitoloji temel çalışması | 9 / 12 / 14 | — | Çanakkale Boğazı süzülen kuş göç yolu: ilkbahar (Mar–Haz) + sonbahar (Ağu–Eki) |
| CED | ÇED olumlu | 6 / 9 / 15 | ONL, KUS | 58,8 MW RES → tam ÇED; halkın katılımı, inceleme |
| IMR | İmar, arazi, izinler | 6 / 9 / 15 | CED | Orman/hazine izinleri, kamulaştırma |
| TBA | TEİAŞ bağlantı + sistem kullanım anlaşması | 3 / 6 / 12 | ONL | |
| LIS | Üretim lisansı | 2 / 3 / 6 | CED, IMR | |
| PPA | PPA müzakeresi | 3 / 6 / 10 | ONL | |
| FIN | Finansman kapanışı (FID) | 3 / 4 / 8 | LIS, OLC, TBA, PPA | |
| TUR | Türbin tedariki | 12 / 15 / 20 | FIN | Sektör teslim süreleri |
| BOP | RES altyapı inşaatı | 6 / 8 / 12 | FIN | Enerjisa YEKA RES-2 projelerinde inşaat 12–21 ay ([DFC özetleri](https://www3.dfc.gov/environment/eia/enerjisa/6-HarmancikWPP/Harmancik%20RES_TOO.pdf)) |
| SEB | Şebeke bağlantısı (TM/ENH) | 9 / 12 / 20 | TBA, FIN | TEİAŞ iletim yatırımı gecikmeleri |
| MNT | Türbin montajı | 3 / 4 / 6 | TUR, BOP | |
| DRES | RES test, devreye alma, COD | 1 / 2 / 4 | MNT, SEB | |
| BAT | Batarya tedariki | 6 / 8 / 12 | FIN | BESS projelerinde 9–18 ay gecikmeler ([IEEFA 2025](https://ieefa.org/resources/viability-standalone-battery-energy-storage-tariffs-discovered-2025)) |
| BIN | Batarya inşaat ve montaj | 2 / 3 / 5 | BAT, BOP | |
| DBAT | Batarya devreye alma | 1 / 1,5 / 3 | BIN, SEB | |
| SFK | SFK ön yeterlilik testleri | 1 / 2 / 4 | DBAT | TEİAŞ performans testleri |

Tüm süreler TAHMİN: örnek projelerden gerekçelendirildi, ama projeye özgü değil.

### 4.2 CPM ve Monte Carlo (10.000 iterasyon)
**Deterministik kritik yol** (geliştirme senaryosu):
Ornitoloji (12) → ÇED (9) → imar (9) → lisans (3) → FID (4) → türbin (15) → montaj (4) → COD (2) = **58 ay → Ağustos 2031**.

![Gantt](../outputs/07/takvim_gantt.png)

| | RES COD P50 | P80 | P90 | Modelin varsayımına göre gecikme (P50) |
|---|---|---|---|---|
| Geliştirmeden başlayan proje | **Oca 2032** | **Nis 2032** | Haz 2032 | +48 ay |
| İnşaata hazır proje (ÇED, imar, lisans tamam) | **Mar 2030** | **May 2030** | Tem 2030 | +26 ay |

**Kritiklik indeksi** (kritik yolda olma olasılığı): ornitoloji, ÇED, imar, lisans, FID ve COD %100; türbin tedariki ve
montaj %98; şebeke bağlantısı %60; batarya montajı %40.
**Gecikmeye en çok katkı** (Spearman süre ↔ COD): ÇED 0,51, imar 0,50, türbin tedariki 0,42, FID 0,29, ornitoloji 0,27.

![COD ve kritiklik](../outputs/07/takvim_cod_kritiklik.png)

### 4.3 Takvim → NPV
- Finansal model COD'u Ocak 2028 varsayıyordu. RES gecikmesi ve SFK başlangıç gecikmesi, doyum + kesinti dahil Monte
  Carlo'nun erteleme eğrilerinden NPV'ye çevrildi (3 yılın ötesi doğrusal dışdeğerleme; kaba).
- Formül: NPV ≈ NPV_RES+PPA(d_RES) + [bataryanın artımsal değeri](d_SFK).

| Olgunluk / batarya politikası | SFK başlangıcı P50 | E[NPV] PPA | E[NPV] tüccar | E[NPV] YEKDEM endeksli | P(COD ≤ 2030) |
|---|---|---|---|---|---|
| Geliştirme, B1 (batarya RES ile birlikte) | Eyl 2031 | −1,5 | −0,9 | −0,9 (YEKDEM yok) | ~%0 |
| Geliştirme, B2 (FID+12 ay sipariş) | Haz 2032 | −2,3 | — | — | ~%0 |
| Geliştirme, B3 (erken/bağımsız) | Tem 2031 | −1,4 | — | — | ~%0 |
| İnşaata hazır, B1 | Kas 2029 | −0,3 | 0,4 | **2,1** | ~%100 |
| İnşaata hazır, B2 | Ağu 2030 | −1,2 | — | — | ~%100 |
| İnşaata hazır, B3 | Eyl 2029 | −0,1 | — | — | ~%100 |

(Model takviminde, yani COD 2028'de, PPA'lı öneri 2,4 M$.)

**Bulgular:**

1. **Takvim, SFK penceresini kapatıyor.** Baz doyum senaryosunda SFK 2029'da tabana iniyor. Gerçekçi COD (2030–2032)
   ile batarya pencerenin büyük kısmını kaçırıyor; değeri yavaş doyum senaryosuna kalıyor.
2. **"Bataryayı 12 ay geç sipariş et" koşulu takvimle çelişiyor.** B1'de batarya kritik yolda değil ve RES'ten ~2 ay
   önce hazır (%91 olasılıkla RES'ten önce SFK'da). 12 ay geç sipariş (B2) SFK başlangıcını ~9–10 ay geciktirip
   **~0,8–0,9 M$** kaybettiriyor. Aşama 6'da bu koşulun gerekçesi "2027 verisini gördükten sonra karar vermek"ti.
   Gerçekçi takvimde FID zaten 2029 (inşaata hazır) ya da 2030 (geliştirme) yılında. O zamana kadar doyum büyük ölçüde
   gözlenmiş olacak, yani **bilgi beklemeden geliyor.** **Koşul güncellendi:** batarya FID'de, o andaki SFK fiyatı ve
   kurulu depolama görülerek RES ile birlikte sipariş edilir.
3. **Erken / bağımsız batarya (B3)** yalnızca ~0,1–0,2 M$ kazandırıyor. Batarya yine şebeke bağlantısını ve lisansı
   bekliyor; ayrı finansman ve lisans karmaşıklığına değmez.
4. **Proje olgunluğu en büyük kaldıraç.** İnşaata hazır proje COD'u ~22 ay öne çekiyor ve YEKDEM'in 2030 sonu sınırına
   yetişmeyi neredeyse kesinleştiriyor. **YEKDEM ancak inşaata hazır bir projeyle erişilebilir.**
5. **Edinim primi:** Takvim dahil endeksli YEKDEM senaryosunda beklenen NPV 2,1 M$. Bu, inşaata hazır bir proje için
   ödenebilecek en yüksek primin (geliştirici kârı) ~2 M$ (~35 bin $/MW) olduğu anlamına geliyor. PPA ile bu tavan ~0.

---

## 5. Risk kaydı
20 risk (`outputs/07/risk_kaydi.xlsx`, `risk_kaydi.csv`). Puanlar uzman yargısı (TAHMİN); sayısal etkiler model
çıktılarından.

![Risk ısı haritası](../outputs/07/risk_isi_haritasi.png)

**En yüksek beş risk** (olasılık × etki):

| No | Risk | Puan | Sayısal etki | Azaltım | Kalıntı |
|---|---|---|---|---|---|
| R01 | Elektrik fiyat seviyesi düşük kalır | 20 | Varyansın %45–85'i | YEKDEM/PPA, muhafazakâr borç | 9 |
| R02 | SFK piyasasının doyumu | 16 | E[NPV] 28,4 → 6,2 M$ | 30 MW + koşullu büyütme, kararı FID'de ver | 8 |
| R07 | ÇED, imar ve lisans gecikmesi | 16 | COD +4 yıl, NPV −3,9 M$ | İnşaata hazır proje | 9 |
| R05 | YEKDEM taban/tavanı nominal kalır | 12 | 5,5 vs 0,8 M$ | Hukuki görüş; nominal ise PPA | 6 |
| R08 | YEKDEM için 2030 sonu COD sınırını kaçırma | 12 | YEKDEM kaybı | İnşaata hazır proje, türbin slotu, gecikme cezalı EPC | 6 |

**Modelde olmayan önemli riskler:**
- **Ornitoloji (R13):** Çanakkale Boğazı süzülen kuş göç yolu üzerinde. ÇED'de ret ya da tadil, göç döneminde radar
  destekli seçici durdurma (tahmini %1–3 üretim kaybı) mümkün.
- **Yerel kabul ve dava (R14).**
- **Kur (R15).**
- **PPA alıcısı temerrüdü (R18).**
- **EPC / OEM iflası (R20).**

---

## 6. Nihai öneri (Aşama 7)

**Karar:**
- **Geliştirme aşamasındaki bir proje (ön lisans devri) için yatırım önerilmez.** Beklenen NPV tüm gelir yapılarında
  negatif; YEKDEM'in 2030 sonu sınırına yetişilemiyor.
- **Koşullu onay**, ancak **inşaata hazır** (ÇED, imar ve üretim lisansı tamamlanmış) bir 50 MW RES projesi ~2 M$'ın
  altında bir primle edinilebilirse:
  - **Tasarım:** RES 58,8 MW + 30 MW / 52,5 MWh batarya (büyütme opsiyonlu).
  - **Gelir yapısı:** YEKDEM. Bunun için USD taban/tavanının ABD enflasyonuyla endekslendiği hukuken teyit edilmeli;
    değilse PPA.

**Koşullar (FID öncesi):**
1. **İnşaata hazır proje**, COD ≤ 31.12.2030 için türbin teslim slotu ve gecikme cezalı EPC.
2. **YEKDEM endekslemesinin hukuki teyidi.** Endeksli değilse PPA (≥ ~52 $/MWh) seçilir ve beklenen NPV ~0'a iner;
   bu durumda yatırım ancak edinim primi ~0 ise anlamlı.
3. **Teşvik belgesi** (KDV istisnası; yoksa NPV −5,8 M$).
4. **TEİAŞ SFK ön yeterliliği** (batarya için).
5. **Muhafazakâr borç** (SFK'sız, 45 $/MWh; YEKDEM'de ~41 M$) + 6 ay DSRA.
6. **Batarya kararı FID'de**, o anki SFK fiyatı ve kurulu depolama görülerek; sipariş RES ile birlikte. Aşama 6'daki
   "12 ay sonra" koşulu kaldırıldı.

**Tetikleyiciler (Aşama 6'dakilere ek):**

| Gösterge | Eşik | Karar |
|---|---|---|
| RES'lere YAT/kesinti (EPİAŞ, referans santraller) | 2027'de de > %8 | Gelir tahminini düşür; PPA'ya "deemed generation" maddesi şart |
| YEKDEM mevzuatı | 2030 sonrası uzatılır ya da değiştirilir | Geliştirme senaryosu yeniden değerlendirilir |
| İnşaata hazır proje primi | > ~2 M$ (YEKDEM), > 0 (PPA) | Edinme |
| Türbin teslim süresi teklifleri | > 18 ay | 2030 COD riski; YEKDEM'e güvenme |
| ETS karbon fiyatı | > €30/t ve gaz marjda | Yüksek fiyat senaryosuna ağırlık ver; tüccar payını artır |

---

## 7. Sınırlamalar
- **Kesinti:** Santral bazında YAT verisi yok; tahmin eşzamanlı düşüş yöntemine ve 2026 ERA5'ine dayanıyor. Tazmin oranı
  bilinmiyor.
- **YEKDEM:** Endeksleme belirsiz; dispatch, PPA noktasından yaklaşıklandı; resmî tatillerde KGÜP üstü üretim kuralı
  ihmal edildi.
- **Takvim:** Süreler projeye özgü değil. Takvim–NPV bağlantısı erteleme eğrilerinin 3 yılın ötesine doğrusal
  dışdeğerlemesiyle kuruldu (kaba). İnşaata hazır proje primi modele girmedi.
- **Risk kaydı:** Puanlar uzman yargısı.
