"""
Arayüz tasarımı — iki tasarım yönünün (A: koyu kontrol odası, B: açık yatırım raporu) statik taslakları ve ekran görüntüleri.

Taslaklar gerçek verilerle üretilir (ön tarama haritası, Ezine hızlı tarama ve tam analiz sonucu motor önbelleğinden); yalnız
görünüm denemesidir, uygulamanın kendisini değiştirmez. Düzen Streamlit'te yapılabilir öğelerle sınırlıdır (üst gezinme,
sütunlar, HTML kartlar, Plotly, folium).

Çalıştırma: .venv/bin/python src/v2_tasarim_taslak.py
Çıktılar: outputs/v2_tasarim/taslak/*.html, docs/img/tasarim/yon_{A,B}/*.jpg, docs/img/tasarim/marka/markalar.png
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK
from src.motor import KullaniciVarsayimlari, onbellekten

# Adım 1 taslak belirteçleri (tarihsel; uygulamanın belirteçleri uygulama/tasarim/tokenlar.py)
VIRIDIS6 = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"]

YONLER: dict[str, dict] = {
    "A": {
        "ad": ("Kontrol odası", "Control room"),
        "kip": "dark",
        "renk": {
            "zemin": "#0b0f0e",
            "yuzey": "#121816",
            "yuzey2": "#18201d",
            "cizgi": "#26312c",
            "metin": "#e7ece9",
            "metin_soluk": "#9aa8a1",
            "metin_silik": "#7c8a84",
            "vurgu": "#f5b53d",  # sinyal kehribarı
            "vurgu_metin": "#0b0f0e",
            "iyi": "#3fcf8e",
            "uyari": "#ff9a4d",
            "kotu": "#ff6474",
            "bilgi": "#6cb6ff",
            "deniz": "#0a1416",
            "kara": "#141b19",
            "sinir": "#2c3833",
        },
        "veri": {"res": "#5aa9ff", "ges": "#ff9a4d", "batarya": "#b39bff", "hibrit": "#3fcf8e", "notr": "#7d8a84"},
        "harita_skala": VIRIDIS6[::-1],  # sınıf 0 (en cazip) = sarı: koyu altlıkta en parlak
        "altlik": "CartoDB dark_matter",
        "yazi": {
            "arayuz": "IBM Plex Sans",
            "sayi": "IBM Plex Mono",
            "baslik": "IBM Plex Sans",
            "google": "family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700",
        },
        "kose": 6,
    },
    "B": {
        "ad": ("Yatırım raporu", "Investment memo"),
        "kip": "light",
        "renk": {
            "zemin": "#f8f6f1",
            "yuzey": "#ffffff",
            "yuzey2": "#f0ede5",
            "cizgi": "#e2ddd2",
            "metin": "#1b1f1d",
            "metin_soluk": "#585f5b",
            "metin_silik": "#8a8f8b",
            "vurgu": "#0f6b57",  # derin çam yeşili
            "vurgu_metin": "#ffffff",
            "iyi": "#1d7a4c",
            "uyari": "#9a6200",
            "kotu": "#b3261e",
            "bilgi": "#2958a8",
            "deniz": "#e6ecec",
            "kara": "#fbfaf6",
            "sinir": "#cfc9bd",
        },
        "veri": {"res": "#2f6fb5", "ges": "#d06a1f", "batarya": "#7a5bc2", "hibrit": "#0f6b57", "notr": "#8a8f8b"},
        "harita_skala": VIRIDIS6[:],  # sınıf 0 (en cazip) = koyu mor: açık altlıkta en belirgin
        "altlik": "CartoDB positron",
        "yazi": {
            "arayuz": "Public Sans",
            "sayi": "Public Sans",
            "baslik": "Newsreader",
            "google": "family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Public+Sans:wght@400;500;600;700",
        },
        "kose": 4,
    },
}


TASLAK = CIKTILAR / "v2_tasarim" / "taslak"
IMG = KOK / "docs" / "img" / "tasarim"
SAHA = {"ad": "Taslak", "enlem": 39.79, "boylam": 26.33}
MARKA = KOK / "docs" / "img" / "tasarim" / "marka"


def sayi(x, d=1):
    x = float(x) + (5e-7 if x >= 0 else -5e-7)
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def rgba(hex_: str, a: float) -> str:
    return "rgba(" + ",".join(str(int(hex_[i : i + 2], 16)) for i in (1, 3, 5)) + f",{a})"


def isaret_svg(boyut=28) -> str:
    s = (MARKA / "esik_isaret.svg").read_text()
    return s.replace('width="32" height="32"', f'width="{boyut}" height="{boyut}"')


IKON = {
    "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "ayar": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "simsek": '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
    "katman": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "indir": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "uyari": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
    "bilgi": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>',
    "dosya": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 13h5M10 17h5"/>',
    "ok": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "imlec": '<path d="M5 3l14 7-6 2-2 6z"/>',
}


def ikon(ad: str, boyut: int = 16) -> str:
    return (
        f'<svg class="ikon" width="{boyut}" height="{boyut}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{IKON[ad]}</svg>'
    )


# ------------------------------------------------------------------ CSS
def css(y: dict) -> str:
    r, f = y["renk"], y["yazi"]
    A = y is YONLER["A"]
    k = y["kose"]
    return f"""
