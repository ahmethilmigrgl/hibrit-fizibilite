"""
Ön tarama haritası (folium). Hücreler 0,25° dikdörtgenler (tek GeoJSON katmanı); renk viridis sıralı skala (renk körlüğünde
sıralama korunur): açık temada koyu mor, koyu temada parlak sarı = daha cazip. Düşük güvenli hücreler soluk dolguyla ayrılır.
Kalibre santraller ayrı, açılıp kapatılabilir katman.

Altlık: üçüncü taraf karo yok. İl sınırları ve kıyılar (data/atlas/altlik_tr.geojson: geoBoundaries + Natural Earth) temanın
renkleriyle çizilir; API anahtarı veya karo kullanım politikası gerektirmez. Saha ölçeğinde ayrıntı için katman menüsünden
isteğe bağlı OpenStreetMap altlığı seçilebilir (© OpenStreetMap katkıcıları; herkese açık yayında OSM karo kullanım
politikasına uyulmalı).
"""

from __future__ import annotations

import html
import json
from functools import lru_cache

import folium
import numpy as np
import pandas as pd

from src import veri_katmani
from uygulama.ortak import T, sayi, yuzde
from uygulama.tasarim.tokenlar import TEMALAR

# katman: (sütun, TR ad, EN ad, birim, yüksek değer iyi mi)
KATMANLAR = {
    "basabas_en_iyi": ("En iyi tasarımın başabaş fiyatı", "Break-even price of the best design", "$/MWh", False),
    "basabas_res": ("RES başabaş fiyatı", "Wind break-even price", "$/MWh", False),
    "basabas_ges": ("GES başabaş fiyatı", "Solar break-even price", "$/MWh", False),
    "res_kf": ("RES kapasite faktörü", "Wind capacity factor", "%", True),
    "ges_kf": ("GES kapasite faktörü", "Solar capacity factor", "%", True),
    "baglanti_kusd_mw": ("Şebeke bağlantı maliyeti (50 MW)", "Grid connection cost (50 MW)", "bin $/MW", False),
    "egim_ort": ("Ortalama eğim (2 km yarıçap)", "Mean slope (2 km radius)", "°", False),
    "uygunluk": ("Çok kriterli uygunluk (TOPSIS)", "Multi-criteria suitability (TOPSIS)", "/100", True),
}
KISA_AD = {
    "basabas_en_iyi": ("Başabaş", "Break-even"),
    "basabas_res": ("RES başabaş", "Wind break-even"),
    "basabas_ges": ("GES başabaş", "Solar break-even"),
    "res_kf": ("RES KF", "Wind CF"),
    "ges_kf": ("GES KF", "Solar CF"),
    "baglanti_kusd_mw": ("Bağlantı", "Connection"),
    "egim_ort": ("Eğim", "Slope"),
    "uygunluk": ("Uygunluk", "Suitability"),
}
ALTYAPI = {
    "trafo": ("Trafo merkezleri (≥154 kV)", "Substations (≥154 kV)"),
    "hat": ("İletim hatları", "Transmission lines"),
    "agir_yol": ("Ağır nakliye yolları", "Heavy-haul roads"),
    "tedarik": ("Limanlar ve üreticiler", "Ports and manufacturers"),
    "koruma": ("Koruma alanları", "Protected areas"),
    "goc": ("Göç koridorları (yaklaşık)", "Migration corridors (approx.)"),
}
DUSUK_GUVEN_OPAKLIK, YUKSEK_GUVEN_OPAKLIK = 0.34, 0.86
SINIF = 6
BOS_KARO = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"  # saydam 1 px: "sade" altlık


@lru_cache(maxsize=1)
def _altlik() -> dict | None:
    try:
        p = veri_katmani.yol("atlas/altlik_tr.geojson", zorunlu=False)
        return json.loads(p.read_text(encoding="utf-8")) if p is not None else None
    except Exception:
        return None


def siniflar(v: pd.Series, iyi_yuksek: bool) -> tuple[np.ndarray, list[float]]:
    """6 sınıf (eşit yüzdelikler); sınıf 0 = en cazip."""
    q = np.nanquantile(v, np.linspace(0, 1, SINIF + 1))
    s = np.clip(np.searchsorted(q[1:-1], v, side="right"), 0, SINIF - 1)
    return (SINIF - 1 - s if iyi_yuksek else s), q.tolist()


def gosterim(kolon: str, x: float) -> str:
    return yuzde(100 * x, 1) if kolon.endswith("_kf") else sayi(x, 0)


