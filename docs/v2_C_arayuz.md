# v2 Faz C — Web uygulaması (yerel Streamlit)

Faz C, Faz B'nin analiz motorunu (`analiz_et`) Türkiye'nin herhangi bir noktası için kullanılabilir bir web uygulamasına
dönüştürüyor:

- **Açılış ekranı:** Türkiye'nin ön tarama haritası.
- **Saha seçimi:** üç yol (harita, koordinat, il/ilçe).
- **Analiz:** hızlı tarama ve tam analiz.
- **Diğer sayfalar:** v1 Ezine vaka çalışması ve yöntem.

Uygulama şimdilik **yerelde** çalışıyor ve yalnız yerel veri paketlerini okuyor. Çalışma anında hiçbir dış API'ye ve kişisel
kimlik bilgisine (CDS, EPİAŞ) bağlanmıyor. Barındırma ve yayın ayrı bir aşama.

```bash
.venv/bin/streamlit run app.py          # http://localhost:8501
```

## 0. Ön adım: atlas aktarımı düzeltmesi

Özet aşağıda; ayrıntı `docs/v2_A_veri_altyapisi.md §5b`.

**Şüphe:** "Atlas KF'yi kopyalıyor".

**Bu kısım doğru değil.** Aktarım hız uzayında yapılıyor: aynı K, E-92/80 m ile %22,7, E-141/120 m ile %30,2 veriyor.

**Ancak iki gerçek hata bulundu ve düzeltildi:**
1. Santral GWA referansı sahanın moduna bağlıydı; türbin yerleşimi bu yüzden etkisizdi.
2. Santraller ortak bir vekil türbinle kalibre ediliyordu; eski türbinlerin düşük verimi yeni sahaya "düşük rüzgâr" olarak taşınıyordu.

Ayrıca talimat ve arıza saatleri k'ya girmiyor artık; sistem kesintisi finans modelinde ayrıca uygulanıyor.

**Sonuç:**
- Ezine (E-141/120 m): KF nokta %29,3, yerleşim 2 km %33,9, 3 km %35,5; v1 kalibre değeri %37,8.
- Güven seviyeleri iki seviyeye indi. Eski "orta" seviye, gerçek aktarım altında sıralamayı korumuyordu.
- Varsayılan türbin yerleşimi **açık**. Çapraz doğrulamada RMSE 9,2 → 7,2 puan, yanlılık −4,1 → −1,1 puan.

## 1. Mimari

```
app.py                          giriş: sayfa ayarı, TR/EN, gezinme (st.navigation, üstte), altbilgi (atıflar)
uygulama/
  ortak.py                      dil ve sayı biçimi (TR ondalık virgül), palet, uyarı bandı, atıflar, istek sınırı, Markdown $ kaçışı
  servis.py                     arayüz ↔ motor/veri köprüsü: ön tarama, santraller, il/ilçe, adaylar, nokta bilgisi, yüzdelik
  harita.py                     folium ön tarama haritası + lejant
  sayfa_analiz.py               açılış: harita → saha seçimi → varsayımlar → hızlı / tam analiz → paylaşım bağlantısı
  sayfa_vaka.py                 v1.0.0 Ezine dashboard'u (değiştirilmeden) + karar yolculuğu
  sayfa_yontem.py               kaynaklar, atlas ve güven, modlar, basitleştirmeler, doğrulama, sınırlamalar, gizlilik
src/veri_katmani.py             TEK veri erişim katmanı (mantıksal yol → yerel dosya; "yerel" | "uzak" mod)
src/motor/                      Faz B analiz motoru (sıra numarası, sıra sınırı, önbellekten okuma eklendi)
```

### 1.1 Veri katmanı (C1)

Çalışma anındaki bütün okumalar `src/veri_katmani.yol(mantiksal)` üzerinden geçer:
- atlas ve paketler,
- ERA5 / PVGIS / GWA 250 m / rakım gridleri,
- ön tarama.

Mod `config.yaml → v2.veri_erisim.mod`:
- **"yerel"** (şimdiki): yalnız `data/atlas` ve `data/grid` okunur. Eksik dosyada ağa çıkılmaz; iki dilli `VeriYok` hatası verilir.
- **"uzak"**: yerelde olmayan grid dosyaları barındırma servisinden indirilir (`hf_veri`; henüz kullanılmıyor). Verileri bir servise taşırken yalnız bu modül değişir.

Çalışma anı dış çağrıları kaldırıldı:

| Önce | Şimdi |
|---|---|
| PVGIS API (güneş) | **PVGIS GES KF gridi**: 1.464 hücrenin temsilî kara noktası, saatlik AC KF uint16, `src/v2_C1_pvgis_grid.py` |
| Open-Meteo yükseklik API'si | **Rakım ızgarası** 0,02°, Copernicus DEM GLO-90 COG özet katmanı, `src/v2_C1_rakim_grid.py` |
| Grid yoksa Open-Meteo hava API'si | Yerel modda kapalı |

### 1.2 ERA5 gridi bütünlüğü (C1)

`src/v2_C1_grid_butunluk.py` → `outputs/v2C/C1_grid_butunluk.csv`. İndirme 2026-10-06 12:41'de bitti; hatalı 4 hücre ikinci turda indi.

