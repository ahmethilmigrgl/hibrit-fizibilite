# Yatırım Komitesi Memosu — Ezine RES + Batarya Projesi Edinimi

**Kime:** Yatırım Komitesi · **Hazırlayan:** Ahmet Hilmi Görgülü · **Tarih:** Ekim 2026 · **Gizlilik:** Kurum içi
**Para birimi:** reel 2026 USD, %7 reel WACC · **Kaynak:** proje modeli (`config.yaml → nihai_baz_vaka`), Excel finansal model

---

## 1. Talep edilen karar

Komiteden, inşaata hazır bir Ezine RES + batarya projesinin edinimini **rafa kaldırmayı** ve §8'deki **izleme
tetikleyicilerini** onaylamasını talep ediyoruz. **Durum tespiti bütçesi ve teklif yetkisi talep etmiyoruz.**

Gerekçe: Fiyat varsayımı tutarlı hale getirildiğinde (beklenen fiyat 58 $/MWh) baz vakada beklenen NPV **−1,7 M$**,
kâr olasılığı **%42**, azami edinim primi **0**. Durum tespitiyle çözülebilecek kalemlerin hiçbiri, olumlu sonuçlansa bile
kararı değiştirmiyor. Bir tetikleyici gerçekleşirse proje yeniden komiteye getirilecek. En yakın tetikleyici YEKDEM USD
koridorunun endeksli olduğunun hukuken teyidi: bu durumda beklenen NPV +0,4 M$ olur.

## 2. Proje özeti

| Konu | Ayrıntı |
|---|---|
| Saha | Çanakkale-Ezine (dört aday saha arasında en güçlü rüzgâr kaynağı; kalibre kapasite faktörü %37,7) |
| Tasarım | RES 58,8 MW (14 × 4,2 MW) + batarya 30 MW / 60 MWh; 50 MW şebeke bağlantısı. GES hiçbir optimizasyonda girmedi. |
| CAPEX | 82,9 M$ (RES 67,6 · batarya 9,3 · şebeke 6,0) |
| Gelir yapısı | Her yıl 30 Kasım'da YEKDEM'e katılım kararı (10 yıllık hak, nominal USD koridoru 4,95–6,05 ¢/kWh); katılınmayan yıllarda tüccar satış; batarya SFK kapasite geliri, dengesizlik azaltımı |
| COD | Kasım 2029 (P50), Mart 2030 (P80) — inşaata hazır proje varsayımıyla; geliştirme aşamasından başlansa Mayıs 2032 |
| Önlenen emisyon | ~113 bin t CO2/yıl (ETKB 2024 faktörü) |

## 3. Değerlendirme: neden şimdi değil

- **Tasarım doğru, değer yetersiz.** Güneş kanibalizasyon nedeniyle eleniyor. Rüzgâr ortalama fiyatın üstünde
  yakalıyor. Batarya SFK geliriyle değer katıyor. Buna rağmen 58 $/MWh beklenen fiyatta proje %7 reel getiriyi
  karşılamıyor.
- **Önceki olumlu sonuç bir model tutarsızlığından geliyordu.** Monte Carlo'da 58 $/MWh, log-fiyat sürecinin
  *medyanı* olarak ayarlanmıştı. Lognormal dağılımda ortalama medyanın üstünde kalır; simüle edilen ortalama fiyat
  (iskonto ağırlıklı) 61,8 $/MWh çıkıyordu. Beklenen fiyat 58'e sabitlenince baz vaka +1,5'ten −1,7 M$'a indi.
- **YEKDEM opsiyonu değerli ama yetmiyor.** Her yıl seçilebilen YEKDEM hakkının saf tüccara göre değeri +0,5 M$;
  koridor endeksliyse +2,5 M$.
- **Değerin büyük kısmı durum tespitiyle çözülemeyen belirsizliklerde.** Tüm belirsizliğin bilgi değeri (EVPI) 5,3 M$.
  Bunun büyük kısmı fiyat seviyesi ve SFK piyasasının doyum hızından geliyor (doyum senaryosunun bilgi değeri 2,0 M$).
  Bunlar durum tespitiyle değil, zamanla piyasada gözlenir.

