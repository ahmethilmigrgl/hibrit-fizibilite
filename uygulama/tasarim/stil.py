"""
Uygulama kabuğu: aktif tema, özel CSS, tema algılayıcı betik, logo ve üst çubuk denetimleri (dil + tema).

Tema mekanizması:
- Streamlit'in yerel açık/koyu temaları (.streamlit/config.toml → [theme.light], [theme.dark]) tüm yerleşik öğeleri
  (açılır menüler, tablolar, düğmeler) boyar. Tercih tarayıcıda `stActiveTheme-<yol>-v2` anahtarında tutulur.
- Üst çubuktaki Açık/Koyu düğmesi bu tercihi ve `esik_tema` çerezini yazar, sayfayı yeniden yükler (seçim ve sonuçlar URL
  parametrelerinden ve sonuç önbelleğinden geri gelir).
- Özel CSS iki temanın değişkenlerini birlikte taşır; algılayıcı betik uygulamanın gerçek arka plan rengine bakıp
  <html data-tema="..."> yazar. Böylece CSS, Streamlit'in Ayarlar menüsünden ya da sistemden gelen değişikliklere de uyar;
  Python tarafının (grafik, harita) temasıyla uyuşmazlık görürse bir kez yeniden yükler.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from uygulama.tasarim.tokenlar import ICERIK_GENISLIK, KOSE, METIN_GENISLIK, TEMALAR

KOK = Path(__file__).resolve().parents[2]
MARKA = KOK / "static" / "marka"


# ---------------------------------------------------------------- aktif tema
def aktif_tema() -> str:
    """'acik' | 'koyu'. Sıra: oturumdaki seçim → esik_tema çerezi → Streamlit'in bildirdiği tema → açık."""
    t = st.session_state.get("tema")
    if t in TEMALAR:
        return t
    try:
        t = st.context.cookies.get("esik_tema")
    except Exception:  # test ortamı (AppTest) çerez taşımaz
        t = None
    if t not in TEMALAR:
        try:
            t = "koyu" if st.context.theme.type == "dark" else "acik"
        except Exception:
            t = "acik"
    st.session_state["tema"] = t
    return t


def renk(ad: str) -> str:
    return TEMALAR[aktif_tema()]["renk"][ad]


# ---------------------------------------------------------------- CSS
def _degiskenler(t: dict) -> str:
    r, y = t["renk"], t["yazi"]
    koyu = t["streamlit"] == "dark"
    satir = [f"--{k.replace('_', '-')}:{v};" for k, v in r.items()]
    satir += [
        f"--f-arayuz:'{y['arayuz']}',system-ui,sans-serif;",
        f"--f-sayi:'{y['sayi']}',ui-monospace,monospace;",
        f"--f-baslik:'{y['baslik']}',{'system-ui,sans-serif' if koyu else 'Georgia,serif'};",
        f"--f-kod:'{y['kod']}',ui-monospace,monospace;",
        f"--baslik-agirlik:{t['baslik_agirlik']};",
        f"--k:{KOSE['orta'] if koyu else KOSE['kucuk']}px;",
        f"--sayi-izleme:{'-0.02em' if koyu else '-0.01em'};",
        f"--etiket-donusum:{'uppercase' if koyu else 'none'};",
        f"--etiket-izleme:{'0.08em' if koyu else '0'};",
        f"--etiket-yazi:{'var(--f-kod)' if koyu else 'var(--f-arayuz)'};",
        f"--golge:{'none' if koyu else '0 1px 2px rgba(27,31,29,.05)'};",
    ]
    return "".join(satir)


