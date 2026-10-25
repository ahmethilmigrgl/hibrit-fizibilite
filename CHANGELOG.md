# Değişiklik günlüğü

Proje aşamalar halinde geliştirildi. Her aşama bir commit; revizyonlar ve önerinin nasıl değiştiği aşağıda. Ayrıntılar
`docs/00–07`, `docs/RAPOR.md` ve `docs/MODEL_DOGRULAMA.md` içinde.

## Karar yolculuğu

| Adım | Ne değişti | Beklenen NPV | Öneri |
|---|---|---|---|
| Aşama 4 | Deterministik optimum: yalnız RES 58,8 MW | −1,6 M$ | Yatırım yapılamaz |
| Aşama 5 | Batarya + SFK (yan hizmet) geliri, Monte Carlo | +28,4 M$ | Güçlü evet |
| Aşama 6 | SFK piyasası doyum stres testi | +4,5 M$ | Koşullu onay (PPA, aşamalı batarya) |
| Aşama 7 | Gerçekçi takvim, sistem kesintisi, YEKDEM | +2,1 M$ | Koşullu onay (inşaata hazır + YEKDEM) |
| Tutarlılık 1 (Ö1–Ö2) | YEKDEM/PPA'da batarya arbitrajı kaldırıldı | −11,4 M$ | Yatırım önerilmez |
| Tutarlılık 2 | YEKDEM yıllık opsiyon, ortak batarya sürücüsü, inşaata hazır takvim | +1,5 M$ | Durum tespiti + ≤1,5 M$ teklif |
| Nihai (Aşama 9 A) | Fiyat ortalaması: 58 $/MWh medyan değil beklenen değer | −1,7 M$ | Rafa kaldır, tetikleyicileri izle |
| **Düzeltme (v3, yorum A)** | **Lazard O&M'i sigorta ve araziyi içeriyorsa çift sayım kaldırılır; Lazard açıkça yazmıyor ([docs/v1_duzeltme_notu.md](docs/v1_duzeltme_notu.md))** | **+0,9 M$** | **Durum tespiti + ≤0,9 M$ teklif (yorum B: rafa kaldır)** |

## [Yayınlanmadı] — v4 (dal `v4-sektor`)

### Faz I — Mevcut RES'e GES ve batarya ekleme (2026-10-25)
- **Yardımcı kaynak analizi** (`src/ekleme/`): mevcut santral kendi kalibrasyon matrisi ve türbin vekiliyle (86 santralde
  model–gözlenen KF farkı mutlak medyan 0,6 puan); ortak maliyetler sıfırlanmış artımsal ekonomi; MILP'te santral tek
  "türbin" (N = 1 sabit), GES ve batarya serbest; bağlantı = MWe.
- **Ortak rastgele sayılar:** artımsal NPV aynı senaryolarla; varyans %10–79 azalıyor.
- **MCP:** kullanıcının üretim CSV'si model dönemiyle örtüşüyorsa oran aynı saatlerden (uzun dönem düzeltmeli). Doğrulama
  ilk sürümdeki hatayı yakaladı (1,146 → 1,100).
- **GES başabaş CAPEX'i** ve 86 santrallik Türkiye taraması (`data/atlas/v4_ekleme_tarama.csv`): bugünkü maliyetle (620 bin
  $/MW) hiçbir santralde GES eklemesi kârlı değil (başabaş medyan 437); batarya 85/86 santralde değer yaratıyor (SFK ağırlıklı).
- Arayüz: yeni sayfa "Mevcut santrale ekleme" (`/ekleme`; anonim kod, CSV yükleme). Belge `docs/v4_I_mevcut_santral_ekleme.md`,
  betik `src/v4_I1_ekleme.py` → `outputs/v4I/`, testler `tests/test_v4_I.py`.

### Faz H — Bankaya sunulabilir verim ve proje finansmanı (2026-10-25)
- **Belirsizlik bütçesi** (`src/finansman/verim.py`): yıllık / kalıcı bileşenler, hibritte RES–GES korelasyonu, 1 ve 10
  yıllık P50…P99; Monte Carlo'nun satılan enerji P değerleriyle karşılaştırma. Atlas model hatası iz/kayıp içerdiği için
  ayrıca eklenmiyor (çift sayım).