| Kontrol | ERA5 gridi | PVGIS gridi |
|---|---|---|
| Beklenen kara hücresi | 1.464 | 1.464 |
| Eksik | **0** | **0** |
| Açılamayan / yanlış uzunluk / yanlış başlangıç | 0 | 0 |
| Aralık dışı değer | 3 hücrede birer saat v100 > 60 m/s | 0 |
| Komşulara göre aykırı ortalama (> %40) | 18 kıyı hücresi (işaret) | 0 |
| Boyut | 0,71 GB | 127 MB |

- **Aralık dışı değerler:** 41,00° K; 39,00 / 39,25 / 40,00° D. Tek saatlik, fiziksel olmayan sıçramalar: 6 → 63 → 16 m/s, aynı saatte 10 m hızı 0,8 m/s.
  - CDS zaman serisi ürününün artefaktı.
  - Okumada temizleniyor (`era5_grid.sicrama_temizle`): > 40 m/s ve komşu saatlerin 2,5 katından büyükse komşu ortalaması.
- **Aykırı ortalamalar:** Antalya, Muğla ve Karadeniz kıyısındaki hücreler. Denizin baskın olduğu hücrelerde ERA5 hızı iç komşulardan doğal olarak yüksek; hata değil.

## 2. Yeniden üretilen tablolar (ön adım Ö2)

### 2.1 Güven seviyeleri

`data/atlas/guven_seviyeleri.csv`. Değerler mutlak KF hatası (puan); parantez içinde bootstrap %90 güven aralıkları.

| Seviye | Tanım | n | Medyan | P90 |
|---|---|---|---|---|
| Önce: yüksek / orta / düşük | ≤15 km / 15–30 km / yok (vekil türbin, kapalı döngü) | 28 / 8 / 54 | 2,1 / 5,2 / 5,9 | 7,5 / 11,8 / 13,6 |
| **Sonra: yüksek** | benzer kalibre santral ≤ 30 km | 37 | 3,8 (2,9–6,9) | 9,8 (8,0–12,8) |
| **Sonra: düşük** | yok (GWA × ulusal medyan R) | 53 | 5,6 (4,6–7,8) | 11,5 (10,6–12,6) |

### 2.2 Ezine regresyonu (tam analiz, v1 kalibrasyonu ve tasarımı)

Düzeltmeden **etkilenmedi**, çünkü bu mod v1 matrisini kullanıyor. Kaynak: `outputs/v2B/B5_regresyon.csv`.

| Gelir yapısı | v1 E[NPV] | v2 E[NPV] | Fark | SE |
|---|---|---|---|---|
| YEKDEM opsiyonu | −1,66 | −1,43 | +0,23 | 0,24 |
| Tüccar | −2,11 | −1,88 | +0,23 | 0,24 |
| PPA | −6,05 | −5,93 | +0,12 | 0,18 |

Karar aynı: rafa kaldır, tetikleyicileri izle.

### 2.3 Hızlı ↔ tam tutarlılığı (önce / sonra)

`outputs/v2B/B5_tutarlilik.csv` (önce: `outputs/v2C/once/`). Süreler 2 çekirdek, soğuk tablolar.

| Saha | Hızlı tasarım (önce → sonra) | Hızlı det. NPV | Tam MILP det. NPV | Tam E[NPV] | Tam karar | Tam süre |
|---|---|---|---|---|---|---|
| Ezine | kurulum yok → **RES 54,6 + BESS 30/58** | −6,1 → −4,9 | −4,9 → −1,7 | −7,6 → −7,3 | rafa kaldır | 260 → 480 s |
| Sivas-Gürün | RES 58,8 + BESS 30 → aynı | −1,6 → +3,4 | +1,2 → +5,2 | −3,8 → −1,5 | rafa kaldır | 325 → 465 s |
| Balıkesir-Susurluk | RES 58,8 + BESS 31 → aynı | +4,9 → −0,3 | +4,2 → +0,2 | −3,1 → −7,8 | rafa kaldır | 309 → 537 s |

**Gözlemler:**
- **Ezine.** Ezine artık iki modda da aynı tasarımı seçiyor (RES 13 türbin + batarya). Önceki "kurulum yok / 2 türbin" köşe çözümü, yerleşimin etkisiz olmasından geliyordu.
- **Gürün.** Gürün iyileşti. Komşusu Kangal RES (14 km) zaten E-92 sınıfı türbine eşlendi; k neredeyse değişmedi (1,703 → 1,688). İyileşmenin nedenleri:
  - santral GWA referansı artık Kangal'ın gerçek türbin konumlarından geliyor (R = 1,05);
  - sahada türbin yerleşimi artık etkili.
- **Susurluk.** Susurluk kötüleşti. Komşuları Balıkesir ve Şamlı RES GE103 / 95 m'ye eşlendi; daha yüksek göbek ve daha düşük özgül güç, aynı üretim için daha düşük hız gerektiriyor. k %3–5 düştü (R ≈ 0,88). Ortak E-92 / 80 m vekili bu santrallerin verimini "yüksek rüzgâr" olarak sahaya taşıyordu.
- **Kararlar.** Üç sahada da karar aynı ve hızlı ↔ tam tasarımları aynı.
- **Süre.** Tam analiz süresi arttı. Tasarımlar artık bataryalı ve YEKDEM tablosu da üretiliyor; işletme tabloları Ezine'de 160 → 328 s, MILP 88 → 125 s. Hepsi 600 s hedefinin içinde, ama payı daraldı (§7.1).

