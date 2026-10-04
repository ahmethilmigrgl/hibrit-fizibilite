"""
Hibrit GES + RES + BESS fizibilite — Streamlit dashboard.

Yalnızca results/ (küçük, toplulaştırılmış sonuçlar) ve config.yaml ile çalışır; kimlik bilgisi veya ham veri gerekmez.
Yerelde:  .venv/bin/streamlit run app.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from src.ayarlar import config_oku  # noqa: E402
from src.risk.gezgin import TURBIN_GUCU, gezgin_degerle, gezgin_yukle  # noqa: E402

R = KOK / "results"
REPO_URL = "https://github.com/KULLANICI/hibrit-fizibilite"   # yayından sonra güncellenecek

# Palet (outputs/ grafikleriyle aynı; renk körlüğü için doğrulanmış kategorik sıra)
RES, GES, HIBRIT, BATARYA, KOYU, SOLUK = "#2a78d6", "#eb6834", "#1baf7a", "#7f6bd1", "#1d4f91", "#8a8984"
TASARIM_RENK = {"A": RES, "C": BATARYA, "D": HIBRIT, "E": KOYU, "F1": GES, "F2": "#b8860b", "F2a": "#c9a227"}
SENARYO_RENK = {"Yavaş doyum": HIBRIT, "Baz doyum": RES, "Hızlı doyum": GES, "SFK'ya katılamama": SOLUK}

st.set_page_config(page_title="Hibrit Fizibilite — Ezine", page_icon="⚡", layout="wide")

ust1, ust2 = st.columns([6, 1])
with ust2:
    dil = st.radio("Dil / Language", ["TR", "EN"], horizontal=True, label_visibility="collapsed")


def T(tr: str, en: str) -> str:
    return tr if dil == "TR" else en


def sayi(x: float, d: int = 1) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if dil == "TR" else s


def yuzde(x: float, d: int = 0) -> str:
    return f"%{sayi(x, d)}" if dil == "TR" else f"{sayi(x, d)}%"


def sekil(fig: go.Figure, baslik: str = "", y: str = "", x: str = "", yukseklik: int = 380) -> go.Figure:
    fig.update_layout(title=dict(text=baslik, x=0, font=dict(size=15)), height=yukseklik, margin=dict(l=10, r=10, t=50, b=10),
                      plot_bgcolor="white", paper_bgcolor="white", legend=dict(orientation="h", y=-0.2),
                      font=dict(family="Inter, Arial", size=12), hovermode="x unified")
    fig.update_xaxes(title=x, showgrid=False, linecolor="#d0cfca")
    fig.update_yaxes(title=y, gridcolor="#ecebe7", zerolinecolor="#b9b8b2")
    return fig


@st.cache_data
def oku(ad: str, **kw) -> pd.DataFrame:
    return pd.read_csv(R / ad, encoding="utf-8-sig", **kw)


@st.cache_resource
def kaynaklar():
    return config_oku(), gezgin_yukle(R), np.load(R / "s_npv_ornekleri.npz", allow_pickle=False)


cfg, gz, npv_orn = kaynaklar()
met = oku("s_metrikler.csv")
pen = oku("s_minimum_pencere.csv")
eski = oku("b_metrikler_revizyon_oncesi.csv")
kisa = lambda s: s.split(":")[0]
m_ = {kisa(r["Tasarım"]): r for _, r in met.iterrows()}
e_ = {kisa(r["Tasarım"]): r for _, r in eski.iterrows()}

with ust1:
    st.title(T("Ezine hibrit RES + batarya fizibilitesi", "Ezine hybrid wind + battery feasibility"))
    st.caption(T("50 MW şebeke bağlantısında GES/RES/batarya boyutlandırma, NPV optimizasyonu (Pyomo + HiGHS) ve Monte Carlo risk analizi. "
                 "Reel 2026 USD, %7 reel WACC.",
                 "Sizing solar/wind/battery behind a 50 MW grid connection in Türkiye: NPV optimisation (Pyomo + HiGHS) and Monte Carlo "
                 "risk analysis. Real 2026 USD, 7% real WACC."))

sekmeler = st.tabs([T("Özet", "Summary"), T("Saha ve üretim", "Site & generation"), T("Piyasa", "Market"),
                    T("Tasarım gezgini", "Design explorer"), T("Risk", "Risk"), T("Yöntem", "Method")])

# =====================================================================================================================
with sekmeler[0]:
    st.subheader(T("Yatırım önerisi", "Investment recommendation"))
    st.success(T(
        "**Koşullu onay: RES 58,8 MW (14 × 4,2 MW) + 30 MW / 52,5 MWh batarya (40 MW'a büyütme opsiyonu) + P90 üretimin %70'ine 12 yıllık PPA.** "
        "Koşullar: (1) TEİAŞ'tan hibrit tesisteki bataryanın SFK'ya katılabileceğine dair yazılı ön yeterlilik, (2) PPA fiyatı ≥ ~52 $/MWh, "
        "(3) borcun SFK geliri olmadan ve 45 $/MWh ile boyutlandırılması (~43 M$), (4) batarya siparişinin RES FID'inden ~12 ay sonra, "
        "2027 SFK fiyatları ve kurulu depolama görülerek verilmesi.",
        "**Conditional approval: 58.8 MW wind (14 × 4.2 MW) + 30 MW / 52.5 MWh battery (option to expand to 40 MW) + 12-year PPA on 70% of P90 output.** "
        "Conditions: (1) written TEİAŞ pre-qualification that the battery inside the hybrid plant may provide secondary reserve (SFK), "
        "(2) PPA price ≥ ~52 $/MWh, (3) debt sized without SFK revenue at 45 $/MWh (~43 M$), (4) battery order placed ~12 months after the "
        "wind FID, once 2027 SFK prices and installed storage are known."))
    st.caption(T("Öneri, SFK doyum stres testinden sonra değişti: Aşama 5'te 40 MW'lık bataryalı tasarım %97 olasılıkla kârlı görünüyordu; "
                 "doyum hesaba katılınca bu ~%60'a indi ve bataryanın değeri bir opsiyona dönüştü. Tetikleyiciler: Risk sekmesi ve docs/RAPOR.md.",
                 "The recommendation changed after the SFK saturation stress test: in stage 5 the 40 MW battery design looked profitable with 97% "
                 "probability; with saturation this falls to ~60% and the battery becomes an option. Triggers: Risk tab and docs/RAPOR.md."))
    k = st.columns(4)
    if "F2P" in m_:
        f = m_["F2P"]
        k[0].metric(T("Önerilen tasarım: E[NPV]", "Recommended design: E[NPV]"), f"{sayi(f['Beklenen NPV [M USD]'])} M$",
                    T("doyum senaryolu Monte Carlo", "Monte Carlo with saturation"), delta_color="off")
        k[1].metric(T("Önerilen tasarım: P(NPV > 0)", "Recommended design: P(NPV > 0)"), yuzde(f["P(NPV > 0) [%]"]),
                    T(f"CVaR %5: {sayi(f['CVaR %5 [M USD]'])} M$", f"CVaR 5%: {sayi(f['CVaR %5 [M USD]'])} M$"), delta_color="off")
    if "A" in m_:
        k[2].metric(T("Karşılaştırma: yalnız RES", "Benchmark: wind only"), f"{sayi(m_['A']['Beklenen NPV [M USD]'])} M$",
                    T(f"P(NPV > 0) {yuzde(m_['A']['P(NPV > 0) [%]'])}", f"P(NPV > 0) {yuzde(m_['A']['P(NPV > 0) [%]'])}"), delta_color="off")
    if "C" in e_ and "C" in m_:
        k[3].metric(T("40 MW batarya: Aşama 5 → doyumlu", "40 MW battery: stage 5 → saturation"),
                    f"{yuzde(e_['C']['P(NPV > 0) [%]'])} → {yuzde(m_['C']['P(NPV > 0) [%]'])}",
                    T("kâr olasılığı", "probability of profit"), delta_color="off")
    st.subheader(T("Tek cümlelik bulgular", "Key findings in one line each"))
    st.markdown(T(
        "- **Ezine neden?** Dört aday saha arasında en güçlü rüzgâr kaynağı (kalibre RES kapasite faktörü %37,7, E-141/120 m) ve en iyi GES–RES tamamlayıcılığı.\n"
        "- **GES neden elendi?** Kanibalizasyon: Türkiye'de güneş yakalanma oranı 2019'dan bu yana hızla düşüyor ve 50 MW bağlantıda ek GES'in "
        "%14–40'ı kesiliyor; hiçbir optimizasyonda GES tasarıma girmedi.\n"
        "- **Bataryanın değeri nereden?** Neredeyse tamamen SFK (sekonder frekans) kapasite gelirinden (%87); arbitraj tek başına bataryayı ödemiyor.\n"
        "- **En büyük risk?** Elektrik fiyat seviyesi (NPV varyansının %50–85'i) ve bataryalı tasarımda SFK piyasasının doyumu: ~1 GW'lık ihtiyaca "
        "karşı 28–33 GW depolamalı ön lisans var.",
        "- **Why Ezine?** Strongest wind resource of four candidate sites (calibrated wind capacity factor 37.7%, E-141/120 m) and the best solar–wind complementarity.\n"
        "- **Why no solar?** Cannibalisation: Turkish solar capture rates have fallen fast since 2019 and 14–40% of added PV is curtailed behind 50 MW; "
        "solar never entered any optimal design.\n"
        "- **Where does battery value come from?** Almost entirely from secondary-reserve (SFK) capacity payments (87%); arbitrage alone does not pay.\n"
        "- **Biggest risk?** The power price level (50–85% of NPV variance) and, for the battery, saturation of the ~1 GW SFK market against "
        "28–33 GW of storage pre-licences."))

# =====================================================================================================================
with sekmeler[1]:
    saha = oku("saha_tarama.csv")
    c1, c2 = st.columns(2)
    with c1:
        s = saha.sort_values("RES KF E-141 [%]")
        fig = go.Figure([go.Bar(y=s["Saha"], x=s["RES KF E-141 [%]"], orientation="h", name="RES", marker_color=RES),
                         go.Bar(y=s["Saha"], x=s["GES KF [%]"], orientation="h", name="GES", marker_color=GES)])
        fig.update_layout(barmode="group")
        st.plotly_chart(sekil(fig, T("Saha taraması: kapasite faktörü [%]", "Site screening: capacity factor [%]"), yukseklik=430),
                        width="stretch")
    with c2:
        fig = go.Figure(go.Scatter(x=saha["Saatlik korelasyon"], y=saha["Hibrit satılan [MWh/yıl/MW bağlantı]"], mode="markers+text",
                                   text=saha["Saha"].str.split("-").str[-1], textposition="top center", marker=dict(size=11, color=HIBRIT)))
        st.plotly_chart(sekil(fig, T("Tamamlayıcılık vs bağlantı başına enerji", "Complementarity vs energy per MW of grid"),
                              T("Hibrit satılan [MWh/yıl/MW]", "Hybrid sold [MWh/yr/MW]"), T("GES–RES saatlik korelasyonu", "Hourly solar–wind correlation"),
                              430), width="stretch")
    ay = oku("profil_aylik.csv", header=[0, 1], index_col=0)
    gi = oku("profil_gun_ici.csv", index_col=[0, 1])
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for tek, renk, ad in [("res_kf", RES, "RES"), ("ges_kf", GES, "GES")]:
            fig.add_trace(go.Scatter(x=ay.index, y=100 * ay[("p90", tek)], line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=ay.index, y=100 * ay[("p10", tek)], fill="tonexty", line=dict(width=0), fillcolor=renk + "33",
                                     name=f"{ad} P10–P90", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=ay.index, y=100 * ay[("ortalama", tek)], line=dict(color=renk, width=2.5), name=ad))
        st.plotly_chart(sekil(fig, T("Aylık kapasite faktörü (2014–2023)", "Monthly capacity factor (2014–2023)"), "%", T("Ay", "Month")),
                        width="stretch")
    with c2:
        mevsim = st.selectbox(T("Mevsim", "Season"), ["Yaz", "İlkbahar", "Sonbahar", "Kış"])
        d = gi.loc[mevsim]
        fig = go.Figure([go.Scatter(x=d.index, y=100 * d["res_kf"], name="RES", line=dict(color=RES, width=2.5)),
                         go.Scatter(x=d.index, y=100 * d["ges_kf"], name="GES", line=dict(color=GES, width=2.5))])
        st.plotly_chart(sekil(fig, T("Gün içi profil (TSİ)", "Diurnal profile (local time)"), "%", T("Saat", "Hour")), width="stretch")
    st.markdown(T("**Revizyonun etkisi.** ERA5 öğleden sonraki deniz meltemini kaçırıyordu; bölgedeki üç RES'in gözlenen üretimiyle ay × saat "
                  "hız katsayısı kalibre edildi. Gün içi şekil gözlenene oturdu, GES–RES korelasyonu −0,11'den +0,12'ye çıktı (GES'in "
                  "aleyhine).",
                  "**Effect of the revision.** ERA5 missed the afternoon sea breeze; a month × hour wind-speed correction was calibrated on three "
                  "nearby wind farms. The diurnal shape now matches observations and the solar–wind correlation moved from −0.11 to +0.12 "
                  "(against solar)."))
    kal = oku("kalibrasyon_gun_ici.csv", index_col=0)
    fig = go.Figure()
    for i, kol in enumerate([c for c in kal.columns if "Model" not in c]):
        fig.add_trace(go.Scatter(x=kal.index, y=kal[kol], name=kol, line=dict(color=["#9ec5ef", "#5d9be0", "#2a78d6"][i % 3], width=1.5)))
    fig.add_trace(go.Scatter(x=kal.index, y=kal["Model, sabit k"], name=T("ERA5, sabit katsayı (eski)", "ERA5, constant factor (old)"),
                             line=dict(color=SOLUK, dash="dash", width=2)))
    fig.add_trace(go.Scatter(x=kal.index, y=kal["Model, ay × saat k"], name=T("ERA5, ay × saat katsayısı (revize)", "ERA5, month × hour factor (revised)"),
                             line=dict(color=GES, width=3)))
    st.plotly_chart(sekil(fig, T("Gün içi RES profili: gözlenen santraller vs model", "Diurnal wind profile: observed plants vs model"),
                          T("Kapasite faktörü [%]", "Capacity factor [%]"), T("Saat (TSİ)", "Hour (local)")), width="stretch")
    st.dataframe(oku("revizyon_karsilastirma.csv", index_col=0).round(3), width="stretch")

# =====================================================================================================================
with sekmeler[2]:
    yak = oku("yakalanma_trend.csv", index_col=0)
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for kol, renk, tire in [("Türkiye güneş yakalanma oranı", GES, None), ("Ezine GES (model) yakalanma oranı", GES, "dot"),
                                ("Türkiye rüzgâr yakalanma oranı", RES, None), ("Ezine RES (model) yakalanma oranı", RES, "dot")]:
            fig.add_trace(go.Scatter(x=yak.index, y=yak[kol], name=kol, line=dict(color=renk, dash=tire, width=2.5)))
        fig.add_hline(y=1, line_color=SOLUK, line_width=1)
        st.plotly_chart(sekil(fig, T("Yakalanma oranı = yakalanan fiyat / ortalama PTF", "Capture rate = captured price / average price"),
                              "", T("Yıl", "Year")), width="stretch")
    with c2:
        fg = oku("fiyat_gun_ici.csv", index_col=0)
        yillar_sec = st.multiselect(T("Yıllar", "Years"), list(fg.index), default=[y for y in [2019, 2022, 2024, 2025] if y in fg.index])
        fig = go.Figure()
        ren = ["#c6dbf5", "#8ab4ea", "#4a8ddc", "#1d4f91", "#0b2b57"]
        for i, y in enumerate(yillar_sec):
            r = fg.loc[y]
            fig.add_trace(go.Scatter(x=list(range(24)), y=r.values / r.values.mean(), name=str(y), line=dict(color=ren[i % 5], width=2.5)))
        st.plotly_chart(sekil(fig, T("Ördek eğrisi: gün içi fiyat / günlük ortalama", "Duck curve: hourly price / daily mean"), "",
                              T("Saat (TSİ)", "Hour (local)")), width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        df_ = oku("dusuk_fiyatli_saatler.csv", index_col=0)
        fig = go.Figure([go.Bar(x=df_.index, y=df_[c], name=c, marker_color=col) for c, col in zip(df_.columns, [GES, "#f3a77f", SOLUK])])
        st.plotly_chart(sekil(fig, T("Düşük fiyatlı saat sayısı / yıl", "Low-price hours per year"), T("saat", "hours"), T("Yıl", "Year")),
                        width="stretch")
    with c2:
        yh = oku("yan_hizmet_aylik.csv", index_col=0)
        fig = go.Figure([go.Scatter(x=yh.index, y=yh["sfk_fiyat_usd"], name=T("SFK kapasite", "Secondary reserve (SFK)"), line=dict(color=BATARYA, width=2.5)),
                         go.Scatter(x=yh.index, y=yh["pfk_fiyat_usd"], name=T("PFK kapasite", "Primary reserve (PFK)"), line=dict(color="#b9aef0", width=2))])
        st.plotly_chart(sekil(fig, T("Yan hizmet kapasite fiyatları (aylık ort.)", "Ancillary capacity prices (monthly avg.)"), "USD/MW-h"),
                        width="stretch")
    st.caption(T("Kaynak: EPİAŞ Şeffaflık Platformu (PTF, gerçek zamanlı üretim, yan hizmet), kendi hesaplamam.",
                 "Source: EPİAŞ Transparency Platform (day-ahead prices, real-time generation, ancillary services); own calculations."))

# =====================================================================================================================
with sekmeler[3]:
    st.markdown(T("Tasarımı ve senaryoyu seçin; NPV, IRR, LCOE ve gelir dağılımı önceden hesaplanmış işletme tablolarından anında hesaplanır.",
                  "Choose a design and scenario; NPV, IRR, LCOE and revenue mix are computed instantly from pre-computed dispatch tables."))
    c = st.columns(4)
    turbin = c[0].slider(T("Türbin sayısı (4,2 MW)", "Turbines (4.2 MW)"), 8, 20, 14)
    ges = c[1].slider(T("GES [MWac]", "Solar [MWac]"), 0, 50, 0, 5)
    p_mw = c[2].slider(T("Batarya gücü [MW]", "Battery power [MW]"), 0, 45, 40, 5)
    sure = c[3].slider(T("Batarya süresi [saat]", "Battery duration [h]"), 1.0, 4.0, 1.75, 0.25)
    c = st.columns(4)
    sev_ad = c[0].selectbox(T("Fiyat senaryosu", "Price scenario"), [T("Baz 58 $/MWh", "Base 58 $/MWh"), T("Düşük 45", "Low 45"), T("Yüksek 72", "High 72")])
    seviye = {0: 58.0, 1: 45.0, 2: 72.0}[[T("Baz 58 $/MWh", "Base 58 $/MWh"), T("Düşük 45", "Low 45"), T("Yüksek 72", "High 72")].index(sev_ad)]
    kan = c[1].selectbox(T("Kanibalizasyon", "Cannibalisation"), ["devam", "durur"],
                         format_func=lambda x: {"devam": T("Devam eder (2033'te 0,60)", "Continues (0.60 by 2033)"), "durur": T("Durur", "Stops")}[x])
    sfk_ops = {"kapali": T("SFK kapalı", "No SFK"), "yavas": T("SFK: yavaş doyum", "SFK: slow saturation"),
               "baz": T("SFK: baz doyum", "SFK: base saturation"), "hizli": T("SFK: hızlı doyum", "SFK: fast saturation"),
               "asama5": T("SFK: Aşama 5 varsayımı (doyumsuz)", "SFK: stage-5 assumption (no saturation)")}
    sfk = c[2].selectbox(T("Yan hizmet (SFK)", "Ancillary service (SFK)"), list(sfk_ops), index=2, format_func=lambda x: sfk_ops[x])
    ppa = c[3].toggle(T("PPA (%70 P90, 12 yıl, %10 iskonto)", "PPA (70% of P90, 12 yrs, 10% discount)"), value=False)
    e_mwh = p_mw * sure
    r = gezgin_degerle(gz, cfg, turbin, ges, p_mw, e_mwh, seviye=seviye, kanibalizasyon=kan, sfk=sfk, ppa=ppa)
    k = st.columns(5)
    k[0].metric("NPV", f"{sayi(r['npv'])} M$")
    k[1].metric(T("Proje IRR (reel)", "Project IRR (real)"), "—" if np.isnan(r["irr"]) else yuzde(100 * r["irr"], 1))
    k[2].metric(T("LCOE (satılan)", "LCOE (sold)"), f"{sayi(r['lcoe'])} $/MWh")
    k[3].metric(T("Kesinti", "Curtailment"), yuzde(100 * r["kesinti"], 1))
    k[4].metric("CAPEX", f"{sayi(r['capex'])} M$")
    if p_mw > 0 and not r["sfk_katilim"] and sfk != "kapali":
        st.info(T("30 MW altındaki batarya SFK'ya katılamaz (TEİAŞ usul ve esasları); SFK geliri sıfır alındı.",
                  "Batteries below 30 MW cannot provide SFK (TEİAŞ rules); SFK revenue set to zero."))
    g = r["gelir"]
    fig = go.Figure([go.Bar(x=r["yillar"], y=g["spot"], name=T("RES/GES satış (spot + PPA)", "Wind/solar sales (spot + PPA)"), marker_color=RES),
                     go.Bar(x=r["yillar"], y=g["arbitraj"], name=T("Batarya arbitrajı", "Battery arbitrage"), marker_color=GES),
                     go.Bar(x=r["yillar"], y=g["sfk"], name=T("SFK kapasite geliri", "SFK capacity revenue"), marker_color=BATARYA),
                     go.Bar(x=r["yillar"], y=-r["dengesizlik"], name=T("Dengesizlik maliyeti", "Imbalance cost"), marker_color=SOLUK)])
    fig.update_layout(barmode="relative")
    st.plotly_chart(sekil(fig, T("Yıllık gelir dağılımı [M$, reel]", "Annual revenue mix [M$, real]"), "M$", T("Yıl", "Year"), 400),
                    width="stretch")
    hata = oku("gezgin_hata.csv")
    st.caption(T(f"Yaklaşım: tek temsilî hava yılı + 4 boyutlu ızgara ara değerlemesi (türbin × GES × batarya gücü × süre). Tam modelle fark: "
                 f"RES 58,8 için {sayi(hata.iloc[0]['Fark [M USD]'], 2)} M$, Aşama 5 C tasarımı için {sayi(hata.iloc[1]['Fark [M USD]'], 2)} M$. "
                 "Ara değerlerde (ızgara dışı) hata büyüyebilir; deterministik beklenen değer, borç ve vergi kalkanı dahil değil.",
                 f"Approximation: one representative weather year + 4-D grid interpolation (turbines × solar × battery power × duration). "
                 f"Difference vs full model: {sayi(hata.iloc[0]['Fark [M USD]'], 2)} M$ for wind 58.8 and {sayi(hata.iloc[1]['Fark [M USD]'], 2)} M$ "
                 "for the stage-5 battery design. Error can be larger off-grid; deterministic expected value, unlevered."))

# =====================================================================================================================
with sekmeler[4]:
    st.markdown(T("**Stres testi:** SFK fiyatı artık piyasa yapısına bağlı (batarya kurulumu / SFK ihtiyacı). Dört senaryo olasılıklarla ağırlıklı: "
                  "yavaş %25, baz %40, hızlı %20, SFK'ya katılamama %15. 10.000 simülasyon, ortak rastgele sayılar.",
                  "**Stress test:** SFK prices now depend on market structure (installed batteries / SFK requirement). Four probability-weighted "
                  "scenarios: slow 25%, base 40%, fast 20%, no participation 15%. 10,000 simulations, common random numbers."))
    goster = [k for k in ["A", "C", "D", "E", "F1", "F2"] if k in npv_orn.files]
    adlar = {kisa(t): t for t in met["Tasarım"]}
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        for k_ in goster:
            x = np.sort(npv_orn[k_])
            idx = np.linspace(0, len(x) - 1, 400).astype(int)
            fig.add_trace(go.Scatter(x=x[idx], y=(idx + 1) / len(x), name=adlar.get(k_, k_), line=dict(color=TASARIM_RENK[k_], width=2.5)))
        fig.add_vline(x=0, line_color="#555", line_dash="dash")
        st.plotly_chart(sekil(fig, T("NPV birikimli dağılımı (sağdaki daha iyi)", "NPV cumulative distribution (right is better)"),
                              T("Olasılık", "Probability"), "NPV [M$]", 430), width="stretch")
    with c2:
        fig = go.Figure()
        for _, rr in eski.iterrows():
            kk = kisa(rr["Tasarım"])
            if kk in ("C", "D"):
                fig.add_trace(go.Scatter(x=[rr["CVaR %5 [M USD]"]], y=[rr["Beklenen NPV [M USD]"]], mode="markers+text", text=[f"{kk} " + T("(Aşama 5)", "(stage 5)")],
                                         textposition="middle right", marker=dict(size=12, color="white", line=dict(color=TASARIM_RENK[kk], width=2)),
                                         showlegend=False))
        for _, rr in met.iterrows():
            kk = kisa(rr["Tasarım"])
            if kk == "F2a":
                continue
            fig.add_trace(go.Scatter(x=[rr["CVaR %5 [M USD]"]], y=[rr["Beklenen NPV [M USD]"]], mode="markers+text", text=[kk],
                                     textposition="top center", marker=dict(size=14, color=TASARIM_RENK.get(kk, SOLUK)), name=rr["Tasarım"]))
        fig.add_hline(y=0, line_color="#555")
        fig.update_layout(hovermode="closest")
        st.plotly_chart(sekil(fig, T("Risk-getiri (dolu: doyumlu, boş: Aşama 5)", "Risk-return (filled: saturation, hollow: stage 5)"),
                              "E[NPV] [M$]", "CVaR 5% [M$]", 430), width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        pdf = oku("s_pencere.csv")
        fig = go.Figure()
        for kol in pdf.columns[1:]:
            kk = kisa(kol)
            fig.add_trace(go.Scatter(x=pdf["N [yıl]"], y=pdf[kol], name=kol, line=dict(color=TASARIM_RENK.get(kk, SOLUK), width=2.5)))
        for kk, ad in [("A", T("A: yalnız RES", "A: wind only")), ("E", T("E: RES + PPA", "E: wind + PPA"))]:
            ref = pen["Bataryasız alternatif"].str.extract(rf"{kk}: (-?[\d.]+)")[0].dropna()
            if len(ref):
                fig.add_hline(y=float(ref.iloc[0]), line_color=TASARIM_RENK[kk], line_dash="dash", annotation_text=ad)
        st.plotly_chart(sekil(fig, T("Fırsat penceresi: SFK geliri N yıl sürerse NPV", "Opportunity window: NPV if SFK lasts N years"),
                              "NPV [M$]", T("N [yıl]", "N [years]"), 430), width="stretch")
    with c2:
        kat = oku("s_varyans_katkisi.csv", index_col=0)
        kat = kat.loc[kat.mean(axis=1).sort_values().index[-8:]]
        fig = go.Figure([go.Bar(y=kat.index, x=kat[c_], orientation="h", name=c_, marker_color=TASARIM_RENK.get(kisa(c_), SOLUK)) for c_ in kat.columns])
        fig.update_layout(barmode="group", hovermode="closest")
        st.plotly_chart(sekil(fig, T("NPV varyansına birinci derece katkı [%]", "First-order contribution to NPV variance [%]"), yukseklik=430),
                        width="stretch")
    st.markdown(T("**Metrikler (doyum senaryolu Monte Carlo)**", "**Metrics (Monte Carlo with saturation)**"))
    st.dataframe(met.set_index("Tasarım").round(2), width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(T("**Erteleme (beklenen NPV, 2026 değeri)**", "**Delay (expected NPV, 2026 value)**"))
        st.dataframe(oku("s_erteleme.csv").set_index("Erteleme [yıl]").round(2), width="stretch")
    with c2:
        st.markdown(T("**Doyum senaryosuna göre E[NPV] [M$]**", "**E[NPV] by saturation scenario [M$]**"))
        st.dataframe(oku("s_senaryo_npv.csv").set_index("Tasarım").round(2), width="stretch")

# =====================================================================================================================
with sekmeler[5]:
    st.markdown(T(
        """