- **Çok senaryolu borç LP'si** (`src/finansman/borc_lp.py`, HiGHS): P50 / P90-1y / P99-1y / aşağı yön senaryolarında DSCR
  kısıtlarını aynı anda sağlayan en büyük heykelsi borç; gelir türüne göre DSCR (sözleşmeli / batarya / tüccar); dual
  değerlerle bağlayan kısıt. Tek senaryoda v1 kapalı formuyla birebir aynı.
- **Nakit şelalesi** (`src/finansman/selale.py`): DSRA, dağıtım kilidi, temerrüt; Monte Carlo'da olasılıklar ve öz kaynak
  IRR'ı. **Olasılık tabanlı boyutlandırma:** P(temerrüt) ≤ %5 olan en büyük borç (şans kısıtı, ikiye bölme).
- **Saha ölçümünün borç kapasitesine etkisi:** Ezine 50,4 MW RES'te 22,0 → 33,5 M$ (+%52).
- Bulgular: DSCR kurallarıyla boyutlanan borçta temerrüt olasılığı %12–43 (fiyat ve SFK riski kredi veren senaryolarına
  sığmıyor); SFK'ya dayalı batarya bankalanabilir değil; sözleşme (YEKDEM/PPA) borç riskini düşürüyor.
- Motor: `KullaniciVarsayimlari(finansman=True)`; Monte Carlo'ya GES model belirsizliği (`m_ges`) ve ızgara dışı RES çarpanı
  (`m_disdeger`). Ezine E[NPV] −1,67 → −1,62 M$. Arayüz: tam analizde "Proje finansmanı" bölümü (`uygulama/v4_bolumler.py`).
- Belge `docs/v4_H_finansman.md`, betik `src/v4_H1_finansman.py` → `outputs/v4H/`, testler `tests/test_v4_H.py`.

## [3.0.0-rc2] — 2026-10-11 (dal `v3-ie`, etiket v3.0.0-rc2, yayınlanmadı)

### v3 kapanış
- **Optimize edicinin laneti** (`src/portfoy/lanet.py`, `src/v3_G1_optimizer_laneti.py`):
  - Ampirik kanıt: çapraz doğrulamada yüksek tahminler fazla tahmin ediyor (en üst çeyrek +%14, kalibrasyon eğimi 0,36).
  - Simülasyon (200 tekrar): saf seçimde beklenen hayal kırıklığı portföyde 46,3 M$, en iyi tek sahada 15,7 M$.
  - Bayesçi büzülme (bölgesel öncül, ampirik Bayes) hayal kırıklığını 6,8 / 3,1 M$'a indiriyor ve gerçekleşen değeri
    artırıyor.
  - Gerçek karar: Faz F'nin 41,1 M$'lık portföyü sonsal beklentide 19,3 M$. Büzülmüş seçim 4 saha, 20,4 M$.
  - Eşikler: fiyat 46 → 52 $/MWh, risk ağırlığı λ 0,40 → 0,25.
  - Uygulamada düzeltme varsayılan, notla açıklanıyor.
- **Lazard kapsamı:** LCOE+ 2025 ve v13–v15 tam metninde sigorta, emlak vergisi ya da arazi hiç geçmiyor; örnek nakit
  akışında işletme gideri yalnız yakıt + O&M. Kesin ifade yok → düzeltme notunda iki yorum ve kararları (A: +0,92 M$,
  durum tespiti; B: −1,66 M$, rafa kaldır).
  - "Bu ne anlama geliyor" bölümü eklendi; karar yolculuğu grafiğine ±2,6 M$'lık karar bandı şeridi kondu.
  - Not kutuları (rapor, memo, Excel, Vaka sayfası) ve Excel (96/96 mutabık) güncellendi.
