"""
Mevcut santrale ekleme (v4 Faz I): mevcut bir RES'in bağlantısına yardımcı kaynak olarak GES ve/veya bütünleşik batarya.

1. Tarama: atlasın kalibre santralleri için bağlantı kullanımı, RES–GES korelasyonu, GES başabaş CAPEX'i ve MILP'in önerdiği
   ekleme (data/atlas/v4_ekleme_tarama.csv; src/v4_I1_ekleme.py).
2. Santral analizi: santralin kendi kalibrasyonuyla profil (isteğe bağlı üretim CSV'si), artımsal MILP, ortak rastgele sayılarla
   Monte Carlo (src/ekleme/analiz.py). Santral adları gösterilmez (anonim kod + il; config v3.performans.santral_adlari_goster).
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from src.ekleme.analiz import YAPI_AD, EklemeVarsayimlari, ekleme_analizi
from src.ekleme.santraller import liste
from src.motor.varsayimlar import MotorHatasi
from uygulama import harita as H
from uygulama.ortak import BATARYA, GES, RES, SOLUK, T, ciz, dil, istek_izni, md, para, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.grafik import dolgu
from uygulama.tasarim.stil import aktif_tema
from uygulama.tasarim.tokenlar import TEMALAR


@st.cache_data(show_spinner=False)
def _tarama() -> pd.DataFrame | None:
    p = veri_katmani.yol("atlas/v4_ekleme_tarama.csv", zorunlu=False)
    return None if p is None else pd.read_csv(p)


def _csv_oku(dosya) -> pd.Series:
    """Saatlik üretim CSV'si: 'zaman' (TSİ, Europe/Istanbul) ve 'uretim_mw' sütunları → UTC indeksli MW serisi."""
    d = pd.read_csv(io.BytesIO(dosya.getvalue()))
    if not {"zaman", "uretim_mw"} <= set(d.columns):
        raise MotorHatasi("csv", "CSV'de 'zaman' ve 'uretim_mw' sütunları olmalı.", "The CSV must have 'zaman' and 'uretim_mw' columns.")
    z = pd.to_datetime(d["zaman"])
    if z.dt.tz is None:
        z = z.dt.tz_localize("Europe/Istanbul", ambiguous="NaT", nonexistent="NaT")
    s = pd.Series(pd.to_numeric(d["uretim_mw"], errors="coerce").to_numpy(), index=z.dt.tz_convert("UTC").dt.tz_localize(None))
    return s[s.index.notna()].dropna()


st.title(T("Mevcut santrale ekleme", "Add-on to an existing plant"))
st.markdown(md(T(
    "Mevcut bir rüzgâr santralinin **bağlantısı zaten var** ve rüzgâr çoğu saat onu doldurmuyor. Aynı bağlantıya *yardımcı kaynak* "
    "olarak GES ve/veya bütünleşik batarya eklemek, yeni bir sahaya göre şebeke maliyeti ve izin süresi olmadan kapasiteyi kullanır. "
    "Mekanik güç (MWm) artar, elektriksel güç (MWe) aynı kalır; fazla üretim kesilir ya da bataryaya gider.",
    "An existing wind farm **already has a grid connection** that the wind leaves idle most hours. Adding solar and/or an integrated "
    "battery as an *auxiliary source* on the same connection uses that capacity without new grid cost or a new permit cycle. "
    "Mechanical capacity (MWm) grows, electrical capacity (MWe) stays; surplus is curtailed or stored.",
)))  # fmt: skip
B.uyari_kutusu(
    T(
        "Santraller anonim kodla gösterilir. Sonuçlar bir modelden türetilmiştir (santralin kendi kalibrasyonu + piyasa varsayımları); "
        "lisans tadili, arazi, ÇED ve TEİAŞ/dağıtım görüşü modellenmez. Yardımcı kaynağın YEKDEM fiyat kuralı ikincil kaynaktan.",
        "Plants are shown by anonymous code. Results are model-derived (the plant's own calibration + market assumptions); licence "
        "amendment, land, EIA and grid-operator approval are not modelled. The auxiliary-source YEKDEM price rule is from a secondary source.",
    ),
    "uyari",
)
sl = liste()
tema = aktif_tema()
rk = TEMALAR[tema]["renk"]