def _harita_css(r: dict, y: dict, koyu: bool) -> str:
    """Leaflet denetimlerini (yakınlaştırma, katman menüsü, ipucu, ölçek, atıf) temaya uydurur."""
    return f"""<style>
.leaflet-container{{background:{r["deniz"]}!important;font-family:'{y["arayuz"]}',system-ui,sans-serif;}}
.leaflet-bar a,.leaflet-control-layers{{background:{r["yuzey"]}!important;color:{r["metin"]}!important;border-color:{r["cizgi"]}!important;}}
.leaflet-bar{{border:1px solid {r["cizgi"]}!important;box-shadow:none!important;}}
.leaflet-control-layers{{border:1px solid {r["cizgi"]}!important;box-shadow:none!important;border-radius:6px;font-size:12px;}}
.leaflet-control-layers-toggle{{filter:{"invert(.85)" if koyu else "none"};}}
.leaflet-tooltip{{background:{r["yuzey"]};color:{r["metin"]};border:1px solid {r["cizgi"]};border-radius:6px;box-shadow:0 4px 14px rgba(0,0,0,.18);
  font-size:12px;line-height:1.45;padding:7px 9px;font-variant-numeric:tabular-nums;}}
.leaflet-tooltip-top:before,.leaflet-tooltip-bottom:before,.leaflet-tooltip-left:before,.leaflet-tooltip-right:before{{display:none;}}
.leaflet-control-scale-line{{background:{r["yuzey"]}cc;color:{r["metin_soluk"]};border-color:{r["metin_soluk"]};}}
.leaflet-control-attribution{{background:{r["yuzey"]}cc!important;color:{r["metin_soluk"]};font-size:10px;}}
.leaflet-control-attribution a{{color:{r["metin_soluk"]};}}
.esik-secim{{width:22px;height:22px;border-radius:50%;background:{r["vurgu"]};border:3px solid {r["yuzey"]};box-shadow:0 0 0 2px {r["vurgu"]},0 2px 8px rgba(0,0,0,.35);}}
.esik-tedarik{{width:22px;height:22px;border-radius:5px;background:{r["yuzey"]};color:{r["metin"]};border:1.5px solid {r["metin"]};
  display:flex;align-items:center;justify-content:center;font:700 11px/1 '{y["sayi"]}',monospace;}}
.esik-tedarik.soluk{{opacity:.5;border-style:dashed;}}
.esik-aday{{width:22px;height:22px;border-radius:50%;background:{r["yuzey"]};color:{r["metin"]};border:2px solid {r["vurgu"]};
  font:600 11px/18px '{y["sayi"]}',monospace;text-align:center;}}
</style>"""