def css() -> str:
    a, k = TEMALAR["acik"], TEMALAR["koyu"]
    return f"""
:root,html[data-tema="acik"]{{{_degiskenler(a)}}}
html[data-tema="koyu"]{{{_degiskenler(k)}}}

/* ---- kabuk ---- */
[data-testid="stHeader"]{{background:var(--zemin);border-bottom:1px solid var(--cizgi);}}
[data-testid="stMainBlockContainer"]{{max-width:{ICERIK_GENISLIK}px;padding:5.2rem 2rem 3rem;}}
[data-testid="stDecoration"]{{display:none;}}
[data-testid="stLogo"]{{height:2.1rem;max-width:none;}}
[data-testid="stSidebarCollapsedControl"] img,[data-testid="stLogo"]{{margin-right:.5rem;}}
*:focus-visible{{outline:2px solid var(--vurgu)!important;outline-offset:2px!important;}}
::selection{{background:var(--vurgu-zemin);}}

/* Streamlit "çalışıyor" göstergesi: üst çubuktaki dil/tema düğmeleriyle çakışmasın diye sağ altta küçük rozet */
[data-testid="stStatusWidget"]{{position:fixed!important;top:auto!important;bottom:1rem;right:1rem;z-index:999992;background:var(--yuzey);
  border:1px solid var(--cizgi);border-radius:99px;padding:.15rem .6rem;box-shadow:0 2px 10px rgba(0,0,0,.12);}}
/* üst çubuk denetimleri (dil + tema): başlık çubuğuna sabitlenir */
.st-key-ust_kontroller{{position:fixed;top:.62rem;right:1.1rem;z-index:999991;width:auto!important;gap:.4rem;}}
.st-key-ust_kontroller [data-testid="stButtonGroup"] button{{min-height:2rem;padding:0 .7rem;font-size:.8rem;font-weight:600;}}
.st-key-ust_kontroller [data-testid="stElementContainer"]{{width:auto!important;}}

/* ---- yazı ---- */
h1,h2,h3{{font-family:var(--f-baslik)!important;letter-spacing:-0.012em;}}
[data-testid="stMarkdownContainer"] h2{{border-top:1px solid var(--metin);padding-top:.9rem;margin-top:1.6rem;}}
html[data-tema="koyu"] [data-testid="stMarkdownContainer"] h2{{border-top-color:var(--cizgi);}}
[data-testid="stCaptionContainer"]{{color:var(--metin-soluk);}}
code{{font-family:var(--f-kod)!important;}}
[data-testid="stMetricValue"],table,.esik-sayi,[data-testid="stDataFrame"]{{font-variant-numeric:tabular-nums;}}

/* ---- KPI kartı (st.metric) ---- */
[data-testid="stMetric"]{{background:var(--yuzey);border:1px solid var(--cizgi);border-radius:var(--k);padding:.85rem 1rem;
  box-shadow:var(--golge);height:100%;}}
[data-testid="stMetricLabel"] p{{font-size:.8rem;color:var(--metin-soluk);font-family:var(--etiket-yazi);
  text-transform:var(--etiket-donusum);letter-spacing:var(--etiket-izleme);}}
[data-testid="stMetricValue"]{{font-family:var(--f-sayi);font-size:1.55rem;font-weight:600;letter-spacing:var(--sayi-izleme);
  line-height:1.2;}}
html[data-tema="koyu"] [data-testid="stMetricValue"]{{font-weight:500;}}
[data-testid="stMetricValue"] *,[data-testid="stMetricLabel"] *{{white-space:normal!important;overflow:visible!important;
  text-overflow:clip!important;}}
[data-testid="stMetricLabel"]{{height:auto!important;min-height:1.2rem;}}
[data-testid="stMetricDelta"]{{background:transparent!important;padding:0!important;color:var(--metin-soluk)!important;font-size:.76rem;}}
[data-testid="stMetricDelta"] svg{{display:none;}}

/* ---- uyarı kutusu ---- */
[data-testid="stAlertContainer"]{{border-radius:var(--k);border:1px solid color-mix(in srgb,currentColor 22%,transparent);
  padding:.75rem 1rem;}}
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"]{{color:var(--metin);}}

/* ---- düğmeler, sekmeler, genişleticiler, girişler ---- */
.stButton button,.stDownloadButton button,.stLinkButton a{{font-weight:600;min-height:2.6rem;}}
[data-testid="stBaseButton-primary"]{{box-shadow:var(--golge);}}
[data-testid="stExpander"] details{{border-radius:var(--k);background:var(--yuzey);}}
[data-testid="stExpander"] summary p{{font-weight:600;}}
[data-baseweb="tab-list"]{{gap:.25rem;}}
[data-baseweb="tab"] p{{font-weight:600;}}
[data-testid="stProgress"] > div > div{{height:.4rem;border-radius:99px;}}
[data-testid="stCode"] pre{{border:1px solid var(--cizgi);}}

/* ---- grafik ve harita kartları ---- */
[data-testid="stPlotlyChart"]{{background:var(--yuzey);border:1px solid var(--cizgi);border-radius:var(--k);padding:.4rem .5rem .2rem;
  box-shadow:var(--golge);}}
.st-key-harita_kart iframe{{border-radius:var(--k);border:1px solid var(--cizgi)!important;}}
[data-testid="stDataFrame"]{{border-radius:var(--k);}}

/* ---- keyed kartlar ---- */
[class*="st-key-kart_"]{{background:var(--yuzey);border:1px solid var(--cizgi);border-radius:var(--k);padding:1.1rem 1.2rem;
  box-shadow:var(--golge);}}
[class*="st-key-kart_"] [data-testid="stMetric"]{{box-shadow:none;}}
[class*="st-key-kart_"] h4{{font-family:var(--f-baslik)!important;font-size:1.35rem;margin:0;padding:0;}}

/* karar başlık kartı: üst şerit durum renginde; öneri kutusu manşete dönüşür */
[class*="st-key-karar_"]{{background:var(--yuzey);border:1px solid var(--cizgi);border-radius:var(--k);padding:1.2rem 1.3rem 1.1rem;
  box-shadow:var(--golge);border-top:3px solid var(--durum);}}
.st-key-karar_iyi{{--durum:var(--iyi);}} .st-key-karar_uyari{{--durum:var(--uyari);}} .st-key-karar_kotu{{--durum:var(--kotu);}}
[class*="st-key-karar_"] [data-testid="stAlertContainer"]{{background:transparent!important;border:0;padding:0;}}
[class*="st-key-karar_"] [data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] p{{font-family:var(--f-baslik);
  font-size:1.65rem;line-height:1.18;font-weight:var(--baslik-agirlik);color:var(--durum);letter-spacing:-0.01em;}}
[class*="st-key-karar_"] [data-testid="stAlertContainer"] strong:first-child{{display:block;font:600 .72rem/1.2 var(--f-kod);letter-spacing:.14em;
  text-transform:uppercase;color:var(--metin-soluk);margin-bottom:.45rem;}}
[class*="st-key-karar_"] [data-testid="stMetric"]{{border:0;border-left:1px solid var(--cizgi);border-radius:0;background:transparent;
  padding:.2rem 0 .2rem 1rem;}}
[class*="st-key-karar_"] [data-testid="stMetricValue"]{{font-size:2.1rem;}}

/* indirme kartları */
.st-key-indir_kartlari .stDownloadButton button,.st-key-indir_kartlari .stLinkButton a{{justify-content:flex-start;text-align:left;
  min-height:4rem;padding:.8rem 1rem;background:var(--yuzey);border:1px solid var(--cizgi);box-shadow:var(--golge);}}
.st-key-indir_kartlari .stDownloadButton button:hover,.st-key-indir_kartlari .stLinkButton a:hover{{border-color:var(--vurgu);}}
.st-key-indir_kartlari [data-testid="stIconMaterial"]{{color:var(--vurgu);}}

/* uzun metin sayfaları (Vaka, Yöntem): okunaklı satır uzunluğu */
html[data-sayfa="vaka"] [data-testid="stMarkdownContainer"] :is(p,li),html[data-sayfa="yontem"] [data-testid="stMarkdownContainer"] :is(p,li)
  {{max-width:{METIN_GENISLIK};line-height:1.65;}}
html[data-sayfa="vaka"] [data-testid="stCaptionContainer"] p,html[data-sayfa="yontem"] [data-testid="stCaptionContainer"] p{{max-width:{METIN_GENISLIK};}}

/* ---- HTML bileşenleri (bilesenler.py) ---- */
.esik-kas{{font:600 .72rem/1 var(--f-kod);letter-spacing:.14em;text-transform:uppercase;color:var(--vurgu);margin:0 0 .2rem;}}
.esik-kas.ara{{margin-top:.7rem;}}
.esik-not{{font-size:.8rem;color:var(--metin-soluk);margin-bottom:.2rem;}}
.st-key-giris h1{{font-size:clamp(2rem,1.2rem + 2.6vw,3.1rem)!important;line-height:1.06!important;font-weight:var(--baslik-agirlik)!important;
  max-width:19ch;padding:.2rem 0 .6rem!important;}}
html[data-tema="koyu"] .st-key-giris h1{{max-width:24ch;font-size:clamp(1.8rem,1.1rem + 2vw,2.5rem)!important;}}
.st-key-giris_kompakt h1{{font-size:1.5rem!important;padding:0!important;font-weight:var(--baslik-agirlik)!important;}}
.esik-giris{{font-size:1.08rem;color:var(--metin-soluk);max-width:60ch;margin:0 0 1rem;line-height:1.55;}}
.esik-eylem{{display:flex;gap:1rem;align-items:center;flex-wrap:wrap;}}
.esik-cta{{display:inline-flex;align-items:center;gap:.5rem;background:var(--vurgu);color:var(--vurgu-metin)!important;font-weight:600;
  padding:.65rem 1.05rem;border-radius:var(--k);text-decoration:none!important;font-size:.93rem;}}
.esik-cta:hover{{filter:brightness(1.08);}}
.esik-cta2{{display:inline-flex;align-items:center;gap:.4rem;color:var(--metin)!important;font-weight:500;font-size:.93rem;text-decoration:none!important;}}
.esik-cta2:hover{{color:var(--vurgu)!important;}}
.esik-oneler{{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--cizgi);border-radius:var(--k);background:var(--yuzey);
  box-shadow:var(--golge);}}
.esik-one{{padding:1rem 1.1rem;border-left:1px solid var(--cizgi);}} .esik-one:first-child{{border-left:0;}}
.esik-one b{{display:block;font:600 1.75rem/1.1 var(--f-sayi);letter-spacing:-0.02em;color:var(--metin);font-variant-numeric:tabular-nums;}}
html[data-tema="koyu"] .esik-one b{{font-weight:500;}}
.esik-one b small{{font-size:.8rem;font-weight:500;color:var(--metin-soluk);margin-left:.2rem;letter-spacing:0;}}
.esik-one span{{display:block;font-size:.8rem;color:var(--metin-soluk);margin-top:.25rem;line-height:1.35;}}
.esik-ikon{{font-family:'Material Symbols Rounded';font-weight:400;font-style:normal;line-height:1;letter-spacing:normal;text-transform:none;
  display:inline-block;white-space:nowrap;direction:ltr;-webkit-font-feature-settings:'liga';font-feature-settings:'liga';
  -webkit-font-smoothing:antialiased;flex:none;vertical-align:-.2em;}}

.esik-adim{{display:flex;border:1px solid var(--cizgi);border-radius:var(--k);background:var(--yuzey);overflow:hidden;margin:.2rem 0 .4rem;
  box-shadow:var(--golge);}}
.esik-adim > div{{flex:1;display:flex;align-items:center;gap:.6rem;padding:.65rem .9rem;border-left:1px solid var(--cizgi);min-width:0;}}
.esik-adim > div:first-child{{border-left:0;}}
.esik-adim i{{font:600 .72rem/1.45rem var(--f-kod);font-style:normal;width:1.45rem;height:1.45rem;text-align:center;border-radius:50%;
  border:1px solid var(--cizgi);color:var(--metin-soluk);flex:none;}}
.esik-adim .ad{{font-size:.88rem;color:var(--metin-soluk);white-space:nowrap;}}
.esik-adim .not{{font-size:.75rem;color:var(--metin-soluk);margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  font-variant-numeric:tabular-nums;}}
.esik-adim .aktif{{box-shadow:inset 0 -2px 0 var(--vurgu);}}
.esik-adim .aktif .ad{{color:var(--metin);font-weight:600;}}
.esik-adim .aktif i{{background:var(--vurgu);color:var(--vurgu-metin);border-color:var(--vurgu);}}
.esik-adim .tamam .ad{{color:var(--metin);}}
.esik-adim .tamam i{{background:var(--vurgu-zemin);color:var(--vurgu);border-color:transparent;}}

.esik-rozet{{display:inline-flex;align-items:center;gap:.4rem;font:600 .74rem/1 var(--f-arayuz);padding:.32rem .6rem;border-radius:99px;
  border:1px solid currentColor;white-space:nowrap;vertical-align:middle;}}
.esik-rozet::before{{content:"";width:.42rem;height:.42rem;border-radius:50%;background:currentColor;}}
.esik-rozet.iyi{{color:var(--iyi);background:var(--iyi-zemin);}} .esik-rozet.uyari{{color:var(--uyari);background:var(--uyari-zemin);}}
.esik-rozet.kotu{{color:var(--kotu);background:var(--kotu-zemin);}} .esik-rozet.bilgi{{color:var(--bilgi);background:var(--bilgi-zemin);}}
.esik-rozet.notr{{color:var(--metin-soluk);background:var(--yuzey2);}}

.esik-bolum{{display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap;border-top:1px solid var(--metin);padding-top:.7rem;margin:1.6rem 0 .3rem;}}
html[data-tema="koyu"] .esik-bolum{{border-top-color:var(--cizgi);}}
.esik-bolum h3{{font-family:var(--f-baslik);font-size:1.3rem;font-weight:var(--baslik-agirlik);margin:0;padding:0;line-height:1.2;color:var(--metin);}}
html[data-tema="koyu"] .esik-bolum h3{{font:600 .8rem/1.2 var(--f-kod);letter-spacing:.14em;text-transform:uppercase;color:var(--metin-soluk);}}
.esik-bolum span{{font-size:.82rem;color:var(--metin-soluk);}}

.esik-tablo-kap{{overflow-x:auto;border:1px solid var(--cizgi);border-radius:var(--k);background:var(--yuzey);box-shadow:var(--golge);}}
.esik-tablo{{width:100%;border-collapse:collapse;font-size:.86rem;}}
.esik-tablo th{{text-align:right;font:600 .74rem/1.3 var(--etiket-yazi);color:var(--metin-soluk);padding:.6rem .8rem;border-bottom:1px solid var(--cizgi);
  text-transform:var(--etiket-donusum);letter-spacing:var(--etiket-izleme);white-space:nowrap;background:var(--yuzey2);}}
.esik-tablo td{{text-align:right;padding:.58rem .8rem;border-bottom:1px solid var(--cizgi);font-family:var(--f-sayi);white-space:nowrap;}}
.esik-tablo tr:last-child td{{border-bottom:0;}}
.esik-tablo th:first-child,.esik-tablo td:first-child{{text-align:left;font-family:var(--f-arayuz);white-space:normal;}}
.esik-tablo tr.vurgulu td{{background:var(--vurgu-zemin);}}
.esik-tablo tr.vurgulu td:first-child{{box-shadow:inset 3px 0 0 var(--vurgu);font-weight:600;}}
.esik-tablo td.negatif{{color:var(--kotu);}}

.esik-liste{{list-style:none;margin:0;padding:0;}}
.esik-liste li{{position:relative;padding:.55rem 0 .55rem 1.3rem;border-top:1px solid var(--cizgi);font-size:.93rem;line-height:1.5;}}
.esik-liste li:last-child{{border-bottom:1px solid var(--cizgi);}}
.esik-liste li::before{{content:"";position:absolute;left:.15rem;top:1.05rem;width:.45rem;height:.45rem;border-radius:2px;background:var(--vurgu);}}
.esik-liste.uyari li::before{{background:var(--uyari);}}

.esik-bos{{border:1px dashed var(--cizgi);border-radius:var(--k);padding:1.4rem 1.2rem;text-align:center;color:var(--metin-soluk);
  font-size:.9rem;background:var(--yuzey);}}
.esik-bos .esik-ikon{{color:var(--vurgu);display:block;margin:0 auto .45rem;width:max-content;}}
.esik-bos b{{display:block;color:var(--metin);font-size:1rem;margin-bottom:.25rem;}}

.esik-iskelet{{display:grid;gap:.8rem;}}
.esik-iskelet .satir{{display:grid;grid-template-columns:repeat(var(--n,4),1fr);gap:.8rem;}}
.esik-iskelet .blok{{height:var(--h,5.2rem);border-radius:var(--k);background:linear-gradient(90deg,var(--iskelet) 25%,var(--iskelet-parlak) 37%,var(--iskelet) 63%);
  background-size:400% 100%;animation:esik-parilti 1.4s ease infinite;}}
@keyframes esik-parilti{{0%{{background-position:100% 50%}}100%{{background-position:0 50%}}}}
@media (prefers-reduced-motion:reduce){{.esik-iskelet .blok{{animation:none;}}}}
.esik-sira{{display:flex;gap:.8rem;align-items:center;padding:.9rem 1rem;border:1px solid var(--cizgi);border-radius:var(--k);background:var(--yuzey);}}
.esik-sira b{{font:600 1.6rem/1 var(--f-sayi);color:var(--vurgu);}}

.esik-lejant{{display:flex;flex-wrap:wrap;gap:.6rem 1.4rem;align-items:flex-end;font-size:.78rem;color:var(--metin-soluk);padding:.55rem .1rem 0;}}
.esik-lejant .baslik{{color:var(--metin);font-weight:600;font-size:.8rem;margin-bottom:.3rem;}}
.esik-lejant .siniflar{{display:flex;gap:2px;}}
.esik-lejant .sinif{{display:flex;flex-direction:column;gap:.2rem;min-width:2.6rem;}}
.esik-lejant .sinif i{{height:.6rem;display:block;border-radius:1px;}}
.esik-lejant .sinif span{{font-family:var(--f-sayi);font-variant-numeric:tabular-nums;font-size:.7rem;white-space:nowrap;}}
.esik-lejant .anahtar{{display:flex;gap:1rem;flex-wrap:wrap;}}
.esik-lejant .anahtar span{{display:inline-flex;align-items:center;gap:.35rem;}}
.esik-lejant .anahtar i{{display:inline-block;width:.85rem;height:.85rem;border-radius:2px;}}

.esik-alt{{font-size:.74rem;color:var(--metin-soluk);line-height:1.55;border-top:1px solid var(--cizgi);margin-top:2.5rem;padding-top:1rem;}}
.esik-alt a{{color:var(--metin-soluk);}}

/* ---- mobil ---- */
@media (max-width:640px){{
  [data-testid="stMainBlockContainer"]{{padding:4.6rem 1rem 2.5rem;}}
  /* KPI satırları mobilde ikişer ikişer (Streamlit sütunları normalde alt alta dizer) */
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]){{flex-flow:row wrap;gap:.6rem;}}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"]{{
    flex:1 1 calc(50% - .3rem)!important;min-width:calc(50% - .3rem)!important;width:auto!important;}}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"]:not(:has([data-testid="stMetric"])){{
    flex-basis:100%!important;min-width:100%!important;}}
  [data-testid="stMetric"]{{padding:.65rem .75rem;}}
  [data-testid="stMetricLabel"] p{{font-size:.72rem;}}
  /* dar ekranda başlık çubuğunda gezinme düğmesine yer kalsın: denetimler içeriğin en üstünde, sağa yaslı */
  .st-key-ust_kontroller{{position:static;margin:0 0 .6rem;justify-content:flex-end;width:100%!important;}}
  .st-key-ust_kontroller [data-testid="stButtonGroup"] button{{padding:0 .55rem;}}
  .esik-oneler{{grid-template-columns:repeat(3,1fr);}}
  .esik-one{{padding:.7rem .65rem;}} .esik-one b{{font-size:1.25rem;}} .esik-one span{{font-size:.7rem;}}
  .esik-adim > div{{padding:.55rem .6rem;justify-content:center;}}
  .esik-adim .not{{display:none;}}
  .esik-adim > div:not(.aktif) .ad{{display:none;}}
  [class*="st-key-karar_"] [data-testid="stMetric"]{{border-left:0;border-top:1px solid var(--cizgi);padding:.6rem 0 0;}}
  [class*="st-key-karar_"]{{padding:1rem;}}
  [class*="st-key-karar_"] [data-testid="stMetricValue"]{{font-size:1.7rem;}}
  [class*="st-key-karar_"] [data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] p{{font-size:1.4rem;}}
  [data-testid="stMetricValue"]{{font-size:1.3rem;}}
  .esik-tablo .gizle-m{{display:none;}}
  .esik-giris{{font-size:1rem;}}
}}
"""


