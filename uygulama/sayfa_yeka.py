"""
YEKA teklif stratejisi (v4 Faz J): YEKA RES yarışmalarında katkı payı açık artırması.

Veri: data/atlas/v4_yeka.json (src/v4_J1_yeka.py) — lot değerlemeleri, rakip değer modeli (en çok olabilirlik), birini dışarıda
bırak doğrulaması, piyasa primi duyarlılığı ve R26 (2 Kasım 2026) tahminleri. Teklif eğrileri sayfada hesaplanır (src/yeka/muzayede.py).
"""

from __future__ import annotations

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from src.yeka import muzayede as M
from uygulama.ortak import GES, RES, SOLUK, T, ciz, md, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.grafik import dolgu


@st.cache_data(show_spinner=False)
def _paket() -> dict | None:
    p = veri_katmani.yol("atlas/v4_yeka.json", zorunlu=False)
    return None if p is None else json.loads(p.read_text(encoding="utf-8"))


def k(x: float | None, d: int = 0) -> str:
    """€/MW → 'bin €/MW' metni."""
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{sayi(x / 1e3, d)}"


st.title(T("YEKA teklif stratejisi", "YEKA bidding strategy"))
st.markdown(md(T(
    "YEKA RES yarışmalarında fiyat 5,50'den taban 3,50 Avro-sent/kWh'ye iner; tabanda iki ya da daha fazla istekli kalırsa yarışma "
    "**MW başına katkı payı** üzerinden açık artırmaya döner. 2024–25'teki 11 yarışmanın hepsi tabana indi ve kazananı katkı payı "
    "belirledi (56–312 bin €/MW). Bu bir İngiliz artırmasıdır: en iyi strateji, katkı payı kendi değerinize ulaşınca çekilmektir; "
    "kazanan yaklaşık **ikinci en yüksek** değeri öder.",
    "In YEKA wind auctions the price descends from 5.50 to the 3.50 euro-cent/kWh floor; if two or more bidders remain at the floor "
    "the auction switches to an ascending **contribution fee per MW**. All 11 auctions in 2024–25 reached the floor and were decided "
    "by the fee (56–312 k€/MW). This is an English auction: the optimal strategy is to drop out when the fee reaches your value; the "
    "winner pays roughly the **second-highest** value.",
)))  # fmt: skip
B.uyari_kutusu(
    T(
        "Yarışma alanlarının koordinatları yayımlanmadığı için değerler ilin rüzgârlı hücrelerinden temsilî bir noktayla hesaplandı. "
        "Bu sayfa bir yatırım ya da teklif tavsiyesi değildir; rakip modeli 11 gözleme dayanır.",
        "Auction-site coordinates are not published, so values use a representative point from the province's windy cells. This page "
        "is not investment or bidding advice; the rival model rests on 11 observations.",
    ),
    "uyari",
)
p = _paket()
if p is None:
    B.bos_durum(T("YEKA paketi yok", "No YEKA package"), T("src/v4_J1_yeka.py çalıştırılmalı.", "Run src/v4_J1_yeka.py."))
    st.stop()
m = p["model"]
lot = {x["kod"]: x for x in p["lotlar"]}
r26 = [x for x in p["r26"] if x["senaryo"] == "basvuru"]
r26_12 = {x["kod"]: x for x in p["r26"] if x["senaryo"] == "2025_rekabeti"}

# --- 1. R26
B.bolum_basligi(
    T("1. YEKA RES-2026 (2 Kasım 2026)", "1. YEKA RES-2026 (2 November 2026)"),
    T("7 yarışma · 1.500 MWe · 29 teklif", "7 auctions · 1,500 MWe · 29 bids"),
)
u = st.columns(4)
B.kpi_karti(u[0], T("Piyasa primi δ", "Market premium δ"), f"{k(m['delta'])} {T('bin €/MW', 'k€/MW')}",
            aciklama=T(f"%90 GA {k(m['guven_araligi_90']['delta'][0])}–{k(m['guven_araligi_90']['delta'][1])}",
                       f"90% CI {k(m['guven_araligi_90']['delta'][0])}–{k(m['guven_araligi_90']['delta'][1])}"),
            yardim=T("Rakiplerin ortalama değerinin bizim modelimizin değerinden farkı (150 MW'lık lot için).",
                     "Gap between rivals' mean value and our model's value (for a 150 MW lot)."))  # fmt: skip
