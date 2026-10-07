# v2 arayüz tasarım sistemi — "Eşik"

Web uygulamasının görünüm katmanı. Hesaplama, analiz motoru, veri ve sonuç değerleri bu katmandan bağımsızdır; burada
yalnız sunum tanımlanır. Tüm dosyalar `uygulama/tasarim/` altında; sayfalar bileşenleri çağırır.

| Dosya | Görev |
|---|---|
| `uygulama/tasarim/tokenlar.py` | **Tek kaynak:** renk, yazı tipi, boşluk, köşe, marka adı, harita skalası, veri paleti |
| `uygulama/tasarim/stil.py` | Aktif tema, özel CSS (iki temanın değişkenleri), tema algılayıcı betik, logo, üst çubuk (dil + tema) |
| `uygulama/tasarim/bilesenler.py` | KPI kartı, güven rozeti, uyarı kutusu, bölüm başlığı, karşılaştırma tablosu, adım göstergesi, boş durum, iskelet, kuyruk kartı, kart/karar kartı kapsayıcıları |
| `uygulama/tasarim/grafik.py` | Ortak Plotly şablonu, `sekil()` ve `ciz()`; koyu temada veri renklerini çevirir |
| `uygulama/tasarim/marka.py`, `logo_yollari.py` | "Eşik" işareti ve yazı markası (SVG; yazı yola çevrilmiş) |
| `uygulama/harita.py` | Ön tarama haritası (folium): karosuz altlık, temaya göre viridis, HTML lejant |
| `.streamlit/config.toml` | Streamlit'in açık/koyu temaları; **üretilir** (`src/v2_tasarim_tema.py`), elle düzenlenmez |
| `static/fonts/`, `static/marka/` | Yerel yazı tipleri (SIL OFL 1.1) ve logo/favicon dosyaları |
| `data/atlas/altlik_tr.geojson` | Harita altlığı (il sınırları + kıyılar; `src/v2_tasarim_altlik.py`) |

Üretim betikleri: `src/v2_tasarim_tema.py` (config + logolar + favicon), `src/v2_tasarim_logo.py` (yazı yolları; geçici
`uv` ortamında fontTools ile), `src/v2_tasarim_altlik.py` (altlık), `src/v2_tasarim_ekran.py` (ekran görüntüleri),
`src/v2_tasarim_sure.py` (önce/sonra süre ölçümü), `src/v2_tasarim_taslak.py` (Adım 1 yön taslakları, tarihsel).
Testler: `tests/test_v2_tasarim.py`.

## 1. İki tema
Kullanıcı üst çubuktaki **Açık / Koyu** düğmesiyle seçer. Varsayılan sistem temasıdır.

| | Açık — "Yatırım raporu" (B yönü) | Koyu — "Kontrol odası" (A yönü) |
|---|---|---|
| Zemin / yüzey / ikinci yüzey | `#f8f6f1` / `#ffffff` / `#f0ede5` | `#0b0f0e` / `#121816` / `#18201d` |
| Çizgi | `#e2ddd2` | `#26312c` |
| Metin / soluk / silik | `#1b1f1d` / `#585f5b` / `#737a75` | `#e7ece9` / `#9aa8a1` / `#7c8a84` |
| Vurgu (ana renk) | çam yeşili `#0f6b57` (üstünde beyaz) | sinyal kehribarı `#f5b53d` (üstünde koyu) |
| Durum: iyi / uyarı / kötü / bilgi | `#1d7a4c` / `#8f5b00` / `#b3261e` / `#2958a8` | `#3fcf8e` / `#ffa45c` / `#ff6f7d` / `#6cb6ff` |
| Başlık yazı tipi | Newsreader (serif, 500) | IBM Plex Sans (600) |
| Arayüz yazı tipi | Public Sans | IBM Plex Sans |
| Sayılar | Public Sans, `tabular-nums` | IBM Plex Mono |
| Kod, küçük etiketler | IBM Plex Mono | IBM Plex Mono (etiketler BÜYÜK HARF) |
| Köşe | 4 px | 6 px |
| Harita altlığı | kâğıt kara `#fbfaf6`, deniz `#e4eaea` | kara `#141b19`, deniz `#0a1416` |

