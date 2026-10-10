# v3 Faz E — Coğrafi katmanlar, çok kriterli saha seçimi, lojistik

Bu belge iki bölümden oluşur: §0 Faz D tutarlılık ön adımı (Ö1–Ö4), §1– Faz E.

---

## 0. Ön adım: Faz D tutarlılık konuları

| | |
|---|---|
| Kod | `src/bakim/isletme.py` (işletme modeli), `src/uretim/kayip.py` (kayıp tablosu), `src/motor/v3.py` |
| Betikler | `src/v3_E0_isletme_mutabakati.py`, `src/v3_E0_bakim_duyarlilik.py`, `src/v3_E0_uc_asama.py` |
| Çıktılar | `outputs/v3E/E0_*`, `data/atlas/v3_bakim_duyarlilik.json` |
| Config | `v3.isletme` (yeni), `v3.kayip.tablo` (yeni), `v3.bakim` (genel gider 1,0, diğer sabit 0) |

### 0.1 Ö1 — O&M kapsam mutabakatı

**v1'in kaynağı:** Lazard LCOE+ 2025, kara RES "Fixed O&M" 24,5–40 $/kW-yıl (300 MW referans santral). Raporda kalem
kırılımı yok; ABD pratiğinde arazi kirası, emlak vergisi ve sigortayı da içeren her şey dahil işletme gideridir (LBNL'nin
her şey dahil örnekleri 33–59 $/kW-yıl). v1 bandın üstünden 35 $/kW-yıl alıp **ayrıca** sigorta (%0,35 CAPEX ≈ 4,0) ve arazi
kirası (1,5) ekliyordu: toplam 40,5 $/kW-yıl, sigorta ve arazide kısmi çift sayım olasılığıyla.

Kapsam tablosu (`outputs/v3E/E0_om_kapsam.csv`, $/kW-yıl):

| Kalem | Lazard | LBNL 2019 | DWG 2024 | v1 | Bakım modeli (DES) | v3 FSA | Finansta ayrı |
|---|---|---|---|---|---|---|---|
| Türbin planlı + plansız bakım | dahil | 14–28 (ort. 20) | 14–18 (tam bakım sözleşmesi) | 35 içinde | 10,8 (kendi yapsaydık) | **20,0** | – |
| Kendi bakım organizasyonu | dahil | ölçek etkisi | – | 35 içinde | yok | FSA'ya dahil | – |
| BOP bakımı (trafo merkezi/şalt, kablo) | dahil | 5,0 / 7,9 | (diğer) | 35 içinde | yok | 5,0 | – |
| Yol ve saha, O&M tesisleri | dahil | 2,0 | (diğer) | 35 içinde | yok | 1,5 | – |
| SCADA ve haberleşme | dahil | (varlık yön.) | (işletme yön.) | 35 içinde | yok | 1,0 | – |
| Varlık yönetimi, genel giderler | dahil | 2,2–2,6 | 4,3–5,4 | 35 içinde | yok | 3,5 | – |
| Sahibin saha personeli | dahil | – | (işletme yön.) | 35 içinde | yok | 1,0 | – |
| Beklenmeyen/diğer | dahil | 0,4+ | 6,5–7,6 | 35 içinde | yok | 2,0 | – |
| **Toplam O&M** | 24,5–40 | 33–59 (her şey dahil) | 53–62 (her şey dahil) | 35 | – | **34,0** | |
| Sigorta | muhtemelen dahil | 2,6 | 1,1 | +4,0 | – | ayrı | evet (4,0) |
| Arazi kirası | muhtemelen dahil | 4,2–5,0 | 19–21 (Almanya) | +1,5 | – | ayrı | evet (1,5) |

Kaynaklar: Lazard LCOE+ June 2025 (s. 35); Wiser vd. 2019, LBNL "Benchmarking wind power operating costs in the United
States" (Şekil 4–5, §3.6); Deutsche WindGuard 2024 "Kostensituation der Windenergie an Land" (Abb. 10; 1 € = 1,08 $).
Sahip kalemlerinin tek tek değerleri bu aralıklardan **TAHMİN** olarak seçildi.

**İki işletme modeli** (`src/bakim/isletme.py`, config `v3.isletme`):
- **(i) FSA — üreticiyle tam kapsamlı servis sözleşmesi:** O&M = FSA fiyatı 20 $/kW-yıl (aralık 14–29) + sahip kalemleri
  14 = **34 $/kW-yıl**. Kullanılabilirlik: %97 zaman bazlı garanti; garantinin altı tazminatla karşılandığı için
  beklenen kullanılabilirlik E[max(A_sim, 0,97)] (garanti bir "satım opsiyonu" gibi çalışır).
- **(ii) Kendi bakımı:** O&M = DES türbin bakım maliyeti (ekip, malzeme × 1,15 parça primi, vinç, önleyici, CMS, stok)
  + organizasyon sabit gideri 0,6 M$/yıl (TAHMİN: bakım müdürü, mühendisler, depo, araç, eğitim, 7/24 izleme) + sahip
  kalemleri. Kullanılabilirlik E[A_sim].

**Varsayılan FSA (10–15 türbinlik tek saha) gerekçesi:**
1. Başabaş filonun altında (aşağıda).
2. Finansman: DWG'ye göre Alman projelerinin büyük kısmı 20 yıllık tam bakım sözleşmesi kullanıyor, çünkü planlanabilir
   maliyet ve kullanılabilirlik garantisi iyi finansman koşulları için gereken risk azaltımını sağlıyor.
3. Büyük bileşen riski (dişli kutusu değişimi ~250 bin $) tek santralin bilançosunda kalmıyor.
4. LBNL: tam kapsamlı sözleşmeler türbin O&M'ini %10–12 artırıyor ama varlık yönetimi giderini azaltıp %97 üstü
   kullanılabilirlik sağlıyor.

**Kendi bakımının başabaş filo büyüklüğü** (`outputs/v3E/E0_isletme_basabas.csv`; Ezine profili, durum stratejisi, ekip
sayısı her 7 türbinde bir artar):

| Yöntem | Başabaş türbin sayısı |
|---|---|
| DES maliyetiyle (kendi türbin bakımı ölçekte 10,8 $/kW-yıl), FSA 20 | **16** |
| FSA 14 / 29 $/kW-yıl | 46 / 8 |
| Literatüre kalibre: ölçekte %19 / %25 / %30 tasarruf (IHS Markit 2018 / orta / Briggs 2017) | 38 / 29 / 24 |

