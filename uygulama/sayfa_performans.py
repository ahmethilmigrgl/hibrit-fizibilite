"""
Performans izleme (v3 Faz F4): kalibre RES santrallerinde gözlenen üretim / model beklentisi, akran düzeltmesi, istatistiksel süreç
kontrolü (Shewhart, EWMA, CUSUM), durum haritası, seçilen santralin kontrol kartları ve olay zaman çizelgesi.

Veri yalnız türetilmiş tablolar (data/atlas/izleme; src/v3_F4_performans.py, aylık güncelleme). Santral adları config
v3.performans.santral_adlari_goster ile; varsayılan kapalı (sonuçlar modelden türetilir, belirli bir şirkete doğrulanmamış iddia
bağlamamak için anonim kod + il).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from src.ayarlar import config_oku, deger
from uygulama import harita as H
from uygulama.ortak import RES, SOLUK, T, ciz, md, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.stil import aktif_tema
from uygulama.tasarim.tokenlar import TEMALAR

DURUM = {
    "normal": ("Normal", "Normal"),
    "izleniyor": ("İzleniyor", "Watch"),
    "kalici_sapma": ("Kalıcı sapma", "Persistent deviation"),
    "veri_yetersiz": ("Veri yetersiz", "Insufficient data"),
}


@st.cache_data(show_spinner=False)
def _veri():
    k = "atlas/izleme/"
    d = pd.read_csv(veri_katmani.yol(k + "durum.csv"))
    a = pd.read_parquet(veri_katmani.yol(k + "aylik.parquet"))
    g = pd.read_parquet(veri_katmani.yol(k + "gunluk.parquet"))
    dg = json.loads(veri_katmani.yol(k + "dogrulama.json").read_text(encoding="utf-8"))
    return d, a, g, dg


st.title(T("Performans izleme", "Performance monitoring"))
B.uyari_kutusu(
    T(
        "**Bu sayfa bir modelin çıktısıdır, santrallerin performansı hakkında bir yargı değildir.** Beklenen üretim ERA5 yeniden analizi, "
        "atlas kalibrasyonu ve akran santrallerle hesaplanır. **Model ile gözlem arasında kalıcı sapma** şunlardan kaynaklanabilir: model hatası "
        "(yerel rüzgâr, türbin vekili, yıllar arası ERA5 sapması), sistem talimatı ya da şebeke kısıtı, planlı bakım, veri sorunu (EPİAŞ "
        "kaydı, kapasite değişikliği) veya gerçek bir performans kaybı. Neden ancak santral sahibinin işletme verisiyle ayırt edilebilir.",
        "**This page is the output of a model, not a judgement on any plant's performance.** Expected output comes from ERA5 reanalysis, "
        "atlas calibration and peer plants. A **persistent deviation between model and observation** can stem from model error (local wind, "
        "turbine proxy, year-to-year ERA5 bias), system instructions or grid constraints, planned maintenance, data issues (EPİAŞ record, "
        "capacity change) or a genuine performance loss. Only the owner's operating data can tell these apart.",
    ),
    "uyari",
)
try:
    d, a, g, dg = _veri()
except Exception:
    B.bos_durum(T("İzleme verisi yok", "No monitoring data"), T("src/v3_F4_performans.py çalıştırılmalı.", "Run src/v3_F4_performans.py."))
    st.stop()
adlar = bool(deger(config_oku()["v3"]["performans"])["santral_adlari_goster"])
d["etiket"] = [f"{r.kod} · {r.il}" + (f" · {r.ad}" if adlar else "") for r in d.itertuples()]
tema = aktif_tema()
rk = TEMALAR[tema]["renk"]
vr = TEMALAR[tema]["veri"]
renk = {"normal": rk["iyi"], "izleniyor": rk["uyari"], "kalici_sapma": rk["kotu"], "veri_yetersiz": rk["metin_silik"]}

# --- 1. Durum
B.bolum_basligi(
    T("1. Durum haritası", "1. Status map"),
    T(f"{len(d)} kalibre santral · son ay {dg['son_donem'][:7]}", f"{len(d)} calibrated plants · last month {dg['son_donem'][:7]}"),
)
say = d["durum"].value_counts()
k = st.columns(4)
for i, (kk, (tr, en)) in enumerate(DURUM.items()):
    B.kpi_karti(k[i], T(tr, en), sayi(int(say.get(kk, 0)), 0), aciklama=T("santral", "plants"))
c = st.columns([1.3, 1], gap="medium")
with c[0]:
    try:
        from streamlit_folium import st_folium

        ip = [
            f"<b>{r.etiket}</b><br>{T(*DURUM[r.durum])}"
            + (f" · {T('son 6 ay açık', 'last 6 months gap')} {yuzde(100 * r.son_acik, 1)}" if pd.notna(r.son_acik) else "")
            for r in d.itertuples()
        ]
        m = H.nokta_haritasi(d, [renk[x] for x in d["durum"]], ip, tema, boyut=[4 + 2.2 * np.sqrt(x / 30) for x in d["kapasite_mw"]])
        st_folium(m, height=400, use_container_width=True, returned_objects=[], key="pi_harita")
    except Exception:
        pass
    st.caption(T("Yeşil normal · sarı izleniyor (son 3 ayda alarm) · kırmızı kalıcı sapma (son 6 ayın ≥ 3'ünde EWMA alarmı ve ≥ %3 açık) · gri veri yetersiz. Nokta büyüklüğü kurulu güç.",
                 "Green normal · amber watch (alarm in the last 3 months) · red persistent deviation (EWMA alarm in ≥ 3 of the last 6 months and ≥ 3% gap) · grey insufficient data. Marker size: capacity."))  # fmt: skip
with c[1]:
    sap = d[d["durum"].isin(["kalici_sapma", "izleniyor"])].sort_values(["durum", "son_acik"], ascending=[True, False])
    B.karsilastirma_tablosu(
        [T("Santral", "Plant"), T("Durum", "Status"), T("Son 6 ay açık", "Last 6 months gap"), T("Tahmini kayıp", "Est. loss")],
        [[r.etiket, T(*DURUM[r.durum]), yuzde(100 * r.son_acik, 1) if pd.notna(r.son_acik) else "–", f"{sayi(r.kayip_usd / 1e6, 2)} M$"] for r in sap.head(14).itertuples()],
        mobilde_gizle=(3,),
    )  # fmt: skip
    st.caption(T("Tahmini kayıp: izleme dönemi boyunca EWMA alarmlı aylarda taban göreli performansa göre üretim açığı × aylık ortalama PTF (USD). Modelden türetilmiş üst sınır.",
                 "Estimated loss: output shortfall versus baseline relative performance in EWMA-alarm months × monthly average spot price (USD). A model-derived upper bound."))  # fmt: skip

# --- 2. Santral ayrıntısı
B.bolum_basligi(T("2. Kontrol kartları", "2. Control charts"))
sec = st.selectbox(T("Santral", "Plant"), d["epias_id"].tolist(), format_func=lambda x: d.set_index("epias_id").loc[x, "etiket"],
                   index=int(np.argmax(d["durum"].eq("kalici_sapma").to_numpy())) if (d["durum"] == "kalici_sapma").any() else 0, key="pi_santral")  # fmt: skip
s = a[a["epias_id"] == sec].sort_values("donem")
kp = dg["kart_parametreleri"]
lam = 0.2
cfg_p = deger(config_oku()["v3"]["performans"])
lam, kc = cfg_p["ewma_lambda"], cfg_p["cusum_k"]
c = st.columns(2, gap="medium")
with c[0]:
    f = go.Figure()
    f.add_trace(
        go.Scatter(
            x=s["donem"],
            y=100 * s["rel"].clip(upper=2.0),
            mode="lines+markers",
            line={"color": RES, "width": 1.8},
            marker={"size": 4},
            name=T("akran düzeltmeli oran", "peer-adjusted ratio"),
        )
    )
    al = s[s["alarm_ewma"] | s["alarm_cusum"]]
    f.add_trace(
        go.Scatter(
            x=al["donem"],
            y=100 * al["rel"].clip(upper=2.0),
            mode="markers",
            marker={"color": rk["kotu"], "size": 8, "symbol": "x"},
            name=T("alarm (EWMA/CUSUM)", "alarm (EWMA/CUSUM)"),
        )
    )
    f.add_hline(y=100, line={"color": SOLUK, "dash": "dot"})
    ciz(
        sekil(
            f,
            T("Performans oranı (taban = 100; 200’de kırpıldı)", "Performance ratio (baseline = 100; capped at 200)"),
            "%",
            "",
            yukseklik=300,
        )
    )
with c[1]:
    f = go.Figure()
    f.add_trace(go.Scatter(x=s["donem"], y=s["ewma"], mode="lines", line={"color": vr["res"]}, name="EWMA"))
    f.add_hline(y=-kp["ewma"] * np.sqrt(lam / (2 - lam)), line={"color": rk["kotu"], "dash": "dash"})
    f.add_trace(go.Scatter(x=s["donem"], y=-s["cusum"], mode="lines", line={"color": vr["ges"]}, name="−CUSUM", yaxis="y2"))
    f.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
    f.add_hline(y=-kp["cusum"], line={"color": vr["ges"], "dash": "dot"}, yref="y2")
    ciz(
        sekil(
            f, T("EWMA ve CUSUM (kesikli: alt kontrol sınırları)", "EWMA and CUSUM (dashed: lower control limits)"), "z", "", yukseklik=300
        )
    )
gg = g[g["epias_id"] == sec].copy()
gg["ay"] = gg["gun"].dt.to_period("M").dt.start_time
ev = gg.groupby("ay").agg(bolgesel=("bolgesel", "sum"), yat=("yat", "sum"), kapasite=("kapasite_olayi", "sum"))
f = go.Figure()
f.add_trace(
    go.Bar(
        x=ev.index,
        y=ev["bolgesel"],
        marker_color=SOLUK,
        name=T("bölgesel eşzamanlı düşüş günleri (dışlandı)", "regional simultaneous-drop days (excluded)"),
    )
)
f.add_trace(
    go.Bar(
        x=ev.index, y=ev["yat"], marker_color=vr["altin"], name=T("ulusal YAT günleri (dışlandı)", "national curtailment days (excluded)")
    )
)
for x in ev.index[ev["kapasite"] > 0]:
    f.add_vline(x=x, line={"color": vr["batarya"], "width": 2})
for x in s.loc[s["alarm_ewma"], "donem"]:
    f.add_vrect(x0=x, x1=x + pd.offsets.MonthEnd(1), fillcolor=rk["kotu"], opacity=0.12, line_width=0)
f.update_layout(barmode="stack")
ciz(
    sekil(
        f,
        T(
            "Olay zaman çizelgesi (dikey çizgi: kapasite artırımı/yenileme; gölge: EWMA alarmı)",
            "Event timeline (vertical line: capacity increase/repowering; shading: EWMA alarm)",
        ),
        T("gün", "days"),
        "",
        yukseklik=260,
    )
)
r = d[d["epias_id"] == sec].iloc[0]
st.caption(md(T(
    f"Taban gürültüsü σ0 = {yuzde(100 * r.sigma0, 1)} (aylık) · akran ağırlığı b = {sayi(r.b_akran, 2)} ({int(r.akran_sayisi)} akran ≤ 100 km) · "
    f"izleme {int(r.izleme_donem)} ay · EWMA alarmlı {int(r.alarm_donem_ewma)} ay.",
    f"Baseline noise σ0 = {yuzde(100 * r.sigma0, 1)} (monthly) · peer weight b = {sayi(r.b_akran, 2)} ({int(r.akran_sayisi)} peers ≤ 100 km) · "
    f"monitored {int(r.izleme_donem)} months · EWMA alarm in {int(r.alarm_donem_ewma)} months.",
)))  # fmt: skip

# --- 3. Yöntem ve doğrulama
B.bolum_basligi(T("3. Yöntem ve doğrulama", "3. Method and validation"))
st.markdown(md(T(
    "1. **Oran:** gözlenen üretim / model beklentisi (ERA5 + atlas k matrisi × kapasite), günlük ve aylık.\n"
    "2. **Ayıklama:** aynı bölgede santrallerin yarısının aynı gün düştüğü günler (sistem talimatı, şebeke olayı) ve ulusal YAT günleri analiz dışı; "
    "kapasite artırımları ayrı olay.\n"
    "3. **Akran düzeltmesi:** x = ln oran − b · ln akran oranı; b taban dönemde en küçük varyansı veren ağırlık (hava ve model hatasının ortak kısmı).\n"
    "4. **Kayan taban:** her ay için taban, 7–30 ay önceki dönemin medyanı (yavaş kaymalar elenir; 6 aya kadar süren düşüş tabanı kirletmez).\n"
    f"5. **Kartlar:** Shewhart (ani düşüş), EWMA (λ = {lam}) ve CUSUM (k = {kc}); sınırlar ortalama çalışma uzunluğu ARL0 = {dg['hedef_arl0_donem']} ay olacak şekilde "
    "(santral başına yaklaşık 4 yılda bir yanlış alarm) blok bootstrap ile seçildi.",
    "1. **Ratio:** observed output / model expectation (ERA5 + atlas k matrix × capacity), daily and monthly.\n"
    "2. **Screening:** days when half of the plants in a region drop together (system instruction, grid event) and national curtailment days are "
    "excluded; capacity increases are separate events.\n"
    "3. **Peer adjustment:** x = ln ratio − b · ln peer ratio; b is the minimum-variance weight in the baseline (shared weather and model error).\n"
    "4. **Moving baseline:** for each month, the median of months 7–30 earlier (slow drifts are removed; a drop of up to 6 months does not contaminate it).\n"
    f"5. **Charts:** Shewhart (sudden drops), EWMA (λ = {lam}) and CUSUM (k = {kc}); limits set by block bootstrap so that the average run length ARL0 = "
    f"{dg['hedef_arl0_donem']} months (about one false alarm per plant every 4 years).",
)))  # fmt: skip
ya = pd.DataFrame(dg["yapay_ariza"])
p = ya.pivot_table(index=["dusus", "sure_donem"], columns="kart", values="yakalama").reset_index()
gc = ya.pivot_table(index=["dusus", "sure_donem"], columns="kart", values="gecikme_medyan_donem").reset_index()
B.karsilastirma_tablosu(
    [T("Yapay düşüş", "Synthetic drop"), T("Süre (ay)", "Duration (months)"), "Shewhart", "EWMA", "CUSUM", T("CUSUM gecikme (ay)", "CUSUM delay (months)")],
    [[yuzde(100 * x.dusus, 0), str(int(x.sure_donem)), yuzde(100 * x.shewhart, 0), yuzde(100 * x.ewma, 0), yuzde(100 * x.cusum, 0), sayi(y.cusum, 0)]
     for x, y in zip(p.itertuples(), gc.itertuples())],
    mobilde_gizle=(5,),
)  # fmt: skip
fa = dg["yanlis_alarm_yil_gercek_normal"]
st.caption(md(T(
    f"Yakalama: arıza süresi + 2 ay içinde alarm. Yanlış alarm (normal santrallerin gerçek serilerinde): Shewhart {sayi(fa['shewhart'], 2)}, EWMA {sayi(fa['ewma'], 2)}, "
    f"CUSUM {sayi(fa['cusum'], 2)} / santral-yıl (hedef {sayi(dg['yanlis_alarm_yil_teorik'], 2)}). Aylık gürültü σ0 ≈ {yuzde(100 * dg['sigma0_medyan'], 0)}: model tabanlı "
    "izleme %10'luk ve birkaç ay süren düşüşleri iyi, %3'lük düşüşleri zayıf yakalar — bu, ERA5 çözünürlüğünün sınırıdır.",
    f"Detection: alarm within the fault duration + 2 months. False alarms (real series of normal plants): Shewhart {sayi(fa['shewhart'], 2)}, EWMA {sayi(fa['ewma'], 2)}, "
    f"CUSUM {sayi(fa['cusum'], 2)} per plant-year (target {sayi(dg['yanlis_alarm_yil_teorik'], 2)}). Monthly noise σ0 ≈ {yuzde(100 * dg['sigma0_medyan'], 0)}: model-based "
    "monitoring catches 10% drops lasting a few months well and 3% drops poorly — the limit of ERA5 resolution.",
)))  # fmt: skip
