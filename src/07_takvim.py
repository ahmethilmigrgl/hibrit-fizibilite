"""
Aşama 7 — 4. Proje takvimi ve takvim riski (CPM + Monte Carlo)

Aktivite ağı: geliştirme kararından (Ekim 2026, t = 0) ticari işletmeye (COD) kadar. Süreler ay, üçgen (iyimser, olası,
kötümser) — gerekçeler docs/07 §4 ve config.yaml → takvim. Öncelikler bitiş-başlangıç (FS).

1. CPM: olası sürelerle ileri/geri geçiş → ES, EF, LS, LF, bolluk, kritik yol.
2. Monte Carlo (10.000): COD dağılımı (P50/P80/P90), kritiklik indeksi (aktivitenin o iterasyonun kritik yolunda olma
   olasılığı), Spearman duyarlılığı (süre ↔ COD).
3. Batarya politikaları: (B1) RES ile birlikte sipariş, (B2) FID'den 12 ay sonra sipariş (Aşama 6 koşulu),
   (B3) erken/bağımsız batarya (lisans + bağlantı anlaşmasından sonra ayrı öz kaynakla, şebeke bağlantısı öne çekilir).
4. Finansal bağlantı: finansal model COD = Ocak 2028 (t = 15 ay) varsayıyor. RES gecikmesi ve SFK başlangıç gecikmesi
   (yıl), doyum + kesinti dahil Monte Carlo erteleme eğrilerinden (outputs/07/erteleme_kesintili.csv) NPV'ye çevrilir:
   NPV ≈ NPV_E(d_RES) + [NPV_F2P(d_SFK) − NPV_E(d_SFK)]   (RES+PPA kısmı + bataryanın artımsal değeri).

Çıktılar: outputs/07/takvim_*.csv, takvim_gantt.png, takvim_cod.png, takvim_kritiklik.png
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src import gorsel as g
from src.ayarlar import CIKTILAR, config_oku, deger
from src.risk.monte_carlo import ucgen_ters

CIKTI = CIKTILAR / "07"
KAYNAK = "Kaynak: kendi modelim (CPM + Monte Carlo). Süreler: Enerjisa YEKA RES-2 ÇSED özetleri (DFC), EPDK/ÇED mevzuatı, sektör kaynakları; bkz. docs/07."
T0 = pd.Timestamp("2026-10-01")
MODEL_COD_AY = 15  # finansal model: Ocak 2028


def log(*a):
    print(*a, flush=True)


HAZIR = ["OLC", "KUS", "CED", "IMR", "LIS", "TBA"]  # inşaata hazır projede tamamlanmış (bağlantı anlaşması lisans öncesi imzalanır)


def ag(cfg, politika: str, olgunluk: str = "gelistirme") -> pd.DataFrame:
    a = pd.DataFrame(deger(cfg["takvim"])["aktiviteler"]).T
    a["onc"] = a["onc"].apply(lambda x: list(x) if x else [])
    a["gecikme"] = 0.0
    if olgunluk == "insaata_hazir":  # ÇED, imar, lisans, ölçüm tamam; yalnız devir + anlaşmalar + finansman
        for k in HAZIR:
            a.loc[k, ["a", "m", "b"]] = [0.0, 0.0, 0.0]
        a.loc["ONL", "ad"] = "Proje devri (inşaata hazır, EPDK onayı)"
    if politika == "B2":
        a.loc["BAT", "gecikme"] = 12.0  # FID'den 12 ay sonra sipariş
    if politika == "B3":  # erken batarya: ayrı karar, bağlantı öne çekilir
        a.loc["BKF"] = pd.Series(
            {"ad": "Batarya ayrı yatırım kararı (öz kaynak)", "a": 1, "m": 2, "b": 3, "onc": ["LIS", "TBA"], "gecikme": 0.0}
        )
        a.at["BAT", "onc"] = ["BKF"]
        a.at["SEB", "onc"] = ["TBA", "BKF"]
    a["gecikme"] = a["gecikme"].fillna(0.0)
    return a


def topolojik(a: pd.DataFrame) -> list:
    sira, kalan = [], set(a.index)
    while kalan:
        hazir = [k for k in a.index if k in kalan and all(p not in kalan for p in a.loc[k, "onc"])]
        sira += hazir
        kalan -= set(hazir)
    return sira


def ileri(a, sure, sira):
    """sure: dict aktivite → (n,) dizisi. Döndürür ES, EF (dict) ve her aktivitenin belirleyici öncülü."""
    ES, EF, belirleyen = {}, {}, {}
    for k in sira:
        onc = a.loc[k, "onc"]
        if onc:
            M = np.stack([EF[p] for p in onc])
            ES[k] = M.max(0) + a.loc[k, "gecikme"]
            belirleyen[k] = np.array(onc)[M.argmax(0)]
        else:
            ES[k] = np.zeros_like(sure[k]) + a.loc[k, "gecikme"]
            belirleyen[k] = np.full(len(sure[k]), None)
        EF[k] = ES[k] + sure[k]
    return ES, EF, belirleyen


def kritik_iz(belirleyen, son, n):
    """Her iterasyonda son aktiviteden geriye belirleyici öncülleri izleyerek kritik yol kümesi (n × aktivite bool)."""
    yol = {k: np.zeros(n, bool) for k in belirleyen}
    akt = np.full(n, son, dtype=object)
    for _ in range(len(belirleyen)):
        for k in belirleyen:
            m = akt == k
            yol[k] |= m
        akt = np.array([belirleyen[x][i] if x is not None else None for i, x in enumerate(akt)], dtype=object)
        if all(x is None for x in akt):
            break
    return yol


def cpm(a):
    sira = topolojik(a)
    sure = {k: np.array([float(a.loc[k, "m"])]) for k in a.index}
    ES, EF, _bel = ileri(a, sure, sira)
    son_t = max(EF[k][0] for k in a.index)
    LF, LS = {}, {}
    for k in reversed(sira):
        ard = [j for j in a.index if k in a.loc[j, "onc"]]
        LF[k] = min([LS[j] - a.loc[j, "gecikme"] for j in ard]) if ard else son_t
        LS[k] = LF[k] - sure[k][0]
    df = pd.DataFrame(
        {
            "Aktivite": a["ad"],
            "İyimser": a["a"],
            "Olası": a["m"],
            "Kötümser": a["b"],
            "Öncüller": a["onc"].apply(lambda x: ", ".join(x)),
            "ES": [ES[k][0] for k in a.index],
            "EF": [EF[k][0] for k in a.index],
            "LS": [LS[k] for k in a.index],
            "LF": [LF[k] for k in a.index],
        },
        index=a.index,
    )
    df["Bolluk"] = (df["LS"] - df["ES"]).round(2)
    df["Kritik"] = df["Bolluk"] <= 1e-6
    return df, sira


def monte_carlo(a, sira, n, tohum):
    rng = np.random.default_rng(tohum)
    sure = {
        k: (
            ucgen_ters(rng.random(n), float(a.loc[k, "a"]), float(a.loc[k, "m"]), float(a.loc[k, "b"]))
            if float(a.loc[k, "b"]) > float(a.loc[k, "a"])
            else np.full(n, float(a.loc[k, "m"]))
        )
        for k in a.index
    }
    ES, EF, bel = ileri(a, sure, sira)
    return sure, ES, EF, bel


def egri(ert, onek, d):
    """Erteleme eğrisi (0-3 yıl; ötesi son eğimle doğrusal)."""
    kol = [k for k in ert.index if k.startswith(onek) and "kesintisiz" not in k][0]
    x = np.array(ert.columns, float)
    y = ert.loc[kol].to_numpy(float)
    return np.where(d <= x[-1], np.interp(np.clip(d, 0, None), x, y), y[-1] + (y[-1] - y[-2]) * (d - x[-1]))


def npv_eslestir(d_res, d_sfk, ert):
    """Erteleme eğrisinden (0-3 yıl; ötesi son eğimle doğrusal) NPV."""
    x = np.array(ert.columns, float)

    def f(kol, d):
        y = ert.loc[kol].to_numpy(float)
        egim = y[-1] - y[-2]
        return np.where(d <= x[-1], np.interp(np.clip(d, 0, None), x, y), y[-1] + egim * (d - x[-1]))

    E = [k for k in ert.index if k.startswith("E:")][0]
    F = [k for k in ert.index if k.startswith("F2P") and "kesintisiz" not in k][0]
    return f(E, d_res) + (f(F, d_sfk) - f(E, d_sfk))


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    n = deger(cfg["monte_carlo"]["senaryo_sayisi"])
    tohum = deger(cfg["monte_carlo"]["tohum"])
    ert = pd.read_csv(CIKTI / "erteleme_kesintili.csv", index_col=0)
    ert.columns = ert.columns.astype(int)

    sonuc, ozet = {}, []
    for olg, olg_ad in [("gelistirme", "Geliştirme (ön lisans devri)"), ("insaata_hazir", "İnşaata hazır proje")]:
        for pol, ad in [
            ("B1", "B1: batarya RES ile birlikte sipariş"),
            ("B2", "B2: batarya FID+12 ay sipariş"),
            ("B3", "B3: erken / bağımsız batarya"),
        ]:
            a = ag(cfg, pol, olg)
            cp, sira = cpm(a)
            sure, _ES, EF, bel = monte_carlo(a, sira, n, tohum)
            cod = EF["DRES"]
            sfk = EF["SFK"]
            d_res = np.clip(cod - MODEL_COD_AY, 0, None) / 12
            d_sfk = np.clip(sfk - MODEL_COD_AY, 0, None) / 12
            npv = npv_eslestir(d_res, d_sfk, ert)
            yol = kritik_iz(bel, "DRES", n)
            yol_sfk = kritik_iz(bel, "SFK", n)
            kritiklik = pd.Series({k: (yol[k] | yol_sfk[k]).mean() for k in a.index})
            dusy = pd.Series({k: spearmanr(sure[k], np.maximum(cod, sfk))[0] for k in a.index})
            sonuc[(olg, pol)] = {
                "a": a,
                "olg": olg_ad,
                "cp": cp,
                "cod": cod,
                "sfk": sfk,
                "npv": npv,
                "kritiklik": kritiklik,
                "dusy": dusy,
                "ad": ad,
            }
            q = lambda x, p: np.percentile(x, p)
            tarih = lambda m: (T0 + pd.DateOffset(months=int(round(m)))).strftime("%Y-%m")
            # YEKDEM (sınırlar endeksli varsayımı): COD 31.12.2030'dan sonraysa YEKDEM'e erişim yok → tüccar
            yekdem_ok = cod <= (pd.Timestamp("2030-12-31") - T0).days / 30.44
            npv_y = np.where(yekdem_ok, egri(ert, "F2Ye:", d_res), egri(ert, "F2:", d_res))
            npv_yn = np.where(yekdem_ok, egri(ert, "F2Y:", d_res), egri(ert, "F2:", d_res))
            ozet.append(
                {
                    "Proje olgunluğu": olg_ad,
                    "Politika": ad,
                    "CPM RES COD": tarih(cp.loc["DRES", "EF"]),
                    "CPM SFK başlangıcı": tarih(cp.loc["SFK", "EF"]),
                    "RES COD P50": tarih(q(cod, 50)),
                    "RES COD P80": tarih(q(cod, 80)),
                    "RES COD P90": tarih(q(cod, 90)),
                    "SFK başlangıcı P50": tarih(q(sfk, 50)),
                    "SFK başlangıcı P80": tarih(q(sfk, 80)),
                    "RES gecikmesi P50 [ay]": q(cod, 50) - MODEL_COD_AY,
                    "SFK gecikmesi P50 [ay]": q(sfk, 50) - MODEL_COD_AY,
                    "Batarya, RES'ten önce SFK'da [%]": 100 * (sfk < cod).mean(),
                    "Beklenen NPV, takvim dahil [M USD]": npv.mean(),
                    "Beklenen NPV, model takvimi (gecikmesiz) [M USD]": float(npv_eslestir(np.zeros(1), np.zeros(1), ert)[0]),
                    "P(COD ≤ 31.12.2030, YEKDEM'e erişim) [%]": 100 * yekdem_ok.mean(),
                    "E[NPV] YEKDEM, sınırlar endeksli, takvim dahil [M USD]": npv_y.mean(),
                    "E[NPV] YEKDEM, sınırlar nominal, takvim dahil [M USD]": npv_yn.mean(),
                    "E[NPV] tüccar, takvim dahil [M USD]": egri(ert, "F2:", d_res).mean(),
                }
            )
            log(
                f"{olg_ad} | {ad}: RES COD P50 {tarih(q(cod, 50))} P80 {tarih(q(cod, 80))} | SFK P50 {tarih(q(sfk, 50))} | E[NPV] {npv.mean():.2f}"
            )
    np.savez_compressed(
        CIKTI / "takvim_cod_ornekleri.npz",
        **{f"{o}_{pp}_{k}": sonuc[(o, pp)][k].astype(np.float32) for (o, pp) in sonuc if pp in ("B1", "B2") for k in ("cod", "sfk")},
    )
    ozet = pd.DataFrame(ozet)
    ozet.round(2).to_csv(CIKTI / "takvim_ozet.csv", encoding="utf-8-sig", index=False)
    b1 = sonuc[("gelistirme", "B1")]
    tab = b1["cp"].copy()
    tab["Kritiklik indeksi (B1)"] = b1["kritiklik"]
    tab["Spearman (süre ↔ COD, B1)"] = b1["dusy"]
    tab["Kritiklik indeksi (B3)"] = sonuc[("gelistirme", "B3")]["kritiklik"].reindex(tab.index)
    tab["Kritiklik indeksi (inşaata hazır, B1)"] = sonuc[("insaata_hazir", "B1")]["kritiklik"].reindex(tab.index)
    tab.round(3).to_csv(CIKTI / "takvim_aktiviteler.csv", encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    log("\n" + ozet.round(2).to_string(index=False))
    log(
        "\n"
        + tab[["Aktivite", "Olası", "ES", "EF", "Bolluk", "Kritik", "Kritiklik indeksi (B1)", "Spearman (süre ↔ COD, B1)"]]
        .round(2)
        .to_string()
    )
    grafikler(sonuc)


def grafikler(sonuc):
    b1 = sonuc[("gelistirme", "B1")]
    cp = b1["cp"].sort_values("ES", ascending=False)
    fig, ax = plt.subplots(figsize=(12, 6.2))
    for i, (_k, r) in enumerate(cp.iterrows()):
        renk = "#c0392b" if r["Kritik"] else g.RENK_RES
        ax.barh(i, r["Olası"], left=r["ES"], color=renk, height=0.6)
        if r["Bolluk"] > 0.05:
            ax.barh(i, r["Bolluk"], left=r["EF"], color="none", edgecolor=g.SOLUK, ls="--", height=0.6)
        ax.text(r["EF"] + 0.3 + max(r["Bolluk"], 0), i, f"{r['Olası']:.0f} ay", va="center", fontsize=7, color=g.IKINCIL)
    ax.set_yticks(range(len(cp)), cp["Aktivite"], fontsize=8)
    ay = np.arange(0, cp["LF"].max() + 7, 6)
    ax.set_xticks(ay, [(T0 + pd.DateOffset(months=int(m))).strftime("%Y-%m") for m in ay], fontsize=8)
    ax.axvline(MODEL_COD_AY, color=g.MUREKKEP, lw=1, ls=":")
    ax.text(MODEL_COD_AY + 0.3, len(cp) - 0.6, "finansal modelin COD'u (Oca 2028)", fontsize=7.5)
    g.eksen_sade(ax, izgara="x")
    g.baslik(
        fig,
        "Proje takvimi (CPM, olası süreler): kritik yol kırmızı",
        "Kesikli çerçeve: bolluk. Kritik yol ÇED → imar → lisans → finansman → türbin tedariki → montaj → devreye alma.",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "takvim_gantt.png")
    plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.4))
    tarih = lambda m: T0 + pd.to_timedelta(m * 30.44, unit="D")
    renk = {"B1": g.RENK_RES, "B2": g.RENK_GES, "B3": g.RENK_HIBRIT}
    for (olg, pol), s in sonuc.items():
        x = np.sort(s["cod"])
        if pol == "B1":
            axs[0].plot(
                tarih(x),
                np.arange(1, len(x) + 1) / len(x),
                color=g.MUREKKEP,
                lw=2,
                ls="-" if olg == "gelistirme" else ":",
                label=f"RES COD — {s['olg']}",
            )
        if olg == "gelistirme":
            xs = np.sort(s["sfk"])
            axs[0].plot(tarih(xs), np.arange(1, len(xs) + 1) / len(xs), color=renk[pol], lw=1.6, ls="--", label=f"SFK — {s['ad']}")
    for p in (50, 80, 90):
        v = np.percentile(b1["cod"], p)
        axs[0].axvline(tarih(v), color=g.SOLUK, lw=0.8, ls=":")
        axs[0].text(tarih(v), {50: 0.04, 80: 0.12, 90: 0.20}[p], f" P{p}", fontsize=7.5, color=g.IKINCIL)
    axs[0].axvline(tarih(MODEL_COD_AY), color="#c0392b", lw=1)
    axs[0].set_ylabel("Birikimli olasılık")
    axs[0].set_title("COD dağılımı (kırmızı: finansal modelin varsayımı)", loc="left")
    axs[0].legend(fontsize=7)
    g.eksen_sade(axs[0], izgara="both")
    k = b1["kritiklik"].sort_values()
    axs[1].barh([b1["a"].loc[i, "ad"] for i in k.index], 100 * k.values, color=[("#c0392b" if v > 0.5 else g.RENK_RES) for v in k.values])
    axs[1].set_xlabel("Kritiklik indeksi [%] (B1)")
    axs[1].tick_params(axis="y", labelsize=7.5)
    axs[1].set_title("Kritik yolda olma olasılığı", loc="left")
    g.eksen_sade(axs[1], izgara="x")
    g.baslik(fig, "Takvim riski: COD dağılımı ve kritiklik indeksi", "10.000 iterasyon, üçgen süreler.")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "takvim_cod_kritiklik.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