def harita(
    ot: pd.DataFrame | None,
    kolon: str,
    santral: pd.DataFrame | None = None,
    secim: tuple[float, float] | None = None,
    aday: pd.DataFrame | None = None,
    turbinler: list | None = None,
    merkez: tuple[float, float] = (39.0, 35.2),
    zoom: int = 6,
    tema: str = "acik",
    altyapi: dict | None = None,
) -> folium.Map:
    t = TEMALAR[tema]
    r, sk = t["renk"], t["harita_skala"]
    koyu = t["streamlit"] == "dark"
    m = folium.Map(location=list(merkez), zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True, min_zoom=5)
    if zoom <= 6:  # ülke görünümü: her ekran genişliğinde Türkiye'nin tamamı
        m.fit_bounds([[35.8, 25.7], [42.1, 44.8]])
    m.get_root().header.add_child(folium.Element(_harita_css(r, t["yazi"], koyu)))
    folium.TileLayer(BOS_KARO, attr="geoBoundaries · Natural Earth", name=T("Sade altlık", "Plain base map"), control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True, show=False).add_to(m)
    alt = _altlik()
    if alt is not None:
        altlik = folium.GeoJson(
            alt,
            name="altlik",
            control=False,
            interactive=False,
            style_function=lambda f: {
                "fillColor": r["kara"],
                "fillOpacity": 1 if f["properties"]["tur"] == "ulke" else 0,
                "color": r["sinir"],
                "weight": 0.7 if f["properties"]["tur"] == "il" else 0.9,
            },
        ).add_to(m)
        # OSM seçilince sade altlık gizlenir (kara dolgusu karoların üstünü örtmesin)
        m.get_root().script.add_child(
            folium.Element(
                f"{m.get_name()}.on('baselayerchange', function(e) {{ if (e.name === 'OpenStreetMap') {{ {m.get_name()}.removeLayer("
                f"{altlik.get_name()}); }} else {{ {altlik.get_name()}.addTo({m.get_name()}); {altlik.get_name()}.bringToBack(); }} }});"
            )
        )
    if ot is not None and len(ot):
        ad_tr, ad_en, birim, iyi_yuksek = KATMANLAR[kolon]
        v = ot[kolon].astype(float)
        sinif, _ = siniflar(v, iyi_yuksek)
        ozellik = []
        for rr, c in zip(ot.itertuples(), sinif, strict=True):
            e, b = rr.hucre_enlem, rr.hucre_boylam
            dusuk = rr.guven != "yüksek"
            ada = bool(getattr(rr, "ada", False))
            ust = bool(getattr(rr, "ust_sinir", False))
            notlar = ([T("Ada: bağlantı denizaltı kablosu gerektirir", "Island: connection requires a submarine cable")] if ada else []) + (
                [T("Üst sınıra yakın: ihtiyatla değerlendirin", "Near the upper bound: treat with caution")] if ust else []
            )
            ozellik.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [b - 0.125, e - 0.125],
                                [b + 0.125, e - 0.125],
                                [b + 0.125, e + 0.125],
                                [b - 0.125, e + 0.125],
                                [b - 0.125, e - 0.125],
                            ]
                        ],
                    },
                    "properties": {
                        "renk": sk[int(c)],
                        "dusuk": bool(dusuk),
                        "ada": ada,
                        "ust": ust,
                        "not": html.escape(" · ".join(notlar)),
                        "yer": f"<b>{html.escape(rr.il)} / {html.escape(rr.ilce)}</b>",
                        "deger": f"{T(ad_tr, ad_en)}: <b>{gosterim(kolon, getattr(rr, kolon))}</b> {'' if birim == '%' else birim}",
                        "res": f"RES KF {gosterim('res_kf', rr.res_kf)} · GES KF {gosterim('ges_kf', rr.ges_kf)}",
                        "guven": T("Güven: ", "Confidence: ") + (T("düşük", "low") if dusuk else T("yüksek", "high")),
                    },
                }
            )
        folium.GeoJson(
            {"type": "FeatureCollection", "features": ozellik},
            name=T("Ön tarama", "Pre-screening"),
            style_function=lambda f: {
                "fillColor": f["properties"]["renk"],
                "fillOpacity": DUSUK_GUVEN_OPAKLIK if f["properties"]["dusuk"] else YUKSEK_GUVEN_OPAKLIK,
                "color": r["metin"]
                if f["properties"]["ust"]
                else (t["veri"]["batarya"] if f["properties"]["ada"] else f["properties"]["renk"]),
                "weight": 2.2 if (f["properties"]["ust"] or f["properties"]["ada"]) else (0 if f["properties"]["dusuk"] else 0.5),
                "dashArray": "1 4" if f["properties"]["ada"] else None,
            },
            highlight_function=lambda f: {"weight": 2, "color": r["metin"]},
            tooltip=folium.GeoJsonTooltip(fields=["yer", "deger", "res", "guven", "not"], labels=False),
        ).add_to(m)
    if santral is not None and len(santral):
        fg = folium.FeatureGroup(name=T("Kalibre RES santralleri", "Calibrated wind farms"), show=True)
        for rr in santral.itertuples():
            folium.CircleMarker(
                [rr.enlem, rr.boylam],
                radius=3.6,
                color=r["zemin"] if koyu else r["metin"],
                weight=1.3,
                fill=True,
                fill_color=r["metin"] if koyu else r["yuzey"],
                fill_opacity=1,
                tooltip=f"<b>{html.escape(rr.ad)}</b><br>{T('gözlenen KF', 'observed CF')} {gosterim('res_kf', rr.gozlenen_kf)} · {html.escape(str(rr.turbin))}",
            ).add_to(fg)
        fg.add_to(m)
    if aday is not None and len(aday):
        fg = folium.FeatureGroup(name=T("Aday noktalar", "Candidate points"))
        for i, rr in enumerate(aday.itertuples(), 1):
            folium.Marker(
                [rr.enlem, rr.boylam],
                tooltip=f"{T('Aday', 'Candidate')} {i}: GWA {sayi(rr.gwa_1km, 1)} m/s",
                icon=folium.DivIcon(html=f'<div class="esik-aday">{i}</div>', icon_size=(22, 22), icon_anchor=(11, 11)),
            ).add_to(fg)
        fg.add_to(m)
    if turbinler:
        fg = folium.FeatureGroup(name=T("Türbin yerleşimi (GWA en rüzgârlı hücreler)", "Turbine layout (windiest GWA cells)"))
        for e, b in turbinler:
            folium.CircleMarker([e, b], radius=2.5, color=r["vurgu"], fill=True, fill_opacity=1, weight=0).add_to(fg)
        fg.add_to(m)
    if secim is not None:
        folium.Marker(
            list(secim),
            tooltip=T("Seçilen nokta", "Selected point"),
            icon=folium.DivIcon(html='<div class="esik-secim"></div>', icon_size=(22, 22), icon_anchor=(11, 11)),
        ).add_to(m)
    if altyapi:
        altyapi_ekle(m, altyapi, tema)
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    return m