### 2.4 Beş saha tipi (önce / sonra)

`outputs/v2B/B5_bes_saha.csv`. Hızlı tarama, varsayılanlar, türbin yerleşimi 2 km.

| Saha tipi | Güven | RES KF önce → sonra | RES başabaş [$/MWh] önce → sonra | En iyi std. tasarım NPV [M$] | Süre |
|---|---|---|---|---|---|
| Kıyı rüzgârlı: Karaburun | yüksek (tek komşu) | %22,1 → **%24,6** | 94,5 → 84,8 | −14,4 (GES) | 4,3 s |
| İç Anadolu: Sivas-Kangal | düşük | %31,0 → %31,8 | 69,1 → 67,8 | −10,7 (RES) | 3,5 s |
| Güneşli güney: Karaman | düşük | %16,2 → %16,8 | 125,6 → 122,2 | −14,2 (GES) | 3,6 s |
| Düşük rüzgârlı: Polatlı | düşük | %18,3 → %18,6 | 106,7 → 105,5 | −15,3 (GES) | 3,5 s |
| Dağlık: Palandöken | düşük | %27,6 → %28,4 | 81,9 → 79,8 | −19,3 (GES) | 3,6 s |

**Karaburun (tek komşu, sırt dışı nokta):**
- Seçilen nokta (38,63 / 26,51) sırtta değil. GWA 2 km yerleşimle 7,38 m/s; dayandığı tek komşu Yaylaköy RES'in türbinleri ise 9,15 m/s'de.
- Tahmin %24,6. Yaylaköy'ün gözlenen KF'si %32,8 (talimat saatleri hariç).
- Fark, R'nin tek santralden taşınmasından ve noktanın rüzgârından geliyor: aynı ilçede en rüzgârlı aday noktalarda ön tarama hücresi %43,7 veriyor (aşağıda, en iyi 10 hücre).
- Uygulama bu durumda "tek komşu" uyarısı veriyor ve il/ilçe yoluyla sırt adaylarını gösteriyor.
- Dersi: bir noktanın rüzgârı, seçilen 2 km'lik pencerenin içindekiyle sınırlı; sırt seçimi kullanıcıya bırakılıyor.

## 3. Türkiye ön tarama haritası (C2)

`src/v2_C2_on_tarama.py` → `data/atlas/on_tarama.parquet` (repoya girer).

**Ne hesaplanıyor.** Her kara hücresinin temsilî noktasında, varsayılan ayarlarla:
- 50 MW bağlantı, baz fiyat 58 $/MWh, türbin yerleşimi 2 km;
- hızlı taramanın deterministik kısmı:
  - RES/GES KF ve güven seviyesi,
  - RES ve GES başabaş fiyatı,
  - 4 standart tasarımın NPV'si,
  - en iyi tasarım (baz fiyatta en yüksek NPV) ve onun başabaş fiyatı.

**Harita.**
- Varsayılan katman: en iyi tasarımın başabaş fiyatı. Diğer katmanlar: RES/GES başabaş, RES/GES KF.
- Renk: tek tonlu mavi sıralı skala, 6 eşit yüzdelik sınıf. Koyu = daha cazip. Renk körlüğünde sıralama açıklıkla korunur.
- Düşük güvenli hücreler soluk dolgu ve kesikli kenarla ayrılır.
- Kalibre santraller ayrı, açılıp kapatılabilen katmandır; araç ipucunda gözlenen KF ve türbin vekili görünür.

**Sonuçlar:**
- **Kapsam:** 1.464 / 1.464 hücre hatasız; 1.833 s (7 süreç); 116 KB.
- **KF dağılımı:** RES KF medyanı %20,5 (P10 %8,4, P90 %33,0). GES KF medyanı %20,0 (%17,3–%21,6).
- **En iyi tasarımın başabaşı:** medyan 90 $/MWh (P10 65, en düşük 46,8).
- **En iyi standart tasarım:** 1.141 hücrede GES (RES zayıf olduğu için), 244 hücrede RES, 79 hücrede RES %30 fazla kurulum.
- **Baz fiyatın altı:** 66 hücrede başabaş 58 $/MWh'in altında, 132'sinde 63,8'in (×1,10) altında. Bunlar deterministik değerler; tam analizin Monte Carlo'su genellikle daha düşük E[NPV] veriyor (v1 dersi).
- **Güven:** 134 hücre yüksek, 1.330 düşük.

**Başabaş fiyatı en düşük 10 hücre:**