# ---------------------------------------------------------------- betik
def _betik(py_tema: str, yenile: str | None, sayfa: str = "") -> str:
    """Tema algılayıcı. yenile: 'acik' | 'koyu' verilirse tercihi yazar ve sayfayı yeniden yükler. sayfa: <html data-sayfa>
    (sayfaya özgü CSS için; :has() seçicisi her DOM değişikliğinde stil hesabını pahalılaştırdığından kullanılmaz)."""
    hedef = "" if yenile is None else ("Light" if yenile == "acik" else "Dark")
    return f"""<script>
(function(){{
  const py = "{py_tema}", hedef = "{hedef}";
  document.documentElement.setAttribute("data-sayfa", "{sayfa}");
  const yollar = () => {{
    const p = window.location.pathname.replace(/\\/(vaka|yontem)\\/?$/, "/");
    const kok = p.endsWith("/") ? p : p + "/";
    return [kok, kok + "vaka", kok + "yontem", window.location.pathname];
  }};
  const yaz = (ad) => {{
    try {{ for (const y of yollar()) localStorage.setItem("stActiveTheme-" + y + "-v2", JSON.stringify(ad)); }} catch (e) {{}}
    document.cookie = "esik_tema=" + (ad === "Dark" ? "koyu" : "acik") + ";path=/;max-age=31536000;SameSite=Lax";
  }};
  if (hedef) {{ yaz(hedef); setTimeout(() => window.location.reload(), 60); return; }}
  const algila = () => {{
    const el = document.querySelector('[data-testid="stApp"]') || document.body;
    const m = getComputedStyle(el).backgroundColor.match(/\\d+/g);
    if (!m) return null;
    const L = (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
    return L < 0.5 ? "koyu" : "acik";
  }};
  const uygula = () => {{
    const t = algila();
    if (!t) return;
    document.documentElement.setAttribute("data-tema", t);
    if (t !== py) {{
      // Streamlit Ayarlar menüsü ya da sistem teması değişti: Python tarafı (grafik, harita) yeni temayla çizilsin
      const k = "esik_tema_yenileme";
      const n = +(sessionStorage.getItem(k) || 0);
      document.cookie = "esik_tema=" + t + ";path=/;max-age=31536000;SameSite=Lax";
      if (n < 2) {{ sessionStorage.setItem(k, n + 1); window.location.reload(); }}
    }} else {{ sessionStorage.removeItem("esik_tema_yenileme"); }}
  }};
  if (window.__esikTema) {{ window.__esikTemaPy = py; return; }}
  window.__esikTema = true; window.__esikTemaPy = py;
  setTimeout(uygula, 400);
  new MutationObserver(() => {{ if (algila() !== document.documentElement.getAttribute("data-tema")) setTimeout(uygula, 250); }})
    .observe(document.querySelector('[data-testid="stApp"]') || document.body, {{attributes: true, attributeFilter: ["class", "style"]}});
}})();
</script>"""