**Kontrast (WCAG AA):** metin ve durum renkleri zemin ve yüzeyde ≥ 4,5:1 (açık metin 14,2:1, koyu 13,9:1); vurgu üstündeki
metin ≥ 6,4:1; durum renkleri kendi açık zeminlerinde ≥ 4,5:1. `metin_silik` yalnız ikincil/süs öğeleri içindir (≥ 3:1).
`tests/test_v2_tasarim.py::test_kontrast_wcag_aa` denetler.

**Tema mekanizması:**
1. Streamlit'in yerel temaları (`[theme.light]`, `[theme.dark]`) yerleşik öğeleri (açılır menü, tablo, düğme, uyarı) boyar.
2. Düğme, tercihi Streamlit'in tarayıcıdaki anahtarına (`stActiveTheme-<yol>-v2`) ve `esik_tema` çerezine yazar, sayfayı
   yeniden yükler. Seçim, sonuç ve dil URL parametrelerinden ve sonuç önbelleğinden geri gelir (seçim anında `url_yaz(None)`).
3. Algılayıcı betik uygulamanın gerçek arka planına bakıp `<html data-tema>` yazar; CSS değişkenleri buna göre seçilir. Tema
   Streamlit'in Ayarlar menüsünden veya sistemden değişirse Python tarafı (grafik, harita) için bir kez yeniden yükler.
4. Python'da aktif tema: `stil.aktif_tema()` (oturum → çerez → `st.context.theme` → açık).

## 2. Veri renkleri ve harita skalası
- **Kategorik veri paleti** v1 grafikleriyle aynı (renk körlüğü için doğrulanmış sıra): RES `#2a78d6`, GES `#eb6834`,
  batarya `#7f6bd1`, koyu mavi `#1d4f91`, gri `#8a8984`. İki ton beyaz yüzeyde ≥ 3:1 grafik kontrastı için koyulaştırıldı:
  hibrit `#15966a`, altın-2 `#a8841a`. Sayfa kodu yalnız bu **kanonik** renkleri kullanır; koyu temada `grafik.ciz()` izleri
  `KOYU_VERI` tonlarına çevirir (RES `#5aa9ff`, GES `#ff8a50` …). Vaka sayfasının sıralı mavi rampaları koyu zeminde ters
  çevrilir (`KOYU_EK`).
- **Harita:** viridis'ten 6 sınıf (eşit yüzdelikler). Açık temada koyu mor, koyu temada parlak sarı = daha cazip; zemine en
  çok karşıtlık veren uç "iyi" uçtur. Viridis algısal olarak düzgündür ve renk körlüğünde sıralama korunur.
- **Güven seviyesi haritada:** yüksek güvenli hücre tam dolu (opaklık 0,86), düşük güvenli hücre soluk (0,34), kenarsız.
  Lejantta iki örnek kare ve kalibre santral simgesi. Sonuç ekranlarında güven rozeti (yüksek = iyi rengi, düşük = uyarı).

## 3. Yazı ve sayı
- Başlık ölçeği (h1…h6): 2,4 / 1,75 / 1,3 / 1,1 / 1 / 0,9 rem. Açılış başlığı `clamp(2rem, …, 3.1rem)`, en çok 19 karakter/satır.
- Uzun metin sayfalarında (Vaka, Yöntem) paragraf genişliği 74ch, satır yüksekliği 1,65 (`<span class="esik-uzun-metin">`).
- Tüm metrik, tablo ve grafik eksen sayıları **tabular rakamlarla**; sayı biçimi değişmedi: `ortak.sayi()` (TR `1.234,5`,
  EN `1,234.5`), grafiklerde `separators` dile göre. Birimler değerin yanında: `$/MWh`, `M$`, `MW`, `MWac`, `%`.
