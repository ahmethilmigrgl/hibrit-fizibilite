# Arayüz tasarımı — Adım 1: mevcut durum ve iki tasarım yönü

## Mevcut arayüz (`once/`)
Ekran görüntüleri: `once/01_acilis_*`, `02_saha_*`, `03_hizli_*`, `04_tam_*`, `05_vaka_*`, `06_yontem_*` (masaüstü 1440 px, mobil 390 px).

Neden sıradan/şablon gibi duruyor:
- **Varsayılan Streamlit iskeleti:** standart başlık + açıklama + `st.metric` sırası, "Deploy" menüsü, sağ üstte tek başına
  duran TR/EN radyo düğmesi; markası, kimliği yok. Gezinmede emoji ikonlar (🗺️ 📘 📐).
- **Açılışta giriş yok:** uygulamanın ne yaptığını söyleyen tek cümle, öne çıkan sayı ya da yönlendirme yok; uzun bir
  başlık ve iki satırlık gri metin.
- **Harita:** renkli OSM karoları veri katmanıyla yarışıyor (yeşil ormanlar, mavi deniz, çok dilli etiketler); lejant
  küçük ve haritadan kopuk; düşük güven gösterimi (kesikli kenar) 1.330 hücrede ızgara gürültüsüne dönüşüyor.
- **Akış görünmüyor:** saha → varsayımlar → hızlı tarama → tam analiz adımları bir ilerleme yapısıyla gösterilmiyor;
  varsayımlar kapalı bir genişletici içinde, boş durum tek satır `st.info`.
- **Sonuç ekranı:** karar en üstte renkli bir `st.warning/error` kutusu; başabaş, NPV ve güven aynı ağırlıkta küçük
  metrikler; sayılar orantılı rakamlarla (hizalanmıyor); grafikler Plotly varsayılanına yakın, başlık ve birimler dağınık.
- **Mobil:** 4'lü metrik satırları alt alta uzun bir sütuna dönüşüyor (hızlı tarama ~5.500 px); karar özeti kayboluyor.

## İki yön

| | **A — Kontrol odası** (`yon_A/`) | **B — Yatırım raporu** (`yon_B/`) |
|---|---|---|
| Hissiyat | Koyu, veri yoğun, enerji ticaret masası / terminal | Açık, editoryal, ferah; yatırım komitesi memosu |
| Zemin / yüzey | `#0b0f0e` / `#121816`, çizgi `#26312c` | Kâğıt `#f8f6f1` / beyaz, çizgi `#e2ddd2` |
| Ana vurgu | Sinyal kehribarı `#f5b53d` (koyu metinle) | Derin çam yeşili `#0f6b57` |
| Durum | iyi `#3fcf8e` · uyarı `#ff9a4d` · kötü `#ff6474` · bilgi `#6cb6ff` | iyi `#1d7a4c` · uyarı `#9a6200` · kötü `#b3261e` · bilgi `#2958a8` |
| Veri renkleri | RES `#5aa9ff`, GES `#ff9a4d`, batarya `#b39bff` | RES `#2f6fb5`, GES `#d06a1f`, batarya `#7a5bc2` |
| Yazı tipi | IBM Plex Sans (arayüz) + **IBM Plex Mono** (sayılar, etiketler) | Newsreader (başlık, serif) + **Public Sans** (arayüz, `tabular-nums`) |
| Kart / KPI | 1 px ızgara çizgisiyle bitişik paneller, büyük harf mono etiketler | Ayrık beyaz kartlar, serif bölüm başlıkları üstte ince kural çizgisi |
| Grafik | Koyu yüzey, noktalı ızgara, mono eksen rakamları | Beyaz yüzey, ince düz ızgara, açıklayıcı alt başlık |
| Harita | Karo yok: koyu kara/deniz altlığı; viridis, **parlak sarı = cazip** | Karo yok: kâğıt kara / açık gri deniz; viridis, **koyu mor = cazip** |