# --- 1. Tarama
tr = _tarama()
B.bolum_basligi(
    T("1. Türkiye taraması", "1. Türkiye screening"),
    T(f"{len(sl)} kalibre RES · deterministik", f"{len(sl)} calibrated wind farms · deterministic"),
)
if tr is not None and len(tr):
    k = st.columns(4)
    B.kpi_karti(k[0], T("Medyan bağlantı kullanımı", "Median connection use"), yuzde(100 * tr["res_kf"].median(), 0),
                aciklama=T("RES KF = bağlantının dolu payı", "wind CF = share of connection used"))  # fmt: skip
    B.kpi_karti(k[1], T("Bağlantının yarısından azı dolu", "Below half the connection"), yuzde(100 * tr["baglanti_bos_saat_orani"].median(), 0),
                aciklama=T("saatlerin medyan payı", "median share of hours"))  # fmt: skip
    B.kpi_karti(k[2], T("GES başabaş CAPEX (medyan)", "Solar break-even capex (median)"), f"{sayi(tr['ges_basabas_capex'].median() / 1e3, 0)} {T('bin $/MW', 'k$/MW')}",
                aciklama=T("bağlantının %25'i kadar GES", "solar = 25% of connection"))  # fmt: skip
    B.kpi_karti(k[3], T("Bataryası kârlı santral", "Plants with profitable battery"), f"{int((tr['milp_bess_mw'] > 1).sum())} / {len(tr)}",
                aciklama=T("MILP tahmini, SFK dahil", "MILP estimate, incl. FCR"))  # fmt: skip
    c = st.columns([1.3, 1], gap="medium")
    with c[0]:
        try:
            from streamlit_folium import st_folium

            x = tr.merge(sl[["enlem", "boylam"]], left_on="kod", right_index=True)
            v = x["ges_basabas_capex"].to_numpy() / 1e3
            esik = np.quantile(v, [1 / 3, 2 / 3])
            renk = [rk["iyi"] if a >= esik[1] else (rk["uyari"] if a >= esik[0] else rk["kotu"]) for a in v]
            ip = [f"<b>{r.kod} · {r.il}</b><br>{sayi(r.kurulu_mw, 0)} MW · KF {yuzde(100 * r.res_kf, 0)} · ρ {sayi(r.korelasyon, 2)}<br>"
                  f"{T('GES başabaş', 'Solar break-even')} {sayi(r.ges_basabas_capex / 1e3, 0)} {T('bin $/MW', 'k$/MW')}" for r in x.itertuples()]  # fmt: skip
            m = H.nokta_haritasi(x, renk, ip, tema, boyut=[4 + 2.2 * np.sqrt(a / 30) for a in x["kurulu_mw"]])
            st_folium(m, height=380, use_container_width=True, returned_objects=[], key="ek_harita")
        except Exception:
            pass
        st.caption(T("Renk: GES başabaş CAPEX'i (yeşil en yüksek üçte bir — güneş eklemeye en yatkın). Nokta büyüklüğü kurulu güç.",
                     "Colour: solar break-even capex (green = top third — most suited to adding solar). Marker size: capacity."))  # fmt: skip
    with c[1]:
        en = tr.sort_values("ges_basabas_capex", ascending=False).head(12)
        B.karsilastirma_tablosu(
            [T("Santral", "Plant"), "MW", "KF", "ρ", T("GES başabaş", "Solar BE")],
            [[f"{r.kod} · {r.il}", sayi(r.kurulu_mw, 0), yuzde(100 * r.res_kf, 0), sayi(r.korelasyon, 2), sayi(r.ges_basabas_capex / 1e3, 0)] for r in en.itertuples()],
            mobilde_gizle=(3,),
        )  # fmt: skip
        st.caption(
            T(
                "ρ: saatlik RES–GES korelasyonu. GES başabaş: bin $/MWac (varsayım 620).",
                "ρ: hourly wind–solar correlation. Solar BE: k$/MWac (assumed 620).",
            )
        )
else:
    st.caption(T("Tarama tablosu yok (src/v4_I1_ekleme.py).", "Screening table missing (src/v4_I1_ekleme.py)."))

