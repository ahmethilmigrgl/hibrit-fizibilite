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