Ortak olanlar (her iki yönde de): karosuz harita altlığı, harita solda + panel sağda (mobilde harita önce gelir), 4 adımlı
ilerleme göstergesi, sonuçta karar başlık kartı (öneri + başabaş fiyatı + beklenen NPV + güven), tabular rakamlar, sade çizgi
ikon seti (emoji yok), WCAG AA kontrast (`uygulama/tasarim/tokenlar.py → kontrast()`; ana metin 15–16:1, soluk metin ≥ 6:1).

**Harita altlığı notu:** CARTO karoları artık API anahtarı istiyor (taslakta filigran çıktı); OSM karoları ise herkese açık
yayında kullanım politikası sorunu taşıyor. Bu yüzden iki yönde de altlık uygulamanın kendi verisinden çiziliyor
(`data/atlas/altlik_tr.geojson`, 303 KB: geoBoundaries il sınırları + Natural Earth kıyıları; `src/v2_tasarim_altlik.py`).
Saha ölçeğinde yakınlaştırınca ayrıntı için OSM, katman menüsünden isteğe bağlı açılabilir.

## İsim ve yazı markası (`marka/`)
1. **Eşik** — projenin kâra geçtiği fiyat eşiği (başabaş). İşaret: RES/GES/batarya sütunları ve yatay eşik çizgisi; eşiği
   aşan kısım vurgu renginde. *(Önerim: uygulamanın ana çıktısını adlandırıyor, kısa, iki dilde söylenebilir.)*
2. **Pafta** — harita paftası; 0,25° ön tarama ızgarası, seçili hücre dolu.
3. **Kerte** — kerteriz; yön halkası ve tek kerte çizgisi.

Dosyalar: `marka/*_isaret.svg` (yalnız işaret, `currentColor` + `--vurgu`), `marka/*_yazi.svg` (işaret + ad), önizleme
`marka/markalar.png` (açık ve koyu zeminde). Taslaklar "Eşik" ile hazırlandı. (Ticari marka taraması yapılmadı; yayından
önce TÜRKPATENT'te bakılmalı.)

## Öneri: **B — Yatırım raporu**
- **Hedef kitle ve amaç:** proje bir yenilenebilir yatırım/proje geliştirme başvurusunun portföy parçası; okuyucu yatırım
  komitesi diliyle düşünen işe alımcı ve yöneticiler. B, sonucu bir yatırım memosu gibi okutuyor: önce karar, sonra kanıt.
  Bu, mevcut Excel modeli, memo ve sunumla (Aşama 8) aynı dili konuşuyor.
- **Okunabilirlik:** uzun metinli Vaka çalışması ve Yöntem sayfaları açık zeminde, serif başlıklarla çok daha rahat
  okunuyor; A'nın koyu terminal hissi sayfalar uzadıkça yoruyor.
- **Harita:** açık altlıkta viridis'in koyu ucu (cazip) en belirgin; A'da sarı hücreler çok parlak ve düşük güvenli hücreler
  koyu zeminde bulanıklaşıyor.
- **Paylaşım ve baskı:** ekran görüntüleri, PDF rapor ve LinkedIn paylaşımlarında açık tema daha iyi duruyor.
- A'nın güçlü yanları B'ye taşınabilir: tabular rakamlı yoğun KPI satırı ve koyu mod (Adım 2'de B'nin koyu kipi A'nın
  paletinden türetilir, böylece iki kip de desteklenir).

Seçiminizi bekliyorum (A, B ya da karışım; isim tercihi).

## Karar (2026-10-07)
Kullanıcı ikisini birden istedi: **açık tema = B (yatırım raporu), koyu tema = A (kontrol odası)**; üst çubuktaki düğmeyle
seçilir (varsayılan: sistem teması). İsim: **Eşik**. Uygulanmış hâli: `docs/v2_tasarim_sistemi.md`, ekran görüntüleri
`sonra/`.
