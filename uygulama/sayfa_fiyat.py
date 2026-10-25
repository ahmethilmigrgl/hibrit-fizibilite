"""
Fiyat projeksiyonu (v4 Faz K): Türkiye elektrik piyasası için merit order (arz yığını) modeli — kalibrasyon, örneklem dışı
doğrulama, 2026–2050 senaryoları ve motora aktarılan fiyat parametreleri.

Veri: data/atlas/v4_merit.json (src/v4_K1_merit_order.py; EPİAŞ ulusal saatlik üretim ve PTF'den çevrimdışı kalibre edilir).
"""

from __future__ import annotations

import json

import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from uygulama.ortak import BATARYA, GES, KOYU, RES, SOLUK, T, ciz, md, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B

SEN_AD = {
    "baz": ("Baz (Ulusal Enerji Planı)", "Base (National Energy Plan)"),
    "hizli_donusum": ("Hızlı dönüşüm (120 GW)", "Fast transition (120 GW)"),
    "yavas": ("Yavaş", "Slow"),
}
SEN_RENK = {"baz": RES, "hizli_donusum": GES, "yavas": SOLUK}
DUY_EN = {
    "Baz": "Base", "Gaz −%30": "Gas −30%", "Gaz +%30": "Gas +30%", "Depolama yok": "No storage", "Depolama ×2": "Storage ×2",
    "Karbon yok": "No carbon", "Karbon ×2": "Carbon ×2", "Talep %2/yıl": "Demand 2%/yr",
}  # fmt: skip


@st.cache_data(show_spinner=False)
def _paket() -> dict | None:
    p = veri_katmani.yol("atlas/v4_merit.json", zorunlu=False)
    return None if p is None else json.loads(p.read_text(encoding="utf-8"))


st.title(T("Fiyat projeksiyonu", "Price outlook"))
st.markdown(md(T(
    "Uzun vadeli elektrik fiyatı ve **güneşin kendi fiyatını düşürmesi** (kanibalizasyon), hibrit santral kararının en büyük iki "
    "belirsizliğidir. Bu sayfa, Türkiye piyasası için saatlik bir **merit order (arz yığını)** modelinin sonuçlarını gösterir: talep, "
    "yenilenebilir üretim, barajlı hidro ve depolama sevk edildikten sonra kalan termik yük, linyit → ithal kömür → doğalgaz sırasıyla "
    "karşılanır; fiyat, marjinal santralin maliyetidir.",
    "The long-run power price and **solar eroding its own price** (cannibalisation) are the two largest uncertainties in a hybrid "
    "plant decision. This page shows an hourly **merit-order (supply stack)** model of the Turkish market: after demand, renewables, "
    "dam hydro and storage are dispatched, the remaining thermal load is met by lignite → imported coal → gas; the price is the "
    "marginal plant's cost.",
)))  # fmt: skip
B.uyari_kutusu(
    T("Senaryo projeksiyonudur, tahmin değildir. Yakıt ve karbon fiyatları, kapasite gelişimi ve talep varsayımdır; model 2018–2025 "
      "verisiyle kalibre edilmiştir ve ithalat/ihracat, şebeke kısıtları ve stratejik teklif davranışı yalnız yaklaşık temsil edilir.",
      "A scenario projection, not a forecast. Fuel and carbon prices, capacity build-out and demand are assumptions; the model is "
      "calibrated on 2018–2025 data and represents imports/exports, grid constraints and strategic bidding only approximately."),
    "uyari",
)  # fmt: skip
p = _paket()
if p is None:
    B.bos_durum(
        T("Merit order paketi yok", "No merit-order package"),
        T("src/v4_K1_merit_order.py çalıştırılmalı.", "Run src/v4_K1_merit_order.py."),
    )
    st.stop()
dog = {r["yil"]: r for r in p["dogrulama"]}
mot = p["motor"]

# --- 1. Doğrulama
B.bolum_basligi(T("1. Model geçmişi ne kadar iyi açıklıyor?", "1. How well does the model explain the past?"),
                T("şekil 2018–2023'te kalibre, 2024–2025 örneklem dışı", "shape calibrated 2018–2023, 2024–2025 out of sample"))  # fmt: skip
