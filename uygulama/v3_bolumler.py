"""
v3 Faz D arayüz bölümleri (tam analiz sonucu): "Türbin yerleşimi" ve "İşletme ve bakım".

Görünüm "Eşik" tasarım sistemiyle: renkler yalnız uygulama/tasarim/tokenlar.py'den (tema renkleri ve veri paleti),
bileşenler uygulama/tasarim/bilesenler.py'den, grafikler ortak Plotly şablonuyla (ortak.sekil / ortak.ciz).
"""

from __future__ import annotations

import html

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from uygulama.ortak import RES, SOLUK, T, ciz, para, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.stil import aktif_tema
from uygulama.tasarim.tokenlar import TEMALAR

AYLAR_TR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
AYLAR_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PARCA_AD = {
    "kanat_rotor": ("Kanat", "Blade"),
    "disli_kutusu": ("Dişli kutusu", "Gearbox"),
    "jenerator": ("Jeneratör", "Generator"),
    "ana_yatak": ("Ana yatak", "Main bearing"),
}
YONTEM_AD = {
    "sa": ("Benzetimli tavlama + yerel arama", "Simulated annealing + local search"),
    "ga": ("Genetik algoritma", "Genetic algorithm"),
    "milp": ("MILP (Glover doğrusallaştırması)", "MILP (Glover linearisation)"),
    "izgara": ("Düzenli ızgara", "Regular grid"),
    "acgozlu": ("Açgözlü", "Greedy"),
}


def _aylar() -> list[str]:
    return AYLAR_TR if T("tr", "en") == "tr" else AYLAR_EN


# ------------------------------------------------------------------------------------------------------- türbin yerleşimi
def _yerlesim_haritasi(y: dict, merkez: tuple[float, float], tema: str):
    import folium

    from uygulama.harita import BOS_KARO, _harita_css

    t = TEMALAR[tema]
    r, sk = t["renk"], t["harita_skala"]
    m = folium.Map(location=list(merkez), zoom_start=13, tiles=None, control_scale=True, prefer_canvas=True)
    m.get_root().header.add_child(folium.Element(_harita_css(r, t["yazi"], t["streamlit"] == "dark")))
    m.get_root().header.add_child(folium.Element(f"<style>.leaflet-container{{background:{r['kara']}!important;}}</style>"))
    folium.TileLayer(BOS_KARO, attr="Eşik", name=T("Sade altlık", "Plain base map")).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
    folium.Circle(list(merkez), radius=y["yaricap_km"] * 1000, color=r["metin_soluk"], weight=1.2, dash_array="4 4", fill=False,
                  tooltip=T("Saha alanı", "Site area")).add_to(m)  # fmt: skip
    if y.get("komsu_turbinler"):
        fg = folium.FeatureGroup(name=T("Komşu santral türbinleri (OSM)", "Neighbouring farm turbines (OSM)"))
        for k in y["komsu_turbinler"]:
            folium.CircleMarker([k["enlem"], k["boylam"]], radius=3, color=r["metin_silik"], weight=1, fill=True, fill_color=r["yuzey2"],
                                fill_opacity=1, tooltip=f"{T('Mevcut türbin', 'Existing turbine')} · {sayi(k['P_mw'], 1)} MW · D {sayi(k['D_m'], 0)} m").add_to(fg)  # fmt: skip
        fg.add_to(m)
    E = np.array([x["E_mwh"] for x in y["turbinler"]])
    kenar = np.quantile(E, np.linspace(0, 1, len(sk) + 1)) if len(E) > 1 else np.array([E.min() - 1, E.max() + 1])
    sinif = np.clip(np.searchsorted(kenar, E, side="right") - 1, 0, len(sk) - 1)
    fg = folium.FeatureGroup(name=T("Önerilen türbinler", "Proposed turbines"))
    for i, (x, c) in enumerate(zip(y["turbinler"], sinif, strict=True), 1):
        ipucu = (
            f"<b>{T('Türbin', 'Turbine')} {i}</b><br>{T('Yıllık üretim', 'Annual energy')} {sayi(x['E_mwh'] / 1000, 2)} GWh · KF {yuzde(100 * x['kf'], 1)}"
            f"<br>{T('İz kaybı', 'Wake loss')} {yuzde(100 * x['toplam_iz'], 1)} · GWA {sayi(x['gwa'], 2)} m/s"
        )
        folium.CircleMarker([x["enlem"], x["boylam"]], radius=7, color=r["metin"], weight=1.2, fill=True, fill_color=sk[c], fill_opacity=0.95,
                            tooltip=ipucu).add_to(fg)  # fmt: skip
    fg.add_to(m)
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    m.fit_bounds([[min(x["enlem"] for x in y["turbinler"]) - 0.01, min(x["boylam"] for x in y["turbinler"]) - 0.012],
                  [max(x["enlem"] for x in y["turbinler"]) + 0.01, max(x["boylam"] for x in y["turbinler"]) + 0.012]])  # fmt: skip
    return m


