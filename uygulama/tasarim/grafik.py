"""
Ortak Plotly grafik şablonu: yazı tipi, renkler, eksen ve ızgara stili, başlık + açıklayıcı alt başlık, birimler, sade araç
çubuğu. Tüm grafikler `sekil()` ile biçimlenir ve `ciz()` ile çizilir.

- Sayfa kodu kanonik (açık tema) veri renklerini kullanır (tokenlar.VERI). Koyu temada `ciz()` iz, şekil ve açıklama
  renklerini aynı anahtardaki KOYU_VERI tonlarına çevirir; sayfa kodu tema bilmez.
- Arka plan, metin ve ızgara renkleri şablondan gelir; `sekil()` renk yazmaz.
- Sayı ayıraçları dile göre (TR 1.234,5 · EN 1,234.5).
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from uygulama.tasarim.tokenlar import KOYU_EK, KOYU_VERI, TEMALAR, VERI, rgba

ARAC_CUBUGU = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "select2d",
        "lasso2d",
        "autoScale2d",
        "zoomIn2d",
        "zoomOut2d",
        "toggleSpikelines",
        "hoverClosestCartesian",
        "hoverCompareCartesian",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "esik_grafik"},
}
_KOYU_ESLEME = {**KOYU_EK, **{VERI[k].lower(): KOYU_VERI[k] for k in VERI}}


def sablon(tema: str) -> go.layout.Template:
    t = TEMALAR[tema]
    r, y = t["renk"], t["yazi"]
    koyu = t["streamlit"] == "dark"
    eksen = dict(
        automargin=True,
        linecolor=r["cizgi"],
        tickcolor=r["cizgi"],
        ticks="outside",
        ticklen=4,
        zeroline=False,
        title=dict(font=dict(size=12, color=r["metin_soluk"]), standoff=8),
        tickfont=dict(family=f"{y['sayi']}, sans-serif", size=11.5, color=r["metin_soluk"]),
    )
    return go.layout.Template(
        layout=dict(
            font=dict(family=f"{y['arayuz']}, system-ui, sans-serif", size=12.5, color=r["metin_soluk"]),
            title=dict(
                font=dict(family=f"{y['arayuz']}, sans-serif", size=15, color=r["metin"]),
                x=0,
                xanchor="left",
                xref="container",
                pad=dict(l=4),
            ),
            paper_bgcolor=r["yuzey"],
            plot_bgcolor=r["yuzey"],
            colorway=[t["veri"][k] for k in ("res", "ges", "hibrit", "batarya", "koyu", "soluk")],
            xaxis=dict(**eksen, showgrid=False),
            yaxis=dict(**eksen, showgrid=True, gridcolor=r["cizgi"], griddash="dot" if koyu else "solid", gridwidth=1),
            legend=dict(
                orientation="h",
                x=0,
                xanchor="left",
                y=-0.2,
                yanchor="top",
                font=dict(size=12, color=r["metin_soluk"]),
                bgcolor="rgba(0,0,0,0)",
                itemclick="toggleothers",
            ),
            margin=dict(l=8, r=12, t=64, b=8),
            hoverlabel=dict(
                bgcolor=r["yuzey2"], bordercolor=r["cizgi"], font=dict(family=f"{y['sayi']}, sans-serif", color=r["metin"], size=12)
            ),
            hovermode="x unified",
            bargap=0.18,
            colorscale=dict(sequential=[[i / 5, c] for i, c in enumerate(t["harita_skala"])]),
        )
    )


def sekil(fig: go.Figure, baslik: str = "", y: str = "", x: str = "", yukseklik: int = 360, alt: str = "") -> go.Figure:
    """Başlık (+ açıklayıcı alt başlık), eksen başlıkları (birimleriyle) ve yükseklik. Renk yazmaz."""
    metin = baslik if not alt else f"{baslik}<br><span style='font-size:12px;font-weight:400'>{alt}</span>"
    fig.update_layout(title=dict(text=metin), height=yukseklik, margin=dict(t=74 if alt else 58))
    fig.update_xaxes(title_text=x)
    fig.update_yaxes(title_text=y)
    return fig


def _rgb(hex_: str) -> tuple[int, int, int]:
    return tuple(int(hex_.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))


_KOYU_RGB = {_rgb(VERI[k]): KOYU_VERI[k] for k in VERI}


def _cevir(deger):
    """Kanonik veri rengi (hex ya da rgba) → koyu tema tonu; diğer değerler aynen döner."""
    if isinstance(deger, str):
        d = deger.strip().lower()
        if d in _KOYU_ESLEME:
            return _KOYU_ESLEME[d]
        if d.startswith("rgba("):
            p = [x.strip() for x in d[5:-1].split(",")]
            koyu = _KOYU_RGB.get(tuple(int(float(x)) for x in p[:3]))
            return rgba(koyu, float(p[3])) if koyu else deger
        return deger
    if isinstance(deger, (list, tuple)):
        return [_cevir(v) for v in deger]
    return deger


def _koyu_renkler(fig: go.Figure) -> None:
    """Kanonik veri renklerini koyu tema tonlarına çevirir (iz çizgisi, işaretçi, dolgu; şekiller ve açıklamalar)."""
    for iz in fig.data:
        for yol in ("line.color", "marker.color", "marker.line.color", "fillcolor"):
            try:
                v = iz[yol]
            except (KeyError, ValueError, AttributeError):
                continue
            if v is not None:
                yeni = _cevir(v)
                if yeni != v:
                    iz[yol] = yeni
    for s in fig.layout.shapes or []:
        if s.line.color:
            s.line.color = _cevir(s.line.color)
        if s.fillcolor:
            s.fillcolor = _cevir(s.fillcolor)
    for an in fig.layout.annotations or []:
        if an.font.color:
            an.font.color = _cevir(an.font.color)


def dolgu(renk: str, saydamlik: float = 0.14) -> str:
    """Alan dolgusu için kanonik rengin saydam hali (koyu temada da kanonik tondan türetilir)."""
    return rgba(renk, saydamlik)


def ciz(fig: go.Figure, tema: str | None = None, dil: str | None = None, **kw) -> None:
    from uygulama.ortak import dil as aktif_dil
    from uygulama.tasarim.stil import aktif_tema

    tema = tema or aktif_tema()
    dil = dil or aktif_dil()
    sab = sablon(tema)
    # Streamlit ön yüzü, şablonda olsa bile üst düzeyde tanımsız arka plan/yazı alanlarını kendi temasıyla doldurur: açıkça yaz
    fig.update_layout(
        template=sab,
        separators=",." if dil == "TR" else ".,",
        paper_bgcolor=fig.layout.paper_bgcolor or sab.layout.paper_bgcolor,
        plot_bgcolor=fig.layout.plot_bgcolor or sab.layout.plot_bgcolor,
        font=dict(family=sab.layout.font.family, color=sab.layout.font.color),
    )
    if TEMALAR[tema]["streamlit"] == "dark":
        _koyu_renkler(fig)
    kw.setdefault("width", "stretch")
    st.plotly_chart(fig, theme=None, config={**ARAC_CUBUGU, **kw.pop("config", {})}, **kw)