# ---------------------------------------------------------------- kabuk
def _tema_degisti() -> None:
    st.session_state["tema"] = st.session_state.get("tema_secim") or st.session_state.get("tema", "acik")
    st.session_state["_tema_yenile"] = True


def uygula(sayfa: str = "") -> str:
    """Her sayfa çalışmasında giriş noktasından çağrılır: CSS, betik, logo, dil ve tema denetimleri. Aktif temayı döndürür.
    sayfa: etkin sayfanın url_path'i (açılış için boş)."""
    from uygulama.ortak import T, dil

    tema = aktif_tema()
    st.html(f"<style>{css()}</style>")
    yenile = st.session_state.pop("_tema_yenile", False)
    st.html(_betik(tema, tema if yenile else None, sayfa), unsafe_allow_javascript=True)
    d = dil().lower()
    logo = str(MARKA / f"logo_{tema}_{d}.svg")
    st.logo(logo, size="large", icon_image=logo)
    with st.container(key="ust_kontroller", horizontal=True, width="content"):
        st.segmented_control("Dil / Language", ["TR", "EN"], key="dil", required=True, label_visibility="collapsed", width="content")
        st.session_state.setdefault("tema_secim", tema)
        st.segmented_control(
            T("Tema", "Theme"),
            list(TEMALAR),
            key="tema_secim",
            required=True,
            label_visibility="collapsed",
            format_func=lambda t: {"acik": ":material/light_mode: ", "koyu": ":material/dark_mode: "}[t] + T(*TEMALAR[t]["ad"]),
            on_change=_tema_degisti,
            width="content",
        )
    return tema
