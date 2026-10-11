"""
Portföy (v3 Faz F): aday sahalar → bütçe, risk ağırlığı ve bağlantı kapasitesiyle iki aşamalı stokastik MILP (ortalama–CVaR),
etkin sınır, seçilen portföyün haritası ve tablosu, sinerji ve çeşitlendirme ayrıştırması, işletme modeli ve yedek parça havuzu.

Veri: data/atlas/portfoy (src/v3_F1_adaylar.py, src/v3_F3_portfoy.py). Uygulamada çözüm 1.000 ortak senaryoluk alt örnekle
(≤ 30 s, 2 çekirdek); etkin sınır ve duyarlılıklar çevrimdışı 2.000 senaryoyla hesaplanmıştır.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from src.portfoy import analiz as PA
from src.portfoy import model as M
from src.portfoy import veri as PV
from uygulama import harita as H
from uygulama.ortak import RES, SOLUK, T, ciz, md, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.stil import aktif_tema
from uygulama.tasarim.tokenlar import TEMALAR

ALT_ORNEK = 1000


@st.cache_data(show_spinner=False)
def _json(ad: str) -> dict:
    p = veri_katmani.yol(f"atlas/portfoy/{ad}", zorunlu=False)
    return json.loads(p.read_text(encoding="utf-8")) if p is not None else {}


@st.cache_resource(show_spinner=False)
def _veri(duzeltme: bool = True):
    return PV.yukle(duzeltme=duzeltme), PV.ortak()


@st.cache_data(show_spinner=False, max_entries=16)
def _coz(kodlar: tuple[str, ...], butce: float, lam: float, bolge: float | None, sinerji: tuple[bool, ...], duzeltme: bool = True) -> dict:
    v, o = _veri(duzeltme)
    sec = v.tas["kod"].isin(kodlar).to_numpy()
    vv = M.Veri(
        tas=v.tas[sec].reset_index(drop=True), ad=v.ad[v.ad["kod"].isin(kodlar)].reset_index(drop=True), V=v.V[sec], lojistik=v.lojistik
    )
    sn = np.random.default_rng(0).choice(v.V.shape[1], ALT_ORNEK, replace=False)
    ad = dict(zip(("isletme", "havuz", "indirim", "ulastirma"), sinerji))
    r = M.coz(vv, M.Ayar(lam=lam, butce_musd=butce, bolge_kapasite_mw=bolge, sinerji=ad, zaman_s=25), senaryo=sn)
    secili = r["secim"].index.to_numpy()
    ce = PA.cesitlendirme(vv.V[secili][:, sn], {k: x[sn] for k, x in o.items()}, r["psi_musd"]) if len(secili) else None
    return {
        "secim": r["secim"].to_dict(orient="records"),
        **{
            k: r[k]
            for k in (
                "e_npv",
                "cvar",
                "p_pozitif",
                "capex_musd",
                "psi_musd",
                "psi_kalem",
                "kendi_bakimi",
                "havuz",
                "indirim_kademesi",
                "sure_s",
                "durum",
            )
        },
        "depo": r["sp"]["depo"],
        "tau": r["sp"]["tau_gun"],
        "cesitlendirme": ce,
        "Pi": r["Pi"].tolist(),
    }


st.title(T("Portföy", "Portfolio"))
st.caption(
    T(
        "Tek bir sahayı değil, birkaç sahadan oluşan bir yatırım portföyünü seçer. Tüm adaylar aynı 2.000 senaryoyla değerlendirildi: "
        "aynı fiyat yolu, aynı batarya/SFK senaryosu, aynı düzenleyici olaylar ve her sahada aynı ERA5 hava yılı (sahalar arası rüzgâr "
        "korelasyonu korunur). Amaç beklenen NPV ile en kötü %5 senaryonun ortalamasının (CVaR) ağırlıklı birleşimi. Ayrıntı: "
        "docs/v3_F_portfoy_performans.md.",
        "Chooses a portfolio of several sites instead of one. All candidates were valued on the same 2,000 scenarios: same price path, "
        "same battery/ancillary scenario, same regulatory events and the same ERA5 weather year at every site (cross-site wind "
        "correlation is preserved). The objective weighs expected NPV against the mean of the worst 5% (CVaR). Details: "
        "docs/v3_F_portfoy_performans.md.",
    )
)
duz = st.toggle(
    T("Optimize edicinin lanetine karşı düzeltme (önerilen)", "Correction for the optimiser's curse (recommended)"),
    True,
    key="pf_duz",
    help=T(
        "40 aday arasından en iyi görünenleri seçmek, rüzgâr tahmini olduğundan iyi çıkmış sahaları seçmek demektir; seçilen portföyün "
        "tahmini değeri sistematik olarak iyimser olur. Düzeltme her adayın KF tahminini, tahmin belirsizliğine (güven seviyesi) göre "
        "bölgesel ortalamaya doğru büzer (Bayesçi büzülme). Ayrıntı: docs/v3_F_portfoy_performans.md §8.",
        "Picking the best-looking of 40 candidates means picking sites whose wind estimate came out too high; the selected portfolio's "
        "estimated value is systematically optimistic. The correction shrinks each candidate's capacity-factor estimate towards the "
        "regional mean according to its estimation uncertainty (Bayesian shrinkage). Details: docs/v3_F_portfoy_performans.md §8.",
    ),
)
try:
    v, o = _veri(duz)
except Exception:
    B.bos_durum(T("Portföy verisi yok", "No portfolio data"), T("src/v3_F1_adaylar.py çalıştırılmalı.", "Run src/v3_F1_adaylar.py."))
    st.stop()
an = _json("analiz.json" if duz else "analiz_duzeltmesiz.json")
if duz:
    st.caption(T("Tahminler optimize edicinin lanetine karşı büzülmüş (varsayılan). Kapatırsanız saf tahminlerle seçilen portföy ortalamada iyimser olur.",
                 "Estimates are shrunk against the optimiser's curse (default). Switching off gives a portfolio that is optimistic on average."))  # fmt: skip
tema = aktif_tema()
vr = TEMALAR[tema]["veri"]
rk = TEMALAR[tema]["renk"]

# --- 1. Girdiler
B.bolum_basligi(
    T("1. Adaylar ve kısıtlar", "1. Candidates and constraints"),
    T(f"{len(v.ad)} aday hücre, {len(v.tas)} tasarım seçeneği", f"{len(v.ad)} candidate cells, {len(v.tas)} design options"),
)
etiket = {r.kod: f"{r.kod} · {r.il}/{r.ilce}" for r in v.ad.itertuples()}
c = st.columns([1.4, 1], gap="medium")
with c[0]:
    kip = st.segmented_control(
        T("Aday kümesi", "Candidate set"), ["oto", "secim"], default="oto",
        format_func=lambda x: T("Otomatik liste (tümü)", "Automatic list (all)") if x == "oto" else T("Kendi seçimim", "My selection"), key="pf_kip",
    ) or "oto"  # fmt: skip
    if kip == "secim":
        kodlar = st.multiselect(
            T("Sahalar", "Sites"), list(etiket), default=list(etiket)[:8], format_func=lambda k: etiket[k], key="pf_kodlar"
        )
    else:
        kodlar = list(etiket)
    butce = st.slider(T("Bütçe (toplam CAPEX, M$)", "Budget (total CAPEX, M$)"), 50, 800, 300, 25, key="pf_butce")
    lam = st.slider(
        T("Risk ağırlığı λ (0 = yalnız beklenen değer)", "Risk weight λ (0 = expected value only)"), 0.0, 0.5, 0.0, 0.05, key="pf_lam",
        help=T("Amaç = (1 − λ) · E[NPV] + λ · CVaR %5. λ büyüdükçe kötü senaryolar ağırlaşır; çok riskten kaçınan yatırımcı için 'hiç yatırım yapma' optimal olabilir.",
               "Objective = (1 − λ) · E[NPV] + λ · CVaR 5%. Larger λ weighs bad scenarios more; for a very risk-averse investor 'invest nothing' can be optimal."),
    )  # fmt: skip
with c[1]:
    bk = st.selectbox(
        T("Bölge başına bağlantı kapasitesi", "Grid capacity per region"), [50.0, 100.0, 150.0, 0.0], index=2,
        format_func=lambda x: T("sınırsız", "unlimited") if x == 0 else f"{x:.0f} MW", key="pf_bolge",
        help=T("TEİAŞ lisanslı bağlantı kapasitesini yayımlamadığı için parametre: aynı bölgedeki sahalar aynı kapasite için yarışır.",
               "A parameter because TEİAŞ does not publish licensed connection capacity: sites in one region compete for the same capacity."),
    )  # fmt: skip
    st.caption(T("Sinerjiler", "Synergies"))
    s1 = st.toggle(T("İşletme ölçeği (kendi bakımı)", "O&M scale (self-perform)"), True, key="pf_s1")
    s2 = st.toggle(T("Yedek parça havuzu", "Spare-part pooling"), True, key="pf_s2", disabled=not s1)
    s3 = st.toggle(T("Toplu türbin alımı indirimi", "Bulk turbine discount"), True, key="pf_s3")
    s4 = st.toggle(T("Çok sahalı ulaştırma (kapasiteler)", "Multi-site transport (capacities)"), True, key="pf_s4")
if not kodlar:
    st.info(T("En az bir saha seçin.", "Select at least one site."))
    st.stop()
with st.spinner(T("Portföy optimize ediliyor (MILP, 1.000 senaryo)…", "Optimising the portfolio (MILP, 1,000 scenarios)…")):
    r = _coz(tuple(kodlar), float(butce), float(lam), None if bk == 0 else float(bk), (s1, s2 and s1, s3, s4), duz)
sec = pd.DataFrame(r["secim"])

# --- 2. Sonuç
B.bolum_basligi(
    T("2. Seçilen portföy", "2. Selected portfolio"), T(f"çözüm {sayi(r['sure_s'], 1)} s", f"solved in {sayi(r['sure_s'], 1)} s")
)
if sec.empty:
    B.uyari_kutusu(
        T("**Hiç yatırım yapmamak optimal.** Bu bütçe ve risk ağırlığında hiçbir saha bileşimi beklenen değer ile kuyruk riskinin dengesini pozitif yapmıyor.",
          "**Investing nothing is optimal.** At this budget and risk weight no combination of sites makes the expected value–tail risk trade-off positive."),
        "bilgi",
    )  # fmt: skip
k = st.columns(5)
B.kpi_karti(k[0], T("Beklenen NPV", "Expected NPV"), f"{sayi(r['e_npv'], 1)} M$")
B.kpi_karti(k[1], "CVaR %5", f"{sayi(r['cvar'], 1)} M$")
B.kpi_karti(k[2], T("Kâr olasılığı", "P(NPV > 0)"), yuzde(100 * r["p_pozitif"], 0))
B.kpi_karti(k[3], "CAPEX", f"{sayi(r['capex_musd'], 0)} M$", aciklama=T(f"bütçe {butce}", f"budget {butce}"))
B.kpi_karti(k[4], T("Saha / türbin", "Sites / turbines"), f"{len(sec)} / {int(sec['N'].sum()) if len(sec) else 0}")
c = st.columns([1.2, 1], gap="medium")
with c[0]:
    try:
        from streamlit_folium import st_folium

        ad = v.ad.set_index("kod")
        secili = set(sec["kod"]) if len(sec) else set()
        aday = v.ad[v.ad["kod"].isin(kodlar)].reset_index(drop=True)
        renk = [vr["res"] if k_ in secili else rk["metin_silik"] for k_ in aday["kod"]]
        ip = [f"<b>{k_}</b> {r_.il}/{r_.ilce}" for k_, r_ in zip(aday["kod"], aday.itertuples())]
        cz = []
        if r["havuz"] and len(sec):
            dp = ad.loc[r["depo"]]
            cz = [{"nokta": [[dp.enlem, dp.boylam], [ad.loc[k_].enlem, ad.loc[k_].boylam]], "renk": vr["altin"]} for k_ in secili]
        m = H.nokta_haritasi(aday, renk, ip, tema, boyut=[8 if k_ in secili else 4 for k_ in aday["kod"]], cizgiler=cz)
        st_folium(m, height=380, use_container_width=True, returned_objects=[], key="pf_harita")
    except Exception:
        pass
    st.caption(T("Dolgulu: seçilen sahalar · soluk: diğer adaylar" + (" · kesikli: yedek parça havuzu deposuna bağlantı" if r["havuz"] else ""),
                 "Filled: selected sites · faint: other candidates" + (" · dashed: link to the spare-part depot" if r["havuz"] else "")))  # fmt: skip
with c[1]:
    if len(sec):
        B.karsilastirma_tablosu(
            [T("Saha", "Site"), T("Tasarım", "Design"), "RES MW", T("Batarya", "Battery"), "CAPEX", "E[NPV]"],
            [[etiket[x.kod], x.tasarim, sayi(x.res_mw, 1), sayi(x.bess_mw, 0), sayi(x.capex_musd, 0), sayi(x.e_npv, 1)] for x in sec.itertuples()],
            mobilde_gizle=(2, 3),
        )  # fmt: skip
        st.caption(
            T(
                "E[NPV]: tek başına (2.000 senaryo). Portföy değeri buna sinerjileri ekler.",
                "E[NPV]: stand-alone (2,000 scenarios). Portfolio value adds synergies.",
            )
        )

# --- 3. Etkin sınır
B.bolum_basligi(
    T("3. Etkin sınır", "3. Efficient frontier"),
    T("beklenen NPV – CVaR %5 (çevrimdışı, bütçe 300 M$)", "expected NPV – CVaR 5% (offline, budget 300 M$)"),
)
es = pd.DataFrame(an.get("etkin_sinir", []))
f = go.Figure()
if len(es):
    es = es.sort_values("cvar")
    f.add_trace(go.Scatter(x=es["cvar"], y=es["e_npv"], mode="lines+markers", line={"color": RES, "width": 2.5}, name=T("Etkin sınır", "Frontier"),
                           text=es["secim"], hovertemplate="CVaR %{x:.1f} · E %{y:.1f}<br>%{text}<extra></extra>"))  # fmt: skip
if an.get("tek_saha"):
    ts = an["tek_saha"]
    f.add_trace(
        go.Scatter(
            x=[ts["cvar"]],
            y=[ts["e_npv"]],
            mode="markers",
            marker={"color": vr["ges"], "size": 11, "symbol": "diamond"},
            name=T("En iyi tek saha", "Best single site"),
            text=[ts["secim"]],
        )
    )
f.add_trace(
    go.Scatter(
        x=[r["cvar"]],
        y=[r["e_npv"]],
        mode="markers",
        marker={"color": vr["altin"], "size": 13, "symbol": "star"},
        name=T("Seçiminiz", "Your choice"),
    )
)
ciz(
    sekil(
        f,
        "",
        T("Beklenen NPV [M$]", "Expected NPV [M$]"),
        T("CVaR %5 [M$] (sağa doğru daha az kuyruk riski)", "CVaR 5% [M$] (less tail risk to the right)"),
        yukseklik=360,
    )
)
if an.get("tek_saha") and an.get("ayni_cvar_portfoy"):
    ts, ac = an["tek_saha"], an["ayni_cvar_portfoy"]
    ayni = len(ac["secim"]) == 1 and ac["secim"][0] == ts["secim"]
    st.markdown(md(T(
        f"En iyi tek saha ({ts['secim']}): E[NPV] {sayi(ts['e_npv'], 1)} M$, CVaR {sayi(ts['cvar'], 1)} M$. "
        + ("**Aynı kuyruk riskinde en iyi portföy bu tek sahanın kendisi:** kuyruk riski ortak fiyattan geldiği için saha eklemek kuyruğu "
           "kötüleştiriyor. Portföy, daha fazla risk karşılığında orantılı daha fazla değer ve sinerji sağlıyor." if ayni else
           f"**Aynı kuyruk riskinde** optimal portföy E[NPV] {sayi(ac['e_npv'], 1)} M$ veriyor ({', '.join(ac['secim'])})."),
        f"Best single site ({ts['secim']}): E[NPV] {sayi(ts['e_npv'], 1)} M$, CVaR {sayi(ts['cvar'], 1)} M$. "
        + ("**At the same tail risk the best portfolio is that single site:** tail risk comes from the common price, so adding sites worsens "
           "the tail. A portfolio buys proportionally more value and synergies for more risk." if ayni else
           f"**At the same tail risk** the optimal portfolio gives E[NPV] {sayi(ac['e_npv'], 1)} M$ ({', '.join(ac['secim'])})."),
    )))  # fmt: skip

# --- 4. Sinerji ve çeşitlendirme
B.bolum_basligi(
    T("4. Değer ayrıştırması", "4. Value decomposition"),
    T("sinerjiler beklenen değeri, çeşitlendirme riski değiştirir", "synergies change expected value, diversification changes risk"),
)
c = st.columns(2, gap="medium")
ad_k = {
    "isletme": T("İşletme ölçeği", "O&M scale"),
    "havuz": T("Yedek parça havuzu", "Spare pooling"),
    "indirim": T("Toplu indirim", "Bulk discount"),
    "ulastirma": T("Ulaştırma", "Transport"),
}
with c[0]:
    pk = r["psi_kalem"]
    f = go.Figure(go.Bar(x=[ad_k[k_] for k_ in pk], y=list(pk.values()), marker_color=[vr["res"] if x >= 0 else vr["batarya"] for x in pk.values()],
                         text=[sayi(x, 2) for x in pk.values()], textposition="outside"))  # fmt: skip
    ciz(sekil(f, T("Sinerjilerin bugünkü değeri", "Present value of synergies"), "M$", "", yukseklik=300))
with c[1]:
    ce = r["cesitlendirme"]
    if ce and ce["n"] > 1:
        parca = {
            T("Ortak piyasa (fiyat, SFK, CAPEX)", "Common market (price, SFK, CAPEX)"): ce["var_ortak_piyasa"],
            T("Hava korelasyonu", "Weather correlation"): ce["var_hava_korelasyonu"],
            T("Sahaya özgü", "Site-specific"): ce["var_sahaya_ozgu"],
        }
        tp = sum(max(x, 0) for x in parca.values())
        f = go.Figure(go.Bar(x=list(parca), y=[100 * max(x, 0) / tp for x in parca.values()], marker_color=[vr["koyu"], vr["res"], vr["ges"]],
                             text=[yuzde(100 * max(x, 0) / tp, 0) for x in parca.values()], textposition="outside"))  # fmt: skip
        ciz(sekil(f, T("Portföy NPV varyansının kaynağı", "Sources of portfolio NPV variance"), "%", "", yukseklik=300))
    else:
        st.caption(
            T("Çeşitlendirme ayrıştırması için en az iki saha gerekir.", "At least two sites are needed for the diversification split.")
        )
if ce and ce["n"] > 1:
    st.markdown(md(T(
        f"**Çeşitlendirme:** sahaların tek tek standart sapmalarının toplamı {sayi(ce['sigma_toplam_tek'], 1)} M$, portföyünki {sayi(ce['sigma_portfoy'], 1)} M$ "
        f"(fark {sayi(ce['cesitlendirme_sigma'], 1)} M$). CVaR %5: tek tek toplam {sayi(ce['cvar_toplam_tek'], 1)}, portföy {sayi(ce['cvar_portfoy'], 1)} M$ "
        f"(iyileşme {sayi(ce['cesitlendirme_cvar'], 1)} M$). Varyansın %{sayi(100 * ce['pay_ortak_piyasa'], 0)}'i ortak piyasadan: fiyat herkes için aynı "
        "olduğundan saha eklemek bu kısmı azaltmaz — çeşitlendirmenin sınırı budur.",
        f"**Diversification:** sum of stand-alone standard deviations {sayi(ce['sigma_toplam_tek'], 1)} M$, portfolio {sayi(ce['sigma_portfoy'], 1)} M$ "
        f"(gap {sayi(ce['cesitlendirme_sigma'], 1)} M$). CVaR 5%: stand-alone sum {sayi(ce['cvar_toplam_tek'], 1)}, portfolio {sayi(ce['cvar_portfoy'], 1)} M$ "
        f"(improvement {sayi(ce['cesitlendirme_cvar'], 1)} M$). {sayi(100 * ce['pay_ortak_piyasa'], 0)}% of the variance is common market risk: the price is the "
        "same for everyone, so adding sites does not reduce it — this is the limit of diversification.",
    )))  # fmt: skip
eg = pd.DataFrame(an.get("cesitlendirme_egrisi", []))
if len(eg):
    f = go.Figure()
    f.add_trace(
        go.Scatter(x=eg["n"], y=eg["sigma_saha_basina"], mode="lines+markers", line={"color": RES}, name=T("σ / saha", "σ per site"))
    )
    f.add_trace(
        go.Scatter(
            x=eg["n"],
            y=100 * eg["ortak_piyasa_payi"],
            mode="lines+markers",
            line={"color": SOLUK, "dash": "dot"},
            name=T("ortak piyasa payı [%]", "common market share [%]"),
            yaxis="y2",
        )
    )
    f.update_layout(yaxis2={"overlaying": "y", "side": "right", "range": [0, 100], "showgrid": False})
    ciz(sekil(f, T("Saha sayısı arttıkça saha başına risk ve ortak piyasa payı (rastgele portföyler)", "Risk per site and common-market share as sites are added (random portfolios)"),
              "M$", T("saha sayısı", "number of sites"), yukseklik=300))  # fmt: skip

# --- 5. İşletme modeli ve yedek parça
B.bolum_basligi(T("5. İşletme modeli ve yedek parça havuzu", "5. Operating model and spare-part pool"))
nt = int(sec["N"].sum()) if len(sec) else 0
oz = _json("parametreler.json")
tr_tr = ", ".join(f"{k_} {sayi(r['tau'][k_], 1)} gün" for k_ in sec["kod"]) if len(sec) else ""
tr_en = ", ".join(f"{k_} {sayi(r['tau'][k_], 1)} days" for k_ in sec["kod"]) if len(sec) else ""
st.markdown(md(T(
    f"Portföyde **{nt} türbin**. Tek saha için kendi bakımının başabaş filo büyüklüğü {oz.get('N_basabas', 16)} türbin (Faz D/E); portföyde organizasyon "
    f"sabit gideri ve her aktif bölgedeki üs maliyeti de hesaba katılarak karar: **{'kendi bakımı' if r['kendi_bakimi'] else 'tam kapsamlı servis sözleşmesi (FSA)'}**. "
    + (f"Yedek parça havuzu kuruldu: depo {etiket.get(r['depo'], r['depo'])}; sahalara transfer {tr_tr}. "
       "FSA'da yedek parça üreticinin sorumluluğunda olduğundan havuz yalnız kendi bakımında anlamlıdır." if r["havuz"] else "Yedek parça havuzu yok (FSA'da parça üreticinin)."),
    f"The portfolio has **{nt} turbines**. Single-site self-perform break-even fleet is {oz.get('N_basabas', 16)} turbines (Phase D/E); including the "
    f"organisation fixed cost and a base per active region, the decision is **{'self-perform' if r['kendi_bakimi'] else 'full service agreement (FSA)'}**. "
    + (f"Spare-part pool set up: depot {etiket.get(r['depo'], r['depo'])}; transfer {tr_en}. "
       "Under an FSA spares are the OEM's, so pooling only matters when self-performing." if r["havuz"] else "No spare-part pool (spares are the OEM's under an FSA)."),
)))  # fmt: skip

# --- 6. Fiyat ve korelasyon
B.bolum_basligi(T("6. Fiyata göre portföy ve bölgeler arası korelasyon", "6. Portfolio by price and cross-regional correlation"))
c = st.columns(2, gap="medium")
with c[0]:
    fy = pd.DataFrame(an.get("fiyat", []))
    if len(fy):
        f = go.Figure()
        f.add_trace(go.Bar(x=fy["fiyat"], y=fy["n"], marker_color=RES, name=T("saha sayısı (λ = 0)", "sites (λ = 0)")))
        f.add_trace(
            go.Scatter(
                x=fy["fiyat"],
                y=fy["n_cvar30"],
                mode="lines+markers",
                line={"color": vr["altin"]},
                name=T("saha sayısı (CVaR ≥ −30)", "sites (CVaR ≥ −30)"),
            )
        )
        ciz(
            sekil(
                f,
                T("Uzun vadeli fiyata göre seçilen saha sayısı", "Sites selected by long-run price"),
                T("saha", "sites"),
                "$/MWh",
                yukseklik=300,
            )
        )
        if an.get("yatirim_yok_esik_fiyat") is not None:
            es = an.get("esik_sinerji") or {}
            ek_tr = ek_en = ""
            if es and es.get("sinerjili_n", 0) > es.get("sinerjisiz_n", 0):
                neg = sum(1 for x in es.get("tek_tek_e", []) if x < 0)
                ek_tr = f" {sayi(es['fiyat'], 0)} $/MWh'de seçilen {es['sinerjili_n']} sahanın {neg}'ü tek başına negatif; portföyü sinerjiler pozitif yapıyor."
                ek_en = f" At {sayi(es['fiyat'], 0)} $/MWh {neg} of the {es['sinerjili_n']} selected sites are negative alone; synergies make the portfolio positive."
            lam_e = an.get("yatirim_yok_esik_lambda")
            st.caption(md(T(f"Hiç yatırım yapmamak optimal: risk nötr yatırımcı için uzun vadeli fiyat ≤ {sayi(an['yatirim_yok_esik_fiyat'], 0)} $/MWh"
                            + (f"; 58 $/MWh'de risk ağırlığı λ ≥ {sayi(lam_e, 2)}." if lam_e is not None else ".") + ek_tr,
                            f"Investing nothing is optimal: for a risk-neutral investor at a long-run price ≤ {sayi(an['yatirim_yok_esik_fiyat'], 0)} $/MWh"
                            + (f"; at 58 $/MWh with risk weight λ ≥ {sayi(lam_e, 2)}." if lam_e is not None else ".") + ek_en)))  # fmt: skip
with c[1]:
    kr = _json("korelasyon.json")
    if kr.get("bolge"):
        mat = kr["bolge"]["aylik"]
        f = go.Figure(go.Heatmap(z=mat["matris"], x=mat["etiket"], y=mat["etiket"], zmin=-0.2, zmax=1, colorscale=[[0, rk["yuzey"]], [1, RES]],
                                 text=[[sayi(x, 2) for x in s_] for s_ in mat["matris"]], texttemplate="%{text}"))  # fmt: skip
        ciz(
            sekil(
                f,
                T("Bölgeler arası aylık RES üretimi korelasyonu", "Monthly wind output correlation between regions"),
                "",
                "",
                yukseklik=320,
            )
        )
        st.caption(md(T(
            f"Saatlik korelasyon mesafeyle ~{sayi(kr['uzunluk_olcegi_km']['saatlik'], 0)} km ölçekle azalıyor: 100 km içinde {sayi(kr['yakin_100km']['saatlik'], 2)}, "
            f"500 km ötesinde {sayi(kr['uzak_500km']['saatlik'], 2)}. Sahalar arası NPV korelasyonu ise ortalama {sayi(kr['npv_korelasyon']['ortalama'], 2)}: fiyat ortak.",
            f"Hourly correlation decays with distance on a ~{sayi(kr['uzunluk_olcegi_km']['saatlik'], 0)} km scale: {sayi(kr['yakin_100km']['saatlik'], 2)} within 100 km, "
            f"{sayi(kr['uzak_500km']['saatlik'], 2)} beyond 500 km. Cross-site NPV correlation averages {sayi(kr['npv_korelasyon']['ortalama'], 2)}: the price is common.",
        )))  # fmt: skip