- Yazı tipleri uygulamanın kendi sunucusundan yüklenir (`app/static/fonts`, latin + latin-ext ≈ 320 KB): ziyaretçinin IP'si
  Google Fonts'a gitmez ("kişisel veri toplanmaz" ilkesi korunur).

## 4. Bileşenler (`bilesenler.py`)
| Bileşen | Kullanım | Not |
|---|---|---|
| `kpi_karti(hedef, etiket, deger, yardim, aciklama)` | Tek sayı + etiket + küçük not | `st.metric` üzerine; etiketler testlerde okunur |
| `karar_karti(durum)` | Sonuç ekranının en üstü | Üst şerit durum renginde; içindeki öneri kutusu manşete, metrikler büyük sayılara dönüşür |
| `kart(ad)` | Panel kartı (saha seçimi, saha bilgisi, takvim) | `st.container(key="kart_…")` |
| `uyari_kutusu(metin, durum)` | bilgi / iyi / uyari / kotu | Emoji yerine Material ikon; anlam yalnız renkle verilmez |
| `guven_rozeti(seviye, etiket)`, `rozet()` | Güven, durum etiketleri | Nokta + metin |
| `bolum_basligi(baslik, alt)` | Bölüm ayırıcı | Açıkta serif + üst kural çizgisi; koyuda mono büyük harf |
| `karsilastirma_tablosu(...)` | Tasarımlar, gelir yapıları | Önceden biçimlenmiş metin; en iyi satır vurgulu, negatif NPV kırmızı, mobilde ikincil sütunlar gizli |
| `adim_gostergesi(adimlar, durumlar)` | Saha → varsayımlar → hızlı tarama → tam analiz | Tamamlanan adımlar onaylı; notta seçilen değer/sonuç |
| `giris_onecikanlar(...)` | Açılış: 3 öne çıkan sayı | Sayılar veriden: hücre sayısı, kalibre santral, en düşük başabaş |
| `bos_durum(...)` | Saha seçilmeden önce | |
| `iskelet_html()`, `sira_karti_html()` | Analiz sürerken iskelet görünüm; tam analiz kuyruğu | Hareket azaltma tercihinde animasyon yok |
| `liste(maddeler, tur)` | Gerekçeler, tetikleyiciler, uyarılar | |
| `ikon(ad)` | Satır içi ikon | Material Symbols Rounded (Streamlit'in yerleşik ikon seti; `st.html` SVG'yi temizler) |

İndirme bağlantıları kart olarak: `st.container(key="indir_kartlari")` içindeki `st.download_button` / `st.link_button`.

## 5. Grafik şablonu (`grafik.py`)
- Yazı tipi temanın arayüz yazı tipi; eksen rakamları sayı yazı tipi. Arka plan yüzey rengi; yalnız y ızgarası (açıkta düz,
  koyuda noktalı), x ızgarası yok; eksen çizgisi ve tikleri çizgi renginde.
- Başlık sola yaslı; **açıklayıcı alt başlık** `sekil(..., alt="…")` ile (ör. "Monte Carlo, n = 8000 · gelir yapısına göre").
  Eksen başlıkları birimleriyle ("NPV, milyon $ (reel)", "kapasite faktörü, %").
- Lejant yatay, grafiğin altında (dar ekranda başlıkla çakışmaz); tıklama "yalnız bunu göster".
- Araç çubuğu sade: yakınlaştır/kaydır/sıfırla/PNG indir (2×); Plotly logosu yok.
- Kullanım: `ciz(sekil(fig, baslik, y, x, yukseklik, alt))`. `sekil()` renk yazmaz; renkler şablondan ve kanonik paletten.