def altyapi_ekle(m: folium.Map, katmanlar: dict, tema: str) -> None:
    """v3 Faz E altyapı katmanları (yalnız kullanıcı seçtiğinde eklenir; açılış süresini etkilemez)."""
    t = TEMALAR[tema]
    r, v = t["renk"], t["veri"]
    if katmanlar.get("goc"):
        folium.GeoJson(
            katmanlar["goc"],
            name=T(*ALTYAPI["goc"]),
            style_function=lambda f: {"fillColor": r["uyari"], "color": r["uyari"], "weight": 0.8,
                                      "fillOpacity": 0.28 if f["properties"]["risk"] == "yuksek" else 0.12},
            tooltip=folium.GeoJsonTooltip(fields=["ad", "risk"], aliases=[T("Koridor", "Corridor"), T("Risk", "Risk")]),
        ).add_to(m)  # fmt: skip
    if katmanlar.get("koruma"):
        folium.GeoJson(
            katmanlar["koruma"],
            name=T(*ALTYAPI["koruma"]),
            style_function=lambda f: {"fillColor": v["hibrit"], "color": v["hibrit"], "weight": 0.6, "fillOpacity": 0.25},
            tooltip=folium.GeoJsonTooltip(fields=["ad", "tur"], aliases=[T("Ad", "Name"), T("Tür", "Type")]),
        ).add_to(m)
    if katmanlar.get("agir_yol"):
        folium.GeoJson(
            katmanlar["agir_yol"],
            name=T(*ALTYAPI["agir_yol"]),
            style_function=lambda f: {
                "color": r["metin_soluk"],
                "weight": 1.6 if f["properties"]["sinif"] == "motorway" else 1.0,
                "opacity": 0.8,
            },
        ).add_to(m)
    if katmanlar.get("hat"):
        folium.GeoJson(
            katmanlar["hat"],
            name=T(*ALTYAPI["hat"]),
            style_function=lambda f: {"color": v["altin"], "weight": 1.6 if f["properties"]["kv"] >= 300 else 0.9, "opacity": 0.9},
        ).add_to(m)
    if katmanlar.get("trafo"):
        fg = folium.FeatureGroup(name=T(*ALTYAPI["trafo"]))
        d = katmanlar["trafo"]
        for e, b, kv, ad in zip(d["enlem"], d["boylam"], d["kv"], d["ad"], strict=True):
            folium.CircleMarker([e, b], radius=2.8 if kv < 300 else 4, color=v["batarya"], weight=1, fill=True, fill_opacity=0.9,
                                tooltip=f"{html.escape(str(ad) if ad == ad else '(adsız)')} · {sayi(kv, 0)} kV").add_to(fg)  # fmt: skip
        fg.add_to(m)
    if katmanlar.get("tedarik"):
        fg = folium.FeatureGroup(name=T(*ALTYAPI["tedarik"]))
        d = katmanlar["tedarik"]
        for ad, tur, e, b, dg, bil in zip(d["ad"], d["tur"], d["enlem"], d["boylam"], d["dogrulandi"], d["bilesenler"], strict=True):
            ikon = T("L", "P") if tur == "liman" else T("Ü", "M")
            folium.Marker(
                [e, b],
                tooltip=f"<b>{html.escape(ad)}</b><br>{html.escape(str(bil).replace(';', ', '))}" + ("" if dg else T(" · doğrulanmadı", " · unverified")),
                icon=folium.DivIcon(html=f'<div class="esik-tedarik{"" if dg else " soluk"}">{ikon}</div>',
                                    icon_size=(22, 22), icon_anchor=(11, 11)),
            ).add_to(fg)  # fmt: skip
        fg.add_to(m)


