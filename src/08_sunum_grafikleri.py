"""
Aşama 8 — sunum ve LinkedIn karuseli için grafikler (outputs/08/grafikler/).

Tüm sayılar model çıktılarından okunur (outputs/07/*.csv, *.npz); karar yolculuğundaki önceki aşamaların değerleri
o aşamaların dokümanlarındaki sonuçlardır (KARAR_YOLCULUGU listesinde kaynak dosyasıyla birlikte).
Grafikler başlıksızdır: mesaj başlığı slaytta/karusel sayfasında yazılır.

Çalıştırma: .venv/bin/python src/08_sunum_grafikleri.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

import src.gorsel as g
from src.ayarlar import CIKTILAR

CIKTI = CIKTILAR / "08" / "grafikler"
TURUNCU, MAVI, YESIL = g.RENK_GES, g.RENK_RES, g.RENK_HIBRIT
GRI = "#8a8984"

# (aşama, neyi değiştirdi, E[NPV] M$, karar, karar türü, kaynak)
KARAR_YOLCULUGU = [
    ("Aşama 4", "Deterministik:\nyalnız RES", -1.58, "Yatırım yapılamaz", "hayir", "docs/04 §4.1"),
    ("Aşama 5", "Batarya + SFK,\nMonte Carlo", 28.4, "Güçlü evet", "evet", "docs/05 B3 (C tasarımı)"),
    ("Aşama 6", "SFK doyum\nstres testi", 4.5, "Koşullu onay\n(PPA, aşamalı batarya)", "kosullu", "docs/05 stres testi (F2P)"),
    ("Aşama 7", "Takvim,\nsistem kesintisi", 2.1, "Koşullu onay\n(inşaata hazır + YEKDEM)", "kosullu", "docs/07 §takvim"),
    ("Tutarlılık 1", "YEKDEM'de\narbitraj yok", -11.4, "Yatırım önerilmez", "hayir", "docs/07 Güncelleme 1"),
    ("Tutarlılık 2", "YEKDEM opsiyonu,\nsürücü, takvim", 1.49, "Durum tespiti +\nsınırlı teklif", "teklif", "docs/07 Güncelleme 2"),
    ("Nihai", "Fiyat ortalaması\n(58 = beklenen)", None, "Rafa kaldır,\ntetikleyicileri izle", "raf", "outputs/07/baz_vaka.csv"),
    (
        "Düzeltme (v3)",
        "Sigorta + arazi\nçift sayımı yok",
        "duzeltilmis",
        "Durum tespiti +\n≤0,9 M$ teklif",
        "teklif",
        "outputs/07/v1_cift_sayim/baz_vaka.csv (docs/v1_duzeltme_notu.md)",
    ),
]
# kare (karusel) sürüm için kısa eksen ve karar etiketleri, aynı sırayla
KISA = [
    ("Aşama 4\nyalnız RES", "Hayır"),
    ("Aşama 5\n+ SFK", "Güçlü evet"),
    ("Aşama 6\nSFK doyumu", "Koşullu"),
    ("Aşama 7\ntakvim", "Koşullu"),
    ("Tutarlılık\nYEKDEM", "Hayır"),
    ("Tutarlılık 2\n3 düzeltme", "DD + teklif"),
    ("Nihai\nfiyat ort.", "Rafa kaldır"),
    ("Düzeltme\nçift sayım", "DD + teklif"),
]
TUR_RENK = {"hayir": TURUNCU, "evet": YESIL, "kosullu": YESIL, "teklif": MAVI, "raf": GRI}


def tr(x: float, fmt: str = "+.1f") -> str:
    """Türkçe sayı: ondalık virgül, gerçek eksi işareti."""
    return format(x, fmt).replace(".", ",").replace("-", "−")


def virgul_ekseni(ax, eksen: str = "y"):
    from matplotlib.ticker import FuncFormatter

    f = FuncFormatter(lambda v, _: format(v, "g").replace(".", ",").replace("-", "−"))
    (ax.yaxis if eksen == "y" else ax.xaxis).set_major_formatter(f)


def baz_vaka() -> pd.DataFrame:
    return pd.read_csv(CIKTILAR / "07" / "baz_vaka.csv")


def kaydet(fig, ad: str):
    CIKTI.mkdir(parents=True, exist_ok=True)
    fig.savefig(CIKTI / ad, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def karar_yolculugu(boyut=(12, 5.0), ad="karar_yolculugu.png", yazi=1.0, kisa: bool = False):
    nihai = float(baz_vaka().query("`Baz vaka` == True")["Beklenen NPV [M USD]"].iloc[0])
    dz = CIKTILAR / "07" / "v1_cift_sayim" / "baz_vaka.csv"
    duz = float(pd.read_csv(dz).query("`Baz vaka` == True")["Beklenen NPV [M USD]"].iloc[0]) if dz.exists() else np.nan
    v = [(a, n, nihai if e is None else (duz if e == "duzeltilmis" else e), k, t) for a, n, e, k, t, _ in KARAR_YOLCULUGU]
    v = [x_ for x_ in v if np.isfinite(x_[2])]
    if kisa:
        v = [(ks[0], None, e, ks[1], t) for (a, n, e, k, t), ks in zip(v, KISA)]
    x = np.arange(len(v))
    y = np.array([e for _, _, e, _, _ in v])
    fig, ax = plt.subplots(figsize=boyut)
    ax.plot(x, y, color=g.IZGARA, lw=2, zorder=1)
    ax.axhline(0, color=g.MUREKKEP, lw=0.9)
    for xi, (_a, _n, e, k, t) in zip(x, v):
        ax.scatter(xi, e, s=150 * yazi, color=TUR_RENK[t], edgecolor="white", linewidth=2, zorder=3)
        ust = e >= 0
        ax.annotate(
            tr(e) + " M$",
            (xi, e),
            xytext=(0, 12 if ust else -16),
            textcoords="offset points",
            ha="center",
            va="bottom" if ust else "top",
            fontsize=11 * yazi,
            fontweight="bold",
            color=g.MUREKKEP,
        )
        ax.annotate(
            k,
            (xi, e),
            xytext=(0, 32 if ust else -36),
            textcoords="offset points",
            ha="center",
            va="bottom" if ust else "top",
            fontsize=8.6 * yazi,
            color=g.IKINCIL,
            linespacing=1.15,
        )
    ax.set_xticks(x, [a if n is None else f"{a}\n{n}" for a, n, *_ in v], fontsize=8.6 * yazi, color=g.IKINCIL, linespacing=1.2)
    ax.set_ylabel("Beklenen NPV [M USD]", fontsize=9 * yazi)
    ax.set_ylim(-24, 40)
    ax.set_xlim(-0.5, len(v) - 0.5)
    g.eksen_sade(ax)
    for t, etiket in [
        ("evet", "Yatırım onayı (koşulsuz/koşullu)"),
        ("hayir", "Yatırım önerilmez"),
        ("teklif", "Durum tespiti + sınırlı teklif"),
        ("raf", "Rafa kaldır, izle"),
    ]:
        ax.scatter([], [], s=80, color=TUR_RENK[t], label=etiket)
    ax.legend(loc="upper right", fontsize=8.6 * yazi, ncol=4, bbox_to_anchor=(1, 1.08))
    ax.tick_params(axis="y", labelsize=8.6 * yazi)
    kaydet(fig, ad)


def gelir_yapilari(boyut=(12, 4.6), ad="gelir_yapilari.png", yazi=1.0):
    df = baz_vaka().iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=boyut)
    y = np.arange(len(df))
    renk = [MAVI if b else (GRI if e < 0 else YESIL) for b, e in zip(df["Baz vaka"], df["Beklenen NPV [M USD]"])]
    ax.hlines(y, df["NPV P10 [M USD]"], df["NPV P90 [M USD]"], color=g.IZGARA, lw=6 * yazi, zorder=1)
    ax.scatter(df["Beklenen NPV [M USD]"], y, s=130 * yazi, color=renk, edgecolor="white", linewidth=2, zorder=3)
    for yi, r in df.iterrows():
        ax.annotate(
            f"{tr(r['Beklenen NPV [M USD]'])}  ·  P(NPV>0) %{r['P(NPV > 0) [%]']:.0f}",
            (r["NPV P90 [M USD]"], yi),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9 * yazi,
            color=g.MUREKKEP,
            fontweight="bold" if r["Baz vaka"] else "normal",
        )
    ax.set_yticks(y, [s + ("  (baz vaka)" if b else "") for s, b in zip(df["Senaryo"], df["Baz vaka"])], fontsize=9 * yazi)
    ax.axvline(0, color=g.MUREKKEP, lw=0.9)
    ax.set_xlabel("NPV [M USD] — nokta: beklenen değer, çubuk: P10–P90", fontsize=9 * yazi)
    ax.set_xlim(-26, 38)
    ax.tick_params(axis="x", labelsize=8.6 * yazi)
    g.eksen_sade(ax, izgara="x")
    virgul_ekseni(ax, "x")
    kaydet(fig, ad)


def selale(boyut=(12, 4.6), ad="baz_vaka_selale.png", yazi=1.0):
    s = pd.read_csv(CIKTILAR / "07" / "baz_vaka_duzeltmeler.csv")
    bas = s["Beklenen NPV [M USD]"].iloc[0]
    adim = s["Adımın katkısı (E[NPV]) [M USD]"].iloc[1:].to_numpy()
    etiket = [
        "Önceki baz vaka\n(YEKDEM 10 yıl sabit)",
        "YEKDEM her yıl\nseçilebilen opsiyon",
        "Ortak batarya\nsürücüsü",
        "İnşaata hazır\ntakvim",
        "Düzeltilmiş\nbaz vaka",
    ]
    fig, ax = plt.subplots(figsize=boyut)
    kum = bas
    ax.bar(0, bas, color=TURUNCU, width=0.6)
    for i, d in enumerate(adim, start=1):
        ax.bar(i, d, bottom=kum, color=YESIL if d >= 0 else TURUNCU, width=0.6)
        ax.text(i, kum + d + 0.6, tr(d, "+.2f"), ha="center", va="bottom", fontsize=10 * yazi, color=g.MUREKKEP)
        kum += d
    son = s["Beklenen NPV [M USD]"].iloc[-1]
    ax.bar(len(etiket) - 1, son, color=MAVI, width=0.6)
    ax.text(0, bas - 0.6, tr(bas), ha="center", va="top", fontsize=10 * yazi, fontweight="bold")
    ax.text(len(etiket) - 1, son + 0.6, tr(son), ha="center", va="bottom", fontsize=10 * yazi, fontweight="bold")
    ax.axhline(0, color=g.MUREKKEP, lw=0.9)
    ax.set_xticks(range(len(etiket)), etiket, fontsize=9 * yazi)
    ax.set_ylabel("Beklenen NPV [M USD]", fontsize=9 * yazi)
    ax.set_ylim(-14, 5)
    g.eksen_sade(ax)
    virgul_ekseni(ax)
    kaydet(fig, ad)


def cod_dagilimi(boyut=(12, 4.4), ad="cod_dagilimi.png", yazi=1.0):
    z = np.load(CIKTILAR / "07" / "takvim_cod_ornekleri.npz")
    bas = pd.Timestamp("2026-10-01")
    takvim = pd.read_csv(CIKTILAR / "07" / "takvim_ozet.csv")
    takvim = (
        takvim[takvim["Politika"].str.startswith("B1")]
        .assign(k=lambda d: d["Proje olgunluğu"].str.split(" \\(").str[0].str.replace(" proje", ""))
        .set_index("k")
    )
    fig, ax = plt.subplots(figsize=boyut)
    for anahtar, renk, ad_ in [
        ("insaata_hazir_B1_cod", MAVI, "İnşaata hazır proje"),
        ("gelistirme_B1_cod", TURUNCU, "Geliştirme (ön lisans devri)"),
    ]:
        ay = np.sort(z[anahtar])
        tarih = bas + pd.to_timedelta(ay * 30.4375, unit="D")
        ax.plot(tarih, np.arange(1, len(ay) + 1) / len(ay), color=renk, lw=2.2, label=ad_)
        p50 = bas + pd.to_timedelta(np.percentile(ay, 50) * 30.4375, unit="D")
        etiket = takvim.loc[ad_.split(" (")[0].replace(" proje", ""), "RES COD P50"]  # tablo ile aynı ay etiketi
        ax.annotate(
            f"P50 {etiket[5:]}/{etiket[:4]}",
            (p50, 0.5),
            xytext=(-8, 8),
            textcoords="offset points",
            ha="right",
            fontsize=9 * yazi,
            color=g.MUREKKEP,
        )
        ax.scatter([p50], [0.5], color=renk, s=40, zorder=3)
    sinir = pd.Timestamp("2030-12-31")
    ax.axvline(sinir, color=g.MUREKKEP, lw=1, ls="--")
    ax.text(sinir, 1.04, "YEKDEM için son COD: 31.12.2030", fontsize=9 * yazi, color=g.MUREKKEP, va="bottom", ha="center")
    ax.set_ylabel("Birikimli olasılık", fontsize=9 * yazi)
    ax.set_xlabel("Ticari işletme tarihi (COD)", fontsize=9 * yazi)
    ax.legend(loc="upper left", fontsize=9 * yazi)
    ax.tick_params(labelsize=8.6 * yazi)
    g.eksen_sade(ax)
    virgul_ekseni(ax)
    kaydet(fig, ad)


def bilgi_degeri(boyut=(12, 4.2), ad="dd_bilgi_degeri.png", yazi=1.0):
    b = pd.read_csv(CIKTILAR / "07" / "durum_tespiti_bilgi_degeri.csv", index_col=0)["değer"]
    kalem = [
        ("TEİAŞ SFK ön yeterliliği", b.filter(like="TEİAŞ").iloc[0]),
        ("Yatırım teşvik belgesi", b.filter(like="teşvik").iloc[0]),
        ("Ornitoloji", b.filter(like="ornitoloji").iloc[0]),
        ("YEKDEM endeksleme hukuki görüşü¹", 0.0),
        ("COD / türbin slotu teyidi¹", 0.0),
    ][::-1]
    fig, ax = plt.subplots(figsize=boyut)
    y = np.arange(len(kalem))
    ax.barh(y, [d for _, d in kalem], color=MAVI, height=0.55)
    for yi, (_, d) in zip(y, kalem):
        ax.text(d + 0.01, yi, f"{d:.2f} M$".replace(".", ","), va="center", fontsize=9.5 * yazi, color=g.MUREKKEP)
    tavan = b.filter(like="tavanı").iloc[0]
    ax.set_yticks(y, [k for k, _ in kalem], fontsize=9.5 * yazi)
    ax.set_xlabel("Kısmi bilgi değeri (EVPPI) [M USD]", fontsize=9 * yazi)
    ax.set_xlim(0, 0.62)
    ax.text(
        0.62,
        0.5,
        f"Toplam = bütçe tavanı {tr(tavan, '.2f')} M\\$ · talep edilen bütçe 0,5 M\\$\n"
        "¹ al/alma kararını değiştirmez; teklif fiyatı ve FID için gerekli",
        ha="right",
        va="center",
        fontsize=8.6 * yazi,
        color=g.IKINCIL,
    )
    ax.tick_params(axis="x", labelsize=8.6 * yazi)
    g.eksen_sade(ax, izgara="x")
    virgul_ekseni(ax, "x")
    kaydet(fig, ad)


def kopru(boyut=(7.6, 5.0), ad="kopru.png", yazi=1.3):
    """Deterministik baz → Monte Carlo köprüsü: bileşen katkıları, fiyat ortalaması düzeltmesi sonrası (çubuk) ve öncesi (nokta)."""
    on, so = (pd.read_csv(CIKTILAR / "07" / f"fark_ayristirma_{e}.csv") for e in ("once", "sonra"))
    kisa = [
        "Deterministik baz (58 sabit)",
        "(i) Fiyat ortalaması",
        "(iii) Oynaklık: batarya",
        "(iv) Oynaklık: vergi vb.",
        "(iv) Kriz tavanı",
        "(ii) YEKDEM opsiyonu",
        "(iii) SFK senaryoları",
        "(v) Hava, kesinti",
        "(iv) CAPEX/OPEX",
        "Takvim (COD)",
        "Monte Carlo E[NPV]",
    ]
    k = "E[NPV] katkısı [M USD]"
    fig, ax = plt.subplots(figsize=boyut)
    y = np.arange(len(so))[::-1]
    renk = [GRI] + [YESIL if d >= 0 else TURUNCU for d in so[k].iloc[1:-1]] + [MAVI]
    ax.barh(y, so[k], color=renk, height=0.6)
    ax.scatter(on[k], y, s=40 * yazi, facecolor="white", edgecolor=g.MUREKKEP, zorder=3, label="Düzeltme öncesi (58 = medyan)")
    fig.legend(
        handles=[
            Patch(color=g.IKINCIL, label="Düzeltme sonrası (58 = beklenen değer)"),
            plt.Line2D([], [], ls="", marker="o", mfc="white", mec=g.MUREKKEP, label="Düzeltme öncesi (58 = medyan)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.0),
        ncol=2,
        fontsize=8.2 * yazi,
    )
    for yi, d, d0 in zip(y, so[k], on[k]):
        etk = tr(d, "+.2f") + (f"  (önce {tr(d0, '+.2f')})" if abs(d - d0) > 0.3 else "")
        sag = d >= 0 or d0 > 0  # işaret değiştiyse etiket sağda (eksen etiketleriyle çakışmasın)
        ax.text(
            (max(d, d0) + 0.2) if sag else (min(d, d0) - 0.2),
            yi,
            etk,
            va="center",
            ha="left" if sag else "right",
            fontsize=8.5 * yazi,
            color=g.MUREKKEP,
        )
    ax.set_yticks(y, kisa, fontsize=8.6 * yazi)
    ax.axvline(0, color=g.MUREKKEP, lw=0.9)
    ax.set_xlim(-4.2, 7.2)
    ax.set_xlabel("Katkı [M USD]", fontsize=9 * yazi)
    ax.tick_params(axis="x", labelsize=8.6 * yazi)
    g.eksen_sade(ax, izgara="x")
    virgul_ekseni(ax, "x")
    kaydet(fig, ad)


def main():
    karar_yolculugu()
    gelir_yapilari()
    selale()
    cod_dagilimi()
    bilgi_degeri()
    bilgi_degeri(boyut=(7.6, 5.0), ad="dd_bilgi_degeri_dar.png", yazi=1.3)  # sunumda yan metinle
    kopru()
    print(f"Kaydedildi: {CIKTI}")


if __name__ == "__main__":
    main()