def _ruzgar_gulu(g: dict, tema: str) -> go.Figure:
    sk = TEMALAR[tema]["harita_skala"]
    r = TEMALAR[tema]["renk"]
    eksen = dict(gridcolor=r["cizgi"], linecolor=r["cizgi"], tickfont=dict(color=r["metin_soluk"]))
    f = go.Figure()
    fr = np.array(g["frekans"])
    yon = [float(s) for s in g["sektor"]]
    pusula = [T("K", "N"), "30°", "60°", T("D", "E"), "120°", "150°", T("G", "S"), "210°", "240°", T("B", "W"), "300°", "330°"]
    for j, ad in enumerate(g["hiz"]):
        f.add_trace(go.Barpolar(r=fr[:, j], theta=yon, name=f"{ad} m/s", marker_color=sk[min(j, len(sk) - 1)], marker_line_width=0))
    f.update_layout(
        polar=dict(
            bgcolor=r["yuzey"],
            angularaxis=dict(direction="clockwise", rotation=90, tickvals=list(range(0, 360, 30)), ticktext=pusula, **eksen),
            radialaxis=dict(
                ticksuffix="%",
                angle=0,
                tickangle=0,
                showline=False,
                nticks=4,
                gridcolor=r["cizgi"],
                tickfont=dict(size=10, color=r["metin_soluk"]),
            ),
        ),
        barmode="stack",
        legend=dict(orientation="h", y=-0.12),
    )
    return sekil(f, T("Rüzgâr gülü (göbek yüksekliği)", "Wind rose (hub height)"), "", "", yukseklik=380,
                 alt=T("ERA5 100 m yönü × kalibre göbek hızı, 2014–2023 · % zaman", "ERA5 100 m direction × calibrated hub speed, 2014–2023 · % of time"))  # fmt: skip