# --- 2. Santral analizi
B.bolum_basligi(
    T("2. Santral analizi", "2. Plant analysis"), T("optimizasyon + Monte Carlo · ~1 dakika", "optimisation + Monte Carlo · ~1 minute")
)
with st.form("ekleme_formu"):
    c = st.columns([1.4, 1, 1])
    kod = c[0].selectbox(T("Santral", "Plant"), sl.index.tolist(),
                         format_func=lambda x: f"{x} · {sl.loc[x, 'il']} · {sayi(sl.loc[x, 'kurulu_mw'], 1)} MW", key="ek_kod")  # fmt: skip
    mwe = c[1].number_input(T("Bağlantı gücü (MWe)", "Connection (MWe)"), 5.0, 300.0, float(np.clip(sl.loc[kod, "kurulu_mw"], 5, 300)), 0.1,
                            help=T("Boş bırakılırsa kurulu güç. Lisanstaki elektriksel güç.", "Defaults to installed capacity. Electrical capacity in the licence."))  # fmt: skip
    ges_ust = c[2].number_input(T("GES üst sınırı (MWm)", "Solar cap (MWm)"), 0.0, 450.0, float(round(1.5 * mwe, 1)), 1.0,
                                help=T("Arazi ve izin sınırı.", "Land and permit limit."))  # fmt: skip
    c = st.columns([1, 1, 1.4])
    yek = c[0].checkbox(T("Santral eski YEKDEM'de", "Plant in legacy YEKDEM"), value=False)
    yek_yil = c[1].number_input(T("YEKDEM son yılı", "Last YEKDEM year"), 2026, 2036, 2029, 1, disabled=False)
    yapilar = c[2].multiselect(
        T("Gelir yapıları", "Revenue structures"), list(YAPI_AD), default=list(YAPI_AD), format_func=lambda x: T(*YAPI_AD[x])
    )
    c = st.columns([1, 1, 1.4])
    cg = c[0].slider(T("GES CAPEX çarpanı", "Solar capex multiplier"), 0.5, 1.5, 1.0, 0.05)
    cb = c[1].slider(T("Batarya CAPEX çarpanı", "Battery capex multiplier"), 0.5, 1.5, 1.0, 0.05)
    dosya = c[2].file_uploader(T("Saatlik üretim CSV'si (isteğe bağlı)", "Hourly production CSV (optional)"), type=["csv"],
                               help=T("Sütunlar: zaman (TSİ), uretim_mw. En az ~1 yıl. Profil ay × saat ortalamasına ölçeklenir; dosya saklanmaz.",
                                      "Columns: zaman (local time), uretim_mw. At least ~1 year. The profile is rescaled to its month × hour means; the file is not stored."))  # fmt: skip
    git = st.form_submit_button(T("Ekleme analizini çalıştır", "Run add-on analysis"), type="primary")

if git:
    izin, mesaj = istek_izni("tam")
    if not izin:
        B.uyari_kutusu(mesaj, "kotu")
    else:
        try:
            csv = _csv_oku(dosya) if dosya is not None else None
            ev = EklemeVarsayimlari(kod=kod, baglanti_mw=mwe, azami_ges_mw=ges_ust, yekdem_bitis_yili=int(yek_yil) if yek else None,
                                    gelir_yapilari=tuple(yapilar or ["tuccar"]), capex_carpani_ges=cg, capex_carpani_bess=cb, uretim_csv=csv)  # fmt: skip
            cubuk = st.progress(0.0, T("Başlıyor…", "Starting…"))
            st.session_state["ek_sonuc"] = ekleme_analizi(ev, lambda o, m: cubuk.progress(min(max(float(o), 0.0), 1.0), m))
            cubuk.empty()
        except MotorHatasi as ex:
            B.uyari_kutusu(ex.mesaj(st.session_state.get("dil", "TR")), "kotu")