| # | İl / ilçe | Hücre noktası | RES KF | Güven (komşu) | En iyi tasarım | Başabaş [$/MWh] |
|---|---|---|---|---|---|---|
| 1 | Çanakkale / Gökçeada | 40,21 / 25,79 | %47,2 | düşük (yok) | RES +%30 | 46,8 |
| 2 | Hatay / Belen | 36,50 / 36,25 | %47,3 | yüksek (Atik, Belen RES) | RES +%30 | 47,2 |
| 3 | Tekirdağ / Çerkezköy | 41,25 / 28,00 | %46,6 | yüksek (Yamaçtepe RES) | RES +%30 | 47,2 |
| 4 | İzmir / Bergama | 39,25 / 27,25 | %45,2 | yüksek (Kınık RES) | RES +%30 | 47,9 |
| 5 | Bursa / Karacabey | 40,39 / 28,50 | %44,3 | yüksek (Harmanlık, Karacabey RES) | RES +%30 | 48,6 |
| 6 | İzmir / Karaburun | 38,66 / 26,37 | %43,7 | düşük (yok) | RES +%30 | 48,8 |
| 7 | Manisa / Soma | 39,25 / 27,50 | %44,0 | yüksek (Kınık RES) | RES +%30 | 48,9 |
| 8 | Edirne / Lalapaşa | 41,99 / 26,79 | %43,7 | yüksek (Süloğlu RES) | RES +%30 | 49,0 |
| 9 | Sivas / Gürün | 38,75 / 36,75 | %45,7 | düşük (yok) | RES +%30 | 49,4 |
| 10 | Edirne / Lalapaşa | 41,95 / 26,59 | %42,5 | yüksek (Süloğlu RES) | RES +%30 | 50,2 |

**Bilinen rüzgârlı bölgelerde makullük** (`src/v2_C2_harita_kontrol.py` → `outputs/v2C/C2_harita_kontrol.csv`). Model hücre KF'si modern türbin (E-141 sınıfı, 105–135 m) ve 2 km yerleşimle; santraller çoğunlukla 2,3–3,3 MW, 85–100 m.

| Bölge | Hücre KF medyan / en yüksek | En düşük başabaş | Santral gözlenen KF medyan / en yüksek | Santralin hücresinde model KF (medyan) |
|---|---|---|---|---|
| Biga yarımadası | %34,9 / %44,3 | 51,0 | %30,8 / %39,3 (7 santral) | %35,9 |
| Karaburun | %32,4 / %33,2 | 62,2 | %32,8 (1) | %31,6 |
| İzmir kuzeyi (Aliağa–Bergama–Soma) | %37,2 / %45,2 | 47,9 | %35,0 / %45,3 (11) | %37,8 |
| Hatay | %14,2 / %47,3 | 47,2 | %32,6 / %33,5 (4) | %41,2 |
| Sivas | %26,5 / %39,0 | 56,8 | %30,2 / %41,3 (3) | %33,9 |

**Değerlendirme:**
- Model, santrallerin bulunduğu hücrelerde gözlenen KF'nin 1–5 puan üstünde. Karaburun'da 1 puan altında; Hatay'da 9 puan üstünde (Belen'deki santraller 85–95 m'de eski türbinli).
- Bu, daha büyük rotorlu ve daha yüksek göbekli modern türbinden beklenen yön ve büyüklük.
- Bölgelerin en iyi hücreleri (%44–47) Türkiye'nin en iyi işletmedeki santralleriyle (Soma bölgesi %45,3) aynı düzeyde.
- Bilinen rüzgârlı bölgelerde gözlenen modern santrallerin altında kalan bir sonuç yok.
- Gökçeada ve Gürün en iyi 10'da ama düşük güvenli (30 km içinde kalibre santral yok): saha ölçümü olmadan karar verilmemeli.

## 4. Saha seçimi ve analiz akışı (C3–C4)

**Üç seçim yolu:**
- **Haritadan tıklama:** `streamlit-folium`, `last_clicked`.
- **Koordinat girme.**
- **İl/ilçe:** ilçe içinde GWA 1 km'ye göre en rüzgârlı 5 nokta; aralarında ≥ 3 km (açgözlü seçim); haritada numaralı. Kullanıcı birini seçer.

**Seçilen noktada anında** (analiz çalıştırmadan, < 1 s):
- il/ilçe;
- GWA 100 m hızı (nokta ve türbin yerleşimi);
- güven seviyesi ve tipik / %90 hata;
- dayandığı komşu santraller (ad, mesafe); tek komşu ise ayrı uyarı;
- ön tarama hücresinin değerleri ve Türkiye yüzdeliği.

**Varsayımlar paneli:**
- Temel: bağlantı MW, proje aşaması, fiyat senaryosu, gelir yapıları.
- Gelişmiş: türbin yerleşimi ve yarıçap, azami RES/GES, serbest fiyat, kanibalizasyon, WACC, CAPEX çarpanları, SFK.
- Hepsi varsayılanlı, sınır kontrollü (`dogrula`) ve açıklamalı.

**Hızlı tarama ekranı.** Yatırım kararı ifadesi kullanılmaz; öne çıkan:
- en iyi standart tasarımın **başabaş fiyatı** ve **Türkiye yüzdeliği**;
- "Tam analize değer mi?" değerlendirmesi:

  | Durum | Başabaş / senaryo fiyatı |
  |---|---|
  | Değer | ≤ 1,10, ya da temsilî gün optimumu pozitif |
  | Sınırda | ≤ 1,25 |
  | Değmez | > 1,25 |

  Eşikler: `config v2.uygulama.tam_analize_deger`.