def yerlesim_bolumu(o: dict, saha: dict) -> None:
    y = o.get("yerlesim")
    if not y:
        return
    tema = aktif_tema()
    B.bolum_basligi(T("Türbin yerleşimi", "Turbine layout"), T(*YONTEM_AD.get(y["yontem_kodu"], (y["yontem"], y["yontem"]))))
    u = st.columns(5)
    B.kpi_karti(u[0], T("Türbin", "Turbines"), f"{y['N']}", aciklama=f"D {sayi(y['turbin_D'], 0)} m")
    B.kpi_karti(
        u[1], T("İç iz kaybı", "Internal wake loss"), yuzde(100 * y["ic_iz"], 1), aciklama=T("PyWake, Bastankhah", "PyWake, Bastankhah")
    )
    B.kpi_karti(u[2], T("Komşu iz kaybı", "Neighbour wake loss"), yuzde(100 * y["dis_iz"], 1),
                aciklama=T(f"{y['komsu_turbin']} mevcut türbin, 10 km", f"{y['komsu_turbin']} existing turbines, 10 km"))  # fmt: skip
    B.kpi_karti(u[3], T("Konum kazancı", "Location gain"), sayi(y["konum_kazanci"], 3), yardim=T(
        "Seçilen konumların GWA hızına göre enerji oranı (1 = profilin temsil ettiği referans konum).",
        "Energy ratio from the GWA speed of the chosen positions (1 = the profile's reference position)."), aciklama="GWA 250 m")  # fmt: skip
    B.kpi_karti(u[4], T("Çiftlik verimi", "Farm efficiency"), yuzde(100 * y["verim"], 1), aciklama=T("konum × iz", "location × wake"))
    c = st.columns([1.35, 1], gap="medium")
    with c[0]:
        from streamlit_folium import st_folium

        st_folium(_yerlesim_haritasi(y, (saha["enlem"], saha["boylam"]), tema), height=430, use_container_width=True, returned_objects=[],
                  key="yerlesim_haritasi")  # fmt: skip
        st.caption(T("Daire: saha alanı · renk: türbinin yıllık üretimi (viridis, koyu = düşük) · gri: komşu santral türbinleri (OSM)",
                     "Circle: site area · colour: turbine annual energy (viridis, dark = low) · grey: neighbouring farm turbines (OSM)"))  # fmt: skip
    with c[1]:
        ciz(_ruzgar_gulu(y["ruzgar_gulu"], tema))
    eg = [e for e in y.get("iz_egrisi", []) if e.get("ic_iz") is not None and e["N"] > 0]
    if eg:
        f = go.Figure()
        f.add_trace(go.Scatter(x=[e["N"] for e in eg], y=[100 * e["ic_iz"] for e in eg], name=T("İç iz kaybı", "Internal wake loss"),
                               mode="lines+markers", line=dict(color=RES, width=2)))  # fmt: skip
        f.add_vline(x=y["N"], line_color=SOLUK, line_dash="dot", line_width=1)
        ciz(sekil(f, T("İz kaybı eğrisi (kapasite MILP'ine girdi)", "Wake-loss curve (input to the capacity MILP)"), "%", T("türbin sayısı", "number of turbines"),
                  yukseklik=280, alt=T("açgözlü iç içe yerleşim, hızlı vekil model · noktalı çizgi seçilen N",
                                       "greedy nested layouts, fast surrogate model · dotted line chosen N")))  # fmt: skip
    tur = y["turbinler"]
    B.karsilastirma_tablosu(
        [T("Türbin", "Turbine"), T("Enlem", "Lat"), T("Boylam", "Lon"), "GWA m/s", T("Yıllık üretim GWh", "Annual GWh"), "KF", T("İz kaybı", "Wake loss")],
        [[str(i), sayi(x["enlem"], 4), sayi(x["boylam"], 4), sayi(x["gwa"], 2), sayi(x["E_mwh"] / 1000, 2), yuzde(100 * x["kf"], 1), yuzde(100 * x["toplam_iz"], 1)]
         for i, x in enumerate(tur, 1)],
        mobilde_gizle=(1, 2, 3),
    )  # fmt: skip
    st.caption(
        T(
            f"Rüzgâr yönü kaynağı: {y['yon_kaynagi']} · hâkim yön {sayi(y['hakim_yon'], 0)}° · {y['aday_sayisi']} aday konum (GWA 250 m) · "
            f"asgari aralık hâkim yönde 5D, dik yönde 3D (elips) · üretim taban kaybı %{sayi(100 * y['taban_kayip'], 1)} (elektrik + atlas ortalama sapması)",
            f"Wind direction source: {y['yon_kaynagi']} · prevailing {sayi(y['hakim_yon'], 0)}° · {y['aday_sayisi']} candidate positions (GWA 250 m) · "
            f"minimum spacing 5D downwind, 3D crosswind (ellipse) · base loss {sayi(100 * y['taban_kayip'], 1)}% (electrical + mean atlas bias)",
        )
    )