## 4. Ana finansal metrikler

**Baz vaka ve senaryolar** (Monte Carlo, 10.000 simülasyon; doyum, sistem kesintisi, ortak batarya sürücüsü dahil; COD Kasım 2029):

| Senaryo | Beklenen NPV | P(NPV>0) | CVaR %5 | NPV P10 / P90 | Azami edinim primi |
|---|---|---|---|---|---|
| **YEKDEM yıllık opsiyonu (nominal) + tüccar — baz vaka** | **−1,66 M$** | **%42** | **−28,0 M$** | −20,3 / +18,5 | **0** |
| YEKDEM yıllık opsiyonu (endeksli) + tüccar | +0,43 M$ | %46 | −22,2 M$ | −15,6 / +19,0 | 0,43 M$ |
| Saf tüccar | −2,11 M$ | %42 | −30,4 M$ | −21,4 / +18,6 | 0 |
| PPA (%70 P90, 12 yıl) | −6,05 M$ | %28 | −26,0 M$ | −19,7 / +9,3 | 0 |
| YEKDEM 10 yıl sabit (nominal) | −12,25 M$ | %12 | −29,7 M$ | −24,0 / +1,6 | 0 |

Önceki memo (fiyat tutarsızlığı düzeltilmeden): baz vaka +1,49 M$, P(NPV>0) %50, CVaR %5 −25,8 M$, azami prim 1,49 M$.

**Deterministik Excel modeli** (baz vaka gelir yapısı, P50, teşvik belgesi var). Excel ile Python modeli 48 senaryonun
tamamında birebir mutabık.

| Fiyat seviyesi | NPV | Proje IRR | Öz kaynak IRR | Asgari DSCR | LCOE |
|---|---|---|---|---|---|
| Düşük (45 $/MWh) | −20,5 M$ | %3,3 | %2,5 | 1,17 | 65,7 $/MWh |
| **Baz (58 $/MWh)** | **−2,4 M$** | **%6,6** | **%7,9** | **1,26** | **67,5 $/MWh** |
| Yüksek (72 $/MWh) | +16,6 M$ | %9,6 | %17,3 | 1,51 | 68,3 $/MWh |

**Deterministik baz (−2,37) → Monte Carlo (−1,66) köprüsü** (bileşenler sırayla stokastik yapıldı, aynı rastgele sayılar):

| Adım | Etki [M$] |
|---|---|
| Fiyat ortalaması sapması (kriz yıllarında fiyat ×1,6; kriz hariç ortalama tam 58) | +2,04 |
| Kriz yıllarında düzenleyici tavan (kriz fiyatı yenilenebilire yansımıyor) | −2,04 |
| Fiyat oynaklığı: vergi, zarar mahsubu vb. (batarya geliri fiyata doğrusal: 0) | −0,86 |
| YEKDEM yıllık opsiyonu (dışbükeylik) | +0,42 |
| SFK doyum senaryoları (yavaş doyumun yukarı potansiyeli; baz yol, karışımın ortalamasının altında) | +2,71 |
| Hava, model hatası, kanibalizasyon, kesinti | −0,87 |
| CAPEX / OPEX / bozunma belirsizliği (CAPEX dağılımı yukarı çarpık) | −0,90 |
| Takvim: COD 2030 → Kasım 2029 | +0,22 |

Teşvik belgesi olmazsa her senaryoda NPV ~5,8–6,3 M$ daha düşük (KDV ön finansmanı ve TL aşınması).

## 5. Temel riskler

