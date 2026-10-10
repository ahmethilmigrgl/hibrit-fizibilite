# v1 düzeltme notu — sigorta ve arazi kirası çift sayımı (Ekim 2026)

Bu not v1.0.0 vaka çalışmasında (Çanakkale-Ezine) sonradan bulunan bir hatayı ve sayısal etkisini belgeler. v1.0.0
etiketi, v1 belgeleri (docs/00–07, RAPOR, memo, sunum) ve `outputs/07` içindeki v1 sonuçları **değiştirilmedi**; yalnızca
bu nota bağlantı veren kısa bir "Düzeltme notu" kutusu eklendi. Düzeltilmiş senaryo ayrı klasörde üretildi
(`outputs/07/v1_cift_sayim/`), Excel modelinde seçilebilir.

## 1. Ne bulundu

v1'in RES işletme gideri **35.000 $/MW-yıl** idi. Kaynağı Lazard LCOE+ 2025'in kara RES "Fixed O&M" bandıdır
(24,5–40 $/kW-yıl). Lazard kalem kırılımı vermez. ABD pratiğinde bu, arazi kirası, emlak vergisi ve sigortayı da içeren
**her şey dahil** işletme gideridir. LBNL'nin (Wiser vd. 2019) her şey dahil örnekleri 33–59 $/kW-yıl'dır; kırılımlarda
sigorta ~2,6, arazi kirası 4,2–5,0 $/kW-yıl'dır.

v1 finansal modeli (`src/finans/model.py`, `src/risk/degerleme.py`) bu 35.000'e **ayrıca** şunları ekliyordu:

| Kalem | Formül | Baz vaka (58,8 MW RES) |
|---|---|---|
| RES arazi kirası | 1.500 $/MW-yıl × 58,8 MW | 88.200 $/yıl |
| RES sigortası | %0,35 × RES CAPEX (1,15 M$/MW × 58,8 MW) | 236.670 $/yıl |
| **Toplam çift sayım** | | **324.870 $/yıl** (≈ 5,5 $/kW-yıl) |

Toplam RES işletme gideri bu yüzden 40,5 $/kW-yıl'a çıkıyordu. Bu değer Lazard bandının üstünde ve Türkiye için
(daha ucuz işçilik) yüksek.

**Düzeltme kapsamı:** yalnız RES'in arazi kirası ve RES CAPEX'i üzerindeki sigorta düşülür. Batarya, şebeke ve GES
sigortası kalır: batarya O&M'i CAPEX oranı (%2,5) olarak ayrı kaynaktan geliyor ve sigorta içermiyor. TEİAŞ bedelleri
ve söküm zaten O&M dışında. Bu bir yorum kararıdır: Lazard'ın sigortayı ve araziyi gerçekten içerip içermediği raporda
yazmaz. "Muhtemelen içerir" değerlendirmesi ABD pratiğine ve LBNL kırılımlarına dayanır. Bu yüzden iki varyant
§3'te ayrıca verildi.

## 2. Nasıl bulundu

v3 Faz D'de türbin bakımı aşağıdan yukarı (ayrık olay simülasyonu) modellendiğinde O&M 25,5 bin $/MW-yıl çıktı. Bu
v1'in 35 binine göre %27 düşüktü. Farkı açıklamak için v3 ön adım Ö1'de (docs/v3_E_cbs_cok_kriterli_lojistik.md
§0.1) bir **O&M kapsam mutabakatı** yapıldı: Lazard, LBNL ve Deutsche WindGuard kırılımları kalem kalem karşılaştırıldı.
Mutabakat tablosunun son iki satırı (sigorta, arazi) v1'de hem "35 içinde" hem "finansta ayrı" olarak işaretlendi.
v3'ün varsayılan işletme modeli (FSA 20 + sahip kalemleri 14 = 34 $/kW-yıl) aşağıdan yukarı kurulduğu için bu iki
kalemi içermez; v3'te ayrı saymak doğrudur.

