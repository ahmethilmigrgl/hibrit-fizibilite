# Yatırım Komitesi Memosu — Ezine RES + Batarya Projesi Edinimi

**Kime:** Yatırım Komitesi · **Hazırlayan:** Ahmet Hilmi Görgülü · **Tarih:** Ekim 2026 · **Gizlilik:** Kurum içi
**Para birimi:** reel 2026 USD, %7 reel WACC · **Kaynak:** proje modeli (`config.yaml → nihai_baz_vaka`), Excel finansal model

---

## 1. Talep edilen karar

Komiteden iki onay talep ediyoruz:

1. **Durum tespiti bütçesi:** inşaata hazır bir Ezine RES projesinin (≈50 MW bağlantı) edinimine yönelik **0,5 M$**'lık
   dar kapsamlı durum tespiti (due diligence) bütçesi.
2. **Teklif yetkisi:** edinim primi **en fazla 1,5 M$** ile sınırlı, **bağlayıcı olmayan teklif** verme yetkisi.

**Bu bir yatırım (FID) kararı değildir.** FID, durum tespitinin §7'deki koşulları karşılaması halinde ayrıca komiteye
getirilecektir. YEKDEM koridorunun endeksli olduğu hukuken teyit edilirse prim tavanı 3,1 M$'a çıkabilir; bu artış için
komiteye yeniden başvurulacaktır.

## 2. Proje özeti

| Konu | Ayrıntı |
|---|---|
| Saha | Çanakkale-Ezine (dört aday saha arasında en güçlü rüzgâr kaynağı; kalibre kapasite faktörü %37,7) |
| Tasarım | RES 58,8 MW (14 × 4,2 MW) + batarya 30 MW / 60 MWh; 50 MW şebeke bağlantısı. GES hiçbir optimizasyonda girmedi. |
| CAPEX | 82,9 M$ (RES 67,6 · batarya 9,3 · şebeke 6,0) |
| Gelir yapısı | Her yıl 30 Kasım'da YEKDEM'e katılım kararı (10 yıllık hak, nominal USD koridoru 4,95–6,05 ¢/kWh); katılınmayan yıllarda tüccar satış; batarya SFK (sekonder frekans) kapasite geliri, dengesizlik azaltımı |
| COD | Kasım 2029 (P50), Mart 2030 (P80) — inşaata hazır proje varsayımıyla; geliştirme aşamasından başlansa Mayıs 2032 |
| Önlenen emisyon | ~113 bin t CO2/yıl (ETKB 2024 faktörü), ~62 bin hanenin tüketimi |

## 3. Yatırım gerekçesi

- **Rüzgâr değeri koruyor.** Güneşin aksine rüzgâr, ortalama fiyatın üstünde yakalıyor (tüccar modda toplam yakalama
  oranı ~1,13). Kanibalizasyon riskine daha az açık.
- **Batarya ucuz bir opsiyon.** 30 MW, SFK'ya ikili katılım eşiği; 2 saatlik enerji tam 30 MW rezerv sağlıyor. SFK
  piyasası doyarsa yalnız RES'e göre kayıp küçük, yavaş doyumda kazanç büyük; her gelir yapısında değer katıyor.
- **YEKDEM bir taban sigortası.** YEK Yönetmeliği'ne göre katılım her yıl ayrı kararla (md. 4/2, 5/1). Fiyatlar düştüğünde
  YEKDEM'e sığınma hakkı var. Bu hakkın saf tüccara göre değeri +0,3 M$; koridor endeksliyse +2,0 M$.
- **Değer ince ve asimetrik.** Sabit 58 $/MWh baz fiyatta deterministik NPV −2,4 M$ (Excel modeli). Beklenen değerin
  pozitif olması belirsizliğin asimetrisinden geliyor: yukarı yönde fiyat ve SFK potansiyeli, aşağı yönde YEKDEM tabanı.
  Bu yüzden önerimiz sınırlı bir primle teklif, kesin taahhüt değil.

## 4. Ana finansal metrikler

**Baz vaka ve senaryolar** (Monte Carlo, 10.000 simülasyon; doyum, sistem kesintisi, ortak batarya sürücüsü dahil; COD Kasım 2029):