| Risk (puan) | Etki | Not |
|---|---|---|
| Elektrik fiyat seviyesi (20) | NPV varyansının yarısından fazlası | Başabaş beklenen fiyat ≈ 59 $/MWh: baz varsayımın yalnız ~%2 üstü |
| SFK piyasasının doyumu (16) | 28–33 GW depolama boru hattı ~1 GW ihtiyacı doyurur | Yavaş doyum değeri pozitife çevirir; gözlenebilir |
| Takvim / COD (16 / 12) | 2030 sonrası COD → YEKDEM hakkı yok | Yalnız inşaata hazır projeler değerlendirilmeli |
| Sistem kaynaklı kesinti (12) | 2026'da Ezine RES'lerinde ~%9,5 | 2027 verisiyle izlenmeli |
| Ornitoloji (12) | Boğaz göç yolu: işletmede seçici durdurma | Yeniden değerlendirmede durum tespiti kalemi |

Ayrıntı: 20 maddelik risk kaydı (`outputs/07/risk_kaydi.xlsx`).

## 6. Takvim

YEKDEM hakkı için COD'un 31.12.2030'dan önce olması gerekiyor. İnşaata hazır bir projede COD P50 Kasım 2029, P90 Mayıs
2030. Yani karar penceresi dar: bir tetikleyici **2027 ortasından** sonra gerçekleşirse YEKDEM'e erişim riski artar ve
proje tüccar değerine (−2,1 M$) yaklaşır.

## 7. Yeniden değerlendirme koşulları ve durum tespiti kapsamı

Bir tetikleyici gerçekleşirse önceki memodaki durum tespiti kapsamı geçerli olur: TEİAŞ SFK ön yeterliliği, yatırım
teşvik belgesi, ornitoloji, YEKDEM endeksleme hukuki görüşü, COD / türbin slotu. Bugün bu kalemlerin bilgi değeri sıfır,
çünkü olumlu sonuç bile beklenen NPV'yi pozitife çevirmiyor (ör. teşvik belgesi riskinin çözülmesi −1,7 → −1,1 M$). Tek
istisna YEKDEM endekslemesi: teyit edilirse karar değişir. Hukuki görüş kurum içi hukuk ekibiyle, bütçesiz olarak
istenebilir.

## 8. İzleme tetikleyicileri

| Gösterge | Eşik | Karar |
|---|---|---|
| YEKDEM koridoru endekslemesi (hukuki görüş / mevzuat) | Endeksli olduğu teyit edilir | Komiteye dön: E[NPV] +0,4 M$, azami prim ~0,4 M$ |
| Uzun vadeli fiyat beklentisi / PPA teklifleri | Beklenen fiyat ≳ 60 $/MWh | Yeniden değerlendir |
| Türbin + EPC fiyatı | Baz CAPEX'in ≳ %2 altında | Yeniden değerlendir |
| Satıcının talep ettiği prim | Sıfır ya da negatif (maliyetine devir) | Yalnız diğer bir tetikleyiciyle birlikte yeniden değerlendir |
| Türkiye'de işletmedeki depolama, SFK fiyatı | 2027'de < ~1 GW ve SFK fiyatı 2026 seviyesinde | Yavaş doyum: yeniden değerlendir |
| RES'lere sistem kesintisi | 2027'de < %5 | Yeniden değerlendir |
| COD penceresi | 2027 ortasından sonra | YEKDEM'siz değer (−2,1 M$) esas alınır |

## 9. Öneri

İnşaata hazır Ezine RES + batarya projesinin edinimini **rafa kaldırmayı** ve §8'deki tetikleyicilerin üç ayda bir
izlenmesini öneriyoruz.

Önceki memodaki olumlu değer (+1,5 M$), fiyat sürecindeki bir tutarsızlıktan geliyordu: Monte Carlo ortalama fiyatı
baz varsayımın ~4 $/MWh üstündeydi. Düzeltilmiş baz vaka −1,7 M$, kâr olasılığı %42. Fark ince (başabaş beklenen fiyat
≈ 59 $/MWh), bu yüzden proje kalıcı olarak reddedilmiyor. Fiyat, SFK doyumu ve YEKDEM endekslemesi gibi gözlenebilir
göstergelerden biri lehte dönerse yeniden değerlendirilecek. **Geliştirme aşamasındaki (ön lisans devri) projelere hiçbir
koşulda teklif önermiyoruz:** COD 2032'ye kayıyor ve YEKDEM hakkı kayboluyor.