- KF'ler ve belirsizlik bandı, yakalanma oranları, LCOE, standart tasarımlar ve hızlı optimizasyon, gün içi/aylık profiller;
- kural tabanlı gerekçeler.

**Tam analiz.**
- Tek tuşla başlar. Sırada iş varsa "Sıradasınız: n" gösterilir; ilerleme çubuğu adım adım ilerler.
- Sonuç ekranı:
  - öneri; tasarım; gelir yapıları (E[NPV], SE, P(NPV>0), CVaR5, P10/P90, IRR);
  - NPV dağılımı; takvim;
  - **güven seviyesinin etkisi**: rüzgâr çarpanının alt/orta/üst üçte birinde E[NPV];
  - tetikleyiciler ve gerekçeler;
  - indirilebilir HTML/PDF saha raporu.
- Tam analiz bitince sonuç ilk sekmede açılır.

**Paylaşım bağlantısı.**
- URL parametreleri: 0,001°'ye yuvarlanmış koordinat, mod ve yalnız varsayılandan farklı varsayımlar.
- Bağlantı açılınca seçim ve varsayımlar yüklenir. Sonuç önbellekteyse (0,01° + varsayımlar + veri sürümü) hesap yapılmadan gösterilir.

## 5. Vaka çalışması, yöntem, dil ve görünüm (C5–C6)

- **Vaka çalışması:** v1.0.0 dashboard'u değiştirilmeden bir sayfa. Başına karar yolculuğu (`results/karar_yolculugu.csv`) ve "bu v1 sonucudur" notu eklendi. Rapor, memo, sunum ve Excel indirmeleri korunuyor.
- **Yöntem:** Doğrulama sayıları `results/v2_dogrulama.json`'dan okunur (`src/v2_C9_sonuclari_paketle.py`).
- **Her sonuç ekranında uyarı bandı:** "ön fizibilite aracıdır, yatırım tavsiyesi değildir; arazi, izin, iz etkisi, şebeke kapasitesi ve yerel koşullar modellenmemiştir".
- **Dil ve sayı biçimi:** TR/EN (sağ üst), TR'de ondalık virgül.
- **Markdown'da `$` kaçışı.** İki `$` arası LaTeX sanılıyordu ("60 /MWh / 92 /MWh"); bu düzeltildi.
- **Palet:** v1 ile aynı.
- **Atıflar:** altbilgide ve Yöntem'de tümü. Copernicus/ERA5, PVGIS, GWA, OSM, geoBoundaries, Copernicus DEM, Natural Earth, EPİAŞ. Open-Meteo artık çalışma anında kullanılmıyor.

## 6. Kötüye kullanım ve gizlilik (C7)

Değerler `config v2.uygulama` ve `v2.motor`.

| Önlem | Değer |
|---|---|
| Oturum başına istek sınırı (kayan pencere) | Saatte 30 hızlı tarama, 3 tam analiz |
| Tam analiz | Aynı anda 1; en fazla 3 iş sırada (fazlası reddedilir) |
| Zaman aşımı | 900 s (bekleme dahil; kullanıcıya anında mesaj, kilit iş bitince bırakılır) |
| Sonuç önbelleği | ≤ 500 MB, en eski erişilenler silinir |

**Gizlilik.**
- Kişisel veri toplanmaz.
- Önbellekte yalnız 0,01°'ye yuvarlatılmış koordinat ve varsayımlar durur.
- Paylaşım bağlantısı yalnız koordinatı ve farklı varsayımları içerir.
- Gizlilik notu Yöntem sayfasında ve altbilgide.

## 7. Test ve doğrulama (C8)

**AppTest** (`tests/test_v2_uygulama.py`):
- açılış ve sayfalar;
- koordinatla seçim ve saha kartı;
- il/ilçe adayları;
- haritadan tıklama (bileşen taklidiyle; Karaburun tek komşu uyarısı);
- hatalı girdi: Ege denizi, Suriye;
- paylaşım bağlantısıyla varsayımların yüklenmesi;
- istek sınırı;
- veri gerektirenler (`-m veri`): hızlı tarama + önbellekten paylaşım, küçük ayarlı tam analiz (`MOTOR_KUCUK=1`: 24 temsilî gün, küçük tablo ızgarası, 500 senaryo; önbellek anahtarı ayrı).

**Gerçek tarayıcı** (`src/v2_C8_tarayici.py`; Playwright + yüklü Chrome; masaüstü 1366 × 900, mobil 390 × 844):
- ekran görüntüleri `docs/img/v2/`;
- her ekranda yatay taşma ve görünüm alanından taşan öğe kontrolü (`outputs/v2C/C8_tasma.csv`).