B.kpi_karti(u[1], T("İstekliler arası dağınıklık s", "Bidder dispersion s"), f"{k(m['s'])} {T('bin €/MW', 'k€/MW')}",
            aciklama=T("rakip değerlerinin standart sapması", "std. dev. of rival values"))  # fmt: skip
B.kpi_karti(u[2], T("Büyüklük etkisi γ", "Size effect γ"), f"{k(m['gamma'])} {T('bin €/MW', 'k€/MW')}",
            aciklama=T("lot gücü iki katına çıkınca × ln 2", "× ln 2 when the lot doubles"))  # fmt: skip
B.kpi_karti(u[3], T("Doğrulama kapsaması", "Validation coverage"), yuzde(100 * m["loo_kapsama_80"], 0),
            aciklama=T("birini dışarıda bırak, %80 aralığı", "leave-one-out, 80% interval"))  # fmt: skip
B.karsilastirma_tablosu(
    [T("Yarışma", "Auction"), "MW", T("Teklif", "Bids"), T("Bizim değerimiz", "Our value"), T("Rakip ortalaması", "Rival mean"),
     T("P(tabana iner)", "P(floor)"), T("Fiyat medyanı", "Median price"), T("Katkı payı P10 / P50 / P90", "Fee P10 / P50 / P90"),
     T("n = 12 olsaydı P50", "P50 if n = 12")],
    [[x["kod"], sayi(lot[x["kod"]]["mw"], 0), str(x["n"]), k(lot[x["kod"]]["v_ort"]), k(x["mu_rakip"]), yuzde(100 * x["p_taban"], 0),
      f"{sayi(x['fiyat_p50'], 2)} €c", f"{k(x['katki_p10'])} / {k(x['katki_p50'])} / {k(x['katki_p90'])}", k(r26_12[x["kod"]]["katki_p50"])]
     for x in r26],
    mobilde_gizle=(3, 4, 8),
)  # fmt: skip
st.caption(md(T(
    "Değerler bin €/MW. Katkı payı yalnız fiyat tabana inerse oluşur. Az teklifli yarışmalarda (4 istekli) ikinci en yüksek değer düşer: "
    "zayıf rüzgârlı lotlarda fiyatın tabana inmeden kapanması beklenir. 'n = 12': 2025'teki ortalama rekabet düzeyi.",
    "Values in k€/MW. A fee arises only if the price reaches the floor. With few bidders (4) the second-highest value falls: weak-wind "
    "lots are expected to close above the floor. 'n = 12': the average competition level in 2025.",
)))  # fmt: skip

# --- 2. Teklif eğrisi
B.bolum_basligi(
    T("2. Teklif eğrisi", "2. Bid curve"),
    T("çekilme eşiğine göre kazanma olasılığı ve beklenen fazla", "win probability and expected surplus by drop-out level"),
)
c = st.columns([1, 1.3])
with c[0]:
    sec = st.selectbox(T("Yarışma", "Auction"), [x["kod"] for x in r26], key="yeka_lot")
    L = lot[sec]
    R = next(x for x in r26 if x["kod"] == sec)
    prim = st.slider(T("Kendi değer primimiz (bin €/MW)", "Our own value premium (k€/MW)"), -200, 1200, int(round(m["delta"] / 1e3 / 10) * 10), 10,
                     help=T("Bizim modelimizin değerine eklenen pay: daha düşük CAPEX, daha düşük sermaye maliyeti ya da daha iyimser fiyat görüşü. "
                            "0 = bizim varsayımlarımız; δ = tipik piyasa katılımcısı.",
                            "Added to our model's value: lower capex, lower cost of capital or a more optimistic price view. 0 = our assumptions; "
                            "δ = a typical market participant."))  # fmt: skip