- **ERA5 yön gridi:** 1.464 hücre paketlendi (hızlı paketleyici, 14 s; 87.648 saat, NaN yok; ham hücrelerle %100 aynı).
  - Tüm sahalar grid kullanıyor; Ezine, Gürün ve Susurluk Faz D sonuçları birebir aynı.
  - Portföy adayları gridle yeniden değerlendi.
- **Kapanış belgeleri:** `docs/PROJE_OZETI.md`, README "Overview".

## [3.0.0-rc1] — 2026-10-11 (dal `v3-ie`, etiket v3.0.0-rc1, yayınlanmadı)

### Faz F ön adım
- **v1 düzeltme notu** ([docs/v1_duzeltme_notu.md](docs/v1_duzeltme_notu.md)): RES sigortası ve arazi kirası 35.000 $/MW-yıl'lık
  "her şey dahil" O&M'in hem içinde hem ayrı kalem olarak sayılıyordu. Düzeltilmiş baz vaka: E[NPV] −1,66 → +0,92 M$,
  P(NPV>0) %42 → %49, CVaR %5 −28,0 → −25,1. Karar (b) rafa kaldır → (a) durum tespiti + ≤0,9 M$ teklif. v1 içerikleri
  değişmedi; rapor, memo, Excel ve Vaka sayfasında not kutusu var. Excel'de seçilebilir (96/96 mutabık). v2'de aynı sorun
  var (+2,4…2,6 M$, karar değişmiyor); v3 FSA'da yok.
- **Bağlantı mesafesi belirsizliği:** YEKA RES-2025/2026 görüşlerinden (14 alan) atanan / en yakın oranı: medyan 0,73,
  log-σ 0,94. Monte Carlo'da senaryo başına; etkisi kuyrukta (Gürün CVaR −3,3 M$).

### Faz F — Portföy optimizasyonu ve performans izleme
Ayrıntılar `docs/v3_F_portfoy_performans.md`, çıktılar `outputs/v3F/`.
- **Portföy** (`src/portfoy/`):
  - 40 aday × 148 tasarım, 2.000 ortak senaryo. Fiyat, ERA5 hava yılı, SFK, CAPEX ve YEKDEM ortak; model hatası,
    bağlantı ve COD sahaya özgü.
  - Bölgeler arası korelasyon: saatlik uzunluk ölçeği 293 km; NPV korelasyonu 0,60.
  - İki aşamalı stokastik ortalama–CVaR MILP'i (Rockafellar–Uryasev), ε-kısıt etkin sınır.
  - Sinerjiler: işletme ölçeği +6,9, toplu alım +2,5, yedek parça havuzu +1,7 (Poisson taban stok, METRIC), ulaştırma 0 M$.
  - Çeşitlendirme ayrıştırması: varyansın %70'i ortak piyasa, %18'i hava korelasyonu, %12'si sahaya özgü.
  - Aynı CVaR'da optimal portföy en iyi tek saha.
  - Yatırım yok: fiyat ≤ 46 $/MWh ya da λ ≥ 0,40.
  - Kaba kuvvet ve CVaR doğrulaması.
- **Performans izleme** (`src/izleme/`):
  - 90 kalibre santral, aylık oran (haftalık gürültü %17–19 olduğu için).
  - Bölgesel ve YAT ayıklama, kapasite olayları.
  - Akran ağırlığı, kayan taban, Shewhart/EWMA/CUSUM (ARL0 = 48 ay, blok bootstrap).
  - Yapay arıza: 6 ay süren %10 düşüşte %71 yakalama; yanlış alarm 0,28 / santral-yıl.
  - Durum: 60 normal, 16 izleniyor, 10 kalıcı sapma.
  - Santral adları varsayılan gizli.
- **Arayüz:** "Portföy" ve "Performans izleme" sayfaları (portföy çözümü ≤ 21 s, performans sayfası ≤ 1,6 s; 2 çekirdek).
- **Kapanış:** docs'taki markdown kod örnekleri ruff ile biçimlendirildi; gizli bilgi taraması temiz; tüm testler geçiyor.

