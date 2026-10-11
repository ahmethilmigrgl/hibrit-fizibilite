# Proje özeti — Türkiye hibrit rüzgâr + güneş + batarya fizibilitesi (v1–v3)

**Soru.** Türkiye'de 50 MW'lık bir şebeke bağlantısının arkasına rüzgâr (RES), güneş (GES) ve batarya kurulmalı mı;
kurulacaksa hangi boyutlarda, hangi sahada, hangi gelir yapısıyla ve belirsizlik altında hangi riskle? Proje üç
sürümde büyüdü: tek bir sahanın yatırım kararı (v1), Türkiye'nin herhangi bir noktası için tarama ve analiz aracı (v2),
endüstri mühendisliği modülleri (v3). Tüm varsayımlar kaynaklarıyla `config.yaml`'da, tüm optimizasyon modellerinin
matematiksel formülasyonları `docs/` altında.

## v1 — Ezine vaka çalışması ve karar

- **Yöntem.**
  - Saatlik üretim profilleri: ERA5 ve PVGIS; rüzgâr çevredeki santrallerin EPİAŞ üretimiyle kalibre edildi.
  - 12 yıllık EPİAŞ fiyat ve yan hizmet verisi.
  - Kapasite boyutlandırması: Pyomo + HiGHS MILP; saatlik batarya dağıtımı ve şebeke kısıtıyla.
  - Risk: reel USD proje finansmanı modeli ve 10.000 senaryolu Monte Carlo (fiyat, hava, SFK piyasa doyumu, takvim,
    sistem kesintisi, YEKDEM).
  - Karar paketi: formüllü Excel, yatırım memosu, sunum.
- **Bulgu.** Tasarım belli: RES 58,8 MW + 30 MW / 60 MWh batarya, GES yok. Değer ise sınırda. Öneri altı kez değişti
  (+28 M$'dan −11 M$'a), çünkü her aşama iyimser ya da kötümser bir varsayımı düzeltti. Nihai baz vaka E[NPV] −1,66 M$,
  kâr olasılığı %42, karar "rafa kaldır, tetikleyicileri izle".
- **Düzeltme notu (v3).** v1'in RES O&M'ine (35.000 $/MW-yıl, Lazard) ayrıca sigorta ve arazi kirası ekleniyordu.
  Lazard bu kalemlerin dahil olup olmadığını yazmıyor (dört sürümde de hiç geçmiyor). Dahilse E[NPV] +0,92 M$ ve karar
  "durum tespiti + ≤0,9 M$ teklif"; değilse v1 geçerli. Ezine'nin beklenen değeri sıfır etrafında ±2,6 M$'lık bir
  bantta. **Analizin asıl katkısı kararın işaretini belirleyen varsayımları bulmak oldu:**
  1. O&M sözleşme kapsamı;
  2. YEKDEM USD koridorunun endekslenmesi;
  3. uzun vadeli fiyat (başabaş ~59 $/MWh);
  4. SFK piyasasının doyma hızı.
- **Doğrulama.** Excel modeli 96/96 senaryoda Python ile birebir uyuşuyor. Monte Carlo yakınsaması, deterministik →
  Monte Carlo köprüsü ve kalibrasyon testleri `docs/MODEL_DOGRULAMA.md`'de.

## v2 — Türkiye geneli araç ve kalibrasyon atlası

- **Yöntem.**
  - EPİAŞ'tan 90 RES santralinin üretimiyle kalibrasyon atlası.
  - Komşu santrallerden yeni sahaya aktarım kuralı (Global Wind Atlas ölçekli, ≤ 30 km komşu).
  - Türkiye'nin 1.464 kara hücresinde ERA5 ve PVGIS gridleri, ön tarama haritası.
  - Analiz motoru: saniyeler içinde hızlı tarama, ~1 dakikada optimizasyon + Monte Carlo.
  - Herkese açık bir web uygulaması için tasarlandı: çalışırken kimlik bilgisi ve dış API yok.
- **Bulgu.** Rüzgâr tahmininin belirsizliği sahaya göre değişiyor ve kararı etkileyecek büyüklükte:
  - yüksek güvenli sahalarda (komşu santral ≤ 30 km) KF hatası medyanı 3,4 puan;
  - düşük güvenli sahalarda 5,6 puan.

  Uygulama bu belirsizliği her sonuçla birlikte gösteriyor.
- **Doğrulama.**
  - Birini dışarıda bırak çapraz doğrulama: 90 santral.
  - Ezine regresyonu: v2 motoru v1 baz vakasını 0,2 M$ içinde, Monte Carlo standart hatası düzeyinde tekrar ediyor.
  - Tarayıcıda uçtan uca testler.

## v3 — Endüstri mühendisliği modülleri