| Ekran | Masaüstü | Mobil (390 px) | Yatay taşma / taşan görünür öğe |
|---|---|---|---|
| Açılış haritası | `01_acilis_harita_masaustu.png` | `01_acilis_harita_mobil.png` | yok / 0 |
| Saha kartı | `02_saha_karti_masaustu.png` | `02_saha_karti_mobil.png` | yok / 0 |
| Hızlı tarama | `03_hizli_tarama_masaustu.png` | `03_hizli_tarama_mobil.png` | yok / 0 |
| Tam analiz | `04_tam_analiz_masaustu.png` | `04_tam_analiz_mobil.png` | yok / 0 |
| Vaka çalışması | `05_vaka_calismasi_masaustu.png` | `05_vaka_calismasi_mobil.png` | yok / 0 |
| Yöntem | `06_yontem_masaustu.png` | `06_yontem_mobil.png` | yok / 0 |

İlk ölçümde mobilde 6 öğe görünüm alanının dışında sayıldı. İnceleme sonucu ikisi de gerçek taşma değildi:
- Gizli sekme panelindeki koordinat girişleriydi (`checkVisibility() = false`).
- v1 sayfasında kendi içinde kaydırılan sekme çubuğuydu.

Kontrol bunları sayıyordu; artık saymıyor.

**Tarayıcı testinin yakaladığı iki hata (düzeltildi):**
1. **Sonuç gizli sekmede kalıyordu.** Sonuçlar sekmelerdeyken tam analiz bitince sonuç gizli sekmede kalıyordu: Streamlit seçili sekmeyi etiketiyle hatırlıyor. Sekmeler kaldırıldı; en son çalıştırılan mod üstte, diğeri açılır bölümde.
2. **Hızlı sonuç açılır bölümde gizli kalıyordu.** Paylaşım bağlantısı önbellekteki tam sonucu da yüklediğinde, sonradan çalıştırılan hızlı tarama açılır bölümde gizli kalıyordu. "son mod" kuralıyla düzeltildi.

### 7.1 Uçtan uca süreler (2 çekirdek benzetimi)

`outputs/v2C/C8_sure.csv` (soğuk, motor önbellekleri silinmiş) ve `C8_sure_sicak.csv`.
- Sunucu `MOTOR_CEKIRDEK=2`, `OMP_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1` ile başlatıldı.
- Süreler tarayıcıda, düğmeye basıştan sonucun görünmesine kadar ölçüldü.

| Ölçüm | Süre |
|---|---|
| Açılış (yeni sunucu, harita çizilene kadar) | **1,7 s** (masaüstü) / 1,2 s (mobil) |
| Açılış (yeniden yükleme) | **0,4 s** |
| Hızlı tarama (profil önbellekte değil) | **4,1 s** |
| Hızlı tarama (profil önbellekte) | 0,9 s |
| Tam analiz, Ezine (soğuk işletme tabloları) | **438 s** (7,3 dk) |
| Tam analiz (sonuç önbelleğinde / paylaşım bağlantısı) | 0,9 s |

Tam analizin adımları (motor, Ezine):

| Adım | Süre |
|---|---|
| Tam yıl MILP | 125 s |
| İşletme tabloları (tüccar + YEKDEM φ = 1) | 328 s |
| Monte Carlo | 3 s |

Tutarlılık testindeki üç sahada tam analiz 465–537 s sürdü. Hepsi 600 s hedefinin içinde, ama payı Faz B'ye göre daraldı: tasarımlar artık bataryalı ve YEKDEM tablosu üretiliyor.

**Not:** Ölçümler sırasında bir macOS sistem hizmeti (BTLEServer) sürekli bir çekirdeği meşgul ediyordu. Gerçek 2 vCPU'lu bir sunucuda tek iş parçacığı başarımı daha düşük olabilir. Yayın öncesinde işletme tablolarının hızlandırılması önerilir: YEKDEM ve tüccar tablolarının paralel üretimi ya da A ızgarasının sadeleştirilmesi (doğruluk ölçümüyle).

## 8. Sınırlamalar ve yayın öncesi açık işler

- **Harita altlığı:** OpenStreetMap karoları (anahtarsız; yerel kullanım). Herkese açık yayında OSM karo politikası nedeniyle bir karo sağlayıcısı seçilmeli.
- **Kalıcılık:** Sıra ve istek sınırı süreç içidir (tek sunucu süreci). Çok süreçli barındırmada sıra numarası süreçler arası paylaşılmaz; kilit `flock` ile paylaşılır.
- **Güneş:** Profil 0,25° hücrenin temsilî noktasından; dağlık ve kıyı hücrelerinde nokta-özel PVGIS'ten farklı olabilir.
- **Ön tarama:** Hücre başına tek nokta. Hücre içindeki en iyi sırt noktası değil; kullanıcı il/ilçe adaylarıyla daha iyi noktaları görebilir.
- **Veri boyutu:** ERA5 gridi ~0,7 GB, PVGIS gridi ~0,13 GB, GWA 250 m 17 MB. Yayında barındırma servisine taşınacak (`veri_katmani` uzak mod).

## 9. Revizyon R (2026-10-07): ilk 10 makullüğü, adalar, üst sınır, tam analiz süresi

Aktarım kuralı ve modern türbin incelemesinin ayrıntısı: `docs/v2_A_veri_altyapisi.md §5c`.

### 9.1 Aktarım kuralı ve ön tarama