u = st.columns(4)
for i, y in enumerate((2024, 2025)):
    B.kpi_karti(u[i], f"R² {y}", sayi(dog[y]["r2"], 2), aciklama=T(f"saatlik · gün içi korelasyon {sayi(dog[y]['gunici_korelasyon'], 2)}",
                                                                  f"hourly · diurnal correlation {sayi(dog[y]['gunici_korelasyon'], 2)}"))  # fmt: skip
B.kpi_karti(u[2], T("Güneş yakalanma 2025", "Solar capture 2025"), f"{sayi(dog[2025]['gunes_yakalanma_model'], 3)}",
            aciklama=T(f"gözlenen {sayi(dog[2025]['gunes_yakalanma_gozlenen'], 3)}", f"observed {sayi(dog[2025]['gunes_yakalanma_gozlenen'], 3)}"))  # fmt: skip
B.kpi_karti(u[3], T("Rüzgâr yakalanma 2025", "Wind capture 2025"), f"{sayi(dog[2025]['ruzgar_yakalanma_model'], 3)}",
            aciklama=T(f"gözlenen {sayi(dog[2025]['ruzgar_yakalanma_gozlenen'], 3)}", f"observed {sayi(dog[2025]['ruzgar_yakalanma_gozlenen'], 3)}"))  # fmt: skip
c = st.columns([1.2, 1], gap="medium")
with c[0]:
    f = go.Figure()
    for y, renk in (("2024", KOYU), ("2025", GES)):
        g = p["dogrulama_gunici"][y]
        f.add_trace(
            go.Scatter(x=list(range(24)), y=g["gozlenen"], name=T(f"{y} gözlenen", f"{y} observed"), line=dict(color=renk, width=2))
        )
        f.add_trace(
            go.Scatter(x=list(range(24)), y=g["model"], name=T(f"{y} model", f"{y} model"), line=dict(color=renk, width=2, dash="dash"))
        )
    ciz(sekil(f, T("Gün içi ortalama PTF (örneklem dışı)", "Average diurnal spot price (out of sample)"), "$/MWh", T("saat (TSİ)", "hour (local)"),
              yukseklik=360, alt=T("öğle çukuru güneşten, akşam tepesi gazdan", "midday dip from solar, evening peak from gas")))  # fmt: skip
with c[1]:
    B.karsilastirma_tablosu(
        [T("Yıl", "Year"), "R²", "RMSE", T("Güneş yak. (göz./model)", "Solar capt. (obs/model)"), T("Rüzgâr yak.", "Wind capt.")],
        [[f"{r['yil']}{'*' if r['donem'] == 'test' else ''}", sayi(r["r2"], 2), sayi(r["rmse"], 1),
          f"{sayi(r['gunes_yakalanma_gozlenen'], 2)} / {sayi(r['gunes_yakalanma_model'], 2)}",
          f"{sayi(r['ruzgar_yakalanma_gozlenen'], 2)} / {sayi(r['ruzgar_yakalanma_model'], 2)}"] for r in p["dogrulama"]],
        mobilde_gizle=(2, 4),
    )  # fmt: skip
    st.caption(T("Yıldızlı yıllar örneklem dışı. Fiyat seviyesi aylık gaz yakıt maliyeti (gizli değişken) ile her ay yeniden tahmin edilir; doğrulama, "
                 "eğrinin ŞEKLİNİ (saatlik tepki, öğle çukuru, yakalanma oranları) sınar.",
                 "Starred years are out of sample. The price level is re-estimated every month through the gas fuel cost (latent variable); validation tests "
                 "the curve's SHAPE (hourly response, midday dip, capture rates)."))  # fmt: skip

# --- 2. Senaryolar
B.bolum_basligi(T("2. Senaryolar 2026–2050", "2. Scenarios 2026–2050"), T("reel 2026 USD", "real 2026 USD"))
c = st.columns(2, gap="medium")
with c[0]:
    f = go.Figure()
    for ad, r in p["projeksiyon"].items():
        f.add_trace(
            go.Scatter(x=[x["yil"] for x in r], y=[x["ort_fiyat"] for x in r], name=T(*SEN_AD[ad]), line=dict(color=SEN_RENK[ad], width=2))
        )
    f.add_hline(y=58, line_color=SOLUK, line_dash="dot", annotation_text=T("varsayılan 58", "default 58"))
    ciz(sekil(f, T("Baz yük ortalama fiyat", "Baseload average price"), "$/MWh", "", yukseklik=360))