| Modül | Yöntem | En önemli bulgu | Doğrulama |
|---|---|---|---|
| **Türbin yerleşimi** (Faz D) | Rüzgâr gülü (ERA5 100 m yön gridi, 1.464 hücre, 2014–2023 saatlik; bütünlüğü ve santral hücreleriyle %100 uyumu doğrulandı), PyWake iz modeli, MILP (Glover doğrusallaştırması) / genetik algoritma / benzetimli tavlama; iz verimi kapasite MILP'ine kesin girer | İz kaybı açık modellenince optimal santral küçülüyor; tavlama, MILP'in %0,13 yakınında 2 saniyede | PyWake'le 1e-6 içinde aynı vekil; "kümelenme izi" hipotezi çürütüldü (p = 0,70) |
| **Bakım ve güvenilirlik** (Faz D, E ön adım) | SimPy ayrık olay simülasyonu (Weibull arızalar, hava pencereleri, vinç), önleyici bakım çizelgesi MILP'i, taban stok; O&M kapsam mutabakatı | Durum bazlı bakım 24 duyarlılık senaryosunun 20'sinde en iyi; tek saha için tam kapsamlı servis sözleşmesi doğru (kendi bakımı ~16–38 türbinde başabaş) | Arıza sayıları girdiyle %±4; kayıp tablosunda çift sayım yok |
| **Çok kriterli saha seçimi** (Faz E) | OSM ve DEM katmanları, dışlama kısıtları, AHP (tutarlılık oranı), TOPSIS (değer fonksiyonu standardizasyonu), Dirichlet dayanıklılığı | Klasik TOPSIS normalizasyonunun ekonomiyi bastırdığı bulundu ve düzeltildi; geliştiricilerin açığa çıkan tercihleri: şebekeye yakınlık %34, kuş göçü %2 (Belen) | Mevcut 171 santralli hücreyle ROC/AUC 0,87 |
| **Lojistik ve bağlantı** (Faz E, F ön adım) | Mesafeye bağlı bağlantı maliyeti (TEİAŞ ihale birim maliyetleri), ağır nakliye ağı (180 bin düğüm) + ulaştırma LP'si, YEKA görüşlerinden bağlantı mesafesi belirsizliği | Gerçek altyapıyla başabaş medyanı +4,4 $/MWh; TEİAŞ'ın atadığı hatlar en yakın trafoya göre medyan 0,73, log-σ 0,94: beklenen değeri az, kuyruğu çok etkiliyor | YEKA RES-2025/2026 görüşleri (14 alan); lojistik payı literatürle aynı büyüklükte |
| **Portföy optimizasyonu** (Faz F) | 40 aday × 148 tasarım, 2.000 **ortak senaryo** (aynı fiyat, ERA5 hava yılı, piyasa ve düzenleyici olaylar), iki aşamalı stokastik ortalama–CVaR MILP'i (Rockafellar–Uryasev), sinerjiler, ε-kısıt etkin sınır, **optimize edicinin lanetine karşı Bayesçi büzülme** | Saf tahminle seçilen 5 sahalık portföyün değeri (41 M$) yarısından fazla seçim etkisi: simülasyonda beklenen hayal kırıklığı 46 M$ (tek sahada 16 M$). Büzülmeyle 4 saha, 20 M$; aynı kuyruk riskinde en iyi portföy en iyi tek saha (varyansın %70'i ortak piyasa); 52 $/MWh altında ya da λ ≥ 0,25'te yatırım yok | Kaba kuvvet aramasıyla birebir; doğrusal CVaR kesin değerle 1e-13 içinde |
| **Performans izleme** (Faz F) | 90 santralde gözlenen / model oranı, bölgesel ve sistem talimatı ayıklama, akran ağırlığı, kayan taban, Shewhart / EWMA / CUSUM (ARL0 kalibrasyonu, blok bootstrap) | Yeniden analiz verisiyle izleme büyük ve birkaç ay süren düşüşleri yakalıyor, küçük verim kayıplarını yakalamıyor (haftalık gürültü %17–19) | Yapay arıza testi: 6 ay %10 düşüşte %71 yakalama, santral-yıl başına 0,28 yanlış alarm |

**Ortak ders.** Her sürümde en değerli çıktı tek bir sayı değil, o sayıyı değiştiren varsayımların listesiydi. Kendi
modelimdeki üç hatayı yine kendi kontrol mekanizmalarım buldu:
- v1'deki O&M kapsamı;
- Faz E'deki TOPSIS normalizasyonu;
- bağlantı mesafesindeki gerilim sınıfı karışıklığı.

Portföyde ise optimize edicinin laneti, "en iyi görünen" sahaların tahmininin neden iyimser olduğunu sayısal olarak
gösterdi.

Ayrıntılar: [README](../README.md), [RAPOR](RAPOR.md), [v1 düzeltme notu](v1_duzeltme_notu.md), Faz D–F belgeleri
`docs/v3_*.md`.