def lejant(ot: pd.DataFrame | None, kolon: str, tema: str = "acik") -> str:
    """HTML lejant: 6 sınıf (renk + aralık) ve güven/santral anahtarı. Sınıflar en cazipten başlar."""
    if ot is None or not len(ot):
        return ""
    ad_tr, ad_en, birim, iyi_yuksek = KATMANLAR[kolon]
    sk = TEMALAR[tema]["harita_skala"]
    r = TEMALAR[tema]["renk"]
    _, q = siniflar(ot[kolon].astype(float), iyi_yuksek)
    araliklar = [(q[i], q[i + 1]) for i in range(SINIF)]
    if iyi_yuksek:
        araliklar = araliklar[::-1]
    kutu = "".join(
        f'<div class="sinif"><i style="background:{sk[i]}"></i><span>{gosterim(kolon, a)}–{gosterim(kolon, b)}</span></div>'
        for i, (a, b) in enumerate(araliklar)
    )
    yon = T("yüksek = daha cazip", "higher = more attractive") if iyi_yuksek else T("düşük = daha cazip", "lower = more attractive")
    anahtar = (
        f'<div class="anahtar"><span><i style="background:{sk[1]};opacity:{YUKSEK_GUVEN_OPAKLIK}"></i>{T("Yüksek güven", "High confidence")}</span>'
        f'<span><i style="background:{sk[1]};opacity:{DUSUK_GUVEN_OPAKLIK}"></i>{T("Düşük güven (30 km içinde kalibre santral yok)", "Low confidence (no calibrated farm within 30 km)")}</span>'
        f'<span><i style="border-radius:50%;width:.6rem;height:.6rem;background:{r["yuzey"]};border:1.5px solid {r["metin"]}"></i>'
        f"{T('Kalibre RES santrali', 'Calibrated wind farm')}</span>"
        f'<span><i style="background:transparent;border:2.2px solid {r["metin"]}"></i>'
        f"{T('Üst sınıra yakın (RES KF gözlenen azaminin üstünde)', 'Near the upper bound (wind CF above the highest observed)')}</span>"
        f'<span><i style="background:transparent;border:2.2px dotted {TEMALAR[tema]["veri"]["batarya"]}"></i>'
        f"{T('Ada (denizaltı kablosu gerekir)', 'Island (submarine cable required)')}</span></div>"
    )
    birim_m = f"{birim}" if birim != "%" else "%"
    return (
        f'<div class="esik-lejant"><div><div class="baslik">{T(ad_tr, ad_en)}, {birim_m} '
        f'<span style="font-weight:400;color:var(--metin-soluk)">· {yon}</span></div><div class="siniflar">{kutu}</div></div>{anahtar}</div>'
    )


def nokta_haritasi(
    df: pd.DataFrame, renk: list[str], ipucu: list[str], tema: str = "acik", boyut: list[float] | None = None, cizgiler: list | None = None
) -> folium.Map:
    """v3 Faz F: sade altlık üzerinde nokta katmanı (portföy adayları, izlenen santraller). Renkler çağıran taraftan,
    yalnız tasarım belirteçlerinden (TEMALAR) verilir."""
    t = TEMALAR[tema]
    r = t["renk"]
    m = folium.Map(location=[39.0, 35.2], zoom_start=6, tiles=None, control_scale=True, prefer_canvas=True, min_zoom=5)
    m.fit_bounds([[35.8, 25.7], [42.1, 44.8]])
    m.get_root().header.add_child(folium.Element(_harita_css(r, t["yazi"], t["streamlit"] == "dark")))
    folium.TileLayer(BOS_KARO, attr="geoBoundaries · Natural Earth", name=T("Sade altlık", "Plain base map")).add_to(m)
    alt = _altlik()
    if alt is not None:
        folium.GeoJson(
            alt,
            control=False,
            interactive=False,
            style_function=lambda f: {
                "fillColor": r["kara"],
                "fillOpacity": 1 if f["properties"]["tur"] == "ulke" else 0,
                "color": r["sinir"],
                "weight": 0.7 if f["properties"]["tur"] == "il" else 0.9,
            },
        ).add_to(m)
    for c in cizgiler or []:
        folium.PolyLine(
            c["nokta"], color=c.get("renk", r["metin_soluk"]), weight=c.get("kalinlik", 1.5), opacity=0.7, dash_array="4 4"
        ).add_to(m)
    for i, rr in enumerate(df.itertuples()):
        folium.CircleMarker(
            [rr.enlem, rr.boylam],
            radius=(boyut[i] if boyut is not None else 6),
            color=r["yuzey"],
            weight=1.2,
            fill=True,
            fill_color=renk[i],
            fill_opacity=0.92,
            tooltip=ipucu[i],
        ).add_to(m)
    return m
