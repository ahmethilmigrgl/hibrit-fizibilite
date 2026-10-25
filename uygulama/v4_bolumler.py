"""
v4 arayüz bölümleri (tam analiz sonucu). Faz H: "Proje finansmanı" — verim bütçesi (P50/P90), çok senaryolu borç LP'si,
olasılık tabanlı boyutlandırma ve Monte Carlo nakit şelalesi.

Görünüm "Eşik" tasarım sistemiyle: renkler yalnız uygulama/tasarim/tokenlar.py'den (ortak paletten), bileşenler
uygulama/tasarim/bilesenler.py'den, grafikler ortak Plotly şablonuyla (ortak.sekil / ortak.ciz).
"""

from __future__ import annotations

import html

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from uygulama.ortak import BATARYA, GES, KOYU, RES, SOLUK, T, ciz, md, para, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.grafik import dolgu

YAPI_AD = {
    "tuccar": ("Tüccar (piyasa)", "Merchant"),
    "yekdem_opsiyon": ("YEKDEM yıllık opsiyon", "YEKDEM annual option"),
    "ppa": ("PPA (%70, 12 yıl)", "PPA (70%, 12 years)"),
}
BILESEN_AD = {
    "yillar_arasi": ("Yıllar arası değişkenlik", "Inter-annual variability"),
    "referans_donem": ("Referans dönem (10 yıl)", "Reference period (10 years)"),
    "iklim_temsiliyeti": ("İklim temsiliyeti", "Future climate representativeness"),
    "model_kalibrasyon": ("Model ve kalibrasyon (atlas)", "Model and calibration (atlas)"),
    "kullanilabilirlik": ("Yıllık kullanılabilirlik", "Annual availability"),
    "isinim_veri_seti": ("Işınım veri seti", "Irradiance dataset"),
    "pv_model": ("PV modeli", "PV model"),
}
SENARYO_AD = {
    "P50": ("P50", "P50"),
    "P90-1y": ("P90 (1 yıl)", "P90 (1 yr)"),
    "P99-1y": ("P99 (1 yıl)", "P99 (1 yr)"),
    "Asagi": ("Aşağı yön (fiyat −%20, SFK −%50)", "Downside (price −20%, FCR −50%)"),
}


def _kas(metin: str) -> None:
    st.html(f'<div class="esik-kas ara">{html.escape(metin)}</div>')