## [3.0.0-E] — 2026-10-10 (dal `v3-ie`, yayınlanmadı)

### v3 ön adım (Ö1–Ö4) — Faz D tutarlılık konuları
- O&M kapsam mutabakatı: varsayılan işletme modeli tam kapsamlı servis sözleşmesi (FSA 20 + sahip kalemleri 14 = 34 $/kW-yıl);
  Faz D'nin 25,5 bin $'ı sahip kalemlerini içermiyordu. Kendi bakımı seçeneği; başabaş filo 16 türbin.
- Kayıp tablosu (IEC 61400-15 kategorileri): çift sayım yok; v2'nin %12'si = kategoriler %11,3 + kalibrasyon farkı %0,8.
- Bakım parametre duyarlılığı + tornado (arayüzde); strateji sıralamasını çeviren eşikler.
- Üç sahada üç aşama: E[NPV] Faz D'ye göre 1,0–1,6 M$ düştü, v2'ye göre hâlâ 2,8–4,4 M$ iyi; karar değişmedi.

### v3 Faz E — Coğrafi katmanlar, çok kriterli saha seçimi, lojistik
Ayrıntılar `docs/v3_E_cbs_cok_kriterli_lojistik.md`, çıktılar `outputs/v3E/`.
- **Coğrafi katmanlar** (çevrimdışı, OSM Geofabrik PBF + Copernicus DEM): sınıflı yollar, gerilimli hat ve trafo
  merkezleri, yerleşim, havalimanı, koruma alanı (WDPA lisansı nedeniyle OSM), 250 m eğim, yaklaşık kuş göç koridorları →
  250 m mesafe gridleri ve 1.464 hücrelik altyapı tablosu.
- **Mesafeye bağlı şebeke bağlantısı** (gerilim kuralı, TEİAŞ ihale birim maliyetleri) sabit 120 bin $/MW yerine;
  YEKA RES-2025 görüşleriyle doğrulama. TEİAŞ lisanslı kapasite yayımlamıyor → ana sınırlama.
- **CBS dışlamaları türbin yerleşimine** bağlandı (Faz D arayüzü): yerleşim/yol/hat/havalimanı tamponları, eğim, koruma.
- **Lojistik:** ağır nakliye ağı (180 bin düğüm) + ulaştırma LP'si (limanlar, yerli üreticiler); CAPEX'e referansa göre
  fark, teslim süresi COD'ye.
- **Çok kriterli seçim:** dışlama + AHP (ikili karşılaştırma, CR) + TOPSIS (değer fonksiyonu standardizasyonu; klasik
  vektör normalizasyonunun ekonomiyi bastırdığı bulundu) + Dirichlet dayanıklılığı + mevcut santrallerle ROC/AUC
  (ekonomi profili 0,87; açığa çıkan tercih: şebekeye yakınlık %34, göç %2).
- **Arayüz:** isteğe bağlı altyapı katmanları, saha kartında bağlantı/lojistik/göç uyarısı, tam analizde "Lojistik ve
  bağlantı", yeni sayfa "Çok kriterli saha seçimi".
- **Etki:** Türkiye başabaş medyanı +4,4 $/MWh, 58 altı hücre 49 → 43, ekonomik ilk 10'un 8'i aynı; Ezine E[NPV] −1,95 →
  −1,63, Gürün −2,91 → −6,98, Susurluk −1,37 → −3,34 M$; karar değişmedi (rafa kaldır).

## [3.0.0-D] — 2026-10-10 (dal `v3-ie`, yayınlanmadı)

### v3 Faz D — Türbin yerleşimi optimizasyonu + bakım ve güvenilirlik
Ayrıntılar `docs/v3_D_yerlesim_bakim.md`, çıktılar `outputs/v3D/`.
- **Türbin yerleşimi** (`src/yerlesim/`):
  - ERA5 100 m yönüyle rüzgâr gülü; GWA 250 m hız çarpanları (atlas kalibrasyonuyla tutarlı).
  - Saha alanı + dışlama katmanı arayüzü (Faz E için).
  - Elips biçimli asgari aralık; PyWake Bastankhah iz modeli (Jensen duyarlılığı) + PyWake'le 1e-6 içinde aynı hızlı vekil.
  - Üç yöntem: MILP (Glover doğrusallaştırması), GA ve SA + yerel arama, düzenli ızgara / v2 kuralı.
  - Web için çok başlangıçlı SA: ~2 s, en iyiye ort. %0,13; MILP 24–60 s.