**Kural değişikliği.**
- Kıyı benzerliği artık sürekli bir oran.
- Komşu artığı ulusal medyana büzülüyor: n0 = 2.
- Birini dışarıda bırak doğrulamasında RMSE 7,17 → 6,87 puan (eşleştirilmiş bootstrap farkı −0,30, %90 GA −0,55…−0,07).

Ön tarama yeniden üretildi: 1.464/1.464 hücre, 952 s, 8 süreç. Komşusu olmayan hücreler değişmedi (KF değişiminin medyanı 0).

**Başabaş fiyatı en düşük 10 hücre** (adalar hariç; `outputs/v2C/C2_ilk10.csv`):

| # | İl / ilçe | RES KF | Güven (komşular) | Başabaş [$/MWh] | Önceki sıra |
|---|---|---|---|---|---|
| 1 | İzmir / Karaburun | %43,7 | düşük (yok) | 48,8 | 6 |
| 2 | Manisa / Soma | %43,9 | yüksek (Soma, Geres, Sayalar) | 49,4 | — |
| 3 | Sivas / Gürün | %45,7 ⚠ üst sınır | düşük (yok) | 49,4 | 9 |
| 4 | Hatay / Belen | %45,2 | yüksek (Atik, Belen) | 49,9 | 2 |
| 5 | Bursa / Karacabey | %42,2 | yüksek (Harmanlık, Karacabey) | 50,3 | 5 |
| 6 | İzmir / Çeşme | %42,6 | yüksek (Çeşme) | 50,7 | — |
| 7 | Tekirdağ / Çerkezköy | %42,0 | yüksek (Çanta, Tayakadın, Yamaçtepe) | 50,9 | 3 |
| 8 | İzmir / Urla | %42,0 | düşük (yok) | 51,0 | — |
| 9 | İzmir / Bergama | %41,6 | yüksek (Kınık) | 51,5 | 4 |
| 10 | Çanakkale / Ezine | %42,0 | yüksek (Sares, Enerjisa, Çamseki) | 51,9 | 26 |

**Listeden çıkanlar.**
- Gökçeada (ada; artık varsayılan olarak hariç).
- İki Edirne/Lalapaşa hücresi: tek komşu Süloğlu'nun yüksek artığı büzüldü.