with c[1]:
    f = go.Figure()
    for ad, r in p["projeksiyon"].items():
        f.add_trace(go.Scatter(x=[x["yil"] for x in r], y=[x["gunes_yakalanma"] for x in r], name=T(f"{SEN_AD[ad][0]} — güneş", f"{SEN_AD[ad][1]} — solar"),
                               line=dict(color=SEN_RENK[ad], width=2)))  # fmt: skip
        f.add_trace(go.Scatter(x=[x["yil"] for x in r], y=[x["ruzgar_yakalanma"] for x in r], name=T(f"{SEN_AD[ad][0]} — rüzgâr", f"{SEN_AD[ad][1]} — wind"),
                               line=dict(color=SEN_RENK[ad], width=1.5, dash="dot")))  # fmt: skip
    ciz(sekil(f, T("Yakalanma oranı (üretim ağırlıklı fiyat / ortalama)", "Capture rate (generation-weighted / average price)"), "", "", yukseklik=360,
              alt=T("düz: güneş · noktalı: rüzgâr", "solid: solar · dotted: wind")))  # fmt: skip
sec = st.radio(T("Senaryo", "Scenario"), list(p["projeksiyon"]), horizontal=True, format_func=lambda x: T(*SEN_AD[x]), key="fiyat_sen")
c = st.columns([1.2, 1], gap="medium")
with c[0]:
    f = go.Figure()
    renk = {"2026": SOLUK, "2030": RES, "2035": GES, "2040": BATARYA}
    for y, v in p["gunici"][sec].items():
        f.add_trace(go.Scatter(x=list(range(24)), y=v, name=y, line=dict(color=renk.get(y, KOYU), width=2)))
    ciz(sekil(f, T("Gün içi fiyat profili", "Diurnal price profile"), "$/MWh", T("saat (TSİ)", "hour (local)"), yukseklik=340,
              alt=T("öğle çukuru güneş arttıkça derinleşir; depolama akşama kaydırır", "the midday dip deepens with solar; storage shifts it to the evening")))  # fmt: skip
with c[1]:
    r = {x["yil"]: x for x in p["projeksiyon"][sec]}
    B.karsilastirma_tablosu(
        [T("Yıl", "Year"), "$/MWh", T("Güneş yak.", "Solar capt."), T("Sıfır fiyat saati", "Zero-price hours"), T("Kesinti TWh", "Curtailment TWh"), "Mt CO₂"],
        [[str(y), sayi(r[y]["ort_fiyat"], 1), sayi(r[y]["gunes_yakalanma"], 2), yuzde(100 * r[y]["sifir_saat"], 1), sayi(r[y]["kesinti_twh"], 1), sayi(r[y]["emisyon_mt"], 0)]
         for y in (2026, 2030, 2035, 2040, 2045, 2050) if y in r],
        mobilde_gizle=(4, 5),
    )  # fmt: skip

