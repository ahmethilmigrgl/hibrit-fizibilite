"""
Ortak grafik stili: renkler, sade eksenler ve kaynak notu.

Renkler doğrulanmış kategorik paletten gelir (GES = turuncu, RES = mavi, renk körlüğü
güvenli çift). Metin her zaman nötr mürekkep rengindedir, seri renginde değil.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RENK_GES = "#eb6834"
RENK_RES = "#2a78d6"
RENK_HIBRIT = "#1baf7a"
MUREKKEP = "#0b0b0b"
IKINCIL = "#52514e"
SOLUK = "#8a8984"
IZGARA = "#e4e3df"

KAYNAK_NOTU = (
    "Kaynak: PVGIS-SARAH3 (AB JRC), ERA5 (Copernicus/ECMWF). "
    "Model: pvlib (PVWatts), windpowerlib (Enercon E-141/4200, 120 m). Kendi hesaplamam."
)

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titlecolor": MUREKKEP,
        "axes.labelcolor": IKINCIL,
        "xtick.color": IKINCIL,
        "ytick.color": IKINCIL,
        "legend.frameon": False,
        "figure.dpi": 100,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    }
)


def eksen_sade(ax: plt.Axes, izgara: str = "y") -> None:
    """Üst/sağ çerçeveyi kaldırır, ızgarayı çekinik yapar."""
    for k in ("top", "right"):
        ax.spines[k].set_visible(False)
    for k in ("left", "bottom"):
        ax.spines[k].set_color(IZGARA)
    if izgara:
        ax.grid(axis=izgara, color=IZGARA, linewidth=0.8)
    ax.set_axisbelow(True)


def baslik(fig: plt.Figure, metin: str, alt: str | None = None) -> None:
    """Sol hizalı başlık ve isteğe bağlı alt başlık."""
    fig.suptitle(metin, x=0.01, ha="left", fontsize=12, color=MUREKKEP, fontweight="bold")
    if alt:
        fig.text(0.01, 0.935, alt, ha="left", va="top", fontsize=9, color=IKINCIL)


def kaynak_notu(fig: plt.Figure, metin: str = KAYNAK_NOTU) -> None:
    """Şeklin altına kaynak notu ekler."""
    fig.text(0.01, -0.01, metin, ha="left", va="top", fontsize=7, color=SOLUK)