r = st.session_state.get("ek_sonuc")
if r:
    sa, d, i = r["santral"], r["tasarim"], r["isletme"]
    y = r["en_iyi_yapi"]
    m = r["metrik"][y]
    durum = "iyi" if m["e_npv"] > 0 and m["p_pozitif"] >= 0.65 else ("uyari" if m["e_npv"] > 0 else "kotu")
    with B.karar_karti(durum):
        c = st.columns([1.5, 1, 1, 1], gap="medium")
        with c[0]:
            ad = (T("Ekleme önerilmez", "No addition recommended") if d["ges_mw"] + d["bess_mw"] < 0.5 else
                  T(f"GES {sayi(d['ges_mw'], 0)} MWm + batarya {sayi(d['bess_mw'], 0)} MW / {sayi(d['bess_mwh'], 0)} MWh",
                    f"Solar {sayi(d['ges_mw'], 0)} MWm + battery {sayi(d['bess_mw'], 0)} MW / {sayi(d['bess_mwh'], 0)} MWh"))  # fmt: skip
            B.uyari_kutusu(md(f"**{T('Önerilen ekleme', 'Recommended addition')}:** {ad}"), durum)
            st.caption(md(f"{sa['kod']} · {sa['il']} · {sayi(sa['kurulu_mw'], 1)} MW · {sa['turbin']} · {T('bağlantı', 'connection')} {sayi(sa['baglanti_mw'], 1)} MWe · "
                          f"KF {T('model', 'model')} {yuzde(100 * sa['model_kf'], 1)} / {T('gözlenen', 'observed')} {yuzde(100 * sa['gozlenen_kf'], 1)}"))  # fmt: skip
        B.kpi_karti(c[1], T("Artımsal E[NPV]", "Incremental E[NPV]"), para(m["e_npv"]),
                    aciklama=f"{T(*YAPI_AD[y])} · ±{sayi(m['se'], 2)}")  # fmt: skip
        B.kpi_karti(c[2], "P(NPV > 0)", yuzde(100 * m["p_pozitif"], 0), aciklama=f"CVaR {para(m['cvar5'])}")
        B.kpi_karti(c[3], T("Bağlantı kullanımı", "Connection use"), f"{yuzde(100 * i['res']['baglanti_kullanim'], 0)} → {yuzde(100 * i['ek']['baglanti_kullanim'], 0)}",
                    aciklama=T("satılan / (MWe × 8760)", "sold / (MWe × 8760)"))  # fmt: skip

    if sa.get("csv"):
        cv = sa["csv"]
        st.caption(md(T(f"Üretim CSV'si: ölçülen KF {yuzde(100 * cv['kullanici_kf'], 1)}, model {yuzde(100 * cv['model_kf'], 1)} → ölçekli {yuzde(100 * cv['olcekli_kf'], 1)} ({cv['hucre']} ay × saat hücresi; " + ("ölçüm model dönemiyle örtüşüyor, oran aynı saatlerden — uzun dönem düzeltmeli)." if cv.get("mcp") else "örtüşme yok, uzun dönem düzeltmesi yapılamadı).") + "",
                        f"Production CSV: measured CF {yuzde(100 * cv['kullanici_kf'], 1)}, model {yuzde(100 * cv['model_kf'], 1)} → rescaled {yuzde(100 * cv['olcekli_kf'], 1)} ({cv['hucre']} month × hour cells; " + ("overlaps the model period, ratio from the same hours — long-term corrected)." if cv.get("mcp") else "no overlap, no long-term correction).") + "")))  # fmt: skip
    c = st.columns(2, gap="medium")
    with c[0]:
        e = pd.DataFrame(r["ges_egrisi"])
        f = go.Figure()
        f.add_trace(go.Scatter(x=e["ges_mw"], y=e["artimsal_npv"], mode="lines+markers", name=T("artımsal NPV (M$)", "incremental NPV (M$)"),
                               line=dict(color=GES, width=2)))  # fmt: skip
        f.add_trace(go.Scatter(x=e["ges_mw"], y=e["basabas_capex"] / 1e3, mode="lines", name=T("başabaş CAPEX (bin $/MW)", "break-even capex (k$/MW)"),
                               line=dict(color=SOLUK, dash="dash"), yaxis="y2"))  # fmt: skip
        f.add_hline(y=0, line_color=SOLUK, line_dash="dot", line_width=1)
        f.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False), hovermode="x unified")
        ciz(sekil(f, T("GES boyutu (bataryasız)", "Solar size (no battery)"), T("milyon $", "million $"), "MWm", yukseklik=360,
                  alt=T(f"kesikli: başabaş GES CAPEX'i (varsayım {sayi(r['ges_capex_usd_mw'] / 1e3, 0)} bin $/MW)",
                        f"dashed: break-even solar capex (assumed {sayi(r['ges_capex_usd_mw'] / 1e3, 0)} k$/MW)")))  # fmt: skip
    with c[1]:
        g = r["gunici"]
        f = go.Figure()
        f.add_trace(go.Scatter(x=g["saat"], y=np.array(g["res"]) * sa["kurulu_mw"], name="RES", line=dict(color=RES, width=2)))
        if d["ges_mw"] > 0:
            f.add_trace(
                go.Scatter(
                    x=g["saat"],
                    y=np.array(g["ges"]) * d["ges_mw"],
                    name=T("GES (önerilen)", "Solar (recommended)"),
                    line=dict(color=GES, width=2),
                )
            )
        f.add_trace(go.Scatter(x=g["saat"], y=np.array(g["ges"]) * sa["baglanti_mw"] * 0.5, name=T("GES (bağlantının yarısı)", "Solar (half of connection)"),
                               line=dict(color=GES, width=1, dash="dot")))  # fmt: skip
        f.add_hline(y=sa["baglanti_mw"], line_color=SOLUK, line_dash="dash", annotation_text="MWe")
        ciz(sekil(f, T("Ortalama gün", "Average day"), "MW", T("saat (TSİ)", "hour (local)"), yukseklik=360,
                  alt=T(f"saatlik RES–GES korelasyonu {sayi(sa['saatlik_korelasyon'], 2)}", f"hourly wind–solar correlation {sayi(sa['saatlik_korelasyon'], 2)}")))  # fmt: skip
    B.bolum_basligi(
        T("Gelir yapıları", "Revenue structures"), T("artımsal, Monte Carlo, milyon $ (reel)", "incremental, Monte Carlo, million $ (real)")
    )
    met = r["metrik"]
    B.karsilastirma_tablosu(
        [T("Gelir yapısı", "Revenue structure"), "E[NPV]", T("Std. hata", "Std. error"), "P(NPV>0)", "CVaR5", "P10 / P90", T("Varyans azaltma", "Variance reduction")],
        [[T(*YAPI_AD[k_]), sayi(v_["e_npv"], 1), f"±{sayi(v_['se'], 2)}", yuzde(100 * v_["p_pozitif"], 0), sayi(v_["cvar5"], 1),
          f"{sayi(v_['p10'], 1)} / {sayi(v_['p90'], 1)}", yuzde(100 * (v_.get("varyans_azaltma") or 0), 0)] for k_, v_ in met.items()],
        vurgulu=list(met).index(y), mobilde_gizle=(2, 5, 6), negatif=[(j, 1) for j, v_ in enumerate(met.values()) if v_["e_npv"] < 0],
    )  # fmt: skip
    h = r["histogram"]
    f = go.Figure()
    renk = {"tuccar": SOLUK, "yekdem_opsiyon": RES, "ppa": GES}
    for k_, hh in h.items():
        e_ = np.array(hh["kenar"])
        f.add_trace(go.Scatter(x=(e_[:-1] + e_[1:]) / 2, y=hh["sayi"], name=T(*YAPI_AD[k_]), mode="lines",
                               line=dict(color=renk.get(k_, BATARYA), width=2, shape="hvh"), fill="tozeroy", fillcolor=dolgu(renk.get(k_, BATARYA), 0.12)))  # fmt: skip
    f.add_vline(x=0, line_color=SOLUK, line_dash="dot", line_width=1)
    ciz(sekil(f, T("Artımsal NPV dağılımı", "Incremental NPV distribution"), T("simülasyon sayısı", "simulations"), T("milyon $ (reel)", "million $ (real)"),
              yukseklik=320, alt=T("aynı senaryolarla: NPV(RES + ekleme) − NPV(yalnız RES)", "same scenarios: NPV(wind + addition) − NPV(wind only)")))  # fmt: skip
    B.bolum_basligi(T("Gerekçeler", "Rationale"))
    for n in r["nedenler"]:
        st.markdown(md("- " + (n["tr"] if dil() == "TR" else n["en"])))
