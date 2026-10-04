"""
Aşama 7 — 1. Sistem kaynaklı kesinti (TEİAŞ / DGP YAT talimatları)

a) EPİAŞ sistem geneli saatlik YAT talimat hacmi (0/1/2 kodlu), 2023–2026: büyüklük ve saatlik yoğunlaşma
   (bayram, bahar öğle, düşük talep).
b) Ezine çevresindeki referans RES'lerde talimat izi: kalibre ERA5 modeli yüksek üretim beklerken en az iki santralin
   aynı saatte beklenenin yarısından az ürettiği saatler ("eşzamanlı düşüş"). 2016–2022 dönemi model hatası tabanı
   olarak kullanılır; 2023–2026'daki fazlalık talimat kaynaklı kesinti tahminidir.
c) Kesinti modeli: yıllık oran (2026 gözlemi, güneş kapasitesiyle büyüyen) × saatlik ağırlık (YAT hacminin saat tipi
   dağılımı). Bataryanın kurtarabildiği pay, şebeke sınırı saatlik düşürülen bir dispatch LP'siyle ölçülür.

Çıktılar: outputs/07/kesinti_*.csv, kesinti_*.png
Çalıştırma: .venv/bin/python src/07_sistem_kesintisi.py  (ERA5 2024–2026 ve talimat verisi gerekli)
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib import appsi

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, KOK, config_oku, deger
from src.uretim import kalibrasyon as kal
from src.uretim import ruzgar

CIKTI = CIKTILAR / "07"
KAYNAK = "Kaynak: EPİAŞ Şeffaflık Platformu (DGP talimat özetleri, gerçek zamanlı üretim), ERA5. Kendi hesaplamam."
SANTRALLER = ["enerjisa_canakkale", "camseki", "intepe"]
# Türkiye resmî ve dinî bayramları (Ramazan ve Kurban bayramı tarihleri, 2016–2026; arife dahil)
BAYRAMLAR = {
    2016: [("07-04", "07-07"), ("09-11", "09-15")], 2017: [("06-24", "06-27"), ("08-31", "09-04")],
    2018: [("06-14", "06-17"), ("08-20", "08-24")], 2019: [("06-03", "06-06"), ("08-10", "08-14")],
    2020: [("05-23", "05-26"), ("07-30", "08-03")], 2021: [("05-12", "05-15"), ("07-19", "07-23")],
    2022: [("05-01", "05-04"), ("07-08", "07-12")], 2023: [("04-20", "04-23"), ("06-27", "07-01")],
    2024: [("04-09", "04-12"), ("06-15", "06-19")], 2025: [("03-29", "04-01"), ("06-05", "06-09")],
    2026: [("03-19", "03-22"), ("05-26", "05-30")],
}
SABIT_TATILLER = ["01-01", "04-23", "05-01", "05-19", "07-15", "08-30", "10-29"]


def log(*a):
    print(*a, flush=True)


def saat_tipi(indeks_utc: pd.DatetimeIndex) -> pd.Series:
    """Her saati bir tipe atar: bayram/tatil, bahar öğle (Mar–Haz, 10–16 TSİ), hafta sonu öğle, diğer."""
    t = indeks_utc.tz_convert("Europe/Istanbul") if indeks_utc.tz is not None else indeks_utc
    tarih = t.strftime("%m-%d")
    bayram = np.zeros(len(t), bool)
    for y, araliklar in BAYRAMLAR.items():
        for a, b in araliklar:
            bayram |= (t.year == y) & (tarih >= a) & (tarih <= b)
    bayram |= np.isin(tarih, SABIT_TATILLER)
    ogle = (t.hour >= 10) & (t.hour <= 16)
    bahar = np.isin(t.month, [3, 4, 5, 6])
    tip = np.where(bayram, "Bayram/tatil", np.where(bahar & ogle, "Bahar öğle (Mar–Haz, 10–16)",
                   np.where(ogle & (t.dayofweek >= 5), "Hafta sonu öğle", np.where(ogle, "Diğer öğle", "Gece/akşam"))))
    return pd.Series(tip, index=indeks_utc)


def sistem_talimat_analizi():
    t = pd.read_parquet(ISLENMIS_VERI / "talimat_ozeti_2023_guncel.parquet")
    t = t[t.index >= "2023-01-01"]
    t["yat"] = t[["yat_0", "yat_1", "yat_2"]].sum(1)
    yil = t.index.tz_convert("Europe/Istanbul").year
    ozet = t.groupby(yil)[["yat_0", "yat_1", "yat", "yal_0", "yal_1"]].sum().div(1e3)
    ozet["Kapsanan ay"] = t.groupby(yil).size() / 730
    ozet.columns = ["YAT 0-kodlu [GWh]", "YAT 1-kodlu (sistem kısıtı) [GWh]", "YAT toplam [GWh]", "YAL 0-kodlu [GWh]",
                    "YAL 1-kodlu [GWh]", "Kapsanan ay"]
    tip = saat_tipi(t.index)
    pay = t.groupby([yil, tip.values])["yat"].sum().unstack().fillna(0)
    saat_payi = pd.Series(tip.values).value_counts(normalize=True)
    yogunluk = (pay.div(pay.sum(1), axis=0) / saat_payi).round(2)    # YAT payı / saat payı (1 = ortalama)
    return t, ozet, yogunluk


def referans_santral_analizi(cfg):
    cr = cfg["uretim"]["ruzgar"]
    kod = deger(cfg["saha"]["kod"])
    saha = cfg["aday_sahalar"][kod]
    spec = importlib.util.spec_from_file_location("rk", Path(__file__).parent / "02_ruzgar_kalibrasyonu.py")
    rk = importlib.util.module_from_spec(spec); spec.loader.exec_module(rk)
    era5 = ruzgar.era5_coklu_yil(kod, saha["enlem"], saha["boylam"], 2016, 2026, cr)
    m = kal.referans_model(era5, cr, rk.VEKIL_TURBIN, rk.VEKIL_GOBEK)
    k = pd.read_parquet(KOK / deger(cr["k_matris_dosyasi"])).to_numpy()
    model = pd.Series(m.kf_matris(k), index=m.indeks)
    goz = pd.read_parquet(ISLENMIS_VERI / "ezine_res_santralleri.parquet")
    kf = pd.DataFrame({s: rk.degisken_kapasiteli_kf(goz[s]) for s in SANTRALLER}).reindex(model.index)
    # Santral başına ölçek düzeltmesi (yıllık oran medyanı, yüksek modelli saatlerde) → model "beklenen" üretimi
    yuksek = model > 0.3
    oran = kf[yuksek].div(model[yuksek], axis=0)
    yil = model.index.tz_convert("Europe/Istanbul").year
    olcek = oran.groupby(yil[yuksek.to_numpy()]).median()
    beklenen = pd.DataFrame({s: model * olcek[s].reindex(yil).to_numpy() for s in SANTRALLER}, index=model.index)
    dusuk = (kf < 0.5 * beklenen) & yuksek.to_numpy()[:, None] & kf.notna()
    esz = (dusuk.sum(1) >= 2)
    kayip = ((beklenen - kf).clip(lower=0).where(dusuk)).sum(1).where(esz, 0)     # kaybedilen KF puanı (santraller toplamı)
    toplam = beklenen.where(kf.notna()).sum(1)
    yillik = pd.DataFrame({"Eşzamanlı düşüş saati": esz.groupby(yil).sum(),
                           "Kayıp enerji payı [%]": 100 * kayip.groupby(yil).sum() / toplam.groupby(yil).sum()})
    taban = yillik.loc[2016:2022, "Kayıp enerji payı [%]"].mean()
    yillik["Taban üstü (talimat tahmini) [%]"] = (yillik["Kayıp enerji payı [%]"] - taban).clip(lower=0)
    tip = saat_tipi(model.index)
    esz_tip = esz[yil >= 2023].groupby(tip[yil >= 2023].values).mean() / esz[(yil >= 2016) & (yil <= 2022)].groupby(
        tip[(yil >= 2016) & (yil <= 2022)].values).mean()
    return yillik, esz, esz_tip, taban


class KesintiLP:
    """Hibrit + batarya dispatch, saatlik şebeke sınırı L_t (talimat saatlerinde düşürülür). Rezerv yok (sade)."""

    def __init__(self, n, P, E, eta, yip):
        m = pyo.ConcreteModel()
        m.T = pyo.RangeSet(0, n - 1)
        m.A = pyo.Param(m.T, mutable=True, initialize=0.0); m.p = pyo.Param(m.T, mutable=True, initialize=0.0)
        m.L = pyo.Param(m.T, mutable=True, initialize=50.0)
        m.y = pyo.Var(m.T, within=pyo.NonNegativeReals); m.k = pyo.Var(m.T, within=pyo.NonNegativeReals)
        m.c = pyo.Var(m.T, bounds=(0, P)); m.d = pyo.Var(m.T, bounds=(0, P)); m.s = pyo.Var(m.T, bounds=(0, E))
        m.o = pyo.Objective(expr=sum(m.p[i] * (m.y[i] + m.d[i]) - yip * m.d[i] for i in m.T), sense=pyo.maximize)
        m.k1 = pyo.Constraint(m.T, rule=lambda m, i: m.y[i] + m.k[i] + m.c[i] == m.A[i])
        m.k2 = pyo.Constraint(m.T, rule=lambda m, i: m.y[i] + m.d[i] <= m.L[i])
        m.k3 = pyo.Constraint(m.T, rule=lambda m, i: m.s[i] == m.s[(i - 1) % n] + eta * m.c[i] - m.d[i] / eta)
        self.m, self.n, self.coz_ = m, n, appsi.solvers.Highs()

    def coz(self, A, p, L):
        for i in range(self.n):
            self.m.A[i].set_value(float(A[i])); self.m.p[i].set_value(float(p[i])); self.m.L[i].set_value(float(L[i]))
        self.coz_.solve(self.m)
        al = lambda v: np.array([v[i].value for i in range(self.n)])
        return {k: al(getattr(self.m, k)) for k in "ykcd"}


def batarya_kurtarma(cfg, oran_hedef: float, tohum: int = 0):
    """
    Temsilî yıl, RES 58,8 MW; talimat saatleri YAT yoğunluğuna göre rastgele seçilir, o saatlerde şebeke sınırı 0'a iner
    (tam YAT). Kayıp gelir: bataryasız ve 30 MW / 52,5 MWh bataryalı.
    """
    spec = importlib.util.spec_from_file_location("gy", Path(__file__).parent / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec); spec.loader.exec_module(gy)
    o = gy.Ortam()
    A = 58.8 * o.r
    q = o.sekiller[(1, o.H[-1])]
    p = 58.0 * q
    idx = pd.date_range("2025-01-01", periods=8760, freq="h", tz="UTC")
    tip = saat_tipi(idx)
    _, _, yog = sistem_talimat_analizi()
    w = tip.map(yog.loc[2026]).fillna(1.0).to_numpy() * (A > 5)
    rng = np.random.default_rng(tohum)
    # Talimat olayları: 4 saatlik bloklar, hedef kayıp oranına ulaşana kadar ağırlıklı seçim
    L = np.full(8760, 50.0)
    secilen = np.zeros(8760, bool)
    while np.minimum(A, 50)[secilen].sum() < oran_hedef * np.minimum(A, 50).sum():
        b = rng.choice(8760, p=w / w.sum())
        secilen[b:b + 4] = True
    L[secilen] = 0.0
    eta = float(np.sqrt(deger(cfg["teknoloji"]["bess"]["verim_gidis_donus"])))
    yip = deger(cfg["teknoloji"]["bess"]["yipranma_maliyeti"])
    sonuc = {}
    for ad, P, E in [("Bataryasız", 0.0, 0.0), ("30 MW / 52,5 MWh", 30.0, 52.5)]:
        lp = KesintiLP(8760, P, E, eta, yip)
        r0, r1 = lp.coz(A, p, np.full(8760, 50.0)), lp.coz(A, p, L)
        g0 = (p * (r0["y"] + r0["d"])).sum() - yip * r0["d"].sum()
        g1 = (p * (r1["y"] + r1["d"])).sum() - yip * r1["d"].sum()
        sonuc[ad] = {"Kesintisiz gelir [M USD]": g0 / 1e6, "Kesintili gelir [M USD]": g1 / 1e6, "Kayıp [M USD]": (g0 - g1) / 1e6,
                     "Kayıp enerji [GWh]": ((r0["y"] + r0["d"]).sum() - (r1["y"] + r1["d"]).sum()) / 1e3,
                     "Talimat saatlerinde ort. fiyat [USD/MWh]": float(p[secilen].mean()),
                     "Talimat saati": int(secilen.sum())}
    df = pd.DataFrame(sonuc).T
    df["Batarya kurtarma payı [%]"] = np.nan
    df.loc["30 MW / 52,5 MWh", "Batarya kurtarma payı [%]"] = 100 * (1 - df.loc["30 MW / 52,5 MWh", "Kayıp [M USD]"] / df.loc["Bataryasız", "Kayıp [M USD]"])
    return df


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    t, ozet, yog = sistem_talimat_analizi()
    ozet.round(2).to_csv(CIKTI / "kesinti_sistem_yat_yillik.csv", encoding="utf-8-sig")
    yog.to_csv(CIKTI / "kesinti_yat_yogunluk.csv", encoding="utf-8-sig")
    log("Sistem YAT (yıllık):\n" + ozet.round(1).to_string())
    log("YAT yoğunluğu (YAT payı / saat payı):\n" + yog.to_string())

    yillik, esz, esz_tip, taban = referans_santral_analizi(cfg)
    yillik.round(3).to_csv(CIKTI / "kesinti_referans_santraller.csv", encoding="utf-8-sig")
    esz_tip.round(2).to_csv(CIKTI / "kesinti_referans_saat_tipi.csv", encoding="utf-8-sig")
    log(f"\nReferans santraller (taban {taban:.2f}%):\n" + yillik.round(2).to_string())
    log("2023–26 eşzamanlı düşüş sıklığı / 2016–22 (saat tipine göre):\n" + esz_tip.round(2).to_string())

    kc = deger(cfg["kesinti"])
    kurt = batarya_kurtarma(cfg, kc["oran_2026"])
    kurt.round(3).to_csv(CIKTI / "kesinti_batarya_kurtarma.csv", encoding="utf-8-sig")
    log("\nBatarya kurtarma:\n" + kurt.round(3).to_string())
    grafik(t, ozet, yog, yillik)


def grafik(t, ozet, yog, yillik):
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4), gridspec_kw={"width_ratios": [1.1, 1.2, 1]})
    ax = axs[0]
    ay = t["yat"].resample("MS").sum() / 1e3
    ax.bar(ay.index.tz_localize(None), ay.values, width=25, color=g.RENK_GES)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("Sistem YAT talimatı [GWh/ay]"); ax.set_title("Aylık YAT hacmi (tüm kaynaklar)", loc="left")
    g.eksen_sade(ax)
    ax = axs[1]
    y = yog.loc[[c for c in [2023, 2024, 2025, 2026] if c in yog.index]].T
    y.plot.barh(ax=ax, color=["#c6dbf5", "#8ab4ea", "#4a8ddc", "#1d4f91"][:y.shape[1]], width=0.8)
    ax.axvline(1, color=g.MUREKKEP, lw=0.8, ls="--")
    ax.set_xlabel("YAT payı / saat payı (1 = ortalama)"); ax.set_title("YAT'ın yoğunlaştığı saatler", loc="left")
    ax.legend(fontsize=7.5, title="Yıl", title_fontsize=7.5); g.eksen_sade(ax, izgara="x")
    ax = axs[2]
    ax.bar(yillik.index, yillik["Kayıp enerji payı [%]"], color=g.RENK_RES)
    ax.axhline(yillik.loc[2016:2022, "Kayıp enerji payı [%]"].mean(), color=g.MUREKKEP, lw=1, ls="--")
    ax.text(2016, yillik.loc[2016:2022, "Kayıp enerji payı [%]"].mean() * 1.08, "2016–22 tabanı (model hatası)", fontsize=7.5,
            color=g.IKINCIL)
    ax.set_ylabel("Eşzamanlı düşüşte kaybolan enerji [%]"); ax.set_title("Ezine RES'lerinde talimat izi", loc="left")
    g.eksen_sade(ax)
    g.baslik(fig, "Sistem kaynaklı kesinti: 2026'da YAT hacmi üç katına çıktı",
             "Sol/orta: EPİAŞ sistem geneli YAT. Sağ: üç referans RES'in kalibre ERA5'e göre eşzamanlı düşüşleri.")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "kesinti_analizi.png"); plt.close(fig)


if __name__ == "__main__":
    main()