- **Komşu iz ve atlas hipotezi:**
  - 85 kalibre santralde iz kaybı medyan %4,7.
  - "Balıkesir–Biga artığı kümelenme izinden" hipotezi çürütüldü: fark 0,34 puan, p = 0,70.
  - İzden arındırılmış katsayılar doğrulamayı kötüleştirdi (RMSE 6,87 → 7,00), atlas güncellenmedi.
  - Çift sayımı önleyen göreli kural (RMSE 6,77).
- **Bakım ve güvenilirlik** (`src/bakim/`):
  - SimPy ayrık olay simülasyonu: ekip, vinç, stok, hava pencereleri.
  - Üç strateji: durum bazlı %97,4 kullanılabilirlik, toplam maliyette en iyi.
  - Zaman indeksli önleyici bakım çizelgesi MILP'i: bahar kampanyasına göre kayıp gelir %46–56 düşük.
  - Baz stok simülasyon tabanlı optimizasyonu: 14 türbinde stok ekonomik değil, 28+ türbinde 1 adet.
  - O&M 25,5 bin $/MW-yıl (v1 35 bin; mutabakat docs §7.6).
- **Motor:**
  - Kapasite MILP'i türbin sayısına bağlı iz verimiyle (ikili seçimle kesin parçalı doğrusal).
  - Seçilen N için yerleşim + DES → profil, OPEX, Monte Carlo kullanılabilirlik gürültüsü.
  - Hızlı tarama önceden hesaplanmış tablolarla.
  - Seçenekler: `yerlesim_bakim`, `yerlesim_yontemi`, `bakim_modeli`, `bakim_stratejisi`. `yerlesim_bakim=False` v2'yi aynen
    verir. Veri sürümü `v3D-2026-10`.
- **Önce/sonra** (tam analiz, E[NPV]): Ezine −6,30 → −0,82, Gürün −5,71 → −1,30, Susurluk −5,04 → −0,36 M$.
  Tasarımlar 10–13 türbine küçüldü; karar değişmedi (rafa kaldır).
- **Süre:** tam analize v3 eki 10–13 s (2 çekirdek).
- **Arayüz:** tam analizde "Türbin yerleşimi" (harita, rüzgâr gülü, iz eğrisi, türbin tablosu) ve "İşletme ve bakım"
  (strateji tablosu, kullanılabilirlik dağılımı, bakım takvimi, mevsimsel hava beklemesi, yedek parça) bölümleri ("Eşik").
- **Bağımlılıklar:** `py_wake==2.6.20`, `simpy==4.1.2` (ikisi de MIT). Testler `tests/test_v3_D.py` (23).

## [2.0.0-rc2] — 2026-10-07 (dal `v2-genel`, yayınlanmadı)

### Arayüz tasarım sistemi birleştirildi (`v2-arayuz` → `v2-genel`)
- **"Eşik" tasarım sistemi:** açık/koyu tema, belirteçler (`uygulama/tasarim/tokenlar.py`), bileşenler, ortak Plotly
  şablonu, yerel yazı tipleri (OFL), karosuz altlık harita, logo. Bkz. `docs/v2_tasarim_sistemi.md`.