**Akış:** veri → üretim → piyasa → finans → optimizasyon → risk

1. **Üretim:** PVGIS-SARAH3 ışınımı + pvlib (PVWatts), ERA5 rüzgârı + windpowerlib (Enercon E-141/4200, 120 m), 2014–2023 saatlik.
   Rüzgâr hızı bölgedeki üç RES'in EPİAŞ üretimiyle ay × saat katsayısıyla kalibre edildi.
2. **Piyasa:** EPİAŞ PTF (2014–2026), yakalanan fiyat ve kanibalizasyon; fiyat senaryoları = seviye × son dönemin saatlik şekli,
   öğle çukuru güneş yakalanma hedefine göre derinleştirilir.
3. **Finans:** reel USD nakit akışı, %25 vergi (5 yıl zarar mahsubu), 10 yıl amortisman, P90'a göre heykelsi borç (DSCR 1,30).
4. **Optimizasyon:** Pyomo + HiGHS. Saatlik batarya dispatch LP'leri, türbin sayısı tamsayı ve yatırım kararı ikili kapasite MILP'i
   (tam yıl 2 × 8.760 saat), SFK'ya katılım ikili (≥30 MW).
5. **Risk:** 10.000 senaryo Monte Carlo (hava blok bootstrap, ortalamaya dönen log-fiyat + kriz/tavan, Gauss kopula), önceden hesaplanmış
   işletme tabloları + ara değerleme; EVPI/EVPPI, birinci derece Sobol; SFK doyum stres testi.