if R["p_taban"] < 0.5:
    with c[0]:
        B.uyari_kutusu(
            T(f"Bu yarışmada fiyatın tabana inme olasılığı yalnız %{sayi(100 * R['p_taban'], 0)}: değerler tabanda çoğunlukla negatif, yarışma "
              f"büyük olasılıkla fiyat aşamasında (medyan {sayi(R['fiyat_p50'], 2)} €c) biter. Katkı payı eğrisi yalnız tabana inilirse geçerlidir.",
              f"In this auction the probability of reaching the floor is only {sayi(100 * R['p_taban'], 0)}%: values at the floor are mostly negative and "
              f"the auction most likely ends in the price stage (median {sayi(R['fiyat_p50'], 2)} €c). The fee curve applies only if the floor is reached."),
            "bilgi",
        )  # fmt: skip
deger_biz = np.random.default_rng(3).normal(L["v_ort"] + prim * 1e3 + m["gamma"] * np.log(L["mw"] / m["mw_ref"]), L["v_sd"], 20_000)
cek = np.linspace(10_000, max(600_000, float(np.percentile(deger_biz, 95)) * 1.1), 60)
s = M.strateji(deger_biz, R["mu_rakip"], m["s"], int(R["n"]), cek, R=60_000)
eg = s["egri"]
en = s["en_iyi"]
with c[0]:
    u = st.columns(2)
    B.kpi_karti(u[0], T("En iyi çekilme eşiği", "Best drop-out level"), f"{k(en['cekilme'])} {T('bin €/MW', 'k€/MW')}",
                aciklama=T(f"beklenen değerimiz {k(float(deger_biz.mean()))}", f"our expected value {k(float(deger_biz.mean()))}"))  # fmt: skip
    B.kpi_karti(u[1], T("Kazanma olasılığı", "Win probability"), yuzde(100 * en["p_kazanma"], 0),
                aciklama=T(f"beklenen ödeme {k(en['beklenen_odeme'])}", f"expected payment {k(en['beklenen_odeme'])}"))  # fmt: skip
    st.caption(md(T(
        f"Beklenen fazla {sayi(en['beklenen_fazla'] / 1e3, 0)} bin €/MW (× {sayi(L['mw'], 0)} MW ≈ {sayi(en['beklenen_fazla'] * L['mw'] / 1e6, 1)} M€). "
        + (f"Kazanırsak değerimizin ödediğimizden düşük çıkma olasılığı %{sayi(100 * en['kazaninca_zarar_olasiligi'], 0)} (kazananın laneti göstergesi)."
           if en.get("kazaninca_zarar_olasiligi") is not None else "Bu primle kazanma olasılığı yok: değerimiz rakiplerin çok altında."),
        f"Expected surplus {sayi(en['beklenen_fazla'] / 1e3, 0)} k€/MW (× {sayi(L['mw'], 0)} MW ≈ {sayi(en['beklenen_fazla'] * L['mw'] / 1e6, 1)} M€). "
        + (f"If we win, probability our value is below what we pay {sayi(100 * en['kazaninca_zarar_olasiligi'], 0)}% (winner's-curse indicator)."
           if en.get("kazaninca_zarar_olasiligi") is not None else "No chance of winning at this premium: our value is far below rivals'."),
    )))  # fmt: skip
with c[1]:
    x = np.array([e["cekilme"] for e in eg]) / 1e3
    f = go.Figure()
    f.add_trace(
        go.Scatter(
            x=x, y=[100 * e["p_kazanma"] for e in eg], name=T("kazanma olasılığı (%)", "win probability (%)"), line=dict(color=RES, width=2)
        )
    )
    f.add_trace(go.Scatter(x=x, y=[e["beklenen_fazla"] / 1e3 for e in eg], name=T("beklenen fazla (bin €/MW)", "expected surplus (k€/MW)"),
                           line=dict(color=GES, width=2), yaxis="y2", fill="tozeroy", fillcolor=dolgu(GES, 0.1)))  # fmt: skip
    f.add_vline(x=en["cekilme"] / 1e3, line_color=SOLUK, line_dash="dot")
    f.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False), hovermode="x unified", legend=dict(y=-0.3))
    ciz(sekil(f, T(f"{sec}: çekilme eşiği", f"{sec}: drop-out level"), "%", T("çekilme eşiği (bin €/MW)", "drop-out level (k€/MW)"), yukseklik=400,
              alt=T(f"{R['n'] - 1} rakip · rakip değerleri N({k(R['mu_rakip'])}; {k(m['s'])}) bin €/MW", f"{R['n'] - 1} rivals · rival values N({k(R['mu_rakip'])}; {k(m['s'])}) k€/MW")))  # fmt: skip