| Senaryo | Beklenen NPV | P(NPV>0) | CVaR %5 | NPV P10 / P90 | Azami edinim primi |
|---|---|---|---|---|---|
| **YEKDEM yıllık opsiyonu (nominal) + tüccar — baz vaka** | **+1,49 M$** | **%50** | **−25,8 M$** | −17,8 / +22,3 | **1,49 M$** |
| YEKDEM yıllık opsiyonu (endeksli) + tüccar | +3,13 M$ | %54 | −20,5 M$ | −13,7 / +22,5 | 3,13 M$ |
| Saf tüccar | +1,15 M$ | %50 | −27,8 M$ | −18,7 / +22,3 | 1,15 M$ |
| PPA (%70 P90, 12 yıl) | −3,98 M$ | %34 | −24,4 M$ | −18,0 / +11,7 | 0 |
| YEKDEM 10 yıl sabit (nominal) | −10,92 M$ | %14 | −28,6 M$ | −22,8 / +3,1 | 0 |

**Deterministik Excel modeli** (baz vaka gelir yapısı, P50, teşvik belgesi var). Excel ile Python modeli 48 senaryonun
tamamında birebir mutabık.

| Fiyat seviyesi | NPV | Proje IRR | Öz kaynak IRR | Asgari DSCR | LCOE |
|---|---|---|---|---|---|
| Düşük (45 $/MWh) | −20,5 M$ | %3,3 | %2,5 | 1,17 | 65,7 $/MWh |
| **Baz (58 $/MWh)** | **−2,4 M$** | **%6,6** | **%7,9** | **1,26** | **67,5 $/MWh** |
| Yüksek (72 $/MWh) | +16,6 M$ | %9,6 | %17,3 | 1,51 | 68,3 $/MWh |

Düşük fiyatta YEKDEM katılımı devreye girer (saf tüccar −21,8 M$; endeksli koridorda −12,9 M$). Sabit fiyatlı
deterministik vakada baz ile Monte Carlo beklenen değeri arasındaki fark (−2,4 → +1,5 M$) bu asimetriden gelir: fiyat
yükseldiğinde kazanç açık uçlu, düştüğünde YEKDEM tabanı kaybı sınırlıyor. Teşvik belgesi olmazsa her senaryoda NPV
~5,8–6,3 M$ düşer (KDV ön finansmanı ve TL aşınması).

## 5. Temel riskler ve azaltımlar

| Risk (puan) | Etki | Azaltım |
|---|---|---|
| Elektrik fiyat seviyesi (20) | NPV varyansının yarısından fazlası | YEKDEM tabanı; muhafazakâr borç |
| SFK piyasasının doyumu (16) | 28–33 GW depolama boru hattı ~1 GW ihtiyacı doyurur | 30 MW batarya; kararı FID'de gözlenen doyumla ver |
| Takvim / COD (16 / 12) | 2030 sonrası COD → YEKDEM hakkı yok | İnşaata hazır proje; türbin slot rezervasyonu; gecikme cezalı EPC |
| Sistem kaynaklı kesinti (12) | 2026'da Ezine RES'lerinde ~%9,5; −2 M$ mertebesi | DGP teklif stratejisi, batarya, sözleşmede kesinti maddesi |
| Ornitoloji (12) | Boğaz göç yolu: işletmede seçici durdurma | Temel çalışma, radar destekli durdurma, mikro-yerleşim |
| Teşvik belgesi (6) | Yoksa −5,8 M$ | FID öncesi belge (CK 9903) |

Ayrıntı: 20 maddelik risk kaydı (`outputs/07/risk_kaydi.xlsx`).

## 6. Takvim

| Kilometre taşı | Tarih (P50) |
|---|---|
| Bağlayıcı olmayan teklif, durum tespiti başlangıcı | Kasım 2026 |
| Durum tespiti tamamlanır, bağlayıcı teklif / FID kararı | 1. çeyrek 2027 |
| Proje devri (EPDK onayı) | ~Mart 2027 |
| Finansman kapanışı (FID) | ~Temmuz 2027 |
| Türbin teslimi, montaj | 2028–2029 |
| **COD** | **Kasım 2029** (P80 Mart 2030, P90 Mayıs 2030) |