## 3. Sayısal etki (v1 nihai baz vaka)

Yöntem: Aşama 7 Monte Carlo'su (`src/07_gelir_yapilari.py`, aynı tohum, 10.000 senaryo) düzeltme açıkken
(`V1_CIFT_SAYIM=1`) ayrı klasöre yeniden koşturuldu. Baz vaka metrikleri ve durum tespiti bilgi değeri
`src/07_baz_vaka.py`'nin kendi fonksiyonlarıyla hesaplandı (`src/v3_O1_v1_duzeltme.py` → `outputs/v3F/O1_v1_duzeltme.csv`).

**Baz vaka: YEKDEM yıllık opsiyonu (nominal) + tüccar, inşaata hazır, COD Kasım 2029**

| Metrik | v1 (çift sayımlı) | Düzeltilmiş | Fark |
|---|---|---|---|
| Beklenen NPV | **−1,66 M$** | **+0,92 M$** | +2,58 |
| P(NPV > 0) | %42,4 | %48,7 | +6,3 puan |
| CVaR %5 | −28,0 M$ | −25,1 M$ | +2,9 |
| NPV P10 / P90 | −20,3 / 18,5 | −17,5 / 21,0 | |
| Azami edinim primi | 0 | **0,92 M$** | |
| Durum tespiti kalemlerinin bilgi değeri (EVPPI toplamı) | 0 | **1,16 M$** | |

Deterministik kontrol: yıllık 324.870 $'ın bugünkü değeri vergi kalkanı sonrası 2,64 M$ (COD 2028). Monte Carlo
farkı 2,58 M$ (COD Kasım 2029; bazı senaryolarda zarar mahsubu vergi kalkanını erteliyor). Tutarlı.

**Diğer gelir yapıları (aynı Monte Carlo):**

| Gelir yapısı | v1 E[NPV] | Düzeltilmiş E[NPV] | Düzeltilmiş P(NPV>0) |
|---|---|---|---|
| YEKDEM yıllık opsiyonu (endeksli) + tüccar | +0,43 | +2,99 | %53,5 |
| Tüccar | −2,11 | +0,47 | %48,1 |
| PPA (%70 P90, 12 yıl) | −6,05 | −3,41 | %35,3 |
| YEKDEM 10 yıl sabit (nominal) | −12,25 | −9,55 | %16,3 |

**Kısmi düzeltme varyantları** (doğrusal, deterministik bugünkü değerle ölçeklenerek):
- Yalnız sigorta çift sayılmış olsaydı: E[NPV] ≈ −1,66 + 1,88 = **+0,22 M$**.
- Yalnız arazi çift sayılmış olsaydı: ≈ −1,66 + 0,70 = **−0,96 M$**.

Kararı değiştiren kalem sigortadır.

## 4. Memo kararı değişiyor mu?

Karar kuralı (docs/07, Güncelleme 3): baz vakada E[NPV] > 0 ve azami prim > 0 ise **(a) durum tespiti + sınırlı teklif**,
aksi halde **(b) rafa kaldır, tetikleyicileri izle**.

- v1: E[NPV] −1,66 → (b).
- **Düzeltilmiş: E[NPV] +0,92 > 0, azami prim 0,92 M$ → (a).** Karar değişiyor.

Düzeltilmiş durumda (a)'nın içeriği:
- **Durum tespiti bütçesi:** bilgi değeri 1,16 M$. Kalemler: TEİAŞ SFK kabulü 0,56, teşvik belgesi 0,43, ornitoloji
  0,18 M$. Bu, tipik maliyetin (0,35–0,6 M$) üstünde; dar kapsamlı (~0,5 M$) durum tespiti savunulabilir.
- **Bağlayıcı olmayan teklif:** edinim primi ≤ 0,9 M$ (Güncelleme 2'deki ≤ 1,5 M$'ın yerine).