# --- 3. Model ve doğrulama
B.bolum_basligi(T("3. Rakip değer modeli ve doğrulama", "3. Rival value model and validation"))
st.markdown(md(T(
    "**Model:** istekli j'nin lot i'deki değeri V = v̂ᵢ + δ + γ·ln(MWᵢ/150) + s·ε. v̂: bizim modelimizin başabaş katkı payı (temsilî nokta, "
    "100 MW RES, 72 ay tüccar + 20 yıl alım). Gözlenen katkı payı = nᵢ istekli arasında ikinci en yüksek değer; yoğunluğu "
    "f(y) = n(n−1) Φ(z)ⁿ⁻² (1−Φ(z)) φ(z)/s, tabana inme koşuluyla (ikinci en yüksek ≥ 10 bin €) kesilmiş — tabana inmeyen yarışmada katkı payı "
    "gözlenmezdi (seçilim yanlılığı). Parametreler 11 geçmiş yarışmadan **en çok olabilirlik** ile; güven aralıkları lot bazında bootstrap.",
    "**Model:** bidder j's value for lot i is V = v̂ᵢ + δ + γ·ln(MWᵢ/150) + s·ε. v̂: our model's break-even fee (representative point, "
    "100 MW wind, 72 months merchant + 20-year purchase). The observed fee = second-highest value among nᵢ bidders; density "
    "f(y) = n(n−1) Φ(z)ⁿ⁻² (1−Φ(z)) φ(z)/s, truncated on reaching the floor (second-highest ≥ 10 k€) — a fee would not be observed in an "
    "auction that stopped above the floor (selection bias). Parameters by **maximum likelihood** from 11 past auctions; confidence intervals by lot bootstrap.",
)))  # fmt: skip
h = [x for x in p["lotlar"] if x.get("katki_eur_mw") is not None]
c = st.columns([1.3, 1], gap="medium")
with c[0]:
    f = go.Figure()
    ad = [x["kod"] for x in h]
    f.add_trace(go.Bar(x=ad, y=[(x["loo_p90"] - x["loo_p10"]) / 1e3 for x in h], base=[x["loo_p10"] / 1e3 for x in h],
                       marker_color=dolgu(SOLUK, 0.35), name=T("tahmin %80 aralığı", "prediction 80% interval")))  # fmt: skip
    f.add_trace(
        go.Scatter(
            x=ad,
            y=[x["loo_p50"] / 1e3 for x in h],
            mode="markers",
            marker=dict(color=SOLUK, size=8),
            name=T("tahmin medyanı", "prediction median"),
        )
    )
    f.add_trace(go.Scatter(x=ad, y=[x["katki_eur_mw"] / 1e3 for x in h], mode="markers", marker=dict(color=GES, size=10, symbol="diamond"),
                           name=T("gözlenen", "observed")))  # fmt: skip
    ciz(sekil(f, T("Birini dışarıda bırak doğrulaması", "Leave-one-out validation"), T("bin €/MW", "k€/MW"), "", yukseklik=380,
              alt=T("her yarışma kalan 10 yarışmayla tahmin edildi", "each auction predicted from the other 10")))  # fmt: skip
with c[1]:
    B.karsilastirma_tablosu(
        [T("Bizim varsayımımız piyasaya yaklaşırsa", "If our assumption moves towards the market"), "δ", T("kapanan", "closed")],
        [[T(x["ad"], x.get("ad_en", x["ad"])), k(x["delta"]), yuzde(100 * x["kapanan_oran"], 0)] for x in p["duyarlilik"]],
    )  # fmt: skip
    st.caption(T("Piyasanın ödediği katkı payı yalnız beş iyimser varsayımın birlikte alınmasıyla açıklanıyor. Ya piyasa bizden belirgin "
                 "biçimde iyimser ya da kazananlar aşırı ödüyor (kazananın laneti).",
                 "The fees the market pays are explained only by taking five optimistic assumptions together. Either the market is markedly "
                 "more optimistic than we are, or winners overpay (winner's curse)."))  # fmt: skip