## 6. Düzen ve akış
- İçerik sütunu en çok 1400 px; mobilde 16 px kenar boşluğu. Üst çubuk: logo + sayfalar + dil + tema.
- Açılış: giriş bölümü (üst etiket, tek cümlelik başlık, açıklama, "Haritadan saha seç" ve vaka bağlantısı, 3 öne çıkan sayı);
  saha seçilince giriş tek satırlık başlığa küçülür.
- Adım göstergesi → harita (solda, mobilde önce) + panel (sağda: saha seçimi, varsayımlar, saha kartı, analiz düğmeleri).
- Sonuçlar tam genişlikte: karar kartı → KPI satırı → zorunlu uyarı bandı → grafikler → tablolar → gerekçeler → rapor kartları.
- Analiz sürerken sonuç alanında başlık + ilerleme çubuğu + iskelet; tam analiz kuyruğunda sıra kartı. Hatalar "kötü"
  durumlu uyarı kutusunda; boş durum kesik kenarlı kartta.
- Mobil (≤ 640 px): KPI'lar ikişerli ızgara, adım göstergesinde yalnız etkin adımın adı, tabloda ikincil sütunlar gizli.

## 7. Erişilebilirlik
- Kontrast: §1. Odak görünürlüğü: tüm odaklanabilir öğelerde 2 px vurgu rengi çerçeve (`:focus-visible`).
- Harita skalası renk körlüğüne uygun (viridis); düşük güven opaklıkla ve lejantta metinle de belirtilir.
- Durum renkleri her zaman metin/ikonla birlikte (karar kartı manşeti, rozet metni, uyarı ikonu).
- `prefers-reduced-motion` iskelet animasyonunu kapatır. Tema düğmelerinde görünür metin (yalnız ikon değil).

## 8. Kurallar
1. Renk kodu yalnız `tokenlar.py`'de (test: `test_renk_kodlari_yalniz_belirteclerde`; v1'den taşınan vaka sayfası hariç).
2. `tokenlar.py` değişince `.venv/bin/python src/v2_tasarim_tema.py` çalıştırılır (config + logolar); test eşitliği denetler.
3. Yeni grafik: kanonik paletle çiz, `sekil()` ile başlık/alt başlık/birim ver, `ciz()` ile göster. Koyu tema otomatik.
4. Yeni sonuç alanı: önce karar/özet, sonra ayrıntı. Testlerin okuduğu metinler (`st.title`, `st.metric` etiketleri, uyarı
   kutusu metinleri) bileşenler üzerinden korunur.
5. Emoji kullanılmaz; ikonlar Material Symbols (`:material/…:` ya da `bilesenler.ikon`).
6. Marka adı `tokenlar.MARKA`'da; değişirse `src/v2_tasarim_logo.py` (uv + fontTools) ve `src/v2_tasarim_tema.py` yeniden çalıştırılır.

## 9. Ölçümler
`src/v2_tasarim_sure.py` → `outputs/v2_tasarim/sure_olcum.csv` (aynı protokol, önceki sürüm `git archive HEAD` ile ayrı
klasörde, aynı veri ve profil önbelleği, masaüstü 1440 px, medyanlar):

| Ölçüm | Önce | Sonra |
|---|---|---|
| Açılış, soğuk (yeni sunucu, n = 3) | 1,94 s | 1,93 s |
| Açılış, sıcak (yeniden yükleme, n = 5) | 0,88 s | 0,87 s |
| Hızlı tarama: sonuç DOM'da (tarayıcı içi, n = 6) | 2,74 s | 2,84 s |
| Hızlı tarama: ilerleme çubuğu görünür | 0,35 s | 0,41 s |
| Hızlı tarama: sunucu süresi ("Süre" notu) | 2,3 s | 2,4 s |