- **Çakışmalar** (`CLAUDE.md`, `uygulama/harita.py`, `uygulama/sayfa_analiz.py`):
  - Hesaplama ve sonuçlar `v2-genel`'den, görünüm `v2-arayuz`'dan alındı.
  - Revizyon R öğeleri yeni bileşenlere taşındı: ada ve üst sınır harita kenarları (belirteç renkleri), lejant anahtarları,
    saha kartında `uyari_kutusu`, sonuç uyarılarında görünür kutu, ilk 10 tablosu (`karsilastirma_tablosu` + "Adaları dahil
    et").
  - Ada hücrelerinde yüzdelik notu "(sıralama adalar hariç)".
  - `.streamlit/config.toml` tema betiğiyle yeniden üretildi.
- **CSV düzeltmesi:** `results/karar_yolculugu.csv` ondalık virgüllü metinleri ("58,8 MW", "≤1,5 M$") tırnaksız
  olduğundan Vaka sayfasında sütunlar kayıyordu. Metin alanları tırnaklandı, okuyucu açıklaştı. Tüm `results/` ve
  `data/atlas/` CSV'leri için alan sayısı testi eklendi (başka bozuk dosya yok).
- **Doğrulama:**
  - 124 test.
  - Açık/koyu × 1440/390 px'de 48 ekran ve 4 yükleniyor çekimi (`docs/img/tasarim/birlesim/`, özel uyarı ekranları `07_*`);
    taşma yok.
  - Süreler kötüleşmedi: açılış 2,2 s, hızlı tarama 4,6 s, tam analiz 66 s (2 çekirdek, soğuk tablolar).

## [2.0.0-rc] — 2026-10-06 (dal `v2-genel`, yayınlanmadı)

Türkiye geneli saha tarama ve analiz uygulaması. Ayrıntı: `docs/v2_A_veri_altyapisi.md`, `docs/v2_B_analiz_motoru.md`,
`docs/v2_C_arayuz.md`.

### Revizyon R — ilk 10 makullüğü, modern türbin, adalar, tam analiz süresi (2026-10-07)
- **Aktarım kuralı:** kıyı benzerliği sürekli oran (20 km eşiğindeki kırılma kaldırıldı), komşu artığı ulusal medyana
  büzülüyor (n0 = 2). Çapraz doğrulamada RMSE 7,17 → 6,87 (fark −0,30, %90 GA −0,55…−0,07). Güven: yüksek medyan 3,4 /
  P90 10,4; düşük 5,6 / 11,4. Trakya'da tek komşulu abartılar düzeldi (Çerkezköy %46,6 → %42,0); Biga/Balıkesir ilk 50'de 10 → 17.
- **Modern türbin doğrulaması:** modern alt kümede (12 santral) sistematik fazla tahmin yok (ort. +1,1 puan); salt türbin
  kazancı eski santrallerde ~7 puan (iddia "1–5 puan" düzeltildi). Gözlenen azamiyi (%45,6) aşan hücre ve sahalar "üst sınıra
  yakın" olarak işaretleniyor.
- **Adalar:** sınır ızgarasından otomatik tespit (Sinop/Cunda istisna); denizaltı kablosu uyarısı, bilinen bağlantı durumu
  (kaynaklı; kapasite doğrulanamadı); sıralamalardan varsayılan olarak çıkarılıyor.
- **Tam analiz 2 çekirdekte ~6× hızlı (471–564 → 71–93 s):** işletme LP'si doğrudan highspy (aynı sonuç), kapasite MILP'i
  96 temsilî günle (tam yıl MILP'i zaman sınırında %2 boşlukta kalıyordu). Sonuçlar Ezine/Susurluk'ta SE'nin altında
  değişti; Gürün'de daha iyi bir tasarım bulundu (+0,8 M$). Karar üç sahada aynı.

### Faz C — Web uygulaması (yerel Streamlit)
- **Ön adım — atlas aktarımı düzeltildi** (`docs/v2_A §5b`):
  - Aktarım hız uzayındaydı; KF kopyalanmıyordu.
  - Ama santral GWA referansı sahanın moduna bağlıydı (türbin yerleşimi etkisizdi) ve santraller ortak bir vekil türbinle
    (E-92/80 m) kalibre ediliyordu.
  - Artık her santral OSM'den çıkarılan kendi türbin vekili ve gerçek türbin konumlarıyla kalibre ediliyor; talimat/arıza
    saatleri k'dan çıkarıldı.
  - Ezine (E-141/120 m): yerleşim 2 km %30,2 → %33,9 (v1 kalibre %37,8).
  - Güven seviyeleri ikiye indi: yüksek (≤ 30 km) medyan 3,8 / P90 9,8 puan; düşük 5,6 / 11,5.
  - Türbin yerleşimi varsayılan açık (çapraz doğrulamada RMSE 9,2 → 7,2).
- **Veri katmanı** (`src/veri_katmani.py`): Çalışma anında yalnız yerel paketler okunuyor. PVGIS GES KF gridi ve Copernicus DEM
  rakım ızgarası eklendi; uygulama hiçbir dış API'ye bağlanmıyor.
- **Ön tarama haritası:** 1.464 kara hücresi için başabaş fiyatları ve KF'ler (`data/atlas/on_tarama.parquet`).
- **Uygulama** (`app.py`, `uygulama/`):
  - Saha seçimi üç yoldan: harita, koordinat, il/ilçe adayları.
  - Hızlı tarama: başabaş fiyatı, Türkiye yüzdeliği ve "tam analize değer mi?" değerlendirmesi.
  - Tam analiz: sıra numarası, ilerleme, öneri, güven etkisi ve HTML/PDF rapor.
  - Paylaşım bağlantısı; vaka çalışması ve yöntem sayfaları; TR/EN.
  - İstek sınırları ve gizlilik notu.
- **Motor:**
  - Tam analiz sırası (sıra numarası, azami uzunluk) ve önbellekten okuma (`onbellekten`).
  - Hızlı taramada en iyi standart tasarımın başabaşı; tam analizde güven seviyesinin E[NPV]'ye etkisi.
  - Hızlı tarama metinlerinden karar dili çıkarıldı.
- **Testler:** AppTest (`tests/test_v2_uygulama.py`); Playwright ile masaüstü/390 px ekran görüntüleri ve taşma kontrolü
  (`src/v2_C8_tarayici.py`).

### Faz B — Analiz motoru (`58a6eeb`)
- `analiz_et(saha, hizli|tam, varsayımlar)`.
- Hızlı tarama ~2 s; tam analiz 2 çekirdekte ~4 dk.
- MILP'te SFK doyum beklentisi; sonuç önbelleği ve tek tam analiz kilidi.
- Ezine regresyonu v1 ile bir standart hata içinde.

### Faz A — Veri altyapısı (`9ba4f3f`, `6165d28` ve öncesi)
- Open-Meteo / ERA5 gridi, Global Wind Atlas (1 km, 250 m).
- 90 santrallik kalibrasyon atlası ve aktarım kuralı.
- Sahaya bağlı parametreler, ulusal piyasa paketi.

## [1.0.0] — 2026-10-04

### Aşama 9 — Yayın öncesi kalite turu
- **Bölüm A (tutarlılık):**
  - Monte Carlo log-fiyat süreci 58'i medyan alıyordu; simüle ortalama fiyat 61,8 $/MWh idi. Süreç beklenen değeri 58
    olacak şekilde düzeltildi (σ²/2 düzeltmesi, `monte_carlo.log_merkez`).
  - Deterministik baz → Monte Carlo farkı bileşenlerine ayrıldı (`src/07_fark_ayristirma.py`).
  - Baz vaka +1,5 → −1,7 M$; öneri "rafa kaldır, tetikleyicileri izle".
  - İkili bilgi değeri formülü negatif beklenen NPV için genelleştirildi.
- **Kod kalitesi:** ruff lint + format (`pyproject.toml`). Dışa açık fonksiyonlara tip ipuçları ve docstring eklendi.
  GitHub Actions CI (`.github/workflows/ci.yml`): ruff + ham veri gerektirmeyen testler; README rozetleri.
- **Veri ve lisanslar:** `DATA_SOURCES.md`. Copernicus/ERA5, PVGIS ve EPİAŞ atıfları README, rapor, memo, sunum eki ve
  dashboard altbilgisinde. MIT yalnız kod için.
- **Doğrulama:** `docs/MODEL_DOGRULAMA.md` (neyin neyle doğrulandığı, neyin doğrulanamadığı, duyarlılıklar).
- **Dashboard:**
  - Hakkında bölümü, favicon.
  - TR/EN sayı biçimi (tablolar ve grafikler), birim tutarlılığı (M$, $/MWh).
  - Markdown'da `$` kaçışı (uyarı metninde LaTeX hatası düzeltildi).
  - Mobil (390 px) kontrolü, README ekran görüntüleri ve GIF.

### Aşama 8 — Karar paketi (`cb14acd`)
- FAST benzeri formüllü Excel modeli: 48/48 senaryo Python ile mutabık, 0 formül hatası.
- Yatırım komitesi memosu (MD + PDF), 13 slaytlık sunum (karar yolculuğu grafiği), dashboard/README indirme bağlantıları.

### Tutarlılık 2 (`8da53ae`)
- YEKDEM 10 yıllık kilit değil, her 30 Kasım'da seçilen yıllık opsiyon (YEK Yön. md. 4/2, 5/1, 8/1).
- Kurulu batarya yayılımı SFK fiyatını, sistem kesintisini ve öğle kanibalizasyonunu birlikte sürüyor (ortak sürücü).
- İnşaata hazır proje takvimi (COD P50 Kasım 2029).

### Tutarlılık 1 — Ö1–Ö2 (`aca7120`)
- YEKDEM'de depolanıp verilen enerji de YEKDEM fiyatından ödenir: arbitraj yok. PPA finansal fark sözleşmesi olarak
  modellendi (batarya tüccar dispatch'i).
- `nihai_baz_vaka` tanımlandı.

### Aşama 7 — Tamamlayıcı analizler (`dc8e04a`)
- Sistem kaynaklı kesinti (EPİAŞ YAT talimatları + referans santraller), teşvik belgesi/KDV, YEKDEM, karbon ve CO2.
- CPM + Monte Carlo proje takvimi, 20 maddelik risk kaydı.

### Aşama 6 — Stres testi ve paketleme (`f113afb`, `d92058f`)
- SFK doyum arz-talep modeli (İngiltere/Almanya/Avustralya kalibrasyonu), fırsat penceresi, erteleme, esnek batarya.
- `calistir.py`, pytest, Streamlit dashboard (TR/EN), rapor PDF'i, README'ler.

### Aşama 5 — Gelir yığını ve risk (`d062808`)
- Yan hizmet (SFK ikili katılım ≥30 MW), dengesizlik, YEK-G, PPA.
- Önceden hesaplanmış dispatch tablolarıyla 10.000 senaryolu Monte Carlo, EVPI/EVPPI, Sobol.

### Aşama 4 — Optimizasyon (`38281c8`)
- Batarya ve hibrit dispatch LP'leri, tamsayı türbin ve ikili yatırım kararlı kapasite MILP'i (tam yıl, Pyomo + HiGHS),
  temsilî günler, pişmanlık analizi.

### Aşama 3 — Finansal model (`52c46cc`)
- Reel USD nakit akışı, vergi ve zarar mahsubu, P90 heykelsi borç, NPV/IRR/LCOE, tornado.

### Aşama 2 — Piyasa analizi (`f1e193c`, revizyon `79b6494`)
- EPİAŞ PTF 2014–2026, yakalanma oranı ve kanibalizasyon, ördek eğrisi.
- ERA5 rüzgârının üç santralle kalibrasyonu.
- Revizyon: zaman hizası ve ay × saat hız katsayısı (gün içi şekil düzeltmesi).

### Aşama 1 — Saha ve üretim (`a8124e8`)
- Dört aday saha taraması. Çanakkale-Ezine için 10 yıllık saatlik GES (PVGIS-SARAH3 + pvlib) ve RES (ERA5 +
  windpowerlib) profilleri.

### Aşama 0 — Kurulum (`cffc32e`)
- Klasör yapısı, Python 3.11 ortamı, ısınma LP modeli.
