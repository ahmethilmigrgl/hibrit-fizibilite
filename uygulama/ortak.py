"""
Arayüz ortak öğeleri: dil ve sayı biçimi (TR ondalık virgül), palet, zorunlu uyarı bandı, veri atıfları, oturum başına istek
sınırı ve paylaşım bağlantısı (URL parametreleri). Kişisel veri toplanmaz: oturum durumunda yalnız seçilen nokta ve
varsayımlar tutulur.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ayarlar import config_oku, deger

# v1 dashboard paleti (renk körlüğü için doğrulanmış kategorik sıra) + harita için tek tonlu sıralı skala
RES, GES, HIBRIT, BATARYA, KOYU, SOLUK = "#2a78d6", "#eb6834", "#1baf7a", "#7f6bd1", "#1d4f91", "#8a8984"
# Başabaş fiyatı: düşük = iyi. Tek tonlu (mavi) sıralı skala, açıktan koyuya; renk körlüğünde sıralama korunur (viridis
# yerine v1 mavisiyle tutarlı). Koyu = düşük başabaş (daha cazip).
SIRALI = ["#08306b", "#1d4f91", "#2a78d6", "#5c9be3", "#9cc3ef", "#d7e7f8"]


def dil() -> str:
    return st.session_state.get("dil", "TR")


def T(tr: str, en: str) -> str:
    return tr if dil() == "TR" else en


def md(metin: str) -> str:
    """Markdown'a giden metinde $ işaretini kaçırır (iki $ arası LaTeX matematiği sanılmasın: 60 $/MWh / 92 $/MWh)."""
    return str(metin).replace("\\$", "$").replace("$", "\\$")


def sayi(x: float | None, d: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    x = float(x) + (5e-7 if x >= 0 else -5e-7)
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if dil() == "TR" else s


def yuzde(x: float | None, d: int = 0) -> str:
    """x oran (0–1) değil, yüzde değeri (ör. 33.9)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    return f"%{sayi(x, d)}" if dil() == "TR" else f"{sayi(x, d)}%"


def para(x: float | None, d: int = 1) -> str:
    return "–" if x is None else f"{sayi(x, d)} M$"


def fiyat(x: float | None, d: int = 0) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{sayi(x, d)} $/MWh"


def tablo(df: pd.DataFrame, **kw) -> None:
    def bicim(v: object) -> str:
        if isinstance(v, (float, np.floating)):
            return "–" if np.isnan(v) else sayi(v, 2)
        return str(v)

    st.dataframe(df.style.format(bicim), **kw)


def ciz(fig: go.Figure, **kw) -> None:
    fig.update_layout(separators=",." if dil() == "TR" else ".,")
    st.plotly_chart(fig, **kw)


def sekil(fig: go.Figure, baslik: str = "", y: str = "", x: str = "", yukseklik: int = 340) -> go.Figure:
    fig.update_layout(
        title=dict(text=baslik, x=0, font=dict(size=14)),
        height=yukseklik,
        margin=dict(l=10, r=10, t=44, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", y=-0.22),
        font=dict(family="Inter, Arial", size=12),
        hovermode="x unified",
    )
    fig.update_xaxes(title=x, showgrid=False, linecolor="#d0cfca")
    fig.update_yaxes(title=y, gridcolor="#ecebe7", zerolinecolor="#b9b8b2")
    return fig


def uyari_bandi() -> None:
    """Her sonuç ekranında: ön fizibilite aracıdır, yatırım tavsiyesi değildir."""
    st.warning(
        T(
            "**Bu bir ön fizibilite aracıdır, yatırım tavsiyesi değildir.** Arazi ve imar, izinler, türbinler arası iz (wake) "
            "etkisi, şebeke bağlantı kapasitesi ve yerel koşullar modellenmemiştir. Rüzgâr tahmini saha ölçümü yerine "
            "yeniden analiz verisi ve komşu santral kalibrasyonuna dayanır.",
            "**This is a pre-feasibility tool, not investment advice.** Land and zoning, permits, turbine wake effects, grid "
            "connection capacity and local conditions are not modelled. The wind estimate relies on reanalysis data and "
            "neighbouring wind-farm calibration rather than on-site measurement.",
        ),
        icon="⚠️",
    )


ATIFLAR_EN = (
    "Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is "
    "responsible for any use that may be made of the Copernicus information or data it contains. "
    "PVGIS © European Communities, 2001-2026 (PVGIS-SARAH3). "
    "Global Wind Atlas 3.0, a free, web-based application developed, owned and operated by the Technical University of "
    "Denmark (DTU), released in partnership with the World Bank Group, utilizing data provided by Vortex, using funding "
    "provided by the Energy Sector Management Assistance Program (ESMAP) — https://globalwindatlas.info (CC BY 4.0). "
    "Wind-farm locations © OpenStreetMap contributors (ODbL). Boundaries: geoBoundaries (Runfola et al. 2020), © OpenStreetMap "
    "contributors. Copernicus DEM GLO-90 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under "
    "COPERNICUS by the European Union and ESA; all rights reserved. Made with Natural Earth."
)


def altbilgi() -> None:
    st.divider()
    st.caption(
        ATIFLAR_EN
        + " "
        + T(
            "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr). Kod MIT lisanslı; veriler kaynaklarının koşullarına tabi "
            "(DATA_SOURCES.md). Gizlilik: kişisel veri toplanmaz (Yöntem sayfası).",
            "Source: EPİAŞ Transparency Platform (seffaflik.epias.com.tr). Code under MIT; data subject to their sources' terms "
            "(DATA_SOURCES.md). Privacy: no personal data is collected (see Method page).",
        )
    )


# --- Kötüye kullanım sınırları (config v2.uygulama)
def ayar() -> dict:
    return deger(config_oku()["v2"]["uygulama"])


def istek_izni(tur: str) -> tuple[bool, str]:
    """Oturum başına kayan pencereli istek sınırı: tur ∈ {'hizli', 'tam'}. (izin, mesaj)"""
    a = ayar()["istek_siniri"][tur]
    simdi = time.time()
    k = f"_istekler_{tur}"
    gecmis = [t for t in st.session_state.get(k, []) if simdi - t < a["pencere_s"]]
    if len(gecmis) >= a["azami"]:
        bekle = int(a["pencere_s"] - (simdi - gecmis[0])) // 60 + 1
        return False, T(
            f"Bu oturumda {a['pencere_s'] // 60} dakikada en fazla {a['azami']} {'hızlı tarama' if tur == 'hizli' else 'tam analiz'} "
            f"yapılabilir. Lütfen ~{bekle} dakika sonra tekrar deneyin.",
            f"At most {a['azami']} {'quick scans' if tur == 'hizli' else 'full analyses'} per {a['pencere_s'] // 60} minutes in a "
            f"session. Please try again in ~{bekle} minutes.",
        )
    gecmis.append(simdi)
    st.session_state[k] = gecmis
    return True, ""


# --- Paylaşım bağlantısı: yalnız yuvarlatılmış koordinat ve varsayılandan farklı varsayımlar
def paylasim_parametreleri(enlem: float, boylam: float, mod: str, farkli: dict) -> dict:
    p = {"enlem": f"{enlem:.3f}", "boylam": f"{boylam:.3f}", "mod": mod}
    p.update({k: str(v) for k, v in farkli.items()})
    return p