**Değer yine çok ince:** P(NPV>0) %49, CVaR %5 −25 M$. Kararın işareti tek bir kapsam yorumuna (Lazard'ın sigortayı
içerip içermediği) bağlı. Gerçek bir edinimde ilk iş, O&M sözleşme teklifinin kapsamını (FSA + sahip kalemleri +
sigorta poliçesi) satıcıdan almak olur. Bu belirsizlik durum tespitinin kendi kalemidir.

Karar yolculuğuna bir adım eklendi: "Düzeltme (v3 Ö1): sigorta + arazi çift sayımı kaldırıldı → +0,9 M$ → durum tespiti
+ ≤0,9 M$ teklif". Grafik `outputs/08/grafikler/karar_yolculugu.png`, tablo `results/karar_yolculugu.csv` ve CHANGELOG.
Sunum PDF'i ve LinkedIn karuseli yeniden üretilmedi (v1 teslim edilmiş haliyle kalır).

## 5. Excel modeli

`outputs/08/Ezine_Hibrit_Finansal_Model.xlsx` → Girdiler sayfasında yeni seçim "Sigorta + arazi çift sayımı":
"v1 (çift sayımlı)" (varsayılan) / "Düzeltilmiş". OPEX sayfasında RES arazi ve sigorta formülleri bu seçime bağlı.
Senaryolar 48'den 96'ya çıktı (48 × v1/düzeltilmiş). Her biri LibreOffice'te yeniden hesaplanıp Python
(`degerleme.nakit_akislari`) ile karşılaştırıldı; sonuç `outputs/08/excel_mutabakat.csv`. Ozet sayfasında düzeltilmiş
Monte Carlo referansı ayrıca verilir.

## 6. v2 ve v3 motorlarında aynı sorun var mı?

- **v2 (dal `v2-genel`): evet.** v2 motoru RES O&M'ini config'teki 35.000'den alır, `Varsayimlar` üzerinden sigorta ve
  arazi kirasını ayrıca ekler: aynı çift sayım tüm sahalarda geçerli. v2 kipinde (v3 kodunda `yerlesim_bakim=False`)
  üç sahada ölçüldü (`src/v3_O1_v2_kontrol.py` → `outputs/v3F/O1_v2_kontrol.csv`):

  | Saha | v2 E[NPV] | Düzeltilmiş | Fark | Başabaş ($/MWh) | Karar |
  |---|---|---|---|---|---|
  | Ezine | −6,30 | −3,68 | +2,62 | 62,6 → 60,7 | rafa kaldır (değişmedi) |
  | Gürün | −5,71 | −3,28 | +2,43 | 62,4 → 60,5 | rafa kaldır (değişmedi) |
  | Susurluk | −5,04 | −2,43 | +2,61 | 61,6 → 59,8 | rafa kaldır (değişmedi) |

  Türkiye ön tarama haritasında başabaş fiyat yaklaşık 2 $/MWh yüksekti (RES ağırlıklı hücrelerde). v2 dalı değiştirilmez.
- **v3 varsayılanı (FSA işletme modeli): hayır.** O&M = FSA 20 + sahip kalemleri 14 $/kW-yıl. Kapsam tablosunda
  sigorta ve arazi açıkça dışarıda; finansta ayrı sayılmaları doğru.
- **v3'teki v2 uyumlu kipler** (`yerlesim_bakim=False`, `bakim_modeli="sabit"`) v2 davranışını aynen verdiği için çift
  sayımı içerir. Bu kipler yalnız karşılaştırma içindir. İstenirse `V1_CIFT_SAYIM=1` ya da config `v1_duzeltme.cift_sayim:
  true` ile düzeltilmiş çalışırlar.

## 7. Ders

Bir "her şey dahil" piyasa rakamı başka bir aşağıdan yukarı modelin kalemleriyle birleştirildiğinde kapsamın kalem
kalem yazılması gerekir. Bu hata, modelin bir parçasını (bakım) bağımsız olarak yeniden kurup sonucu eski varsayımla
mutabık hale getirmeye çalışırken ortaya çıktı.