# --- 3. Motor
B.bolum_basligi(T("3. Saha analizine aktarım", "3. Transfer to site analysis"), T("Varsayımlar → Fiyat görüşü", "Assumptions → Price view"))
B.karsilastirma_tablosu(
    [T("Fiyat görüşü", "Price view"), T("Seviyelendirilmiş fiyat", "Levelised price"), T("Güneş yakalanma tabanı", "Solar capture floor"), T("Taban yılı", "Floor year")],
    [[T("Varsayılan (v1–v3)", "Default (v1–v3)"), "58,0" if T("tr", "en") == "tr" else "58.0", sayi(0.60, 2), "2033"]]
    + [[T(*SEN_AD[a]), sayi(m["seviye"], 1), sayi(m["kanibalizasyon_taban_oran"], 2), str(m["kanibalizasyon_taban_yili"])] for a, m in mot.items()],
)  # fmt: skip
st.caption(md(T(
    "Seviyelendirilmiş fiyat: 2028–2057 proje ömrü boyunca reel %7 ile iskontolu ortalama. Kanibalizasyon: motorun 'taban yılına kadar "
    "doğrusal iniş' yolunun merit order güneş yakalanma yoluna en iyi uyan hâli. Merit order daha **yüksek fiyat** (talep büyümesi + karbon) "
    "ama çok daha **derin güneş kanibalizasyonu** öngörüyor; rüzgârın yakalanma oranı 0,93–0,99'da kalıyor. Sonuç: rüzgâr ve depolama lehine.",
    "Levelised price: 2028–2057 project-life average discounted at 7% real. Cannibalisation: the engine's 'linear decline to the floor year' "
    "path best fitting the merit-order solar capture path. The merit order implies a **higher price** (demand growth + carbon) but much "
    "**deeper solar cannibalisation**; wind capture stays at 0.93–0.99. Net: favours wind and storage.",
)))  # fmt: skip
du = p["duyarlilik"]
B.bolum_basligi(T("4. Duyarlılık (baz senaryo, 2035)", "4. Sensitivity (base scenario, 2035)"))
satir = [x for x in du if x["yil"] == 2035]
B.karsilastirma_tablosu(
    [T("Değişiklik", "Change"), "$/MWh", T("Güneş yakalanma", "Solar capture"), T("Rüzgâr yakalanma", "Wind capture"), T("Sıfır fiyat saati", "Zero-price hours")],
    [[T(x["duyarlilik"], DUY_EN.get(x["duyarlilik"], x["duyarlilik"])), sayi(x["ort_fiyat"], 1), sayi(x["gunes_yakalanma"], 2), sayi(x["ruzgar_yakalanma"], 2),
      yuzde(100 * x["sifir_saat"], 1)] for x in satir],
    mobilde_gizle=(3, 4),
)  # fmt: skip
st.caption(T("Depolama güneş kanibalizasyonunu en çok etkileyen kaldıraç; gaz ve karbon fiyatı seviyeyi taşır.",
             "Storage is the strongest lever on solar cannibalisation; gas and carbon prices drive the level."))  # fmt: skip
with st.expander(T("Model ayrıntısı", "Model details")):
    t = p["teta"]
    st.markdown(md(T(
        f"- **Arz eğrisi:** zorunlu çalışma altında fiyat (x/M)^α ile sıfıra iner (M = {sayi(t['must_oran'], 2)} × (linyit + kömür), α = {sayi(t['alpha'], 1)}); "
        f"doğalgaz bandında ısı oranı HR_min × (1 + (r − 1) q^κ), r = {sayi(t['r'], 2)}, κ = {sayi(t['kappa'], 2)}; eğri N(0, σ = {sayi(t['sigma_RL'], 0)} MW) ile düzgünleştirilir.\n"
        f"- **Döngü indirimi:** termik santraller akşam tepesi için devrede kalmak üzere gün içi çukurda maliyetin altında satar: fiyat × (1 − β d), β = {sayi(t['beta'], 2)}, "
        "d = (günün tepe artık yükü − saatin artık yükü) / termik kapasite. Bu terim öğle çukurunu ve güneş yakalanma oranını açıklamada belirleyici oldu.\n"
        "- **Kalibrasyon:** θ Nelder–Mead ile aylık ortalamaya göre bağıl saatlik hata; aylık gaz maliyeti ve yıllık kömür bandı her θ için doğrusal en küçük kareler.\n"
        "- **Sevk:** barajlı hidro aylık su bütçesiyle su doldurma (tepe tıraşlama), depolama günlük arbitraj, nükleer %90 sabit.",
        f"- **Supply curve:** below must-run the price falls to zero as (x/M)^α (M = {sayi(t['must_oran'], 2)} × (lignite + coal), α = {sayi(t['alpha'], 1)}); "
        f"gas band heat rate HR_min × (1 + (r − 1) q^κ), r = {sayi(t['r'], 2)}, κ = {sayi(t['kappa'], 2)}; smoothed by N(0, σ = {sayi(t['sigma_RL'], 0)} MW).\n"
        f"- **Cycling discount:** thermal units sell below cost in the midday trough to stay online for the evening peak: price × (1 − β d), β = {sayi(t['beta'], 2)}, "
        "d = (daily peak residual load − hourly residual load) / thermal capacity. This term was decisive in explaining the midday dip and solar capture.\n"
        "- **Calibration:** θ by Nelder–Mead on hourly error relative to the monthly mean; monthly gas cost and annual coal band by linear least squares for each θ.\n"
        "- **Dispatch:** dam hydro water-filling within monthly budgets (peak shaving), storage daily arbitrage, nuclear flat at 90%.",
    )))  # fmt: skip
    st.caption(f"θ = {', '.join(f'{k} {sayi(v, 3)}' for k, v in t.items())}")