Kritik yol: devir → finansman → türbin tedariki (12–30 ay) → montaj → devreye alma. YEKDEM için COD'un 31.12.2030'dan önce
olması gerekiyor; P90 bile bu tarihten önce.

## 7. FID koşulları ve durum tespiti kapsamı

Durum tespiti kalemleri FID koşullarından türetildi. Bütçe tavanı, her kalemin **kısmi bilgi değeri** (EVPPI, Monte
Carlo'dan) ile belirlendi:

| Kalem (FID koşulu) | Bilgi değeri (EVPPI) | Gerekçe |
|---|---|---|
| TEİAŞ SFK ön yeterlilik görüşü (hibrit tesisteki batarya) | 0,46 M$ | Red, batarya gelirini sıfırlar |
| Yatırım teşvik belgesi (KDV istisnası) | 0,43 M$ | Yoksa NPV −5,8 M$ |
| Ornitoloji çalışması ve işletme izleme yükümlülükleri | 0,15 M$ | Göç dönemi durdurma riski |
| YEKDEM koridorunun endekslemesine dair hukuki görüş | 0 (al/alma kararı değişmez) | Ama prim tavanını 1,5'ten 3,1 M$'a çıkarabilir: teklif fiyatı için gerekli |
| Takvim / COD ve türbin slotu teyidi | 0 (P90 COD'da bile E[NPV] > 0) | YEKDEM 2030 sınırı ve borç takvimi için gerekli |
| **Toplam (bütçe tavanı)** | **~1,0 M$** | Tüm belirsizliğin bilgi değeri (EVPI) 5,5 M$ |

**Talep edilen bütçe 0,5 M$:** bilgi değeri tavanının yarısı; 60 MW ölçeğinde hukuki, teknik ve çevresel incelemenin tipik
maliyetiyle (0,35–0,6 M$) uyumlu.

**FID koşulları:**
1. TEİAŞ SFK ön yeterliliği.
2. Teşvik belgesi.
3. COD ≤ 31.12.2030 güvencesi (türbin slotu, gecikme cezalı EPC).
4. YEKDEM endekslemesine dair hukuki görüş.
5. Ornitoloji yükümlülüklerinin maliyetlendirilmesi.
6. Borcun SFK geliri olmadan boyutlandırılması.

## 8. İzleme tetikleyicileri

| Gösterge | Eşik | Karar |
|---|---|---|
| TEİAŞ SFK görüşü | Olumsuz | Teklifi bataryasız değere indir (prim ~0) |
| Teşvik belgesi | Alınamaz | Vazgeç |
| YEKDEM endeksleme | Teyit | Prim tavanını 3,1 M$'a çıkarmak için komiteye dön |
| Uzun vadeli fiyat beklentisi / PPA teklifleri | < ~52 $/MWh | Vazgeç |
| RES'lere sistem kesintisi | 2027'de de > %8 | Teklifi düşür |
| Türkiye'de işletmedeki depolama | FID'de > ~1,5 GW | SFK değeri düşük: batarya kararını yeniden değerlendir |
| Türbin teslim teklifi | > 24 ay | COD 2030 sonrası riski: YEKDEM'e güvenme, teklifi düşür |

## 9. Öneri

İnşaata hazır bir Ezine RES projesi için **0,5 M$ durum tespiti bütçesinin** ve **en fazla 1,5 M$ edinim primiyle sınırlı
bağlayıcı olmayan teklif** yetkisinin onaylanmasını öneriyoruz.

Projenin beklenen değeri pozitif ama ince (+1,5 M$, kâr olasılığı yarı yarıya). Değerin önemli bir kısmı durum tespitiyle
çözülebilecek üç belirsizliğe bağlı: TEİAŞ'ın SFK görüşü, teşvik belgesi ve ornitoloji. Bu yüzden doğru adım, sınırlı bir
bedelle bu belirsizlikleri çözmek ve ancak ondan sonra FID'e gelmek. **Geliştirme aşamasındaki (ön lisans devri) projelere
teklif önermiyoruz:** COD 2032'ye kayıyor ve YEKDEM hakkı kayboluyor.