:root{{--zemin:{r["zemin"]};--yuzey:{r["yuzey"]};--yuzey2:{r["yuzey2"]};--cizgi:{r["cizgi"]};--metin:{r["metin"]};
--soluk:{r["metin_soluk"]};--silik:{r["metin_silik"]};--vurgu:{r["vurgu"]};--vurgu-metin:{r["vurgu_metin"]};
--iyi:{r["iyi"]};--uyari:{r["uyari"]};--kotu:{r["kotu"]};--bilgi:{r["bilgi"]};--k:{k}px;
--f-arayuz:'{f["arayuz"]}',system-ui,sans-serif;--f-sayi:'{f["sayi"]}',ui-monospace,monospace;--f-baslik:'{f["baslik"]}',Georgia,serif}}
*{{box-sizing:border-box}} html,body{{margin:0;background:var(--zemin);color:var(--metin);font-family:var(--f-arayuz);
font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}}
.num{{font-family:var(--f-sayi);font-variant-numeric:tabular-nums;letter-spacing:{"-0.02em" if A else "-0.01em"}}}
.ikon{{vertical-align:-3px;flex:none}}
.ust{{display:flex;align-items:center;gap:28px;padding:0 32px;height:60px;border-bottom:1px solid var(--cizgi);
background:{"var(--zemin)" if A else "var(--yuzey)"};position:sticky;top:0;z-index:5}}
.logo{{display:flex;align-items:center;gap:10px;color:var(--metin);font-weight:600;font-size:18px;letter-spacing:-0.01em}}
.logo small{{display:block;font:500 10px/1 var(--f-sayi);letter-spacing:.12em;color:var(--soluk);text-transform:uppercase;margin-top:3px}}
.nav{{display:flex;gap:4px;flex:1}} .nav a{{color:var(--soluk);text-decoration:none;padding:8px 12px;border-radius:var(--k);font-size:14px;font-weight:500}}
.nav a.aktif{{color:var(--metin);background:var(--yuzey2)}}
.dil{{display:flex;border:1px solid var(--cizgi);border-radius:var(--k);overflow:hidden;font:600 12px var(--f-sayi)}}
.dil span{{padding:5px 10px;color:var(--soluk)}} .dil span.aktif{{background:var(--metin);color:var(--zemin)}}
.sayfa{{max-width:1376px;margin:0 auto;padding:{"24px 32px" if A else "40px 32px"} 64px}}
.kas{{font:600 11px/1 var(--f-sayi);letter-spacing:.14em;text-transform:uppercase;color:var(--vurgu)}}
h1{{font-family:var(--f-baslik);font-weight:{600 if A else 500};font-size:{"34px" if A else "50px"};line-height:1.08;
letter-spacing:{"-0.02em" if A else "-0.015em"};margin:12px 0 14px;max-width:{"820px" if A else "900px"}}}
.giris{{display:grid;grid-template-columns:{"1.5fr 1fr" if A else "1.35fr 1fr"};gap:40px;align-items:end;
padding-bottom:{"20px" if A else "36px"};{"border-bottom:1px solid var(--cizgi);" if not A else ""}}}
.on{{color:var(--soluk);font-size:{"15px" if A else "18px"};max-width:640px;margin:0 0 22px}}
.cta{{display:inline-flex;align-items:center;gap:8px;background:var(--vurgu);color:var(--vurgu-metin);font-weight:600;
padding:11px 18px;border-radius:var(--k);font-size:14px;text-decoration:none}}
.cta2{{display:inline-flex;align-items:center;gap:8px;color:var(--metin);font-weight:500;padding:11px 14px;font-size:14px}}
.oneler{{display:grid;grid-template-columns:repeat(3,1fr);gap:{"1px" if A else "0"};background:{"var(--cizgi)" if A else "transparent"};
border:1px solid var(--cizgi);border-radius:var(--k);overflow:hidden}}
.one{{background:var(--yuzey);padding:16px 18px;{"" if A else "border-left:1px solid var(--cizgi);"}}}
.one:first-child{{border-left:0}}
.one b{{display:block;font-family:var(--f-sayi);font-variant-numeric:tabular-nums;font-size:{"26px" if A else "30px"};
font-weight:{500 if A else 600};letter-spacing:-0.02em;color:var(--metin)}}
.one span{{color:var(--soluk);font-size:12.5px;line-height:1.35;display:block;margin-top:2px}}
.adim{{display:flex;gap:0;margin:{"18px 0" if A else "28px 0"};border:1px solid var(--cizgi);border-radius:var(--k);
background:var(--yuzey);overflow:hidden}}
.adim div{{flex:1;display:flex;align-items:center;gap:10px;padding:11px 16px;color:var(--soluk);font-size:13.5px;
border-left:1px solid var(--cizgi);white-space:nowrap}}
.adim div:first-child{{border-left:0}}
.adim i{{font:600 11px/22px var(--f-sayi);font-style:normal;width:22px;height:22px;text-align:center;border-radius:50%;
border:1px solid var(--cizgi);color:var(--soluk);flex:none}}
.adim .aktif{{color:var(--metin);font-weight:600;box-shadow:inset 0 -2px 0 var(--vurgu)}}
.adim .aktif i{{background:var(--vurgu);color:var(--vurgu-metin);border-color:var(--vurgu)}}
.adim .tamam i{{background:var(--yuzey2);color:var(--metin)}}
.adim small{{color:var(--silik);font-weight:400;margin-left:auto;font-family:var(--f-sayi);font-size:11px}}
.izgara{{display:grid;grid-template-columns:1fr 360px;gap:20px}}
.kart{{background:var(--yuzey);border:1px solid var(--cizgi);border-radius:var(--k);padding:18px}}
.kart h3{{font:600 {"12px" if A else "13px"}/1.2 {"var(--f-sayi)" if A else "var(--f-arayuz)"};margin:0 0 12px;
{"letter-spacing:.1em;text-transform:uppercase;color:var(--soluk)" if A else "color:var(--metin)"}}}
.sekme{{display:flex;gap:2px;background:var(--yuzey2);padding:3px;border-radius:var(--k);margin-bottom:14px}}
.sekme span{{flex:1;text-align:center;padding:7px 4px;font-size:13px;color:var(--soluk);border-radius:calc(var(--k) - 2px)}}
.sekme .aktif{{background:var(--yuzey);color:var(--metin);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.12)}}
.bos{{border:1px dashed var(--cizgi);border-radius:var(--k);padding:22px 18px;text-align:center;color:var(--soluk);font-size:13.5px}}
.bos .ikon{{color:var(--vurgu);margin-bottom:6px}}
.bos b{{display:block;color:var(--metin);font-size:14.5px;margin-bottom:4px}}
.cip{{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--cizgi);border-radius:99px;padding:3px 10px;
font-size:12px;color:var(--soluk);margin:0 6px 6px 0;background:var(--yuzey)}} .cip b{{color:var(--metin);font-weight:600}}
.satir{{display:flex;justify-content:space-between;padding:7px 0;border-top:1px solid var(--cizgi);font-size:13.5px}}
.satir span{{color:var(--soluk)}}
.harita-kart{{padding:0;overflow:hidden}}
.harita-ust{{display:flex;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid var(--cizgi);flex-wrap:wrap}}
.harita-ust .baslik{{font-weight:600;font-size:14px;margin-right:auto}}
.seg{{display:flex;border:1px solid var(--cizgi);border-radius:var(--k);overflow:hidden;font-size:12.5px}}
.seg span{{padding:5px 11px;color:var(--soluk);border-left:1px solid var(--cizgi)}} .seg span:first-child{{border-left:0}}
.seg .aktif{{background:var(--yuzey2);color:var(--metin);font-weight:600}}
iframe{{border:0;display:block;width:100%}}
.lejant{{display:flex;align-items:center;gap:18px;padding:10px 14px;border-top:1px solid var(--cizgi);flex-wrap:wrap;font-size:12px;color:var(--soluk)}}
.rampa{{display:flex;flex-direction:column;gap:3px}}
.rampa .kutular{{display:flex}} .rampa .kutular i{{width:38px;height:10px;display:block}}
.rampa .etiket{{display:flex;justify-content:space-between;font-family:var(--f-sayi);font-variant-numeric:tabular-nums;font-size:11px;width:228px}}
.guven-lj{{display:flex;gap:12px;align-items:center}}
.guven-lj i{{display:inline-block;width:14px;height:14px;vertical-align:-3px;margin-right:5px}}
.rozet{{display:inline-flex;align-items:center;gap:6px;font:600 11.5px/1 var(--f-arayuz);padding:5px 9px;border-radius:99px;
border:1px solid currentColor}}
.rozet::before{{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}}
.r-iyi{{color:var(--iyi)}} .r-uyari{{color:var(--uyari)}} .r-kotu{{color:var(--kotu)}} .r-bilgi{{color:var(--bilgi)}}
/* sonuç */
.saha-serit{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:{"14px" if A else "22px"}}}
.saha-serit .yer{{font-family:var(--f-baslik);font-size:{"22px" if A else "30px"};font-weight:{600 if A else 500};letter-spacing:-0.01em}}
.saha-serit .koord{{font-family:var(--f-sayi);font-size:12.5px;color:var(--soluk)}}
.karar{{border:1px solid var(--cizgi);border-radius:var(--k);background:var(--yuzey);display:grid;grid-template-columns:1.25fr 2fr;overflow:hidden;
{"border-top:3px solid var(--kotu)" if A else "border-left:4px solid var(--kotu)"}}}
.karar .sol{{padding:22px 24px;border-right:1px solid var(--cizgi)}}
.karar .etiket{{font:600 11px/1 var(--f-sayi);letter-spacing:.14em;text-transform:uppercase;color:var(--soluk)}}
.karar .hukum{{font-family:var(--f-baslik);font-size:{"26px" if A else "34px"};font-weight:{600 if A else 500};line-height:1.12;margin:10px 0 10px;color:var(--metin)}}
.karar .hukum em{{font-style:normal;color:var(--kotu)}}
.karar p{{margin:0;color:var(--soluk);font-size:13.5px}}
.karar .sag{{display:grid;grid-template-columns:repeat(3,1fr)}}
.buyuk{{padding:22px 22px;border-left:1px solid var(--cizgi);display:flex;flex-direction:column;gap:4px}}
.buyuk:first-child{{border-left:0}}
.buyuk .e{{font-size:12.5px;color:var(--soluk)}}
.buyuk .d{{font-family:var(--f-sayi);font-variant-numeric:tabular-nums;font-size:{"34px" if A else "40px"};font-weight:{500 if A else 600};letter-spacing:-0.03em;line-height:1.05}}
.buyuk .d small{{font-size:14px;font-weight:500;color:var(--soluk);letter-spacing:0;margin-left:4px}}
.buyuk .a{{font-size:12px;color:var(--silik)}}
.kpi-satir{{display:grid;grid-template-columns:repeat(4,1fr);gap:{"1px" if A else "16px"};margin:{"14px 0" if A else "20px 0"};
{"background:var(--cizgi);border:1px solid var(--cizgi);border-radius:var(--k);overflow:hidden" if A else ""}}}
.kpi{{background:var(--yuzey);padding:14px 16px;{"" if A else "border:1px solid var(--cizgi);border-radius:var(--k)"}}}
.kpi .e{{font-size:12px;color:var(--soluk);display:flex;justify-content:space-between}}
.kpi .d{{font-family:var(--f-sayi);font-variant-numeric:tabular-nums;font-size:22px;font-weight:{500 if A else 600};margin-top:4px;letter-spacing:-0.02em}}
.kpi .d small{{font-size:12px;color:var(--soluk);margin-left:3px;font-weight:500}}
.kpi .a{{font-size:11.5px;color:var(--silik);margin-top:2px}}
.iki{{display:grid;grid-template-columns:1.4fr 1fr;gap:{"14px" if A else "20px"};margin-bottom:{"14px" if A else "20px"}}}
.bolum{{display:flex;align-items:baseline;gap:12px;margin:{"22px 0 10px" if A else "36px 0 14px"};
{"" if A else "border-top:1px solid var(--metin);padding-top:12px"}}}
.bolum h2{{font-family:{"var(--f-sayi)" if A else "var(--f-baslik)"};font-size:{"12px" if A else "24px"};font-weight:{600 if A else 500};margin:0;
{"letter-spacing:.14em;text-transform:uppercase;color:var(--soluk)" if A else ""}}}
.bolum span{{color:var(--silik);font-size:12.5px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{text-align:right;font-weight:600;color:var(--soluk);font-size:11.5px;padding:8px 10px;border-bottom:1px solid var(--cizgi);
{"text-transform:uppercase;letter-spacing:.08em;font-family:var(--f-sayi)" if A else ""}}}
td{{text-align:right;padding:9px 10px;border-bottom:1px solid var(--cizgi);font-family:var(--f-sayi);font-variant-numeric:tabular-nums}}
th:first-child,td:first-child{{text-align:left;font-family:var(--f-arayuz)}}
tr.enIyi td{{background:{"rgba(245,181,61,.08)" if A else "rgba(15,107,87,.06)"}}}
tr.enIyi td:first-child{{box-shadow:inset 3px 0 0 var(--vurgu);font-weight:600}}
.liste{{margin:0;padding:0;list-style:none}} .liste li{{padding:9px 0 9px 22px;border-top:1px solid var(--cizgi);position:relative;font-size:13.5px}}
.liste li::before{{content:"";position:absolute;left:4px;top:16px;width:7px;height:7px;border-radius:2px;background:var(--vurgu)}}
.indir{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.indir a{{display:flex;gap:12px;align-items:center;padding:14px;border:1px solid var(--cizgi);border-radius:var(--k);
background:var(--yuzey);color:var(--metin);text-decoration:none}}
.indir a .ikon{{color:var(--vurgu)}} .indir a small{{display:block;color:var(--soluk);font-size:12px}}
.indir a .sag{{margin-left:auto;color:var(--soluk)}}
.uyari-kutu{{display:flex;gap:10px;padding:11px 14px;border-radius:var(--k);font-size:13px;color:var(--soluk);
background:{"rgba(255,154,77,.07)" if A else "#fbf3e4"};border:1px solid {"rgba(255,154,77,.25)" if A else "#ecd9b4"};margin-bottom:16px}}
.uyari-kutu .ikon{{color:var(--uyari)}} .uyari-kutu b{{color:var(--metin)}}
.alt{{color:var(--silik);font-size:11.5px;border-top:1px solid var(--cizgi);padding:16px 32px;max-width:1376px;margin:0 auto}}
@media (max-width:760px){{
 .ust{{padding:0 16px;gap:12px;height:54px}} .nav{{display:none}} .logo small{{display:none}}
 .menu{{display:block!important;margin-left:8px;color:var(--soluk)}}
 .sayfa{{padding:18px 16px 48px}}
 h1{{font-size:{"26px" if A else "32px"}}}
 .giris,.izgara,.iki,.karar,.indir{{grid-template-columns:1fr}}
 .giris{{gap:18px}}
 .on{{font-size:15px}}
 .one{{padding:12px}} .one b{{font-size:21px}} .one span{{font-size:11.5px}}
 .adim{{overflow-x:auto}} .adim div{{padding:10px 12px;font-size:12.5px}} .adim div span.uzun,.adim small{{display:none}}
 .adim div:not(.aktif) span{{display:none}}
 .karar .sol{{border-right:0;border-bottom:1px solid var(--cizgi);padding:18px}}
 .karar .sag{{grid-template-columns:1fr 1fr 1fr}} .buyuk{{padding:14px 12px}} .buyuk .d{{font-size:22px}} .buyuk .d small{{display:block;margin:2px 0 0;font-size:11px}}
 .buyuk .a{{display:none}}
 .kpi-satir{{grid-template-columns:1fr 1fr}}
 .karar .hukum{{font-size:24px}}
 .saha-serit .yer{{font-size:22px}}
 .rampa .kutular i{{width:30px}} .rampa .etiket{{width:180px}}
 table{{font-size:12.5px}} th,td{{padding:7px 6px}} .gizle-m{{display:none}}
 .alt{{padding:16px}}
}}
"""


def ust(aktif: str) -> str:
    nav = "".join(
        f'<a class="{"aktif" if k == aktif else ""}">{ad}</a>'
        for k, ad in [("analiz", "Saha analizi"), ("vaka", "Vaka çalışması: Ezine"), ("yontem", "Yöntem")]
    )
    return (
        f'<header class="ust"><div class="logo">{isaret_svg()}<div>Eşik<small>Hibrit saha analizi</small></div></div>'
        f'<nav class="nav">{nav}</nav><div class="dil"><span class="aktif">TR</span><span>EN</span></div>'
        "</header>"
    )


def adimlar(aktif: int) -> str:
    ad = [
        ("Saha", "haritadan veya il/ilçeden"),
        ("Varsayımlar", "bağlantı, fiyat, gelir"),
        ("Hızlı tarama", "~2 sn"),
        ("Tam analiz", "MILP + Monte Carlo · birkaç dk"),
    ]
    h = ""
    for i, (a, n) in enumerate(ad, 1):
        cls = "aktif" if i == aktif else ("tamam" if i < aktif else "")
        h += f'<div class="{cls}"><i>{"✓" if i < aktif else i}</i><span>{a}</span><small>{n}</small></div>'
    return f'<div class="adim">{h}</div>'


# ------------------------------------------------------------------ harita
def harita_html(y: dict, ot: pd.DataFrame, santral: pd.DataFrame, yon: str, mobil: bool) -> Path:
    sk = y["harita_skala"]
    v = ot["basabas_en_iyi"].astype(float)
    q = np.nanquantile(v, np.linspace(0, 1, 7))
    sinif = np.clip(np.searchsorted(q[1:-1], v, side="right"), 0, 5)
    m = folium.Map(location=[39.0, 35.3], zoom_start=5 if mobil else 6, tiles=None, control_scale=True, prefer_canvas=True,
                   zoom_control=not mobil)  # fmt: skip
    koyu = y["kip"] == "dark"
    r_ = y["renk"]
    m.get_root().header.add_child(folium.Element(f"<style>.leaflet-container{{background:{r_['deniz']}!important}}</style>"))
    altlik = json.loads((KOK / "data" / "atlas" / "altlik_tr.geojson").read_text())
    folium.GeoJson(altlik, style_function=lambda f: {"fillColor": r_["kara"], "fillOpacity": 1 if f["properties"]["tur"] == "ulke" else 0,
                   "color": r_["sinir"], "weight": 0.7 if f["properties"]["tur"] == "il" else 0.9}).add_to(m)  # fmt: skip
    ozellik = []
    for r, c in zip(ot.itertuples(), sinif, strict=True):
        e, b = r.hucre_enlem, r.hucre_boylam
        ozellik.append({"type": "Feature", "properties": {"renk": sk[int(c)], "dusuk": r.guven != "yüksek"},
                        "geometry": {"type": "Polygon", "coordinates": [[[b - .125, e - .125], [b + .125, e - .125], [b + .125, e + .125], [b - .125, e + .125], [b - .125, e - .125]]]}})  # fmt: skip
    folium.GeoJson(
        {"type": "FeatureCollection", "features": ozellik},
        style_function=lambda f: {
            "fillColor": f["properties"]["renk"],
            "fillOpacity": 0.38 if f["properties"]["dusuk"] else 0.85,
            "color": f["properties"]["renk"],
            "weight": 0.0 if f["properties"]["dusuk"] else 0.6,
        },
    ).add_to(m)
    for r in santral.itertuples():
        folium.CircleMarker([r.enlem, r.boylam], radius=3.2, color=y["renk"]["zemin"] if koyu else "#1b1f1d", weight=1.2, fill=True,
                            fill_color=y["renk"]["metin"] if koyu else "#ffffff", fill_opacity=1).add_to(m)  # fmt: skip
    m.fit_bounds([[35.8, 25.7], [42.1, 44.8]])
    p = TASLAK / f"harita_{yon}{'_m' if mobil else ''}.html"
    m.save(str(p))
    return p


def lejant(y: dict, ot: pd.DataFrame) -> str:
    v = ot["basabas_en_iyi"].astype(float)
    q = np.nanquantile(v, np.linspace(0, 1, 7))
    sk = y["harita_skala"]
    kut = "".join(f'<i style="background:{c}"></i>' for c in sk)
    et = f"<span>{sayi(q[0], 0)}</span><span>{sayi(q[3], 0)}</span><span>{sayi(q[6], 0)}</span>"
    return (
        f'<div class="lejant"><div class="rampa"><div style="color:var(--metin);font-weight:600">Başabaş fiyatı, $/MWh '
        f'<span style="font-weight:400;color:var(--soluk)">· düşük = daha cazip</span></div><div class="kutular">{kut}</div>'
        f'<div class="etiket">{et}</div></div><div class="guven-lj">'
        f'<span><i style="background:{sk[1]};opacity:.9"></i>Yüksek güven</span>'
        f'<span><i style="background:{sk[1]};opacity:.35"></i>Düşük güven <span class="gizle-m">(30 km içinde kalibre santral yok)</span></span>'
        f'<span><i style="border-radius:50%;background:var(--metin);width:9px;height:9px;border:1.5px solid var(--zemin)"></i>Kalibre RES (90)</span>'
        f"</div></div>"
    )


# ------------------------------------------------------------------ grafik şablonu (taslak)
def sablon(y: dict) -> dict:
    r, f = y["renk"], y["yazi"]
    return dict(
        layout=dict(
            font=dict(family=f"{f['arayuz']}, sans-serif", size=12, color=r["metin_soluk"]),
            title=dict(font=dict(family=f"{f['arayuz']}, sans-serif", size=14, color=r["metin"]), x=0, xanchor="left", y=0.97),
            paper_bgcolor=r["yuzey"],
            plot_bgcolor=r["yuzey"],
            colorway=[y["veri"][k] for k in ("res", "ges", "batarya", "hibrit", "notr")],
            xaxis=dict(
                automargin=True,
                showgrid=False,
                linecolor=r["cizgi"],
                tickcolor=r["cizgi"],
                ticks="outside",
                ticklen=4,
                zeroline=False,
                title=dict(font=dict(size=11.5, color=r["metin_soluk"])),
            ),
            yaxis=dict(
                automargin=True,
                gridcolor=r["cizgi"],
                griddash="dot" if y["kip"] == "dark" else "solid",
                zeroline=False,
                linecolor=r["cizgi"],
                title=dict(font=dict(size=11.5, color=r["metin_soluk"])),
                tickfont=dict(family=f"{f['sayi']}, monospace"),
            ),
            legend=dict(
                orientation="h",
                x=1,
                xanchor="right",
                y=1.08,
                yanchor="bottom",
                font=dict(size=12, color=r["metin_soluk"]),
                bgcolor="rgba(0,0,0,0)",
            ),
            margin=dict(l=8, r=8, t=56, b=8),
            hoverlabel=dict(bgcolor=r["yuzey2"], bordercolor=r["cizgi"], font=dict(family=f"{f['sayi']}, monospace", color=r["metin"])),
            separators=",.",
            bargap=0.15,
        )
    )


def grafik(fig: go.Figure, y: dict, baslik: str, alt: str, yukseklik: int) -> str:
    fig.update_layout(template=sablon(y), height=yukseklik,
                      title=dict(text=f"{baslik}<br><span style='font-size:11.5px;color:{y['renk']['metin_soluk']}'>{alt}</span>"))  # fmt: skip
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True,
                       "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "zoomIn2d", "zoomOut2d"]})  # fmt: skip


def sayfa_html(y: dict, govde: str) -> str:
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?{y["yazi"]["google"]}&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>{css(y)}</style></head><body>{govde}</body></html>"""


# ------------------------------------------------------------------ ekranlar
def acilis(y: dict, yon: str, ot, santral, mobil: bool) -> str:
    hp = harita_html(y, ot, santral, yon, mobil)
    n_yuksek = int((ot["guven"] == "yüksek").sum())
    govde = (
        ust("analiz")
        + f"""
<main class="sayfa">
 <section class="giris">
  <div>
   <div class="kas">Türkiye · Rüzgâr + Güneş + Batarya</div>
   <h1>Seçtiğiniz sahada hibrit santralin hangi elektrik fiyatında kâra geçtiğini hesaplar.</h1>
   <p class="on">Haritadan bir nokta seçin: rüzgâr ve güneş profili, komşu santral kalibrasyonu, piyasa ve finans modeliyle saniyeler
   içinde hızlı tarama; optimizasyon ve Monte Carlo ile birkaç dakikada tam analiz.</p>
   <a class="cta">{ikon("imlec")} Haritadan saha seç</a><a class="cta2">Ezine vaka çalışması {ikon("ok")}</a>
  </div>
  <div class="oneler">
   <div class="one"><b>{sayi(len(ot), 0)}</b><span>kara hücresi ön tarandı (0,25°)</span></div>
   <div class="one"><b>90</b><span>EPİAŞ verisiyle kalibre RES santrali</span></div>
   <div class="one"><b>{sayi(ot["basabas_en_iyi"].min(), 0)}<span style="display:inline;font-size:13px;margin-left:3px">$/MWh</span></b><span>en düşük başabaş fiyatı (hücre)</span></div>
  </div>
 </section>
 {adimlar(1)}
 <section class="izgara">
  <div class="kart harita-kart">
   <div class="harita-ust"><span class="baslik">{ikon("katman")} Ön tarama haritası</span>
    <div class="seg"><span class="aktif">Başabaş</span><span>RES KF</span><span>GES KF</span></div></div>
   <iframe src="{hp.name}" style="height:{380 if mobil else 560}px"></iframe>
   {lejant(y, ot)}
  </div>
  <div style="display:flex;flex-direction:column;gap:16px">
   <div class="kart"><h3>1 · Saha seçimi</h3>
    <div class="sekme"><span class="aktif">Harita</span><span>Koordinat</span><span>İl / ilçe</span></div>
    <div class="bos">{ikon("pin", 22)}<b>Henüz saha seçilmedi</b>Haritada bir hücreye tıklayın. Tam dolu hücreler kalibre bir santrale
    30 km'den yakın: tahmin daha güvenilir.</div>
   </div>
   <div class="kart"><h3>2 · Varsayımlar <span style="float:right;font-weight:500;letter-spacing:0;text-transform:none;color:var(--vurgu)">Düzenle</span></h3>
    <span class="cip">Bağlantı <b class="num">50 MW</b></span><span class="cip">Fiyat <b class="num">58 $/MWh</b></span>
    <span class="cip">Aşama <b>İnşaata hazır</b></span><span class="cip">Gelir <b>Tüccar · YEKDEM · PPA</b></span>
    <span class="cip">WACC <b class="num">%7</b></span>
   </div>
   <div class="kart" style="background:var(--yuzey2)"><h3>Haritayı okuma</h3>
    <div class="satir"><span>Yüksek güvenli hücre</span><b class="num">{n_yuksek}</b></div>
    <div class="satir"><span>Medyan başabaş fiyatı</span><b class="num">{sayi(ot["basabas_en_iyi"].median(), 0)} $/MWh</b></div>
    <div class="satir"><span>Baz fiyat senaryosu</span><b class="num">58 $/MWh</b></div>
   </div>
  </div>
 </section>
</main>"""
    )
    return sayfa_html(y, govde)


def sonuc(y: dict, yon: str, sh, st_) -> str:
    o, oh = st_.ozet, sh.ozet
    b = o["baz"]
    k = o["karar"]
    ts = o["tasarim"]
    gv = o["guven"]
    v = y["veri"]
    # NPV histogramı
    h = st_.grafikler["npv_histogram"]
    ad = {"tuccar": "Tüccar", "yekdem_opsiyon": "YEKDEM opsiyonu", "ppa": "PPA"}
    renk = {"tuccar": v["notr"], "yekdem_opsiyon": v["res"], "ppa": v["ges"]}
    f = go.Figure()
    for yap, n in h["sayi"].items():
        e = np.array(h["kenar"][yap])
        f.add_trace(go.Scatter(x=(e[:-1] + e[1:]) / 2, y=n, name=ad.get(yap, yap), mode="lines", line=dict(color=renk[yap], width=2, shape="hvh"),
                               fill="tozeroy", fillcolor=rgba(renk[yap], 0.14)))  # fmt: skip
    f.add_vline(x=0, line_color=y["renk"]["metin_soluk"], line_dash="dot", line_width=1)
    f.add_annotation(
        x=0,
        y=1,
        yref="paper",
        text="NPV = 0",
        showarrow=False,
        xanchor="left",
        xshift=4,
        font=dict(size=11, color=y["renk"]["metin_soluk"]),
    )
    f.update_xaxes(title="NPV, milyon $ (reel)")
    f.update_yaxes(title="simülasyon sayısı")
    g1 = grafik(f, y, "NPV dağılımı", f"Monte Carlo, n = {b['n']} · gelir yapısına göre", 340)
    gi = sh.grafikler["gunici"]
    f2 = go.Figure([go.Scatter(x=gi["saat"], y=np.array(gi["res"]) * 100, name="RES", line=dict(color=v["res"], width=2.2)),
                    go.Scatter(x=gi["saat"], y=np.array(gi["ges"]) * 100, name="GES", line=dict(color=v["ges"], width=2.2))])  # fmt: skip
    f2.update_xaxes(title="saat (TSİ)", dtick=6)
    f2.update_yaxes(title="kapasite faktörü, %")
    g2 = grafik(f2, y, "Gün içi profil", "10 hava yılı ortalaması", 340)
    gy = st_.tablolar["gelir_yapilari"]
    en_iyi = o["en_iyi_yapi"]
    satir = ""
    for yap, r in gy.iterrows():
        satir += (f'<tr class="{"enIyi" if yap == en_iyi else ""}"><td>{ad.get(yap, yap)}</td><td>{sayi(r.e_npv, 1)}</td><td class="gizle-m">±{sayi(r.se, 2)}</td>'
                  f'<td>%{sayi(100 * r.p_pozitif, 0)}</td><td>{sayi(r.cvar5, 1)}</td><td class="gizle-m">{sayi(r.p10, 1)} / {sayi(r.p90, 1)}</td></tr>')  # fmt: skip
    tk = o["takvim"]
    tet = "".join(f"<li>{t['tr']}</li>" for t in o.get("tetikleyiciler", [])[:4])
    guven_r = "r-iyi" if gv["seviye"] == "yüksek" else "r-uyari"
    hukum = k["tr"].split(".")[0]
    govde = (
        ust("analiz")
        + f"""
<main class="sayfa">
 <div class="saha-serit"><span class="yer">Çanakkale / Ezine</span><span class="koord">39,7900° K · 26,3300° D</span>
  <span class="rozet {guven_r}">Güven: {gv["seviye"]}</span><span class="rozet r-bilgi">Tam analiz</span>
  <span style="margin-left:auto" class="koord">{ikon("ayar", 14)} 50 MW · 58 $/MWh · inşaata hazır</span></div>
 {adimlar(4)}
 <section class="karar">
  <div class="sol"><div class="etiket">Öneri</div>
   <div class="hukum"><em>{hukum}.</em></div>
   <p style="color:var(--metin);margin-bottom:8px">Başabaş fiyatı (<span class="num">{sayi(o["basabas_fiyat"], 0)}</span> $/MWh) baz senaryonun
   (<span class="num">58</span> $/MWh) üzerinde; pozitif NPV olasılığı <span class="num">%{sayi(100 * b["p_pozitif"], 0)}</span>.</p>
   <p>Tasarım: RES <span class="num">{sayi(ts["res_mw"], 1)}</span> MW · GES <span class="num">{sayi(ts["ges_mw"], 0)}</span> MWac ·
   batarya <span class="num">{sayi(ts["bess_mw"], 0)}</span> MW · CAPEX <span class="num">{sayi(o["capex_musd"], 1)}</span> M$</p></div>
  <div class="sag">
   <div class="buyuk"><span class="e">Başabaş fiyatı</span><span class="d">{sayi(o["basabas_fiyat"], 0)}<small>$/MWh</small></span><span class="a">senaryo 58 $/MWh</span></div>
   <div class="buyuk"><span class="e">Beklenen NPV</span><span class="d">{sayi(b["e_npv"], 1)}<small>M$</small></span><span class="a">±{sayi(b["se"], 2)} standart hata</span></div>
   <div class="buyuk"><span class="e">Güven seviyesi</span><span class="d" style="font-family:var(--f-baslik);letter-spacing:-0.01em">{gv["seviye"].capitalize()}</span><span class="a">tipik KF hatası ±{sayi(gv["medyan_puan"], 1)} puan</span></div>
  </div>
 </section>
 <div class="kpi-satir">
  <div class="kpi"><div class="e">P(NPV &gt; 0)</div><div class="d">%{sayi(100 * b["p_pozitif"], 0)}</div><div class="a">pozitif NPV olasılığı</div></div>
  <div class="kpi"><div class="e">CVaR %5</div><div class="d">{sayi(b["cvar5"], 1)}<small>M$</small></div><div class="a">en kötü %5'in ortalaması</div></div>
  <div class="kpi"><div class="e">RES kapasite faktörü</div><div class="d">%{sayi(100 * oh["res_kf"], 1)}</div><div class="a">bant %{sayi(100 * oh["res_kf_bandi_medyan"][0], 1)}–{sayi(100 * oh["res_kf_bandi_medyan"][1], 1)}</div></div>
  <div class="kpi"><div class="e">COD P50</div><div class="d">{tk["cod_p50"]}</div><div class="a">P80 {tk["cod_p80"]}</div></div>
 </div>
 <div class="uyari-kutu">{ikon("uyari")}<div><b>Ön fizibilite aracıdır, yatırım tavsiyesi değildir.</b> Arazi, izinler, iz etkisi ve şebeke kapasitesi modellenmez; rüzgâr tahmini saha ölçümüne değil yeniden analiz ve komşu santral kalibrasyonuna dayanır.</div></div>
 <div class="iki"><div class="kart" style="padding:10px 12px">{g1}</div><div class="kart" style="padding:10px 12px">{g2}</div></div>
 <div class="bolum"><h2>Gelir yapıları</h2><span>Monte Carlo, milyon $ (reel)</span></div>
 <div class="kart" style="padding:4px 14px"><table><thead><tr><th>Yapı</th><th>E[NPV]</th><th class="gizle-m">Std. hata</th><th>P(NPV&gt;0)</th><th>CVaR %5</th><th class="gizle-m">P10 / P90</th></tr></thead><tbody>{satir}</tbody></table></div>
 <div class="bolum"><h2>Neyi izlemeli</h2><span>kararı değiştirecek tetikleyiciler</span></div>
 <ul class="liste">{tet}</ul>
 <div class="bolum"><h2>Rapor</h2></div>
 <div class="indir"><a>{ikon("dosya", 22)}<div>Saha raporu<small>PDF · yazdırılabilir</small></div><span class="sag">{ikon("indir")}</span></a>
 <a>{ikon("dosya", 22)}<div>Saha raporu<small>HTML · etkileşimli</small></div><span class="sag">{ikon("indir")}</span></a>
 <a>{ikon("katman", 22)}<div>Paylaşım bağlantısı<small>aynı varsayımlarla yeniden açar</small></div><span class="sag">{ikon("ok")}</span></a></div>
</main>"""
    )
    return sayfa_html(y, govde)


def markalar() -> str:
    kutu = ""
    for ad, _isim, acik in [("esik", "Eşik", "Başabaş eşiği: projenin kâra geçtiği fiyat. Üç sütun RES/GES/batarya; çizginin üstü vurgu rengi."),
                           ("pafta", "Pafta", "Harita paftası: Türkiye'yi 0,25° hücrelere bölen ön tarama ızgarası; seçili hücre dolu."),
                           ("kerte", "Kerte", "Kerteriz: yön halkası ve tek kerte çizgisi; rüzgâr yönü ve saha konumu.")]:  # fmt: skip
        svg = (MARKA / f"{ad}_yazi.svg").read_text().replace('width="200" height="40"', 'width="300" height="60"')
        kutu += (f'<div style="flex:1;padding:28px;border:1px solid #e2ddd2;border-radius:6px;background:#fff">'
                 f'<div style="color:#1b1f1d;--vurgu:#0f6b57">{svg}</div>'
                 f'<div style="margin-top:18px;background:#0b0f0e;padding:16px;border-radius:6px;color:#e7ece9;--vurgu:#f5b53d">{svg}</div>'
                 f'<p style="font:13px/1.45 Public Sans,sans-serif;color:#585f5b;margin:16px 0 0">{acik}</p></div>')  # fmt: skip
    return f"""<!doctype html><html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?{YONLER["A"]["yazi"]["google"]}&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?{YONLER["B"]["yazi"]["google"]}&display=swap" rel="stylesheet"></head>
<body style="margin:0;padding:28px;background:#f8f6f1"><div style="display:flex;gap:20px">{kutu}</div></body></html>"""


def main() -> None:
    TASLAK.mkdir(parents=True, exist_ok=True)
    ot = pd.read_parquet(KOK / "data" / "atlas" / "on_tarama.parquet")
    from uygulama import servis

    santral = servis.santraller()
    k = KullaniciVarsayimlari()
    sh, st_ = onbellekten(SAHA, "hizli", k), onbellekten(SAHA, "tam", k)
    if sh is None or st_ is None:
        raise SystemExit("Ezine hızlı tarama ve tam analiz sonucu önbellekte olmalı (önce uygulamada çalıştırın).")
    (TASLAK / "ozet_tam.json").write_text(json.dumps(st_.ozet, default=str, ensure_ascii=False, indent=1))
    sayfalar = {}
    for yon, y in YONLER.items():
        for mobil in (False, True):
            ek = "_m" if mobil else ""
            (TASLAK / f"acilis_{yon}{ek}.html").write_text(acilis(y, yon, ot, santral, mobil))
            sayfalar[f"acilis_{yon}{ek}"] = mobil
        (TASLAK / f"sonuc_{yon}.html").write_text(sonuc(y, yon, sh, st_))
        sayfalar[f"sonuc_{yon}"] = False
        sayfalar[f"sonuc_{yon}@m"] = True
    (TASLAK / "markalar.html").write_text(markalar())
    with sync_playwright() as pw:
        tar = pw.chromium.launch(channel="chrome", headless=True)
        for ad, mobil in sayfalar.items():
            dosya = ad.split("@")[0]
            yon = dosya.split("_")[1]
            boyut = {"width": 390, "height": 844} if mobil else {"width": 1440, "height": 900}
            s = tar.new_page(viewport=boyut)
            s.goto((TASLAK / f"{dosya}.html").as_uri())
            s.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            s.wait_for_timeout(2500)
            s.evaluate("window.scrollTo(0, 0)")
            s.wait_for_timeout(1500)
            (IMG / f"yon_{yon}").mkdir(parents=True, exist_ok=True)
            tur = "acilis" if dosya.startswith("acilis") else "sonuc"
            s.screenshot(
                path=str(IMG / f"yon_{yon}" / f"{tur}_{'mobil' if mobil else 'masaustu'}.jpg"), full_page=True, type="jpeg", quality=72
            )
            s.close()
        s = tar.new_page(viewport={"width": 1240, "height": 400})
        s.goto((TASLAK / "markalar.html").as_uri())
        s.wait_for_timeout(2000)
        s.screenshot(path=str(MARKA / "markalar.png"), full_page=True)
        tar.close()
    print("Taslaklar:", sorted(p.name for p in IMG.glob("yon_*/*.jpg")))


if __name__ == "__main__":
    main()
