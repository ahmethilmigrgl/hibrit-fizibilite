"""
Aşama 5 — Bölüm B: Monte Carlo risk simülasyonu

Aday tasarımlar (outputs/05_risk/adaylar.json, Bölüm A'dan) ortak rastgele sayılarla (aynı senaryolarla)
değerlendirilir. İşletme büyüklükleri önceden hesaplanmış tablolardan ara değerlemeyle alınır
(src/risk/isletme.py); yaklaşım hatası birkaç simülasyonda tam LP çözümüyle ölçülür.

Çıktılar: outputs/05_risk/b_*.png, b_*.csv
Çalıştırma: .venv/bin/python src/05_monte_carlo.py  (Bölüm A'dan sonra)
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, deger
from src.finans.fiyat_senaryosu import _derinlik, _gunes_orani
from src.finans.veri import fiyat_sekil_yillari
from src.risk.degerleme import borc_boyutla, irr_vektor, nakit_akislari, ozkaynak
from src.risk.isletme import ALANLAR, IsletmeLP, Tasarim, birim_toplamlar
from src.risk.monte_carlo import ornekle

CIKTI = CIKTILAR / "05_risk"
KAYNAK = "Kaynak: kendi modelim (Monte Carlo, Pyomo + HiGHS işletme tabloları). Reel 2026 USD, %7 reel WACC."
RENK = {"A": g.RENK_RES, "B": g.RENK_GES, "C": "#7f6bd1", "D": g.RENK_HIBRIT, "E": "#1d4f91"}

spec = importlib.util.spec_from_file_location("gy", Path(__file__).parent / "05_gelir_yigini.py")
gy = importlib.util.module_from_spec(spec); spec.loader.exec_module(gy)


def log(*a):
    print(*a, flush=True)


def borc_deterministik(o, t, tb):
    """Bölüm A ile aynı: P90 CFADS (hava yılları dağılımından) → heykelsi borç."""
    cf = np.array([np.mean([nakit_akislari(t, tb, o.c, o.beklenen_girdi(w=(w, s)))["cfads"][0] for s in range(2)], axis=0)
                   for w in range(tb["T"].shape[0])])
    cfads_p90 = cf.mean(0) - 1.2816 * cf.std(0, ddof=1)
    r = nakit_akislari(t, tb, o.c, o.beklenen_girdi())
    pay = None
    if t.ppa:
        k = np.arange(1, o.v.omur + 1)
        ppa_gelir = np.where(k <= o.c.ppa_vade, o.c.ppa_pay * o.c.ppa_fiyat * (r["E_res"] + r["E_ges"])[0], 0)
        pay = np.clip(ppa_gelir / np.maximum(r["favok"][0], 1), 0, 1)
    return borc_boyutla(cfads_p90, float(r["capex_top"][0]), t, o.cfg, o.c, pay)


def metrikler(npv, irr, oz_irr, dscr_min, enerji):
    q = np.nanpercentile
    kotu = np.sort(npv)[: max(1, int(0.05 * len(npv)))]
    return {"Beklenen NPV [M USD]": npv.mean() / 1e6, "NPV P10 [M USD]": q(npv, 10) / 1e6, "NPV P50 [M USD]": q(npv, 50) / 1e6,
            "NPV P90 [M USD]": q(npv, 90) / 1e6, "P(NPV > 0) [%]": 100 * (npv > 0).mean(), "CVaR %5 [M USD]": kotu.mean() / 1e6,
            "Proje IRR P10 / P50 / P90 [%]": " / ".join(f"{100 * q(irr, p):.1f}" for p in (10, 50, 90)),
            "Proje IRR P50 [%]": 100 * q(irr, 50),
            "Öz kaynak IRR P10 / P50 / P90 [%]": " / ".join(f"{100 * q(oz_irr, p):.1f}" for p in (10, 50, 90)),
            "P(herhangi bir yılda DSCR < 1) [%]": 100 * (dscr_min < 1.0).mean(),
            "P(herhangi bir yılda DSCR < 1,2) [%]": 100 * (dscr_min < 1.2).mean(),
            "Enerji 1 yıl P50 [GWh]": q(enerji[:, 0], 50) / 1e3, "Enerji 1 yıl P90 [GWh]": q(enerji[:, 0], 10) / 1e3,
            "Enerji 10 yıl ort. P50 [GWh]": q(enerji[:, :10].mean(1), 50) / 1e3,
            "Enerji 10 yıl ort. P90 [GWh]": q(enerji[:, :10].mean(1), 10) / 1e3,
            "EVPI [M USD]": (np.maximum(npv, 0).mean() - max(npv.mean(), 0)) / 1e6}


def evppi(npv, surucu, kova=100):
    """Kısmi mükemmel bilgi değeri: E_θ[max(E[NPV|θ], 0)] − max(E[NPV], 0); E[NPV|θ] yüzdelik kovalarıyla."""
    sira = np.argsort(surucu)
    parcalar = np.array_split(npv[sira], kova)
    kosullu = np.array([p.mean() for p in parcalar])
    agirlik = np.array([len(p) for p in parcalar]) / len(npv)
    return float((agirlik * np.maximum(kosullu, 0)).sum() - max(npv.mean(), 0))


def birinci_derece(npv, surucu, kova=50):
    """Sobol birinci derece etkisi tahmini: Var(E[NPV|X]) / Var(NPV), yüzdelik kovalarıyla."""
    sira = np.argsort(surucu)
    parcalar = np.array_split(npv[sira], kova)
    kosullu = np.array([p.mean() for p in parcalar])
    return float(kosullu.var() / npv.var())


def tam_cozum_X(o, t, girdi, i):
    """Doğrulama: simülasyon i için her yılı tam (ara değerlemesiz) LP ile çöz → X (1, N, alan)."""
    sekil, _ = fiyat_sekil_yillari(*deger(o.cfg["fiyat_senaryolari"]["sekil_donemi"]))
    gn = o.u.ges.mean(axis=0); gn = gn / gn.max()
    lp = IsletmeLP(t, **o.sabit)
    k = np.arange(1, o.v.omur + 1)
    deg_r = (1 - o.v.degr_res) ** (k - 1)
    X = np.zeros((1, o.v.omur, len(ALANLAR)))
    for y in range(o.v.omur):
        w, s, h = girdi["w"][i, y], girdi["s"][i, y], girdi["h"][i, y]
        hedef = _gunes_orani(sekil[s], gn, 0.0) - (o.oran0 - h)
        q = sekil[s] * (1 - _derinlik(sekil[s], gn, hedef) * gn); q = q / q.mean()
        G = t.ges_mw * o.u.ges[w]
        A = G + t.res_mw * girdi["m"][i, y] * deg_r[y] * o.u.res[w]
        phi = o.c.ppa_pay if (t.ppa and k[y] <= o.c.ppa_vade) else 0.0
        r = lp.coz(A, 58.0 * q, girdi["a"][i, y] * o.yan[s], phi)
        X[0, y] = birim_toplamlar(r["y"], r["k"], r["c"], r["d"], r["r"], A, G, q, o.yan[s], 0.70)
    return X


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    o = gy.Ortam()
    adaylar = {k: Tasarim(**v) for k, v in json.loads((CIKTI / "adaylar.json").read_text()).items()}
    n = deger(o.cfg["monte_carlo"]["senaryo_sayisi"])
    ornek = ornekle(o.cfg, n, o.yillar, o.oran0, deger(o.cfg["monte_carlo"]["tohum"]))
    girdi, sur = ornek["girdi"], ornek["suruculer"]
    res_kf = o.u.res.mean(1)
    sur["Hava (ort. RES yılı)"] = res_kf[girdi["w"]].mean(1)
    log(f"{n} simülasyon örneklendi ({time.time() - t0:.0f} s)")

    sonuc, tablolar, satirlar = {}, {}, []
    for ad, t in adaylar.items():
        tb = o.tablo(t); tablolar[ad] = tb
        r = nakit_akislari(t, tb, o.c, girdi)
        irr = irr_vektor(r["sna"])
        borc = borc_deterministik(o, t, tb)
        oz = ozkaynak(r, borc, o.c)
        sonuc[ad] = {"npv": r["npv"], "irr": irr, "oz_irr": oz["irr"], "dscr_min": oz["dscr_min"], "enerji": r["satilan"],
                     "borc": borc}
        mt = metrikler(r["npv"], irr, oz["irr"], oz["dscr_min"], r["satilan"])
        mt["EVPPI fiyat [M USD]"] = evppi(r["npv"], sur["Fiyat yolu (iskontolu ort.)"]) / 1e6
        mt["Borç (P90) [M USD]"] = borc["borc_reel"] / 1e6; mt["Borç vadesi [yıl]"] = borc["vade"]
        satirlar.append({"Tasarım": ad, **mt})
        log(f"  {ad}: E[NPV] {mt['Beklenen NPV [M USD]']:.2f} | P(NPV>0) {mt['P(NPV > 0) [%]']:.1f}% | CVaR5 {mt['CVaR %5 [M USD]']:.1f} "
            f"| DSCR<1 {mt['P(herhangi bir yılda DSCR < 1) [%]']:.1f}% | EVPI {mt['EVPI [M USD]']:.2f} EVPPI {mt['EVPPI fiyat [M USD]']:.2f}")
    tablo = pd.DataFrame(satirlar)
    tablo.to_csv(CIKTI / "b_metrikler.csv", encoding="utf-8-sig", index=False, float_format="%.3f")

    # --- Varyans katkısı (birinci derece, kova yöntemi)
    katki = pd.DataFrame({ad: {k: 100 * birinci_derece(sonuc[ad]["npv"], v) for k, v in sur.items()} for ad in adaylar}).round(2)
    katki.to_csv(CIKTI / "b_varyans_katkisi.csv", encoding="utf-8-sig")
    log("\nVaryans katkısı [%]:\n" + katki.to_string())

    # --- Yaklaşım hatası: bataryalı tasarımda 5 simülasyon tam LP ile
    log("\nYaklaşım hatası ölçülüyor...")
    hata = []
    for ad in [a for a, t in adaylar.items() if t.bess_mw > 0.5][:2]:
        t = adaylar[ad]
        for i in [0, 1, 2, 3, 4]:
            X = tam_cozum_X(o, t, girdi, i)
            g1 = {k: (v[i:i + 1] if np.ndim(v) else v) for k, v in girdi.items()}
            tam = nakit_akislari(t, tablolar[ad], o.c, {**g1, "X": X})["npv"][0]
            hata.append({"Tasarım": ad, "Simülasyon": i, "NPV ara değerleme [M USD]": sonuc[ad]["npv"][i] / 1e6,
                         "NPV tam LP [M USD]": tam / 1e6, "Fark [M USD]": (sonuc[ad]["npv"][i] - tam) / 1e6})
    hata = pd.DataFrame(hata)
    hata.to_csv(CIKTI / "b_yaklasim_hatasi.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log(hata.round(2).to_string(index=False))

    pd.DataFrame({"yil": o.yillar, **{f"L P{p}": np.percentile(girdi["L"], p, axis=0) for p in (5, 25, 50, 75, 95)}}).to_csv(
        CIKTI / "b_fiyat_yolu_yuzdelik.csv", encoding="utf-8-sig", index=False, float_format="%.2f")
    grafikler(tablo, sonuc, girdi, katki, o, adaylar)
    log(f"Toplam süre {(time.time() - t0) / 60:.1f} dk")


# =============================================================================
def kisa(ad):
    return ad.split(":")[0]


def grafikler(tablo, sonuc, girdi, katki, o, adaylar):
    # 1) NPV histogram + CDF
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 4.8))
    for ad in sonuc:
        x = sonuc[ad]["npv"] / 1e6
        axs[0].hist(x, bins=80, histtype="step", lw=1.6, color=RENK[kisa(ad)], label=ad, density=True)
        xs = np.sort(x)
        axs[1].plot(xs, np.arange(1, len(xs) + 1) / len(xs), color=RENK[kisa(ad)], lw=2, label=ad)
    for a in axs:
        a.axvline(0, color=g.MUREKKEP, lw=0.8, ls="--")
        g.eksen_sade(a, izgara="both")
    axs[0].set_xlabel("NPV [M USD]"); axs[0].set_ylabel("Yoğunluk"); axs[0].set_title("NPV dağılımı", loc="left")
    axs[1].set_xlabel("NPV [M USD]"); axs[1].set_ylabel("Birikimli olasılık"); axs[1].set_title("Birikimli dağılım (sağdaki daha iyi)", loc="left")
    axs[1].legend(fontsize=7.5, loc="upper left")
    g.baslik(fig, "Monte Carlo: aday tasarımların NPV dağılımları", f"{len(x):,}".replace(",", ".") + " simülasyon, ortak rastgele sayılar")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_npv_dagilim_cdf.png"); plt.close(fig)

    # 2) Risk-getiri
    fig, ax = plt.subplots(figsize=(9, 5))
    for _, r in tablo.iterrows():
        ax.scatter(r["CVaR %5 [M USD]"], r["Beklenen NPV [M USD]"], s=120, color=RENK[kisa(r["Tasarım"])], edgecolor="white", lw=1.5, zorder=3)
        ax.annotate(f"{r['Tasarım']}\nP(NPV>0) %{r['P(NPV > 0) [%]']:.0f}", (r["CVaR %5 [M USD]"], r["Beklenen NPV [M USD]"]),
                    xytext=(-10, 4) if kisa(r["Tasarım"]) == "C" else (8, -4), ha="right" if kisa(r["Tasarım"]) == "C" else "left",
                    textcoords="offset points", fontsize=8, color=g.MUREKKEP)
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xlabel("CVaR %5: en kötü %5'in ortalama NPV'si [M USD] (sağ = daha az risk)")
    ax.set_ylabel("Beklenen NPV [M USD]")
    xl = ax.get_xlim(); ax.set_xlim(xl[0], xl[1] + (xl[1] - xl[0]) * 0.45)
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "Risk-getiri: sağ üst köşe hem daha kârlı hem daha güvenli", "Beklenen NPV ve kuyruk riski (CVaR %5)")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_risk_getiri.png"); plt.close(fig)

    # 3) Fiyat yolu fan grafiği
    fig, ax = plt.subplots(figsize=(10, 4.6))
    L = girdi["L"]; yil = o.yillar
    for a, b, alfa in [(5, 95, 0.15), (25, 75, 0.3)]:
        ax.fill_between(yil, np.percentile(L, a, 0), np.percentile(L, b, 0), color=g.RENK_RES, alpha=alfa, lw=0,
                        label=f"P{a}–P{b}")
    ax.plot(yil, np.percentile(L, 50, 0), color=g.RENK_RES, lw=2, label="Medyan")
    for i in range(4):
        ax.plot(yil, L[i], color=g.SOLUK, lw=0.8)
    ax.axhline(58, color=g.MUREKKEP, ls="--", lw=1); ax.text(yil[-1], 59, "baz 58", ha="right", fontsize=8)
    ax.set_ylabel("Yıllık ortalama PTF [USD/MWh, reel]"); ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(0, np.percentile(L, 99))
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "Fiyat yolları: ortalamaya dönen log-fiyat + kriz sıçramaları",
             "Gri: örnek yollar. Uzun dönem ortalaması simülasyon başına lognormal (medyan 58).")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_fiyat_yollari.png"); plt.close(fig)

    # 4) Enerji P50/P90 (1 ve 10 yıl)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(tablo)); w_ = 0.2
    for j, (kol, renk, et) in enumerate([("Enerji 1 yıl P50 [GWh]", g.SOLUK, "1 yıl P50"), ("Enerji 1 yıl P90 [GWh]", g.MUREKKEP, "1 yıl P90"),
                                         ("Enerji 10 yıl ort. P50 [GWh]", "#9ec5ef", "10 yıl P50"), ("Enerji 10 yıl ort. P90 [GWh]", g.RENK_RES, "10 yıl P90")]):
        c = ax.bar(x + (j - 1.5) * (w_ + 0.01), tablo[kol], w_, color=renk, label=et)
        ax.bar_label(c, fmt="%.0f", fontsize=6.5, padding=1)
    ax.set_xticks(x, [kisa(a) for a in tablo["Tasarım"]]); ax.set_ylabel("Satılan enerji [GWh/yıl]")
    ax.legend(fontsize=8, ncols=4, loc="upper center"); ax.set_ylim(0, tablo["Enerji 1 yıl P50 [GWh]"].max() * 1.2)
    g.eksen_sade(ax)
    g.baslik(fig, "1 yıllık ve 10 yıllık P50 / P90 enerji (hava + model belirsizliği)",
             "10 yıllık ortalamada hava dalgalanması söner, sistematik RES model hatası kalır.")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_enerji_p50_p90.png"); plt.close(fig)

    # 5) DSCR dağılımı
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for ad in sonuc:
        d = np.clip(sonuc[ad]["dscr_min"], 0, 3)
        xs = np.sort(d)
        ax.plot(xs, np.arange(1, len(xs) + 1) / len(xs), color=RENK[kisa(ad)], lw=2, label=f"{ad} (borç vadesi {sonuc[ad]['borc']['vade']} yıl)")
    ax.axvline(1.0, color="#c0392b", lw=1.2, ls="--"); ax.text(1.01, 0.02, "DSCR = 1 (temerrüt eşiği)", fontsize=8, color="#c0392b")
    ax.set_xlabel("Vade boyunca en düşük DSCR"); ax.set_ylabel("Birikimli olasılık")
    ax.legend(fontsize=7.5, loc="lower right")
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "Borç servisini karşılama oranı (DSCR): en kötü yıl dağılımı",
             "Borç P90 üretimle ve hedef DSCR ile deterministik boyutlandırıldı; simülasyonlarda nakit akışı değişiyor.")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_dscr_dagilimi.png"); plt.close(fig)

    # 6) Varyans katkısı
    fig, ax = plt.subplots(figsize=(10.5, 5))
    sira = katki.mean(1).sort_values().index
    y = np.arange(len(sira)); h_ = 0.15
    for j, ad in enumerate(katki.columns):
        ax.barh(y + (j - 2) * h_, katki.loc[sira, ad], h_, color=RENK[kisa(ad)], label=ad)
    ax.set_yticks(y, sira, fontsize=8.5); ax.set_xlabel("NPV varyansına birinci derece katkı [%]")
    ax.legend(fontsize=7.5, loc="lower right")
    g.eksen_sade(ax, izgara="x")
    g.baslik(fig, "Belirsizliğin kaynağı: NPV varyansına katkı",
             "Birinci derece Sobol etkisi (kova yöntemi): Var(E[NPV | X]) / Var(NPV)")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_varyans_katkisi.png"); plt.close(fig)

    # 7) Yakınsama
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.4))
    for ad in sonuc:
        x = sonuc[ad]["npv"] / 1e6
        i = np.arange(1, len(x) + 1)
        axs[0].plot(i, np.cumsum(x) / i, color=RENK[kisa(ad)], lw=1.5, label=kisa(ad))
        axs[1].plot(i, 100 * np.cumsum(x > 0) / i, color=RENK[kisa(ad)], lw=1.5)
    axs[0].set_xscale("log"); axs[1].set_xscale("log")
    axs[0].set_title("Kümülatif ortalama NPV [M USD]", loc="left"); axs[1].set_title("Kümülatif P(NPV > 0) [%]", loc="left")
    for a in axs:
        a.set_xlabel("Simülasyon sayısı (log)"); g.eksen_sade(a, izgara="both")
    axs[0].legend(fontsize=8)
    g.baslik(fig, "Yakınsama: ~3.000 simülasyondan sonra metrikler sabitleniyor", "Sabit tohum (42), ortak rastgele sayılar")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b_yakinsama.png"); plt.close(fig)


if __name__ == "__main__":
    main()
