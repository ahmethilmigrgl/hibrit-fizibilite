"""
Ön tarama haritası (folium). Hücreler 0,25° dikdörtgenler (tek GeoJSON katmanı); renk tek tonlu sıralı skala (koyu = daha
cazip; renk körlüğünde sıralama korunur). Düşük güvenli hücreler soluk dolgu + kesikli kenarla ayrılır. Kalibre santraller
ayrı, açılıp kapatılabilir katman. Altlık harita OpenStreetMap karoları (© OpenStreetMap katkıcıları; anahtarsız, yerel kullanım için — herkese açık yayında OSM karo kullanım politikası nedeniyle bir karo sağlayıcısı seçilmeli).
"""

from __future__ import annotations

import folium
import numpy as np
import pandas as pd

from uygulama.ortak import SIRALI, T, sayi, yuzde

# katman: (sütun, TR ad, EN ad, birim, yüksek değer iyi mi)
KATMANLAR = {
    "basabas_en_iyi": ("En iyi tasarımın başabaş fiyatı", "Break-even price of the best design", "$/MWh", False),
    "basabas_res": ("RES başabaş fiyatı", "Wind break-even price", "$/MWh", False),
    "basabas_ges": ("GES başabaş fiyatı", "Solar break-even price", "$/MWh", False),
    "res_kf": ("RES kapasite faktörü", "Wind capacity factor", "%", True),
    "ges_kf": ("GES kapasite faktörü", "Solar capacity factor", "%", True),
}
DUSUK_GUVEN_OPAKLIK, YUKSEK_GUVEN_OPAKLIK = 0.30, 0.72


def siniflar(v: pd.Series, iyi_yuksek: bool) -> tuple[np.ndarray, list[float]]:
    """6 sınıf (eşit yüzdelikler); sınıf 0 = en cazip (en koyu)."""
    q = np.nanquantile(v, np.linspace(0, 1, len(SIRALI) + 1))
    s = np.clip(np.searchsorted(q[1:-1], v, side="right"), 0, len(SIRALI) - 1)
    return (len(SIRALI) - 1 - s if iyi_yuksek else s), q.tolist()


def gosterim(kolon: str, x: float) -> str:
    return yuzde(100 * x, 1) if kolon.endswith("_kf") else sayi(x, 0)


def harita(
    ot: pd.DataFrame | None,
    kolon: str,
    santral: pd.DataFrame | None = None,
    secim: tuple[float, float] | None = None,
    aday: pd.DataFrame | None = None,
    turbinler: list | None = None,
    merkez: tuple[float, float] = (39.0, 35.2),
    zoom: int = 6,
) -> folium.Map:
    m = folium.Map(location=list(merkez), zoom_start=zoom, tiles="OpenStreetMap", control_scale=True, prefer_canvas=True)
    if ot is not None and len(ot):
        ad_tr, ad_en, birim, iyi_yuksek = KATMANLAR[kolon]
        v = ot[kolon].astype(float)
        sinif, _ = siniflar(v, iyi_yuksek)
        ozellik = []
        for r, c in zip(ot.itertuples(), sinif, strict=True):
            e, b = r.hucre_enlem, r.hucre_boylam
            dusuk = r.guven != "yüksek"
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
                        "renk": SIRALI[int(c)],
                        "dusuk": bool(dusuk),
                        "yer": f"{r.il} / {r.ilce}",
                        "deger": f"{T(ad_tr, ad_en)}: {gosterim(kolon, getattr(r, kolon))} {'' if birim == '%' else birim}",
                        "res": f"RES KF {gosterim('res_kf', r.res_kf)} · GES KF {gosterim('ges_kf', r.ges_kf)}",
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
                "color": "#52514e" if f["properties"]["dusuk"] else f["properties"]["renk"],
                "weight": 0.8 if f["properties"]["dusuk"] else 0.4,
                "dashArray": "3 3" if f["properties"]["dusuk"] else None,
            },
            tooltip=folium.GeoJsonTooltip(fields=["yer", "deger", "res", "guven"], labels=False),
        ).add_to(m)
    if santral is not None and len(santral):
        fg = folium.FeatureGroup(name=T("Kalibre RES santralleri", "Calibrated wind farms"), show=True)
        for r in santral.itertuples():
            folium.CircleMarker(
                [r.enlem, r.boylam],
                radius=4,
                color="#0b0b0b",
                weight=1,
                fill=True,
                fill_color="#ffffff",
                fill_opacity=1,
                tooltip=f"{r.ad} · {T('gözlenen KF', 'observed CF')} {gosterim('res_kf', r.gozlenen_kf)} · {r.turbin}",
            ).add_to(fg)
        fg.add_to(m)
    if aday is not None and len(aday):
        fg = folium.FeatureGroup(name=T("Aday noktalar", "Candidate points"))
        for i, r in enumerate(aday.itertuples(), 1):
            folium.Marker(
                [r.enlem, r.boylam],
                tooltip=f"{T('Aday', 'Candidate')} {i}: GWA {sayi(r.gwa_1km, 1)} m/s",
                icon=folium.DivIcon(
                    html=f'<div style="background:#1d4f91;color:#fff;border-radius:50%;width:22px;height:22px;'
                    f'text-align:center;line-height:22px;font:600 12px Arial;border:2px solid #fff">{i}</div>',
                    icon_size=(22, 22),
                    icon_anchor=(11, 11),
                ),
            ).add_to(fg)
        fg.add_to(m)
    if turbinler:
        fg = folium.FeatureGroup(name=T("Türbin yerleşimi (GWA en rüzgârlı hücreler)", "Turbine layout (windiest GWA cells)"))
        for e, b in turbinler:
            folium.CircleMarker([e, b], radius=2.5, color="#1baf7a", fill=True, fill_opacity=1, weight=0).add_to(fg)
        fg.add_to(m)
    if secim is not None:
        folium.Marker(list(secim), tooltip=T("Seçilen nokta", "Selected point"), icon=folium.Icon(color="red", icon="star")).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def lejant(ot: pd.DataFrame | None, kolon: str) -> str:
    """Markdown/HTML lejant: sınıf eşikleri + güven gösterimi."""
    if ot is None or not len(ot):
        return ""
    ad_tr, ad_en, birim, iyi_yuksek = KATMANLAR[kolon]
    _, q = siniflar(ot[kolon].astype(float), iyi_yuksek)
    araliklar = [(q[i], q[i + 1]) for i in range(len(SIRALI))]
    if iyi_yuksek:
        araliklar = araliklar[::-1]
    kutu = "".join(
        f'<span style="display:inline-block;margin:2px 8px 2px 0"><span style="display:inline-block;width:14px;height:14px;'
        f'background:{SIRALI[i]};vertical-align:middle;margin-right:4px"></span>{gosterim(kolon, a)}–{gosterim(kolon, b)}</span>'
        for i, (a, b) in enumerate(araliklar)
    )
    guven = (
        f'<span style="display:inline-block;margin-left:6px"><span style="display:inline-block;width:14px;height:14px;'
        f'background:{SIRALI[2]};opacity:{DUSUK_GUVEN_OPAKLIK};border:1px dashed #52514e;vertical-align:middle;margin-right:4px">'
        f"</span>{T('düşük güven (30 km içinde kalibre santral yok)', 'low confidence (no calibrated farm within 30 km)')}</span>"
    )
    return (
        f'<div style="font-size:12px;line-height:1.6"><b>{T(ad_tr, ad_en)}</b> ({birim}; {T("koyu = daha cazip", "dark = more attractive")})<br>'
        f"{kutu}{guven}</div>"
    )