# ------------------------------------------------------------------------------------------------------- işletme ve bakım
def bakim_bolumu(o: dict) -> None:
    b = o.get("bakim")
    if not b:
        return
    tema = aktif_tema()
    r = TEMALAR[tema]["renk"]
    st_ = {x["strateji"]: x for x in b["stratejiler"]}
    sec = st_.get(b["strateji"], b["stratejiler"][-1])
    B.bolum_basligi(
        T("İşletme ve bakım", "Operations and maintenance"),
        T(f"ayrık olay simülasyonu, {b['R']} ömür", f"discrete-event simulation, {b['R']} lifetimes"),
    )
    u = st.columns(4)
    B.kpi_karti(u[0], T("Kullanılabilirlik (enerji)", "Availability (energy)"), yuzde(100 * b["A_enerji"], 1),
                aciklama=f"P10–P90 {yuzde(100 * sec['A_enerji_p10'], 1)}–{yuzde(100 * sec['A_enerji_p90'], 1)}")  # fmt: skip
    B.kpi_karti(u[1], "O&M", f"{sayi(b['om_usd_mw_yil'] / 1000, 1)} {T('bin $/MW-yıl', 'k$/MW-yr')}",
                aciklama=T("v1 sabit varsayım 35,0", "v1 fixed assumption 35.0"))  # fmt: skip
    B.kpi_karti(u[2], T("Kayıp gelir", "Lost revenue"), f"{sayi(sec['kayip_gelir_yil'] / 1e3, 0)} {T('bin $/yıl', 'k$/yr')}",
                aciklama=f"{sayi(sec['kayip_mwh_yil'] / 1000, 1)} GWh/{T('yıl', 'yr')}")  # fmt: skip
    cz = b["cizelge"]
    B.kpi_karti(u[3], T("Çizelge kazancı", "Schedule saving"), f"{sayi(cz['kazanc_bahar'] / 1e3, 1)} {T('bin $/yıl', 'k$/yr')}",
                aciklama=T("bahar kampanyasına göre", "vs spring campaign"))  # fmt: skip
    B.karsilastirma_tablosu(
        [T("Strateji", "Strategy"), T("Kullanılabilirlik (zaman / enerji)", "Availability (time / energy)"), T("Kayıp üretim GWh/yıl", "Lost energy GWh/yr"),
         T("Kayıp gelir bin $/yıl", "Lost revenue k$/yr"), T("O&M bin $/yıl", "O&M k$/yr"), T("Toplam bin $/yıl (P10–P90)", "Total k$/yr (P10–P90)")],
        [[T(x["ad_tr"], x["ad_en"]), f"{yuzde(100 * x['A_zaman'], 1)} / {yuzde(100 * x['A_enerji'], 1)}", sayi(x["kayip_mwh_yil"] / 1000, 2),
          sayi(x["kayip_gelir_yil"] / 1e3, 0), sayi(x["om_usd_yil"] / 1e3, 0),
          f"{sayi(x['toplam_maliyet_yil'] / 1e3, 0)} ({sayi(x['toplam_maliyet_p10'] / 1e3, 0)}–{sayi(x['toplam_maliyet_p90'] / 1e3, 0)})"]
         for x in b["stratejiler"]],
        vurgulu=int(np.argmin([x["toplam_maliyet_yil"] for x in b["stratejiler"]])),
        mobilde_gizle=(2, 4),
    )  # fmt: skip
    c = st.columns(2, gap="medium")
    with c[0]:
        a = np.array(b["A_enerji_ornek"]) * 100
        f = go.Figure(go.Histogram(x=a, nbinsx=20, marker_color=RES, marker_line_width=0, name=T("tekrar", "replication")))
        ciz(sekil(f, T("Kullanılabilirlik dağılımı", "Availability distribution"), T("tekrar sayısı", "replications"), T("enerji bazlı kullanılabilirlik, %", "energy-based availability, %"),
                  yukseklik=300, alt=T("her tekrar bir proje ömrü (30 yıl) · seçilen strateji", "each replication is one project life (30 years) · selected strategy")))  # fmt: skip
    with c[1]:
        f = go.Figure()
        f.add_trace(
            go.Bar(x=_aylar(), y=cz["aylik_milp"], name=T("Optimize çizelge (MILP)", "Optimised schedule (MILP)"), marker_color=RES)
        )
        f.add_trace(go.Bar(x=_aylar(), y=cz["aylik_bahar"], name=T("Bahar kampanyası", "Spring campaign"), marker_color=SOLUK))
        f.update_layout(barmode="group")
        ciz(sekil(f, T("Önleyici bakım takvimi", "Preventive maintenance calendar"), T("türbin", "turbines"), "", yukseklik=300,
                  alt=T(f"yıllık bakım başlangıçları · kayıp gelir {sayi(cz['milp_maliyet'] / 1e3, 1)} vs {sayi(cz['bahar_maliyet'] / 1e3, 1)} bin $/yıl",
                        f"annual service start dates · lost revenue {sayi(cz['milp_maliyet'] / 1e3, 1)} vs {sayi(cz['bahar_maliyet'] / 1e3, 1)} k$/yr")))  # fmt: skip
    c = st.columns(2, gap="medium")
    with c[0]:
        mv = b.get("mevsimsel_hava_bekleme_gun")
        if mv:
            f = go.Figure(go.Bar(x=_aylar(), y=mv, marker_color=r["uyari"], name=T("hava beklemesi", "weather delay")))
            ciz(sekil(f, T("Arızanın mevsimine göre hava beklemesi", "Weather delay by season of failure"), T("gün", "days"), "", yukseklik=280,
                      alt=T("vinçli dişli kutusu değişimi: kaldırma (≤ 10 m/s, 6 saat) + iş (≤ 15 m/s, vardiya) · 10 hava yılı",
                            "crane gearbox exchange: lift (≤ 10 m/s, 6 h) + work (≤ 15 m/s, shift) · 10 weather years")))  # fmt: skip
    with c[1]:
        st.html(f'<div class="esik-kas">{html.escape(T("Önerilen yedek parça stoku", "Recommended spare parts"))}</div>')
        B.karsilastirma_tablosu(
            [T("Kalem", "Item"), T("Önerilen stok", "Recommended stock"), T("Tedarik", "Lead time"), T("Stok 0 / 1: toplam bin $/yıl", "Stock 0 / 1: total k$/yr")],
            [[T(*PARCA_AD.get(k, (k, k))), str(v["S"]), f"{v['tedarik_gun']} {T('gün', 'd')}",
              f"{sayi(v['tablo'][0]['toplam_yil'] / 1e3, 1)} / {sayi(v['tablo'][1]['toplam_yil'] / 1e3, 1)}"] for k, v in b["stok"].items()],
        )  # fmt: skip
        st.caption(T("Baz stok (S−1, S) politikası, simülasyon tabanlı optimizasyon (ortak rastgele sayılar): stok tutma maliyeti (%15/yıl) ile "
                     "parça beklerken kaybedilen gelir dengesi. Faz F'de sahalar arası havuzlama ile yeniden değerlendirilecek.",
                     "Base-stock (S−1, S) policy, simulation-based optimisation (common random numbers): holding cost (15%/yr) vs revenue lost "
                     "while waiting for parts. To be re-evaluated with cross-site pooling in Phase F."))  # fmt: skip
    gk = b.get("gider_kalemleri", {})
    if gk:
        ad = {"sabit_ekip": ("Teknisyen ekipleri", "Technician crews"), "duzeltici_malzeme": ("Düzeltici malzeme", "Corrective materials"),
              "vinc": ("Vinç", "Crane"), "onleyici_malzeme": ("Önleyici bakım malzemesi", "Preventive materials"), "cms": ("Durum izleme (CMS)", "Condition monitoring"),
              "stok_tutma": ("Stok tutma", "Spare holding"), "diger_sabit": ("Diğer sabit giderler", "Other fixed costs")}  # fmt: skip
        st.caption(T("O&M kalemleri (bin $/yıl, genel gider dahil): ", "O&M items (k$/yr, incl. overhead): ")
                   + " · ".join(f"{T(*ad.get(k, (k, k)))} {sayi(v / 1e3, 0)}" for k, v in gk.items()))  # fmt: skip


__all__ = ["bakim_bolumu", "para", "yerlesim_bolumu"]