def _cfads_grafigi(d: dict) -> go.Figure:
    """Kredi veren senaryolarının CFADS'si, Monte Carlo P10–P90 bandı ve borç servisi (vade içi, milyon $ reel)."""
    V = d["vade"]
    k = np.arange(1, V + 1)
    mc = d["cfads_mc_reel"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=k, y=np.array(mc["p90"][:V]) / 1e6, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    f.add_trace(go.Scatter(x=k, y=np.array(mc["p10"][:V]) / 1e6, mode="lines", line=dict(width=0), fill="tonexty",
                           fillcolor=dolgu(SOLUK, 0.18), name=T("Monte Carlo P10–P90", "Monte Carlo P10–P90")))  # fmt: skip
    f.add_trace(go.Bar(x=k, y=np.array(d["servis_reel"][:V]) / 1e6, name=T("Borç servisi", "Debt service"),
                       marker_color=dolgu(KOYU, 0.35)))  # fmt: skip
    renk = {"P50": RES, "P90-1y": GES, "P99-1y": BATARYA, "Asagi": SOLUK}
    cizgi = {"P50": "solid", "P90-1y": "dash", "P99-1y": "dot", "Asagi": "dashdot"}
    for a, y in d["cfads_reel"].items():
        f.add_trace(go.Scatter(x=k, y=np.array(y[:V]) / 1e6, mode="lines", name=T(*SENARYO_AD.get(a, (a, a))),
                               line=dict(color=renk.get(a, SOLUK), width=2, dash=cizgi.get(a, "solid"))))  # fmt: skip
    f.update_layout(hovermode="x unified", barmode="overlay", legend=dict(y=-0.3))
    return sekil(
        f, T("Borç servisi ve kredi veren senaryoları", "Debt service and lender cases"), T("milyon $ (reel)", "million $ (real)"),
        T("işletme yılı", "operating year"), yukseklik=430,
        alt=T("Çizgiler: boyutlandırma senaryoları · gri: Monte Carlo P10–P90",
              "Lines: sizing cases · grey: Monte Carlo P10–P90"),
    )  # fmt: skip


def finansman_bolumu(o: dict) -> None:
    """Tam analiz özetinden (ozet["finansman"]) proje finansmanı bölümü."""
    fin = o.get("finansman")
    if not fin or not fin.get("yapilar"):
        return
    B.bolum_basligi(
        T("Proje finansmanı", "Project finance"),
        T("bankaya sunulabilir verim, borç kapasitesi ve temerrüt riski", "bankable yield, debt capacity and default risk"),
    )
    yapilar = list(fin["yapilar"])
    varsayilan = o.get("en_iyi_yapi") if o.get("en_iyi_yapi") in yapilar else yapilar[0]
    y = st.radio(
        T("Gelir yapısı", "Revenue structure"), yapilar, index=yapilar.index(varsayilan), horizontal=True,
        format_func=lambda x: T(*YAPI_AD.get(x, (x, x))), key="fin_yapi",
    )  # fmt: skip
    d = fin["yapilar"][y]
    pd_ = d["pd_hedefli"]
    sl = d["selale"]
    u = st.columns(4)
    B.kpi_karti(u[0], T("Borç kapasitesi (DSCR kuralları)", "Debt capacity (DSCR rules)"), para(d["borc_reel_musd"]),
                aciklama=T(f"borç/CAPEX {yuzde(100 * d['borc_orani'], 0)} · {d['vade']} yıl", f"gearing {yuzde(100 * d['borc_orani'], 0)} · {d['vade']} yr"),
                yardim=T("Tüm kredi veren senaryolarında DSCR eşiklerini aynı anda sağlayan en büyük heykelsi borç (doğrusal program).",
                         "Largest sculpted debt meeting the DSCR thresholds in all lender cases at once (linear program)."))  # fmt: skip
    B.kpi_karti(u[1], T("Temerrüt olasılığı", "Default probability"), yuzde(100 * sl["p_temerrut"], 0),
                aciklama=T("bu borçla, Monte Carlo", "with this debt, Monte Carlo"),
                yardim=T("DSRA tükendikten sonra borç servisinin ödenemediği en az bir yıl olan senaryoların payı.",
                         "Share of scenarios with at least one year of unpaid debt service after the DSRA is exhausted."))  # fmt: skip
    B.kpi_karti(u[2], T(f"Borç (temerrüt ≤ %{sayi(100 * pd_['pd_hedef'], 0)})", f"Debt (default ≤ {sayi(100 * pd_['pd_hedef'], 0)}%)"),
                para(pd_["borc_reel_musd"]), aciklama=T(f"borç/CAPEX {yuzde(100 * pd_['borc_orani'], 0)}", f"gearing {yuzde(100 * pd_['borc_orani'], 0)}"),
                yardim=T("Olasılık tabanlı boyutlandırma: aynı geri ödeme profiliyle temerrüt olasılığını hedefin altında tutan en büyük borç.",
                         "Probability-based sizing: largest debt with the same repayment profile keeping default probability below target."))  # fmt: skip
    if d.get("olcum_sonrasi_borc_reel_musd") is not None:
        fark = d["olcum_sonrasi_borc_reel_musd"] - d["borc_reel_musd"]
        B.kpi_karti(u[3], T("Saha ölçümü sonrası borç", "Debt after on-site measurement"), para(d["olcum_sonrasi_borc_reel_musd"]),
                    aciklama=T(f"{'+' if fark >= 0 else ''}{sayi(fark, 1)} M$ (DSCR kuralları)", f"{'+' if fark >= 0 else ''}{sayi(fark, 1)} M$ (DSCR rules)"),
                    yardim=T("Rüzgâr direği/LiDAR ile ≥ 1 yıl ölçüm + uzun dönem düzeltmesi sonrası RES model belirsizliği küçülür; P90/P99 yükselir.",
                             "After ≥ 1 year of met mast/LiDAR measurement + long-term correction the wind model uncertainty shrinks; P90/P99 rise."))  # fmt: skip
    c = st.columns([1.55, 1], gap="medium")
    with c[0]:
        ciz(_cfads_grafigi(d))
    with c[1]:
        with B.kart("bagla"):
            st.html(f'<div class="esik-kas">{html.escape(T("Kredi metrikleri (P50)", "Credit metrics (P50)"))}</div>')
            bag = ", ".join(
                f"{T(*SENARYO_AD.get(a, (a, a)))} {n} {T('yıl', 'yr')}"
                for a, n in sorted(d["baglayan_senaryo_yil"].items(), key=lambda x: -x[1])
            )
            st.markdown(md(
                f"- {T('Asgari / ortalama DSCR', 'Minimum / average DSCR')}: {sayi(d['dscr_min_p50'], 2)} / {sayi(d['dscr_ort_p50'], 2)}\n"
                f"- LLCR {sayi(d['llcr'], 2)} · PLCR {sayi(d['plcr'], 2)}\n"
                f"- {T('Ortalama ömür', 'Average life')}: {sayi(d['ortalama_omur'], 1)} {T('yıl', 'yr')}\n"
                f"- {T('Bağlayan kısıt', 'Binding constraint')}: "
                + (T("kaldıraç tavanı", "gearing cap") if d["kaldirac_bagliyor"] else (bag or "–")) + "\n"
                f"- {T('Gelir payları (ilk 5 yıl)', 'Revenue shares (first 5 yr)')}: {T('sözleşmeli', 'contracted')} {yuzde(100 * d['sozlesmeli_pay_ilk5'], 0)}, "
                f"{T('batarya', 'battery')} {yuzde(100 * d['batarya_pay_ilk5'], 0)}"
            ))  # fmt: skip
            st.caption(md(T("Bağlayan kısıt: borç LP'sinde dual değeri sıfırdan büyük DSCR kısıtları; o yılın servisini 1 $ gevşetmek borcu (1 + i)^−k $ artırır.",
                            "Binding: DSCR constraints with non-zero dual in the debt LP; relaxing that year's service by $1 raises debt by (1 + i)^−k $.")))  # fmt: skip
    _kas(T("Nakit şelalesi — Monte Carlo", "Cash waterfall — Monte Carlo"))
    sp = pd_["selale"]
    B.karsilastirma_tablosu(
        [T("Borç", "Debt"), "M$", T("P(temerrüt)", "P(default)"), T("P(DSRA kullanımı)", "P(DSRA draw)"), T("P(dağıtım kilidi)", "P(lock-up)"),
         T("Asgari DSCR P5 / P50", "Minimum DSCR P5 / P50"), T("Öz kaynak IRR P10 / P50 / P90", "Equity IRR P10 / P50 / P90")],
        [[T("DSCR kuralları", "DSCR rules"), sayi(d["borc_reel_musd"], 1), yuzde(100 * sl["p_temerrut"], 0), yuzde(100 * sl["p_dsra_kullanim"], 0),
          yuzde(100 * sl["p_kilit"], 0), f"{sayi(sl['dscr_min_p5'], 2)} / {sayi(sl['dscr_min_p50'], 2)}",
          f"{yuzde(100 * sl['irr_p10'], 1)} / {yuzde(100 * sl['irr_p50'], 1)} / {yuzde(100 * sl['irr_p90'], 1)}"],
         [T(f"Temerrüt ≤ %{sayi(100 * pd_['pd_hedef'], 0)}", f"Default ≤ {sayi(100 * pd_['pd_hedef'], 0)}%"), sayi(pd_["borc_reel_musd"], 1),
          yuzde(100 * sp["p_temerrut"], 0), yuzde(100 * sp["p_dsra_kullanim"], 0), yuzde(100 * sp["p_kilit"], 0),
          f"{sayi(sp['dscr_min_p5'], 2)} / {sayi(sp['dscr_min_p50'], 2)}",
          f"{yuzde(100 * sp['irr_p10'], 1)} / {yuzde(100 * sp['irr_p50'], 1)} / {yuzde(100 * sp['irr_p90'], 1)}"]],
        mobilde_gizle=(3, 4, 5),
    )  # fmt: skip
    st.caption(md(T("Şelale: CFADS + faiz vergi kalkanı → borç servisi → DSRA (6 aylık servis) → dağıtım testi (DSCR < 1,10 ise nakit kilitlenir). "
                 "Kural tabanlı borç yalnız seçilmiş senaryolara dayanır; Monte Carlo fiyat, SFK doyumu, hava ve model hatasının tüm "
                 "birleşimlerini görür. İkisi arasındaki fark, kredi veren senaryolarının hangi riski kaçırdığını gösterir. COD gecikmesi dahil değil.",
                 "Waterfall: CFADS + interest tax shield → debt service → DSRA (6 months of service) → distribution test (cash locked if DSCR < 1.10). "
                 "Rule-based debt relies on selected cases only; Monte Carlo sees all combinations of price, FCR saturation, weather and model "
                 "error. The gap shows which risk the lender cases miss. COD delay not included.")))  # fmt: skip
    v = fin["verim"]
    _kas(T("Enerji verimi: P değerleri", "Energy yield: P-values"))
    p = [x for x in v["p"]]
    olc = {(x["ufuk"], x["ad"]): x for x in v.get("olcum_sonrasi_p") or []}
    sim = v.get("simulasyon", {})
    adlar = [x["ad"] for x in p if x["ufuk"] == 1]
    satir = []
    for uf in (1, 10):
        a_ = {x["ad"]: x for x in p if x["ufuk"] == uf}
        satir.append(
            [T(f"Brüt, analitik ({uf} yıl)", f"Gross, analytic ({uf} yr)")]
            + [f"{sayi(a_[n]['mwh'] / 1e3, 1)} ({yuzde(100 * a_[n]['oran'], 0)})" for n in adlar]
        )
        if olc:
            satir.append([T(f"Ölçüm sonrası ({uf} yıl)", f"After measurement ({uf} yr)")]
                         + [f"{sayi(olc[(uf, n)]['mwh'] / 1e3, 1)} ({yuzde(100 * olc[(uf, n)]['oran'], 0)})" for n in adlar])  # fmt: skip
        s_ = sim.get(str(uf))
        if s_:
            satir.append([T(f"Satılan, simülasyon ({uf} yıl)", f"Sold, simulation ({uf} yr)")]
                         + [f"{sayi(s_[n] / 1e3, 1)} ({yuzde(100 * s_[n] / s_['P50'], 0)})" for n in adlar])  # fmt: skip
    B.karsilastirma_tablosu([T("GWh/yıl (P50'ye oran)", "GWh/yr (ratio to P50)"), *adlar], satir, mobilde_gizle=(2, 4))
    st.caption(md(T(
        f"Analitik: σ(T)² = Σ yıllık σ² / T + Σ kalıcı σ²; P_x = P50 · (1 − z_x · σ). RES–GES yıllık değişkenlik korelasyonu ρ = {sayi(v['rho_iav'], 2)}. "
        "Simülasyon: şebeke kısıtı, batarya ve sistem kesintisi sonrası satılan enerji (Monte Carlo; ilk yıl ve ilk 10 yılın ortalaması). "
        "10 yıllık P90 1 yıllığa göre P50'ye yakındır çünkü yıllık bileşenler ortalamada söner; kalıcı model hatası sönmez.",
        f"Analytic: σ(T)² = Σ annual σ² / T + Σ persistent σ²; P_x = P50 · (1 − z_x · σ). Wind–solar inter-annual correlation ρ = {sayi(v['rho_iav'], 2)}. "
        "Simulation: energy sold after the grid limit, battery and system curtailment (Monte Carlo; first year and mean of the first 10 years). "
        "The 10-year P90 is closer to P50 because annual components average out; the persistent model error does not.",
    )))  # fmt: skip
    _kas(T("Belirsizlik bütçesi", "Uncertainty budget"))
    tur_ad = {"yillik": ("yıllık", "annual"), "kalici": ("kalıcı", "persistent")}
    B.karsilastirma_tablosu(
        [T("Teknoloji", "Technology"), T("Bileşen", "Component"), T("Tür", "Type"), "σ", "MWh"],
        [[("RES" if b["teknoloji"] == "res" else "GES") if T("tr", "en") == "tr" else ("Wind" if b["teknoloji"] == "res" else "Solar"),
          T(*BILESEN_AD.get(b["ad"], (b["ad"], b["ad"]))), T(*tur_ad[b["tur"]]), yuzde(100 * b["sigma"], 1), sayi(b["mwh"], 0)]
         for b in v["bilesenler"]],
        mobilde_gizle=(2, 4),
    )  # fmt: skip
    st.caption(T("Atlas model hatası mevcut santrallerin ölçülen üretimiyle karşılaştırmadan gelir; iz, kayıp ve ortalama kullanılabilirliği zaten "
                 "içerdiği için ayrıca eklenmez (çift sayım olur).",
                 "The atlas model error comes from comparison with measured production of existing farms; it already embeds wake, losses and "
                 "average availability, so these are not added again (double counting)."))  # fmt: skip


__all__ = ["finansman_bolumu"]