DES'in ölçekteki tasarrufu (%46) literatürün %19–30'undan büyük: Carroll maliyetleri yalnız malzeme, işçilik Türkiye
ücretiyle. Bu yüzden başabaşı **16–38 türbin** aralığı olarak raporluyorum (merkez ~25–30). 10–15 türbinlik tek saha
FSA'da kalmalı; kendi bakımı ancak portföy ölçeğinde (Faz F) anlamlı.

**Bakım modelinin yeni rolü:** kullanılabilirlik dağılımı (Monte Carlo gürültüsü ve FSA garantisinin değeri), stratejiler
arası fark, bakım takvimi ve yedek parça. Mutlak O&M seviyesi işletme modelinden.

### 0.2 Ö2 — Kayıp tablosu ve çift sayım

**Kodda kayıpların nerede uygulandığı (denetim):**

| Kategori | Nerede | Kaç kez |
|---|---|---|
| İz | `yerlesim.analiz.profil_duzelt` (saatlik η, PyWake + komşular); hızlı taramada tablo | 1 |
| Kullanılabilirlik | `motor.v3.bakim_uygula` (profil × A); MC'de yalnız ortalaması 1 olan gürültü | 1 |
| Elektrik, türbin performansı, çevresel | taban kayıp λ içinde (göreli kural) | 1 |
| Sistem kaynaklı kesinti | finansal model / MC (`kesinti`) | 1 (kayıp tablosunda yok) |
| Türbin bozunması | finansal model (yıllık %0,3) | 1 |
| Dengesizlik | finansal model (gelirin %4'ü) | 1 |

`yerlesim_bakim=False` (v2) yolunda yalnız toplu %12 uygulanıyor; v3 yolunda toplu %12 hiç kullanılmıyor (`toplam_kayip`
taban kayıpla değiştiriliyor). **Çift sayılan ya da hiç sayılmayan kayıp bulunmadı**; `kayip.tablo()` kategorilerin
çarpımının profile uygulanan toplamla birebir eşit olduğunu doğruluyor (`tutarli`, testte).

**Açık tablo** (`src/uretim/kayip.py`, Lee & Fields 2021 Tablo B kategorileri):

| Kategori | Atlas referansı (tipik kalibre santral) | Yeni saha (iz %3,1, kullanılabilirlik %97,4) | Kaynak |
|---|---|---|---|
| İz | %5,1 | %3,1 | atlas ortalaması / PyWake |
| Kullanılabilirlik | %1,0 (yalnız < 48 saat duruşlar) | %2,6 | kalibrasyon / DES + FSA |
| Elektrik | %2,0 | %2,0 | AWS 2014 tipik 2,1; KB Avrupa 1,2 |
| Türbin performansı | %2,0 | %2,0 | AWS 2014 2,4; gözlenen 1,1–2,5 |
| Çevresel: kirlenme/erozyon | %1,0 | %1,0 | AWS 2014 1,0; endüstri 1–2 |
| Çevresel: sıcaklık, yıldırım | %0,5 | %0,5 | AWS 2014 0,6 |
| Çevresel: buzlanma | %0,2 | %0,2 | TAHMİN (Kuzey Amerika tipik 1,0) |
| Atlas kalibrasyon farkı | %0,8 | %0,8 | 0,88 / Π(kategoriler) |
| **Toplam** | **%12,0** | **%11,6** | |

**%12 ile fark:** v2'nin toplu %12'si, kategorilerin kaynaklı toplamıyla (%11,3) + %0,8'lik kalibrasyon farkıyla
açıklanıyor. Fark, K katsayısının kalibre santrallerdeki gerçek kayıplarla ilgili küçük bir sapmayı taşıdığını gösteriyor
(ör. eski filoda bozunma, tam ayıklanamayan kısa talimatlar). Sahaya özgü olmayan kategoriler göreli kuralda sadeleştiği
için finansal sonuca etkileri yok; yeni sahalarda toplam, iz ve kullanılabilirlik farkıyla %10,3–11,5 (üç saha). Buzlanma
yüksek rakımlı doğu sahalarında (Gürün ~1.600 m) daha yüksek olabilir; sahaya özgü buzlanma modeli yok (sınırlama).

### 0.3 Ö3 — Bakım parametreleri duyarlılığı

12 TAHMİN parametresi alt/üst değerine çekildi (24 senaryo; Ezine, 14 türbin, 60 ömür, ortak rastgele sayılar; maliyet =
kendi bakım maliyeti + kayıp gelir). Temel: düzeltici 1.017, takvim 912, durum 896 bin $/yıl.

- **Sıralama:** durum bazlı 20/24 senaryoda, takvim bazlı 4/24 senaryoda en iyi; düzeltici hiçbirinde.
- **Takvimin düzelticiye üstünlüğü (105 bin $/yıl)** yalnız bakımsız yaşlanma varsayımına duyarlı: Weibull ölçek çarpanı
  0,8 → 0,93'ün üstüne çıkarsa (önleyici bakım yaşlanmayı neredeyse hiç yavaşlatmıyorsa) düzeltici takvimin önüne geçiyor.
- **Durum bazlının takvime üstünlüğü (16 bin $/yıl) kırılgan.** Eşikler:
  - CMS maliyeti > 2.330 $/türbin-yıl (temel 1.200),
  - yakalama olasılıkları × 0,74'ün altında,
  - P-F aralığı × 0,65'in altında (≈ 20–80 gün),
  - büyük bileşen değişim oranları × 0,73'ün altında.
- Tornado grafiği `outputs/v3E/E0_tornado.png`; arayüzdeki strateji karşılaştırmasının altında "Strateji sıralamasının
  dayanıklılığı" bölümü aynı veriyi gösteriyor.

**Yorum:** önleyici bakım (takvim) yapmak açıkça doğru; CMS'nin değeri ise satıcı fiyatına ve teşhis başarısına bağlı.
Karar kuralı: CMS teklifi türbin başına yılda ~2.300 $'ın altındaysa ve aktarma organı arızalarının ~%60'ını en az 2–3 ay
önce yakalayabiliyorsa al.

### 0.4 Ö4 — Üç sahada üç aşama (tam analiz, 2 çekirdek)

| Saha | Aşama | RES / BESS | Türbin | O&M bin $/MW-yıl | Kullanılabilirlik | E[NPV] M$ | P(NPV>0) | Başabaş $/MWh | Karar |
|---|---|---|---|---|---|---|---|---|---|
| Ezine | Faz D öncesi (v2) | 58,8 / 31 MW | – | 35,0 | toplu | **-6,30** | %33 | 62,6 | rafa kaldır |
| Ezine | Faz D sonrası | 42,0 / 30 MW | 10 | 28,7 | %97,5 | **-0,82** | %44 | 58,8 | rafa kaldır |
| Ezine | Ön adım sonrası (FSA) | 33,6 / 30 MW | 8 | 34,0 | %97,4 | **-1,95** | %40 | 60,3 | rafa kaldır |
| Ezine |  Ön adım sonrası, kendi bakımı | 29,4 / 30 MW | 7 | 45,4 | %97,3 | **-4,48** | %32 | 64,0 | rafa kaldır |
| Gürün | Faz D öncesi (v2) | 54,6 / 32 MW | – | 35,0 | toplu | **-5,71** | %34 | 62,4 | rafa kaldır |
| Gürün | Faz D sonrası | 46,2 / 31 MW | 11 | 27,7 | %97,3 | **-1,30** | %43 | 59,2 | rafa kaldır |
| Gürün | Ön adım sonrası (FSA) | 37,8 / 30 MW | 9 | 34,0 | %97,4 | **-2,91** | %38 | 61,1 | rafa kaldır |
| Gürün |  Ön adım sonrası, kendi bakımı | 33,6 / 30 MW | 8 | 47,3 | %97,3 | **-6,41** | %29 | 65,6 | rafa kaldır |
| Susurluk | Faz D öncesi (v2) | 58,8 / 31 MW | – | 35,0 | toplu | **-5,04** | %36 | 61,6 | rafa kaldır |
| Susurluk | Faz D sonrası | 54,6 / 31 MW | 13 | 26,2 | %97,4 | **-0,36** | %47 | 58,3 | rafa kaldır |
| Susurluk | Ön adım sonrası (FSA) | 42,0 / 30 MW | 10 | 34,0 | %97,5 | **-1,37** | %43 | 59,3 | rafa kaldır |
| Susurluk |  Ön adım sonrası, kendi bakımı | 42,0 / 30 MW | 10 | 41,6 | %97,4 | **-3,88** | %36 | 61,7 | rafa kaldır |

**Yorum.**
- Faz D'nin E[NPV] iyileşmesinin büyük kısmı O&M'nin 25,5 bin $'a inmesinden geliyordu. Ö1 bunun kapsam farkı olduğunu
  gösterdi (bakım modeli BOP, varlık yönetimi gibi sahip kalemlerini içermiyordu ve servis sözleşmesi fiyatı değil maliyet
  ölçüyordu). FSA ile O&M 34 bin $'a döndü; E[NPV] Faz D'ye göre 1,0–1,6 M$ düştü.
- Faz D'nin kalıcı katkısı tasarımın küçülmesi ve iz kaybının açık modellenmesi: v2'ye göre E[NPV] hâlâ 2,8–4,4 M$ daha iyi.
  O&M daha yüksek olduğu için MILP santrali daha da küçültüyor (8–10 türbin).
- Kendi bakımı (8–10 türbinlik filoda organizasyon sabit gideri 0,6 M$/yıl): O&M 42–47 bin $, E[NPV] 2,5–3,5 M$ daha kötü.
  Tek saha için FSA'nın doğru varsayılan olduğunu doğruluyor.
- **Karar hiçbir aşamada değişmedi:** rafa kaldır. Başabaş fiyat 59,3–61,1 $/MWh (senaryo 58).

---

## 1. Faz E özeti

| | |
|---|---|
| Kod | `src/cbs/` — `katmanlar.py` (CBS gridi okuma, dışlama katmanları, alan özeti), `baglanti.py` (mesafeye bağlı bağlantı), `lojistik.py` (nakliye ağı, ulaştırma LP'si), `altyapi.py` (motora uygulama), `cok_kriterli.py` (AHP, TOPSIS, dayanıklılık, ROC/AUC), `kriterler.py` (hücre kriter tablosu, profiller) |
| Çevrimdışı betikler | `src/v3_E1_osm_katmanlar.py` (Geofabrik PBF → katmanlar), `src/v3_E1_egim_grid.py` (Copernicus DEM → eğim), `src/v3_E1_kaynak_veri.py` (limanlar, üreticiler, göç koridorları, YEKA bağlantı görüşleri), `src/v3_E1_cbs_grid.py` (250 m mesafe gridleri), `src/v3_E4_nakliye_agi.py` (ağır nakliye ağı + Dijkstra), `src/v3_E2_hucre_tablosu.py` (1.464 hücre altyapı tablosu), `src/v3_E2_on_tarama.py` (v3 ön tarama), `src/v3_E3_cok_kriterli.py`, `src/v3_E5_harita_katmanlari.py`, `src/v3_E6_once_sonra.py`, `src/v3_E6_dogrulama.py` |
| Uygulamaya giden küçük dosyalar | `data/atlas/`: `cbs_hucre.parquet`, `trafo_merkezleri.csv`, `havalimanlari.csv`, `tedarik_kaynaklari.csv`, `goc_koridorlari.json`, `teias_yeka_baglanti.csv`, `lojistik_referans.json`, `katman_*.geojson`, `v3_cok_kriterli_dogrulama.json` |
| Ağır gridler (repoda yok) | `data/grid/cbs_tr/v1` (77 MB, 250 m mesafe/koruma/göç), `data/grid/egim_tr/v1` (eğim, rakım), `data/grid/lojistik_tr/v1/ag.npz` (ağ + kaynaklardan en kısa mesafeler) |
| Config | `v3.cbs` (tamponlar, yol sınıfları), `v3.baglanti` (gerilim kuralı, $/km, TM, fider), `v3.lojistik` (bileşen seferleri, taşıma birim maliyeti, süreler, kapasite) |
| Kullanıcı anahtarı | `KullaniciVarsayimlari(altyapi_maliyetleri=True)` — kapatılırsa ön adım sonrası davranış (sabit 120 bin $/MW, CBS dışlaması yok) |

Mimari kural korunur: OSM, DEM, EPİAŞ yalnız çevrimdışı betiklerde işlenir. Uygulama çalışırken yalnız `data/atlas` ve
`data/grid` altındaki ön hesaplanmış dosyaları okur (`src/veri_katmani.py`); dış API çağrısı yok.

## 2. Veri kaynakları ve lisans kararları (E1)

| Katman | Kaynak | Lisans / koşul | Karar |
|---|---|---|---|
| Yollar (sınıflı), iletim hatları ve trafo merkezleri (gerilimli), yerleşimler, havalimanları, koruma alanları | OpenStreetMap, Geofabrik Türkiye PBF (2026-10-08) | ODbL 1.0 — atıf + türev veritabanı ODbL ile paylaşılır | Kullanıldı; türev dosyalar `data/atlas/README.md`'de ODbL olarak işaretli |
| Koruma alanları (resmî) | WDPA / Protected Planet | Yeniden dağıtım ve ticari kullanım yasak; türev ürünler için izin gerekir | **Kullanılmadı** → OSM `boundary=protected_area` / `leisure=nature_reserve` (eksik olabilir; sınırlama olarak yazıldı) |
| Eğim, rakım | Copernicus DEM GLO-90 (AWS açık veri) | Ücretsiz, atıf zorunlu (© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, ESA Copernicus) | Kullanıldı; 250 m karo başına ortalama/azami eğim |
| Limanlar, yerli üreticiler | Liman işletmelerinin ve üreticilerin kendi sayfaları, TÜREB, DARGEB | Olgusal bilgi (konum, ürün) | Doğrulanmayanlar (`dogrulandi=False`) hesaba girmez |
| Kuş göç koridorları | Doğa Derneği, Jobson vd. (2021), Belen RES izleme çalışmaları | Yayınlardan elle sayısallaştırılmış **yaklaşık** eksenler (CC BY 4.0 olarak paylaşılır) | Dışlama değil, değerlendirme kriteri + açık uyarı |
| TEİAŞ bağlantı kapasitesi | TEİAŞ, ETKB | — | **Lisanslı RES için trafo merkezi bazında yayımlanmıyor** (yalnız lisanssız üretim için bölgesel kapasite ve YEKA yarışmasına özel bağlantı görüşleri). Ana sınırlama olarak raporlanır; YEKA RES-2025 görüşleri doğrulamada kullanıldı |

## 3. Mesafeye bağlı şebeke bağlantı maliyeti (E2)

**Parametreler:** bağlantı gücü $P$ [MW]; gerilim kuralı $V(P)$ (≤ 30 MW 34,5 kV; ≤ 300 MW 154 kV; üstü 400 kV);
$c^{hat}_V$ [$/km], $C^{TM}_V$ proje yükseltici TM, $C^{fid}_V$ TEİAŞ TM'de hat fideri; güzergâh çarpanı $g = 1{,}25$;
erişim yolu $c^{yol}$ [$/km], RES CAPEX'inde varsayılan ilk $d_0 = 2$ km.

**Hedef trafo merkezi:** gerilimi $\ge \max(V, 154)$ (400 kV projede ≥ 380) olan en yakın OSM trafo merkezi; uzaklık $d_{TM}$.

$$
C_{bag} = C^{TM}_V + C^{fid}_V + g\, d_{TM}\, c^{hat}_V + g\, \max(0,\; d_{yol} - d_0)\, c^{yol}
$$

$d_{yol}$: sahadan ağır nakliyeye uygun en yakın yola uzaklık (250 m grid). Motor `teknoloji.sebeke.capex = C_bag / P`
olarak kullanır (v1 sabit 120 bin $/MW yerine); hızlı tarama, tam analiz ve ön tarama aynı fonksiyonu kullanır.

**Sezgi.** Sabit kalemler (TM + fider ≈ 5,3 M$) 50 MW'lık projede 106 bin $/MW eder; her ek km hat ≈ 3,75 bin $/MW.
Bu nedenle v1'in 120 bin $/MW varsayımı trafo merkezine ~4 km'deki bir sahaya karşılık gelir; Türkiye medyanı (14 km)
v1'in üzerinde kalır.

**Kapsam dışı:** TEİAŞ kapasite tahsis katkı payı (YEKA/yarışma), sistem güçlendirme (EİH yenileme), kamulaştırma.

## 4. CBS dışlamaları ve türbin yerleşimine bağlantı (E2)

Faz D'nin `DislamaKatmani` arayüzü (`maske(enlem, boylam) → bool`) korunur; `src/cbs/katmanlar.CBSDislama` her kural için
bir katmandır. 250 m gridde önceden hesaplanmış uzaklıklar okunur (Öklid uzaklık dönüşümü, `scipy.ndimage`).

| Kural | Eşik | Kaynak |
|---|---|---|
| Yerleşim tamponu | 500 m | TAHMİN (ulusal asgari mesafe yok; gürültü yönetmeliği uygulaması 300–500 m) |
| Otoyol | 1,5 (H + L) | KGM uygulaması (ikincil kaynak) |
| Devlet / il yolu | 1,25 (H + L) | KGM uygulaması (ikincil kaynak) |
| İletim hattı | 1,5 (H + L) | TAHMİN (devrilme mesafesi) |
| Havalimanı | 5 km | TAHMİN (SHGM görüşü proje bazında) |
| Eğim | ortalama > 15° | TAHMİN (literatür 10–15°) |
| Koruma alanı | içinde | OSM |

$H$ göbek yüksekliği, $L$ kanat uzunluğu (≈ D/2). Tam analizde altyapı açıkken `motor.v3.baglam_kur` bu katmanları
`yerlesim.analiz.hazirla(dislama=...)`'ya verir; aday noktalar elenir, sığan en fazla türbin sayısı azalabilir
(Ezine: 28 → 19 türbin; tasarımı bağlamadı).

## 5. Çok kriterli saha seçimi (E3)

### 5.1 Dışlayıcı kısıtlar ve değerlendirme kriterleri

Dışlayıcı (telafi edilemez): koruma alanı payı ≥ %50; 2 km yarıçapta uygun alan < %10 (§4 dışlamalarından arta kalan);
ada (kullanıcı dahil etmedikçe); hesaplanamayan başabaş.

Değerlendirme (telafi edilebilir, TOPSIS):

| Kriter | Gösterge | Yön |
|---|---|---|
| Ekonomi | en iyi standart tasarımın başabaş fiyatı [$/MWh] | maliyet |
| Şebeke | uygun gerilimli en yakın TM'ye uzaklık [km] | maliyet |
| Yol | ağır nakliye yoluna uzaklık [km] | maliyet |
| Eğim | 2 km yarıçapta ortalama eğim [°] | maliyet |
| Göç | göç koridoru riski (0/1/2) | maliyet |
| Güven | rüzgâr tahmini güveni (yüksek 1 / düşük 0) | fayda |
| Lojistik | bileşen teslim maliyeti [$/MW] | maliyet |

Ekonomi kriteri bağlantı ve lojistik maliyetini zaten içerir; şebeke ve lojistik kriterlerinin ayrıca yer alması
**risk** boyutudur (uzun hat = izin/kamulaştırma ve kapasite riski; uzun rota = teslim gecikmesi riski). Ekonomik
sıralamayla karşılaştırma bu çift etkiyi görünür kılmak içindir.

### 5.2 AHP (Analitik Hiyerarşi Süreci)

**Kümeler:** kriterler $i, j \in \{1..n\}$. **Parametre:** ikili karşılaştırma matrisi $A$, $a_{ij}$ ∈ Saaty ölçeği
{1/9 … 9}, $a_{ji} = 1/a_{ij}$, $a_{ii} = 1$.

Ağırlıklar $A$'nın en büyük özdeğerine ($\lambda_{maks}$) ait özvektördür: $A w = \lambda_{maks} w$, $\sum_i w_i = 1$.

Tutarlılık: $CI = (\lambda_{maks} - n)/(n - 1)$, $CR = CI / RI_n$ (Saaty rastgele indeksi; $RI_7 = 1{,}32$).
$CR > 0{,}10$ ise arayüz uyarır. Tam tutarlı bir matriste ($a_{ij} = s_i/s_j$) $\lambda_{maks} = n$, $CR = 0$.

Hazır profiller önem puanlarından $a_{ij} = s_i / s_j$ ile kurulur (tam tutarlı):

| Profil | Ekonomi | Şebeke | Yol | Eğim | Göç | Güven | Lojistik |
|---|---|---|---|---|---|---|---|
| Ekonomi öncelikli | 9 | 3 | 2 | 2 | 1 | 3 | 3 |
| Risk/çevre öncelikli | 3 | 2 | 2 | 5 | 9 | 6 | 1 |
| Dengeli | 6 | 3 | 2 | 3 | 4 | 4 | 2 |

### 5.3 Standardizasyon (değer fonksiyonu) ve TOPSIS

Karar matrisi $X_{mi}$ (hücre $m$, kriter $i$). Her kriter doğrusal bir **değer fonksiyonuyla** ortak [0, 1] ölçeğe taşınır
(Malczewski 2006, GIS-MCDA'da olağan standardizasyon):

$$
r_{mi} = \min\!\Big(1,\ \max\!\Big(0,\ \frac{x_{mi} - x^{kötü}_i}{x^{iyi}_i - x^{kötü}_i}\Big)\Big)
$$

| Kriter | En iyi (1) | Kabul edilemez (0) |
|---|---|---|
| Başabaş fiyat | 50 $/MWh | 90 $/MWh |
| Trafo uzaklığı | 0 km | 40 km |
| Yol uzaklığı | 0 km | 20 km |
| Eğim | 0° | 15° |
| Göç riski | 0 | 2 |
| Güven | yüksek | düşük |
| Lojistik | 30 bin $/MW | 120 bin $/MW |

(`config v3.cok_kriterli`, TAHMİN; uçlar uygun hücrelerin dağılımından.) Böylece $w_i$, "kriter $i$'de en iyiden kabul
edilemeze geçişin önemi" anlamını kazanır. Bundan sonra tüm kriterler faydadır; ağırlıklı $v_{mi} = w_i r_{mi}$.

**Neden klasik vektör normalizasyonu değil?** İlk denemede klasik TOPSIS ($r_{mi} = x_{mi}/\sqrt{\sum_m x_{mi}^2}$)
kullanıldı. Başabaş fiyatın göreli aralığı dar (iyi hücreler 50–65 $/MWh, ortalamaya göre ±%15), trafo uzaklığınınki geniş
(0,5–60 km, birkaç kat). Vektör normalizasyonu her sütunu kendi büyüklüğüyle böldüğü için dar aralıklı kriteri bastırdı:
"dengeli" profilde (ekonomi ağırlığı %25) ilk sıraya 65 $/MWh'lik Marmaraereğlisi çıktı, ilk 10'un 7'si 60 $/MWh'nin
üstündeydi. Değer fonksiyonuyla ilk sıra Çerkezköy (50,8), ilk 10'un tamamı ≤ 60,3. Karşılaştırma
`outputs/v3E/E3_ilk10_dengeli_vektor.csv`; `normalizasyon: vektor` ile eski davranış geri gelir.

TOPSIS: ideal $A^+$ (her sütunun en büyüğü) ve anti-ideal $A^-$ (en küçüğü). Uzaklıklar
$D^\pm_m = \lVert v_m - A^\pm \rVert_2$, yakınlık katsayısı $C_m = D^-_m / (D^+_m + D^-_m) \in [0, 1]$; uygunluk puanı
$100\,C_m$.

### 5.4 Dayanıklılık

Ağırlıklar $\tilde w \sim \text{Dirichlet}(\alpha w)$, $\alpha = 50$ ile örneklenir (ortalama $w$, her ağırlık yaklaşık
±%20–40 göreli oynar); her örnekte TOPSIS yeniden çalışır. $P(\text{ilk 10})_m$ = hücrenin ilk 10'a girdiği örneklerin
oranı (çalışma betiğinde 1.000, arayüzde 300 örnek).

### 5.5 Doğrulama: mevcut santraller

Etiket $y_m = 1$: hücrede OSM rüzgâr türbini var (geliştiricilerin gerçek kararları). AUC = rastgele bir santralli
hücrenin santralsiz bir hücreden yüksek puan alma olasılığı (Mann–Whitney $U / (n_1 n_0)$). "Gerçek dünya tercihleri":
ağırlık simpleksinde rastgele arama (4.000 Dirichlet(1) örneği + köşeler) ile AUC'yi en büyükleyen ağırlıklar.

**Döngüsellik:** güven kriteri tanımı gereği kalibre santrallere ≤ 30 km yakınlıktır, başabaş fiyat da santrallerden
kalibre edilen katsayıları kullanır. Bu yüzden açığa çıkan tercih ağırlıkları güven kriteri dışarıda bırakılarak aranır
ve ayrıca yalnız rüzgâr KF'li varyant raporlanır. Mevcut santraller "seçilmiş" yerleri gösterir, "en iyi" yerleri değil
(ör. erken dönem santraller iletim hattına yakın, eski türbinler).

## 6. Lojistik (E4)

### 6.1 Ağır nakliye ağı

OSM otoyol/devlet/il yolu (+ bağlantı kolları) ve koşullu ikincil yollar kavşaklarda bölünerek yönsüz grafa
dönüştürülür (179.811 düğüm, 235.944 kenar, 123.908 km). Kenar ağırlığı
$w_e = \ell_e \cdot \rho_{sınıf} \cdot \rho_{yokuş}$: ikincil yol $\rho = 1{,}5$; ≥ 200 m'lik kesitte eğim > %10 ise
$\rho_{yokuş} = 1{,}5$ (TAHMİN; kanat römorkları). Her doğrulanmış kaynaktan Dijkstra (scipy) → tüm düğümlere etkin
mesafe ve öncül; ağ dışı uçlar kuş uçuşu × 1,3. Bir sahaya rota = en yakın ağ düğümünden öncül zinciri.

### 6.2 Ulaştırma LP'si

**Kümeler:** bileşenler $c$ (kanat, kule, nasel, göbek), kaynaklar $s$ (yerli üretici ya da ithalat limanı),
sahalar $j$. **Parametreler:** $u_{csj}$ türbin seti başına teslim maliyeti, $D_{cj}$ talep (türbin sayısı),
$K_{cs}$ yıllık kapasite (biliniyorsa).

$$
u_{csj} = n_c\,\big(F + I + \tau\, m_c\, d_{sj}\big) + \mathbb{1}[s\ \text{liman}]\; N^{navlun}_c
$$

$n_c$ sefer sayısı, $m_c$ sefer başına kütle [t], $\tau$ = 0,40 $/t-km (Cotrell vd. 2014, enflasyonla), $F$ sefer sabit,
$I$ izin/eskort, $d_{sj}$ etkin yol mesafesi.

**Değişken:** $x_{csj} \ge 0$ (türbin seti). **Amaç:** $\min \sum u_{csj} x_{csj}$.
**Kısıtlar:** $\sum_s x_{csj} = D_{cj}$ (talep), $\sum_j x_{csj} \le K_{cs}$ (kapasite).

Tek sahada LP her bileşen için en ucuz kaynağı seçer; yapı Faz F'de çoklu saha ve kapasitelerle aynen kullanılır
(talep kısıtının gölge fiyatı = o sahaya bir türbin daha getirmenin marjinal lojistik maliyeti).

**Teslim süresi:** $T_{cs} = T^0_{c,\,yerli/ithal} + d_{sj} / (300\ \text{km/gün}) / 30$; saha teslim süresi
$\max_c T$ (seçilen kaynaklarla).

### 6.3 CAPEX ve takvime bağlantı

RES CAPEX'i (1,15 M$/MW) teslim edilmiş türbini varsayar. Referans = mevcut santralli 171 hücrenin medyanı
(43,2 bin $/MW, 8,0 ay; `data/atlas/lojistik_referans.json`). Motor:
`res.capex += lojistik_usd_mw − referans`, tam analizde COD örnekleri `+= max(0, teslim − referans)` ay
(türbin tedariki Aşama 7 CPM'inde kritik yolda).

## 7. Sonuçlar ve doğrulama (E6)

### 7.1 Bağlantı maliyeti doğrulaması (`outputs/v3E/E6_baglanti_dogrulama.csv`)

| Proje (YEKA RES-2025) | MW | kV | TEİAŞ hattı (km) | Formül (M$) | bin $/MW | Aynı ilde modelin trafo uzaklığı (medyan km) |
|---|---|---|---|---|---|---|
| Sivas | 500 | 400 | 210 | 79,8 | 160 | 17,6 |
| Balıkesir-1 | 160 | 400 | 46 | 25,7 | 161 | 11,3 |
| Balıkesir-2 | 120 | 400 | 52 | 27,7 | 231 | 11,3 |
| Balıkesir-3 | 110 | 400 | 26 | 19,1 | 173 | 11,3 |
| Aydın-Denizli | 140 | 154 | 14 | 7,4 | 53 | 9,1 |
| Kütahya | 120 | 154 | 24 | 8,9 | 74 | 13,8 |

- Model 50 MW'lık hücrelerde 128 / 175 / 244 bin $/MW (p10 / medyan / p90) veriyor; YEKA projelerine uygulanan aynı
  formül 53–231 bin $/MW. v1'in 120 bin $/MW'si aralığın alt yarısında.
- ~~TEİAŞ'ın atadığı hatlar modelin "en yakın trafo" uzaklığından 2–12 kat uzun; model düşük tahmin etme eğiliminde.~~
  **Düzeltme (Faz F ön adım Ö2):** bu karşılaştırma 400 kV atamaları 154 kV'luk en yakın trafoyla kıyaslıyordu. Aynı gerilim
  sınıfıyla ve RES-2026 görüşleri eklenerek (14 santral alanı) atanan / model oranı medyan 0,73, ortalama 1,14,
  log-σ 0,94: atamalar sistematik olarak uzun değil, çok dağınık (mevcut hatta girdi-çıktı 0,13–0,23; Sivas R25 3,3).
  Bu dağılım artık tam analizin Monte Carlo'sunda bağlantı maliyeti belirsizliği olarak kullanılıyor
  (docs/v3_F_portfoy_performans.md §0.2).
  Mevcut santralli hücrelerde en yakın uygun trafo 8,2 km (tüm hücrelerde 14,0 km): mevcut santraller trafoya yakın
  kurulmuş (bkz. §7.4 açığa çıkan tercih).

### 7.2 Lojistik payı

- Lojistik maliyeti RES CAPEX'inin %3,6 / 5,3 / 8,1'i (p10 / medyan / p90); 41 / 61 / 94 bin $/MW.
- 400 km'lik kule taşımasının "kule + taşıma" maliyetindeki payı %10,5 (kule fiyatı 2.000 $/t TAHMİN). Cotrell vd.
  (2014) ABD için < %8 diyor; Türkiye'de sefer başına izin/eskort ve sefer sabit gideri payı biraz büyütüyor. Aynı
  büyüklük sırası.
- Teslim süresi 8,0–8,1 ay (bileşen hazırlık süreleri baskın; mesafe en fazla birkaç gün ekliyor). COD kayması pratikte
  sıfır (Gürün +0,03 ay): lojistik, takvim riskinden çok maliyet kalemi.

| Saha | Kanat | Kule | Nasel + göbek | $/MW | Hedef TM (km) | Bağlantı (bin $/MW) |
|---|---|---|---|---|---|---|
| Ezine | TPI İzmir (241 km) | Ateş Bergama (183 km) | Bandırma limanı (208 km) | 38.755 | TEİAŞ Ezine 154 kV (1,6) | 112 |
| Gürün | TPI İzmir (1.084 km) | **Samsunport, ithal** (453 km) | Samsunport (453 km) | 68.943 | Kangal RES TM (17,5) | 206 |
| Susurluk | TPI İzmir (208 km) | Gesbey Bandırma (89 km) | Bandırma limanı (65 km) | 32.624 | Poyraz RES Susurluk TM (11,4) | 149 |

Gürün'de LP, kuleyi yerli fabrikadan 1.000 km taşımak yerine (6 sefer × 60 t × 0,40 $/t-km ≈ 144 bin $ + sefer giderleri)
ithal edip Samsun'dan getirmeyi seçiyor: ulaştırma problemi sezgiye aykırı ama doğru bir sonuç veriyor.

### 7.3 Türkiye ön tarama haritası (`outputs/v3E/E6_on_tarama_karsilastirma.csv`)

Üç sürüm: v2 → v3 altyapısız (iz tablosu + FSA + kullanılabilirlik) → v3 (+ mesafeye bağlı bağlantı + lojistik).

| | v2 | v3 |
|---|---|---|
| Başabaş fiyat medyanı (1.457 hücre, adalar hariç) | 90,1 $/MWh | 95,7 $/MWh |
| 58 $/MWh altındaki hücre | 49 | 43 |
| Ekonomik ilk 10'da ortak | 8 / 10 | |
| Sıra korelasyonu (Spearman) | 0,93 | |

- Değişimin ayrıştırması: ön adım (iz/FSA/kullanılabilirlik) medyanda 0 (p10 −0,8 $/MWh; medyan hücrenin en iyi tasarımı
  GES olduğu için RES değişimleri etkilemiyor); **altyapı** medyanda **+4,4** (p10 +0,6, p90 +11,1) $/MWh. 60 $/MWh altı
  84 iyi hücrede altyapı etkisi daha küçük: medyan +1,3 (en çok +6,9): iyi rüzgâr sahaları zaten şebekeye yakın.
- İlk 10'dan çıkanlar: **Sivas-Gürün** (49,5 → 54,2; trafo 17,5 km, lojistik 69 bin $/MW) ve **İzmir-Urla**
  (51,0 → 53,8). Girenler: Balıkesir-Erdek, İzmir-Karaburun (ikinci hücre).

**v3 ekonomik ilk 10** (en düşük başabaş, adalar hariç): Bursa-Karacabey 50,2 · Manisa-Soma 50,3 · İzmir-Karaburun 50,5
(düşük güven) · Tekirdağ-Çerkezköy 50,8 · Hatay-Belen 51,7 · İzmir-Çeşme 52,1 · İzmir-Bergama 52,2 · Çanakkale-Ezine 52,5 ·
Balıkesir-Erdek 52,7 · İzmir-Karaburun 52,9.

### 7.4 Çok kriterli sıralama ve doğrulama (`data/atlas/v3_cok_kriterli_dogrulama.json`)

Dışlama: 1.464 hücreden 98'i koruma alanı, 101'i uygun alan < %10, 4'ü ada → 1.261 sıralanır. Karacabey'in ekonomik
1. hücresi (%100 koruma alanı, Karacabey Longozu çevresi) ve Karaburun'un düşük güvenli hücresi (uygun alan yetersiz) elenir.

| Sıra | Ekonomik (dışlama sonrası) | Dengeli profil (P(ilk 10)) | Risk/çevre profili |
|---|---|---|---|
| 1 | Soma 50,4 | Çerkezköy 50,8 (%100) | Bergama 60,1 |
| 2 | Çerkezköy 50,8 | Çeşme 52,1 (%90) | Çeşme 52,1 |
| 3 | Belen 51,7 | Karacabey 55,5 (%99) | Çerkezköy 50,8 |
| 4 | Çeşme 52,1 | Karacabey 55,8 (%87) | Gönen 62,9 |
| 5 | Bergama 52,2 | Silivri 56,2 (%91) | Büyükçekmece 59,7 |
| 6 | Ezine 52,5 | Karesi 57,6 (%91) | Marmaraereğlisi 65,3 |
| 7 | Urla 53,8 | Büyükçekmece 59,7 (%77) | Ergene 65,1 |
| 8 | Soma 53,8 | Bergama 60,1 (%66) | Uzunköprü 63,3 |
| 9 | Urla 54,0 | Akhisar 57,1 (%54) | Karacabey 55,5 |
| 10 | Bayramiç 54,2 | Saray 60,3 (%46) | Karacabey 55,8 |

- **Belen:** ekonomik 3. → ekonomi profili 27. → dengeli 82. → risk/çevre 1.241. (göç riski 2: Amanos–Belen
  geçidi). Ekonomik sıralamanın en iyi sahalarından biri, çevresel tartıda en kötülerden.
- **Dayanıklılık:** ilk 6 sıra (Çerkezköy, Karacabey, Karesi, Silivri, Çeşme) ağırlık örneklerinin ≥ %87'sinde ilk 10'da;
  8–10. sıralar %45–65: ilk 10'un son üçü ağırlık seçimine bağlı.

**Doğrulama (171 santralli hücre / 1.464):**

| Puan | AUC |
|---|---|
| Rüzgâr KF (tek kriter) | 0,80 |
| Başabaş fiyat | 0,79 |
| Lojistik maliyeti | 0,79 |
| Trafo uzaklığı | 0,76 |
| Güven (döngüsel) | 0,73 |
| Yol, eğim, göç | 0,54 / 0,49 / 0,46 |
| Ekonomi öncelikli profil | **0,87** |
| Dengeli profil | 0,84 |
| Risk/çevre profili | 0,71 |
| Açığa çıkan tercih (güven hariç) | **0,88** |

**Gerçek dünya tercihleri** (güven hariç, AUC 0,876): ekonomi %33, **şebekeye yakınlık %34**, lojistik %18, yol %8,
eğim %5, **göç %2**. Yorum: Türkiye'deki geliştiriciler trafo merkezine yakınlığa rüzgâr kadar önem vermiş, kuş göçünü
neredeyse hiç tartmamış (göçün tek başına AUC'si 0,46 < 0,5: santraller göç koridorlarında rastgeleden biraz *fazla*).
Eğimin AUC'si 0,49: santraller rüzgârlı sırtlarda, düz arazi tercihi yok. Bu ağırlıklar normatif değil betimseldir.

### 7.5 Üç sahada tam analiz: Faz E öncesi / sonrası (2 çekirdek, soğuk önbellek; `outputs/v3E/E6_once_sonra.csv`)

| Saha | Kip | RES MW | Türbin | CAPEX (M$) | Bağlantı (M$) | Lojistik ($/MW) | Uygun alan | E[NPV] (M$) | P(NPV>0) | Başabaş | Karar | Süre (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ezine | öncesi | 33,6 | 8 | 55,1 | 6,0 (sabit) | ort. | – | −1,95 | %40 | 60,3 | rafa kaldır | 54 |
| Ezine | sonrası | 25,2 | 6 | 44,6 | 5,6 | 38.755 | %46 | **−1,63** | %39 | 60,5 | rafa kaldır | 46 |
| Gürün | öncesi | 37,8 | 9 | 60,1 | 6,0 (sabit) | ort. | – | −2,91 | %38 | 61,1 | rafa kaldır | 66 |
| Gürün | sonrası | 29,4 | 7 | 55,1 | 10,3 | 68.943 | %89 | **−6,98** | %25 | 67,4 | rafa kaldır | 55 |
| Susurluk | öncesi | 42,0 | 10 | 65,0 | 6,0 (sabit) | ort. | – | −1,37 | %43 | 59,3 | rafa kaldır | 72 |
| Susurluk | sonrası | 42,0 | 10 | 66,0 | 7,4 | 32.624 | %44 | **−3,34** | %37 | 61,3 | rafa kaldır | 70 |

- **Ezine iyileşti** (+0,3 M$): TEİAŞ Ezine TM 1,6 km'de (5,6 M$ < 6,0) ve lojistik referansın altında. CBS dışlamaları
  yerleşim alanının yarısını kapattı (yerleşim ve yol tamponları) ama MILP zaten küçük bir santral (6 türbin) seçiyor.
- **Gürün kötüleşti** (−4,1 M$): bağlantı 10,3 M$ (Kangal TM 17,5 km), lojistik referansın 26 bin $/MW üstünde; başabaş
  61 → 67 $/MWh. Hızlı taramadaki "en iyi ilk 10" sahalarından biri gerçek altyapıyla listeden düşüyor.
- **Susurluk kötüleşti** (−2,0 M$): bağlantı +1,4 M$; ayrıca dışlamalar (uygun alan %44) türbinleri daha az rüzgârlı
  konumlara itiyor (konum kazancı 1,011 → 0,990, KF %36,0 → %35,1).
- Karar hiçbir sahada değişmedi: rafa kaldır.

### 7.6 Süreler (2 çekirdek benzetimi)

| Ölçüm | Faz E öncesi | Faz E sonrası |
|---|---|---|
| Tam analiz (3 saha) | 54–72 s | 46–70 s |
| Hızlı tarama, soğuk / sıcak profil | 2,9–3,8 / 2,5–3,3 s (Faz D) | 3,4–5,0 / 2,9–4,6 s |
| Uygulama açılışı, soğuk / sıcak (tarayıcı, masaüstü) | 2,2 / 0,5 s (v2 C8) | 2,7 / 0,6 s |
| Dört altyapı katmanını açma | – | 5,0 s (yalnız seçilince yüklenir) |
| Çok kriterli sayfa (300 örnekli dayanıklılık dahil) | – | 0,8–1,1 s |

Tam analiz kısaldı, çünkü dışlamalar aday nokta sayısını azaltıyor (Ezine 208 → 96). Hızlı tarama ~0,5 s uzadı (bağlantı
+ lojistik + 2 km alan özeti). Açılış, katmanlar isteğe bağlı olduğu için değişmedi. Ekran görüntüleri `docs/img/v3/E_*`
(açık/koyu, masaüstü/mobil); 16 ekranın hiçbirinde yatay taşma yok (`outputs/v3E/E6_tasma.csv`).

## 8. Sınırlamalar

1. **TEİAŞ bağlantı kapasitesi** lisanslı RES için yayımlanmıyor (ana sınırlama, §7.1). Atanacak trafonun belirsizliği Faz F
   ön adımında (Ö2) Monte Carlo'ya eklendi; kapasite tahsis katkı payı, EİH yenilemeleri ve kamulaştırma dahil değil.
2. **OSM eksikleri:** trafo merkezlerinin %45'inde gerilim etiketi yok (bu merkezler hedef olamaz → uzaklık fazla
   tahmin edilebilir); koruma alanları resmî listeden eksik olabilir (WDPA kullanılamadı).
3. **Göç koridorları yaklaşık:** altı koridor yayınlardan elle sayısallaştırıldı; ÇED kuş izlemesinin yerini tutmaz.
4. **Tamponlar** (yerleşim 500 m, havalimanı 5 km, eğim 15°) TAHMİN; karayolu kuralı ikincil kaynaktan.
5. **Lojistik:** sefer sayıları, kütleler, sabit giderler ve teslim süreleri TAHMİN; köprü/tünel/viraj yarıçapı kısıtları
   ağda yok (yalnız yol sınıfı ve eğim). Yerli fabrika kapasiteleri tek saha için bağlayıcı değil.
6. **Çok kriterli doğrulama betimseldir:** mevcut santraller seçilmiş yerlerdir, en iyi yerler değil; güven ve başabaş
   kriterleri santrallerden kalibre edildiği için AUC iyimser.