Açılış değişmedi. Hızlı taramada sonuç ~0,1 s (≈ %4) geç görünüyor: daha zengin sayfanın (karar kartı, HTML bileşenleri,
altlıklı harita) çizimi. Altlık bu yüzden il çokgenleri yerine tek ülke çokgeni + birleştirilmiş sınır çizgileriyle
181 KB'a indirildi (ilk sürüm 303 KB). Playwright'ın `wait_for` ölçümü (2,94 → 3,36 s) yoklama aralığı nedeniyle ~0,5 s'lik
basamaklara yuvarlanır; ince ölçüm tarayıcı içi MutationObserver'dandır. Ekran görüntüleri: `docs/img/tasarim/once/` (önceki arayüz), `docs/img/tasarim/sonra/`
(açık + koyu, masaüstü + mobil), yön taslakları `yon_A/`, `yon_B/`, marka `marka/`.

## 10. Ana dalla birleştirme notu
Bu dal `495110b`'den ayrıldı. Bu sırada `v2-genel` dalına `52b5627` ("Revizyon R") eklendi; aynı dosyalara dokunduğu için
birleştirmede çakışma beklenir. Önerilen yol: `v2-genel`'i bu dala birleştirip çakışan bloklarda **ana dalın işlevini** yeni
bileşenlerle yeniden yazmak:

| Ana daldaki ekleme | Bu daldaki karşılığı |
|---|---|
| `harita.py`: ada / üst sınır hücre kenarı (`#0b0b0b`, `#7f6bd1` noktalı), ipucunda `not` alanı | Kenar renkleri belirteçlerden: üst sınır = `renk["metin"]`, ada = `veri["batarya"]` (koyu temada `KOYU_VERI`); `tooltip` alanlarına `not` eklenir |
| `harita.lejant`: üst sınır ve ada anahtarları | `.esik-lejant .anahtar` içine iki `<span><i …></i>…</span>` (satır içi renk değil, belirteç) |
| `saha_karti`: ada ve üst sınır uyarıları (`st.warning`) | `B.uyari_kutusu(metin, "uyari")`, `with B.kart("saha"):` bloğunun içinde |
| `uyari_listesi`: `kod ∈ {ada, ust_sinir}` → görünür kutu | O kodlar için `B.uyari_kutusu(…, "uyari")`, kalanlar `B.liste(…, "uyari")` |
| Haritanın altında "en düşük 10 hücre" genişleticisi (`tablo`) | Aynı genişletici; tablo `B.karsilastirma_tablosu` ile (sayılar `sayi()` ile biçimlenmiş metin) |

Diğer çakışma adayları: `CLAUDE.md` (iki dal da sona ekledi; ikisi de korunur), `uygulama/servis.py` (yalnız ana dal
değiştirdi, çakışmaz), `.streamlit/config.toml` (üretilen dosya; birleştirmeden sonra `src/v2_tasarim_tema.py` yeniden
çalıştırılır), `docs/img/v2/` ve `outputs/v2C/C8_*` (ana dal yeniden üretti; bu dal dokunmadı).

**Birleştirme tamamlandı (2026-10-07, `v2-genel`).** Yukarıdaki eşleme uygulandı:
- **Harita:** üst sınır kenarı `renk["metin"]`, ada kenarı noktalı `veri["batarya"]` (koyu temada `KOYU_VERI`); ipucunda
  `not` alanı. Lejantın `.anahtar` bölümüne iki satır eklendi.
- **Saha kartı:** ada ve üst sınır uyarıları `B.uyari_kutusu(…, "uyari")` ile kartın içinde; tek komşu uyarısı zaten bu dalda
  aynı bileşendeydi.
- **Sonuç uyarıları:** `ada` / `ust_sinir` kodları görünür kutu, diğerleri `B.liste(…, "uyari")`.
- **İlk 10:** genişletici içinde "Adaları dahil et" anahtarı + `B.karsilastirma_tablosu` (sayılar `sayi()`/`yuzde()` ile).
- **Diğer:** `.streamlit/config.toml` `src/v2_tasarim_tema.py` ile yeniden üretildi. Ekran görüntüleri
  `docs/img/tasarim/birlesim/` (07_* özel uyarı ekranları dahil).