**Bölge sayımı** (ilk 50'deki hücre):
- Trakya: 14 → 7.
- Balıkesir/Biga: 10 → 17.

### 9.2 Adalar ve üst sınır

**Adalar.**
- 7 ada hücresi tespit edildi: Gökçeada 4, Bozcaada 1, Marmara 2.
- Sıralamalardan (ilk 10, Türkiye yüzdeliği) varsayılan olarak çıkarılıyor. Haritanın altındaki "en düşük başabaşlı 10 hücre" tablosunda "Adaları dahil et" anahtarıyla eklenebiliyor.
- Haritada mor noktalı kenarla gösteriliyor.
- Saha kartında ve analiz sonuçlarında uyarı çıkıyor: "50 MW ölçeğinde bağlantı denizaltı kablosu gerektirir; maliyeti modelde yok". Bilinen bağlantı durumu da gösteriliyor (§5c; doğrulanamayan kısımlar açıkça belirtiliyor).

**Üst sınır.**
- Eşik: tahmini RES KF ≥ %45,6, yani Türkiye'de gözlenen en yüksek santral KF'si (Geres RES).
- İşaretli hücreler: Gökçeada %47,2 ve Gürün %45,7.
- Haritada kalın siyah kenar; saha kartında ve sonuçlarda "üst sınıra yakın, ihtiyatla değerlendirin".
- Belen yeni kuralla %45,2 ve eşiğin hemen altında. Karmaşık arazide 2 km yerleşimin seçtiği sırt hücrelerinin (GWA 9,4) santral konumlarından belirgin biçimde rüzgârlı olduğu, §5c'de ayrıca not edildi.

### 9.3 Tam analiz süresi (hedef ≤ 5 dk, 2 çekirdek, ilk kez)

`src/v2_R5_tam_hiz.py` → `outputs/v2R/R5_tam_hiz.csv`. Her çalıştırma ayrı süreçte; işletme tablosu ve sonuç önbellekleri silinmiş.

**Profil (önce).**

| Adım | Süre | Not |
|---|---|---|
| İşletme tabloları | 199–304 s | Pyomo LP'sinde çözüm başına ~0,85 s; her durumda ~26 bin parametre Python döngüsüyle atanıp amaç ifadesi yeniden kuruluyordu |
| Tam yıl MILP | 255–271 s | Model kurulumu < 1 s; süre dal-sınır ve LP gevşetmesinde. 240 s zaman sınırına çarpıyordu: sınırsız denemede 2.055 s sonra bile %2 boşluk; tamsayılar sabitlenince LP bile > 10 dk |
| Monte Carlo | 2–3 s | Zaten küçük; erken durdurma kazandırmaz |

**Değişiklikler.**
1. **İşletme LP'si doğrudan highspy ile** (`IsletmeLPHizli`).
   - Matris bir kez kuruluyor; her durumda yalnız amaç katsayıları ve üretim dengesinin sağ tarafı vektörel güncelleniyor; çözüm önceki bazdan sıcak başlıyor.
   - Formülasyon birebir aynı: rastgele test durumlarında amaç farkı %0,0 (test: `tests/test_v2_revizyon.py`).
   - ~3,5 kat hızlı.
2. **Kapasite MILP'i 96 temsilî günle** (`config v2.motor.tam_milp_temsili_gun`).
   - 5–15 s'de kesin optimum.
   - 24 / 48 / 96 günün tasarımları tam yıl çözümüyle ±1 türbin, ±1 MW batarya içinde.
   - Tasarımın değeri zaten 10 hava yılı × 8760 saatlik işletme tablolarıyla Monte Carlo'da ölçülüyor.
3. **Denenip bırakılanlar.**
   - Temsilî gün çözümünden "N0 ± 2" ile daraltılmış tam yıl MILP'i: zaman sınırında kötü ara çözümde kaldı.
   - Tamsayıları sabitlenmiş tam yıl LP'leri: tek LP > 10 dk.

**Sonuç** (2 çekirdek, soğuk tablolar):

| Saha | Süre önce → sonra | MILP | Tablolar | Tasarım önce → sonra | YEKDEM opsiyonu E[NPV] | Tüccar E[NPV] | P(NPV>0) | Başabaş | Karar |
|---|---|---|---|---|---|---|---|---|---|
| Ezine | 478 → **72 s** | 271 → 5 s | 199 → 63 s | RES 58,8 + 31,7/60 → 58,8 + 31,3/60 | −6,31 → −6,30 | −6,66 → −6,65 | %33,2 → %33,3 | 62,6 → 62,6 | aynı (rafa kaldır) |
| Gürün | 471 → **73 s** | 265 → 6 s | 202 → 63 s | 58,8 + 32,0 → **54,6** + 31,5 | −6,49 → −5,71 | −6,86 → −6,05 | %33,0 → %34,1 | 62,7 → 62,4 | aynı |
| Susurluk | 564 → **94 s** | 255 → 15 s | 304 → 75 s | 58,8 + 32,0 → 58,8 + 31,0 | −5,07 → −5,04 | −5,43 → −5,40 | %35,6 → %35,6 | 61,6 → 61,6 | aynı |

**Yorum.**
- Ezine ve Susurluk'ta sonuçlar standart hatanın (0,19 M$) çok altında değişti.
- Gürün'de 96 günlük MILP 13 türbin seçti. Zaman sınırına takılan tam yıl MILP'i 14 seçmişti. Monte Carlo, 13 türbinli tasarımı 0,8 M$ daha iyi buluyor; yani eski yol optimal değildi.
- Tam analiz artık 2 çekirdekte ~1,5 dakika (hedef ≤ 5 dk).

**Uçtan uca süreler** (tarayıcı, 2 çekirdek; `outputs/v2C/C8_sure.csv`; önce: `outputs/v2R/C8_sure_once.csv`):

| Ölçüm | Önce | Sonra |
|---|---|---|
| Açılış (yeni sunucu) | 1,7 s | 2,2 s |
| Açılış (yeniden yükleme) | 0,4 s | 0,9 s |
| Hızlı tarama | 4,1 s | 4,3 s |
| Tam analiz (arayüz, soğuk tablolar, Ezine) | 438 s | **93 s** |

12 ekranın hiçbirinde taşma yok; ekran görüntüleri yenilendi.

### 9.4 Yeniden üretilen doğrulama tabloları

**Hızlı ↔ tam tutarlılık** (`outputs/v2B/B5_tutarlilik.csv`):

| Saha | Hızlı tasarım | Tam tasarım | Tam E[NPV] (YEKDEM opsiyonu) | Karar |
|---|---|---|---|---|
| Ezine | RES 58,8 + 31/60 | aynı | −6,3 | rafa kaldır |
| Gürün | RES 58,8 + 31/60 | RES 54,6 + 32/60 | −5,7 | rafa kaldır |
| Susurluk | RES 54,6 + 30/60 | RES 58,8 + 31/60 | −5,0 | rafa kaldır |

İki sahada hızlı ve tam analiz 1 türbin (4,2 MW) farklı; hızlı tarama 24, tam analiz 96 temsilî gün kullanıyor. Kararlar aynı.

**Beş saha tipi** (`outputs/v2B/B5_bes_saha.csv`; önce: `outputs/v2R/B5_bes_saha_once.csv`):

| Saha | RES KF önce → sonra | RES başabaş önce → sonra |
|---|---|---|
| Karaburun | %24,6 → **%32,8** | 84,8 → 63,5 |
| Kangal | %31,8 | 67,8 (komşusuz; değişmedi) |
| Karaman | %16,8 | 122,2 (değişmedi) |
| Polatlı | %18,6 | 105,5 (değişmedi) |
| Palandöken | %28,4 | 79,8 (değişmedi) |

**Karaburun'daki değişim.** Tek komşusu Yaylaköy'ün düşük artığı (R 0,78) ulusal medyana çekildi. Sahanın E-141 ile tahmini (%32,8), Yaylaköy'ün GE103 ile gözlenen %32,8'ine denk geliyor. Önceki %24,6, tek santralin artığının aynen taşınmasından kaynaklanan bir eksik tahmindi.