""",
        """
**Flow:** data → generation → market → finance → optimisation → risk

1. **Generation:** PVGIS-SARAH3 irradiance + pvlib (PVWatts), ERA5 wind + windpowerlib (Enercon E-141/4200, 120 m), hourly 2014–2023.
   Wind speeds calibrated with a month × hour factor against three nearby wind farms (EPİAŞ data).
2. **Market:** EPİAŞ day-ahead prices (2014–2026), capture prices and cannibalisation; price scenarios = level × recent hourly shape,
   with the midday trough deepened to a target solar capture rate.
3. **Finance:** real-USD cash flows, 25% tax (5-year loss carry-forward), 10-year depreciation, P90-sculpted debt (DSCR 1.30).
4. **Optimisation:** Pyomo + HiGHS. Hourly battery dispatch LPs and a capacity MILP with integer turbines and a binary build decision
   (full year, 2 × 8,760 h), binary SFK participation (≥30 MW).
5. **Risk:** 10,000-scenario Monte Carlo (block-bootstrapped weather, mean-reverting log price + crisis/cap, Gaussian copula) using
   pre-computed dispatch tables + interpolation; EVPI/EVPPI, first-order Sobol; SFK saturation stress test.
"""))
    st.markdown(T("**Varsayımlar (config.yaml, kaynaklarıyla)**", "**Assumptions (config.yaml, with sources)**"))
    va = oku("varsayimlar.csv")
    bolum = st.multiselect(T("Bölüm", "Section"), sorted(va["Bölüm"].unique()), default=["teknoloji", "finans", "stres_testi"])
    st.dataframe(va[va["Bölüm"].isin(bolum)], width="stretch", hide_index=True, height=360)
    st.markdown(T(
        "**Sınırlamalar:** SFK fiyatı, doyum hızı ve PPA iskontosu tahmine dayanıyor; dispatch mükemmel öngörülü; ERA5 kalibrasyonu yalnızca "
        "üç santrale dayanıyor (saha ölçümü yok); kur riski ayrıca modellenmedi; borç simülasyonda yeniden yapılandırılmıyor.",
        "**Limitations:** SFK prices, saturation pace and PPA discount are estimates; dispatch assumes perfect foresight; ERA5 calibration rests "
        "on three plants (no on-site met mast); FX risk not modelled separately; debt is not restructured within simulations."))
    st.markdown(f"[{T('Rapor', 'Report')} (docs/RAPOR.md)]({REPO_URL}/blob/main/docs/RAPOR.md) · "
                f"[{T('Formülasyonlar', 'Formulations')} (docs/)]({REPO_URL}/tree/main/docs) · [GitHub]({REPO_URL})")
