"""
Aşama 4 — Optimizasyon: Basamak 1-4

    B1  Batarya arbitrajı (LP), 2025 fiyatları, şebekeden şarj serbest (öğrenme amaçlı)
    B2  Sabit hibrit (b) + batarya (LP), santralden şarj, şebeke kısıtı gölge fiyatları
    B3  Kapasite MILP: temsilî günler (K = 12/24/48) vs tam yıl
    B4  Ayrıntılı değerlendirme, senaryolar + pişmanlık, şebeke boyutu, GES × batarya ızgarası, başabaş fiyat

Çıktılar: outputs/04_optimizasyon/*.png, *.csv  — çalıştırma ~15-20 dk
Çalıştırma: .venv/bin/python src/04_optimizasyon.py
"""

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.metrikler import basabas_fiyat
from src.finans.model import Varsayimlar, proje_degerle
from src.finans.veri import _standart_yil, uretim_profili
from src.optimizasyon.batarya import arbitraj_coz
from src.optimizasyon.hibrit import dispatch_kancasi, hibrit_coz, temsili_hava_yili
from src.optimizasyon.kapasite import Segment, ekonomi_hesapla, kapasite_coz
from src.optimizasyon.temsili_gunler import segmentleri_kur

CIKTI = CIKTILAR / "04_optimizasyon"
SEVIYELER = ["dusuk", "baz", "yuksek"]
VARYANTLAR = ["durur", "devam"]
SEV_AD = {"dusuk": "Düşük (45)", "baz": "Baz (58)", "yuksek": "Yüksek (72)"}
KAYNAK = "Kaynak: kendi modelim (Pyomo + HiGHS). Girdiler: EPİAŞ PTF, PVGIS, ERA5 (kalibre), Aşama 3 varsayımları. Reel 2026 USD."
AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def log(*a):
    print(*a, flush=True)


class Hazirlik:
    """Ortak girdiler: config, profiller, temsilî hava yılı, seviyelendirilmiş fiyatlar."""

    def __init__(self):
        self.cfg = config_oku()
        self.u = uretim_profili()
        self.v = Varsayimlar.configten(self.cfg)
        self.opt = {**{k: deger(x) for k, x in self.cfg["optimizasyon"].items()},
                    "verim_gd": deger(self.cfg["teknoloji"]["bess"]["verim_gidis_donus"])}
        dz = self.cfg["duzenleme"]
        self.duzen = {"yardimci_kaynak": deger(dz["yardimci_kaynak_siniri"]), "depolamali": deger(dz["depolamali_tesis_modu"])}
        self.sebekeden = deger(dz["sebekeden_sarj"])
        self.w = temsili_hava_yili(self.u.ges, self.u.res, self.u.hava_yillari)
        # Temsilî hava yılı, 10 yıl ortalama KF'ye ölçeklenir (şekil korunur)
        self.g = self.u.ges[self.w] * self.u.ges.mean() / self.u.ges[self.w].mean()
        self.r = self.u.res[self.w] * self.u.res.mean() / self.u.res[self.w].mean()
        self.DF = (1 + self.v.wacc) ** -(self.v.insaat_suresi + np.arange(1, self.v.omur + 1))
        self.senaryo = {(s, k): fiyat_senaryosu_uret(self.cfg, self.u, s, k) for s in SEVIYELER for k in VARYANTLAR}

    def seviyeli_fiyat(self, f, v=None):
        DF = self.DF if v is None else (1 + v.wacc) ** -(v.insaat_suresi + np.arange(1, v.omur + 1))
        return (f.fiyatlar * DF[:, None, None]).sum(0) / DF.sum()         # (S, 8760)

    def coz(self, f, L=50, K=None, sabit=None, v=None, zaman=900, yatirim="zorunlu"):
        v = v or self.v
        p = self.seviyeli_fiyat(f, v)
        eko = ekonomi_hesapla(v, float(p.mean()))
        seg = segmentleri_kur([p[0], p[1]], self.g, self.r, K, Segment)
        return kapasite_coz(seg, v, eko, L, self.opt, self.duzen, sabit=sabit, zaman_siniri=zaman, yatirim=yatirim)


def konfig_of(r, L=50):
    return dict(res_mw=r["RES [MW]"], ges_mw=r["GES [MWac]"], bess_mw=r["BESS [MW]"], bess_mwh=r["BESS [MWh]"], sebeke_mw=L)


def tasarim_metni(r):
    if r.get("Yatırım", 1) == 0:
        return "Yatırım yapma"
    s = f"RES {r['RES [MW]']:.1f} ({r['N']}×4,2) + GES {r['GES [MWac]']:.0f}"
    return s + (f" + BESS {r['BESS [MW]']:.0f}/{r['BESS [MWh]']:.0f}" if r["BESS [MWh]"] > 0.5 else "")


# =============================================================================
def basamak1(h: Hazirlik):
    log("\n=== Basamak 1: batarya arbitrajı ===")
    b = h.opt["basamak1_batarya"]
    p = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")["ptf_usd"]
    f = _standart_yil(p.loc["2025-01-01":"2025-12-31 23:00"])
    df, oz = arbitraj_coz(f, b["mw"], b["mwh"], h.opt["verim_gd"], h.v.bess_yipranma)
    gun = f.reshape(365, 24)
    ust = float((np.sort(gun, 1)[:, -4:].sum(1) - np.sort(gun, 1)[:, :4].sum(1)).sum() * b["mw"])
    eta = h.opt["verim_gd"]
    tek = float(np.clip(np.sort(gun, 1)[:, -4:].sum(1) * eta - np.sort(gun, 1)[:, :4].sum(1)
                        - 4 * eta * h.v.bess_yipranma, 0, None).sum() * b["mw"])
    gd = df.desarj.to_numpy().reshape(365, 24).sum(1) / b["mwh"]
    oz.update({"Üst sınır: günde 1 döngü, kayıpsız [USD]": ust, "Günde 1 döngü, verim + yıpranma [USD]": tek,
               ">1 döngü yapılan gün": int((gd > 1.01).sum()), "Hiç çalışmayan gün": int((gd < 0.01).sum()),
               "Gelir / kW-yıl [USD]": oz["Amaç (gelir − yıpranma) [USD]"] / (b["mw"] * 1000)})
    pd.Series(oz).to_csv(CIKTI / "b1_arbitraj_ozet.csv", encoding="utf-8-sig", header=["deger"])
    for k, x in oz.items():
        log(f"  {k}: {x:,.2f}" if isinstance(x, float) else f"  {k}: {x}")
    return oz


def basamak2(h: Hazirlik):
    log("\n=== Basamak 2: sabit hibrit (b) + batarya ===")
    b = h.opt["basamak2_batarya"]
    p = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")["ptf_usd"]
    f = _standart_yil(p.loc["2025-01-01":"2025-12-31 23:00"])
    df, oz = hibrit_coz(25 * h.g, 50 * h.r, f, 50, b["mw"], b["mwh"], h.opt["verim_gd"], h.v.bess_yipranma, False)
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="h", tz="UTC")
    oz["Temsilî hava yılı"] = h.u.hava_yillari[h.w]
    oz["Gölge fiyat ort. (bağlayıcı saatler) [USD/MWh]"] = float(df.sebeke_golge[df.sebeke_golge > 1e-6].mean())
    oz["Gölge fiyat toplamı = 1 MW ek bağlantının yıllık değeri [USD/MW-yıl]"] = float(df.sebeke_golge.sum())
    pd.Series(oz).to_csv(CIKTI / "b2_hibrit_ozet.csv", encoding="utf-8-sig", header=["deger"])
    df.to_parquet(CIKTI / "b2_dispatch_2025.parquet")
    for k, x in oz.items():
        log(f"  {k}: {x:,.2f}" if isinstance(x, float) else f"  {k}: {x}")
    grafik_dispatch(df, b)
    grafik_golge(df)
    return oz


def basamak3(h: Hazirlik):
    log("\n=== Basamak 3: kapasite MILP — temsilî günler vs tam yıl ===")
    f = h.senaryo[("baz", "devam")]
    satir = []
    for K in [12, 24, 48, None]:
        r = h.coz(f, K=K)
        satir.append({"Zaman temsili": f"{K} temsilî gün" if K else "Tam yıl (2 × 8760 saat)",
                      **{k: x for k, x in r.items() if k != "model"}})
        log(f"  {satir[-1]['Zaman temsili']}: {tasarim_metni(r)} | NPV {r['NPV tahmini [M USD]']:.2f} | "
            f"{r['Çözüm süresi [s]']:.1f}s | boşluk {r['MIP boşluğu']:.1e}")
    tablo = pd.DataFrame(satir)
    tablo.to_csv(CIKTI / "b3_temsili_vs_tam.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    grafik_temsili(tablo)
    tam = {k: x for k, x in satir[-1].items()}
    return tam, tablo


def basamak4(h: Hazirlik, opt_baz: dict):
    sonuc = {}
    kanca = dispatch_kancasi(h.opt["verim_gd"], h.v.bess_yipranma, h.v.teias_enerji, h.sebekeden)
    f_baz = h.senaryo[("baz", "devam")]

    # --- a) Ayrıntılı değerlendirme
    log("\n=== Basamak 4a: ayrıntılı değerlendirme ===")
    k_opt = konfig_of(opt_baz)
    bd = kanca if k_opt["bess_mw"] > 0.5 else None
    t = time.time()
    ayr = proje_degerle(k_opt, h.v, f_baz, h.u, bess_dispatch=bd)
    u1 = type(h.u)(ges=h.g[None], res=h.r[None], hava_yillari=[h.u.hava_yillari[h.w]])
    ayr1 = proje_degerle(k_opt, h.v, f_baz, u1, bess_dispatch=bd)
    sonuc["ayrintili"] = {"Optimizasyon NPV tahmini [M USD]": opt_baz["NPV tahmini [M USD]"],
                          "Ayrıntılı, temsilî hava yılı [M USD]": ayr1.npv / 1e6,
                          "Ayrıntılı, 10 hava yılı [M USD]": ayr.npv / 1e6, "Ayrıntılı IRR [%]": 100 * ayr.irr,
                          "Ayrıntılı kesinti [%]": ayr.ozet["Kesinti oranı [%]"],
                          "Optimizasyon kesinti [%]": opt_baz["Kesinti [%]"], "Süre [s]": time.time() - t}
    log("  ", {k: round(x, 2) for k, x in sonuc["ayrintili"].items()})

    # --- b) Senaryolar ve pişmanlık
    log("\n=== Basamak 4b: senaryolar ===")
    serbest, zorunlu = {}, {}
    for (s_, kv), f in h.senaryo.items():
        serbest[(s_, kv)] = h.coz(f, yatirim="serbest")
        zorunlu[(s_, kv)] = h.coz(f, yatirim="zorunlu")
        log(f"  {SEV_AD[s_]}/{kv}: karar → {tasarim_metni(serbest[(s_, kv)])} (NPV {serbest[(s_, kv)]['NPV tahmini [M USD]']:.2f}) | "
            f"kurulursa en iyi → {tasarim_metni(zorunlu[(s_, kv)])} (NPV {zorunlu[(s_, kv)]['NPV tahmini [M USD]']:.2f})")
    senaryo_tablo = pd.DataFrame([{
        "Fiyat": SEV_AD[s_], "Kanibalizasyon": kv,
        "Optimal karar": tasarim_metni(serbest[(s_, kv)]), "Optimal NPV [M USD]": serbest[(s_, kv)]["NPV tahmini [M USD]"],
        "Kurulursa: türbin": r["N"], "RES [MW]": r["RES [MW]"], "GES [MWac]": r["GES [MWac]"],
        "BESS [MW]": r["BESS [MW]"], "BESS [MWh]": r["BESS [MWh]"], "Kurulursa NPV [M USD]": r["NPV tahmini [M USD]"],
        "Kesinti [%]": r["Kesinti [%]"], "BESS döngü/yıl": r["BESS döngü/yıl"]} for (s_, kv), r in zorunlu.items()])
    senaryo_tablo.to_csv(CIKTI / "b4_senaryo_tasarimlari.csv", encoding="utf-8-sig", index=False, float_format="%.3f")

    # Aday tasarımlar: her senaryonun "kurulursa en iyi" tasarımı (benzersiz) + "yatırım yapma"
    adaylar = {}
    for sk, r in zorunlu.items():
        imza = (r["N"], round(r["GES [MWac]"], 1), round(r["BESS [MW]"], 1), round(r["BESS [MWh]"], 1))
        if r["N"] == 0 and r["GES [MWac]"] < 0.5 and r["BESS [MWh]"] < 0.5:
            continue                      # sıfır kapasite = "yatırım yapma" seçeneği zaten listede
        adaylar.setdefault(imza, (sk, r))
    log(f"  Benzersiz tasarım sayısı: {len(adaylar)} (+ yatırım yapma)")
    pis = [{"Tasarım": "Yatırım yapma", "Seçildiği senaryo": "—",
            **{f"{SEV_AD[sk[0]]}/{sk[1]}": serbest[sk]["NPV tahmini [M USD]"] - 0.0 for sk in h.senaryo}}]
    npv_tasarim = {"Yatırım yapma": {sk: 0.0 for sk in h.senaryo}}
    for imza, (kaynak, r) in adaylar.items():
        ad = tasarim_metni(r)
        npv_tasarim[ad] = {}
        for sk, f in h.senaryo.items():
            if sk == kaynak:
                npv_tasarim[ad][sk] = r["NPV tahmini [M USD]"]
            else:
                npv_tasarim[ad][sk] = h.coz(f, sabit={"N": r["N"], "G": r["GES [MWac]"], "P": r["BESS [MW]"],
                                                      "E": r["BESS [MWh]"]})["NPV tahmini [M USD]"]
        pis.append({"Tasarım": ad, "Seçildiği senaryo": f"{SEV_AD[kaynak[0]]}/{kaynak[1]}",
                    **{f"{SEV_AD[sk[0]]}/{sk[1]}": serbest[sk]["NPV tahmini [M USD]"] - npv_tasarim[ad][sk] for sk in h.senaryo}})
    pismanlik = pd.DataFrame(pis)
    kol = [c for c in pismanlik.columns if c not in ("Tasarım", "Seçildiği senaryo")]
    pismanlik["En büyük pişmanlık [M USD]"] = pismanlik[kol].max(axis=1)
    pismanlik.to_csv(CIKTI / "b4_pismanlik.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    pd.DataFrame({ad: {f"{SEV_AD[sk[0]]}/{sk[1]}": x for sk, x in d_.items()} for ad, d_ in npv_tasarim.items()}).T.to_csv(
        CIKTI / "b4_tasarim_senaryo_npv.csv", encoding="utf-8-sig", float_format="%.3f")
    log(pismanlik.round(2).to_string(index=False))
    grafik_senaryo(senaryo_tablo, pismanlik)
    sonuc["senaryo"], sonuc["pismanlik"] = senaryo_tablo, pismanlik

    # --- c) Şebeke boyutu (yatırım zorunlu: bağlantı boyutuna göre en iyi tasarım), baz ve yüksek fiyat
    log("\n=== Basamak 4c: şebeke boyutu ===")
    eko = ekonomi_hesapla(h.v, 58.0)
    baglanti_maliyeti_npv = eko.a_sebeke * eko.vergi_carpani / 1e6       # M USD / MW (bugünkü değer)
    satirlar = []
    for sev in ["baz", "yuksek"]:
        f = h.senaryo[(sev, "devam")]
        for L in [30, 40, 50, 60, 70, 80]:
            r = h.coz(f, L=L)
            satirlar.append({"Fiyat": SEV_AD[sev], "Bağlantı [MW]": L, "Türbin": r["N"], "RES [MW]": r["RES [MW]"],
                             "GES [MWac]": r["GES [MWac]"], "BESS [MW]": r["BESS [MW]"], "BESS [MWh]": r["BESS [MWh]"],
                             "NPV [M USD]": r["NPV tahmini [M USD]"], "Kesinti [%]": r["Kesinti [%]"]})
            log(f"  {SEV_AD[sev]} L={L}: {tasarim_metni(r)} | NPV {r['NPV tahmini [M USD]']:.2f}")
    seb = pd.DataFrame(satirlar)
    seb["Marjinal NPV [M USD/MW]"] = seb.groupby("Fiyat")["NPV [M USD]"].diff() / seb.groupby("Fiyat")["Bağlantı [MW]"].diff()
    # Bağlantı maliyeti (CAPEX + TEİAŞ kapasite bedeli) öncesi marjinal değer: bağlantı hakkı için ödenebilecek
    # azami tutar (katkı payı teklif tavanı) = marjinal NPV + bağlantının kendi maliyeti
    seb["Bağlantı maliyeti öncesi marjinal değer [M USD/MW]"] = seb["Marjinal NPV [M USD/MW]"] + baglanti_maliyeti_npv
    seb.to_csv(CIKTI / "b4_sebeke_boyutu.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    log(seb.round(3).to_string(index=False))
    sonuc["sebeke"], sonuc["baglanti_maliyeti_npv"] = seb, baglanti_maliyeti_npv
    grafik_sebeke(seb, baglanti_maliyeti_npv)

    # --- d) GES × batarya ızgarası (RES optimalde sabit), temsilî günler K=24
    log("\n=== Basamak 4d: GES × batarya ızgarası ===")
    ges_l = np.arange(0, 61, 10)
    mwh_l = np.arange(0, 161, 20)
    izgara = np.zeros((len(mwh_l), len(ges_l)))
    for i, E in enumerate(mwh_l):
        for j, G in enumerate(ges_l):
            r = h.coz(f_baz, K=24, sabit={"N": opt_baz["N"], "G": float(G), "P": float(E) / 4, "E": float(E)})
            izgara[i, j] = r["NPV tahmini [M USD]"]
    iz = pd.DataFrame(izgara, index=pd.Index(mwh_l, name="BESS [MWh] (4 saat)"), columns=pd.Index(ges_l, name="GES [MWac]"))
    iz.to_csv(CIKTI / "b4_ges_bess_izgara.csv", encoding="utf-8-sig", float_format="%.3f")
    log(iz.round(2).to_string())
    grafik_izgara(iz, opt_baz)
    # RES türbin sayısı eğrisi (GES/BESS optimum için serbest), temsilî günler
    nlist = list(range(9, 20))
    n_npv = [h.coz(f_baz, K=24, sabit={"N": n})["NPV tahmini [M USD]"] for n in nlist]
    pd.DataFrame({"Türbin": nlist, "RES [MW]": np.array(nlist) * 4.2, "NPV (K=24) [M USD]": n_npv}).to_csv(
        CIKTI / "b4_turbin_egrisi.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    sonuc["izgara"], sonuc["turbin"] = iz, (nlist, n_npv)

    # --- e) Başabaş fiyat
    log("\n=== Basamak 4e: başabaş fiyat ===")
    def onbellekli(kanca_):
        """Başabaş kök bulmada dispatch planı ilk (baz) çağrıda çözülüp sonraki fiyat seviyelerinde yeniden kullanılır."""
        hafiza = {}
        def sar(Gx, Rx, P4, konfig, v):
            if "x" not in hafiza:
                hafiza["x"] = kanca_(Gx, Rx, P4, konfig, v)
            return hafiza["x"]
        return sar

    bb = {}
    for ad, k in {"Optimal (baz)": k_opt, "(a) RES 50": dict(res_mw=50, sebeke_mw=50),
                  "(b) RES 50 + GES 25": dict(res_mw=50, ges_mw=25, sebeke_mw=50)}.items():
        bb[ad] = {kv: basabas_fiyat(k, h.cfg, h.u, h.v, kv,
                                    bess_dispatch=onbellekli(kanca) if k.get("bess_mw", 0) > 0.5 else None)
                  for kv in VARYANTLAR}
    bb = pd.DataFrame(bb).T.rename(columns={"durur": "Kanibalizasyon durur", "devam": "Kanibalizasyon devam"})
    bb.to_csv(CIKTI / "b4_basabas.csv", encoding="utf-8-sig", float_format="%.2f")
    log(bb.round(1).to_string())
    sonuc["basabas"] = bb
    return sonuc


# =============================================================================
def grafik_dispatch(df, b):
    # En çok kesinti kurtarılan hafta
    hafta = df.kesinti.rolling(168).sum().shift(-167)
    kurtar = (df.kullanilabilir.clip(upper=50) * 0 + (df.kullanilabilir - 50).clip(lower=0) - df.kesinti).rolling(168).sum().shift(-167)
    bas = kurtar.idxmax()
    d = df.loc[bas: bas + pd.Timedelta(hours=167)]
    x = d.index.tz_convert("Europe/Istanbul")
    fig, axs = plt.subplots(3, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1, 1]})
    ax = axs[0]
    ax.stackplot(x, d.dogrudan, d.desarj, colors=[g.RENK_HIBRIT, "#7f6bd1"], labels=["Santralden doğrudan satış", "Bataryadan deşarj"])
    ax.plot(x, d.kullanilabilir, color=g.MUREKKEP, lw=1.2, label="Kullanılabilir üretim (GES + RES)")
    ax.fill_between(x, d.dogrudan + d.sarj, d.dogrudan + d.sarj + d.kesinti, color=g.SOLUK, alpha=0.6, lw=0, label="Kesinti")
    ax.fill_between(x, d.dogrudan, d.dogrudan + d.sarj, color=g.RENK_GES, alpha=0.5, lw=0, label="Bataryaya şarj")
    ax.axhline(50, color=g.MUREKKEP, ls="--", lw=1)
    ax.text(x[2], 51, "50 MW bağlantı", fontsize=8, color=g.MUREKKEP)
    ax.set_ylabel("MW"); ax.legend(fontsize=8, ncols=3, loc="upper right")
    axs[1].plot(x, d.soc, color="#7f6bd1", lw=1.8); axs[1].set_ylabel("Şarj durumu [MWh]")
    axs[1].set_ylim(0, b["mwh"] * 1.05)
    axs[2].plot(x, d.fiyat, color=g.MUREKKEP, lw=1.4); axs[2].set_ylabel("PTF [USD/MWh]")
    for a in axs:
        g.eksen_sade(a, izgara="both")
    g.baslik(fig, "Örnek hafta: batarya kesintiyi depolayıp akşam pikinde satıyor",
             f"Konfigürasyon (b) + {b['mw']} MW / {b['mwh']} MWh batarya, 2025 PTF, temsilî hava yılı. Saatler TSİ.")
    fig.tight_layout(rect=(0, 0, 1, 0.93)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b2_ornek_hafta_dispatch.png"); plt.close(fig)


def grafik_golge(df):
    tsi = df.index.tz_convert("Europe/Istanbul")
    t = df.sebeke_golge.groupby([tsi.month, tsi.hour]).mean().unstack()
    fig, ax = plt.subplots(figsize=(10, 4.8))
    im = ax.imshow(t.values, aspect="auto", cmap="Greens", vmin=0)
    ax.set_yticks(range(12), AYLAR); ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_xlabel("Saat (TSİ)")
    for k in ax.spines.values():
        k.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.outline.set_visible(False)
    cb.set_label("Ortalama gölge fiyat [USD/MWh]", color=g.IKINCIL)
    g.baslik(fig, "Bağlantı kapasitesi en çok Temmuz–Ağustos öğleden sonralarında değerli",
             f"Şebeke kısıtının saatlik gölge fiyatı (1 MW ek bağlantının o saatteki değeri), ay × saat ortalaması. "
             f"Yıllık toplam: {df.sebeke_golge.sum():,.0f} USD/MW".replace(",", "."))
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b2_sebeke_golge_fiyati.png"); plt.close(fig)


def grafik_temsili(tablo):
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    et = ["12 gün", "24 gün", "48 gün", "Tam yıl"]
    renk = [g.SOLUK] * 3 + [g.MUREKKEP]
    axs[0].bar(et, tablo["NPV tahmini [M USD]"], color=renk); axs[0].set_title("NPV tahmini [M USD]", loc="left")
    axs[0].axhline(0, color=g.MUREKKEP, lw=0.8)
    axs[1].bar(et, tablo["RES [MW]"], color=g.RENK_RES, label="RES"); axs[1].bar(et, tablo["GES [MWac]"], bottom=tablo["RES [MW]"], color=g.RENK_GES, label="GES")
    axs[1].set_title("Optimal kapasite [MW]", loc="left"); axs[1].legend(fontsize=8, loc="lower right")
    axs[2].bar(et, tablo["Çözüm süresi [s]"], color=renk); axs[2].set_yscale("log"); axs[2].set_title("Çözüm süresi [s, log]", loc="left")
    for a, col in zip(axs, ["NPV tahmini [M USD]", "RES [MW]", "Çözüm süresi [s]"]):
        for i, val in enumerate(tablo[col]):
            a.text(i, val, f"{val:.1f}", ha="center", va="bottom", fontsize=8, color=g.MUREKKEP)
        g.eksen_sade(a)
    g.baslik(fig, "Temsilî günler kapasiteyi yakalıyor, NPV'yi ~0,7 M$ düşük tahmin ediyor",
             "Kapasite MILP'i, baz senaryo. Temsilî günler moment eşleştirmeli (ortalama fiyat ve KF tam yılla aynı).")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b3_temsili_vs_tam_yil.png"); plt.close(fig)


def grafik_senaryo(st, pis):
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"width_ratios": [1.4, 1]})
    ax = axs[0]
    et = [f"{a.split(' ')[0]}\n{b}" for a, b in zip(st["Fiyat"], st["Kanibalizasyon"])]
    x = np.arange(len(st)); w = 0.26
    ax.bar(x - w, st["RES [MW]"], w, color=g.RENK_RES, label="RES [MW] (kurulursa)")
    ax.bar(x, st["GES [MWac]"], w, color=g.RENK_GES, label="GES [MWac]")
    ax.bar(x + w, st["BESS [MWh]"] / 4, w, color="#7f6bd1", label="BESS [MWh] / 4")
    for i, r in st.iterrows():
        bos = r["RES [MW]"] < 0.5 and r["GES [MWac]"] < 0.5 and r["BESS [MWh]"] < 0.5
        metin = "Kârlı tasarım\nyok\nYAPMA" if bos else (f"NPV {r['Kurulursa NPV [M USD]']:+.1f}\n"
                                                         + ("YAPMA" if r["Optimal karar"] == "Yatırım yapma" else "KUR"))
        ax.text(i, max(r["RES [MW]"], r["GES [MWac]"], r["BESS [MWh]"] / 4) + 3, metin, ha="center", fontsize=7.5, color=g.MUREKKEP)
    ax.set_xticks(x, et, fontsize=8); ax.set_ylabel("Kapasite"); ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Kurulursa en iyi tasarım, NPV ve optimal karar (KUR / YAPMA)", loc="left")
    g.eksen_sade(ax)
    ax = axs[1]
    kol = [c for c in pis.columns if c not in ("Tasarım", "Seçildiği senaryo", "En büyük pişmanlık [M USD]")]
    M = pis[kol].to_numpy()
    im = ax.imshow(M, aspect="auto", cmap="Reds", vmin=0)
    ax.set_xticks(range(len(kol)), [c.replace(" (", "\n(").replace("/", "\n") for c in kol], fontsize=7)
    ax.set_yticks(range(len(pis)), [t.replace(" + ", "+\n", 1) for t in pis["Tasarım"]], fontsize=7)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.1f}", ha="center", va="center", fontsize=7, color=g.MUREKKEP if M[i, j] < M.max() * 0.6 else "white")
    ax.set_title("Pişmanlık [M USD]: o senaryonun optimumuna göre kayıp", loc="left")
    for k in ax.spines.values():
        k.set_visible(False)
    g.baslik(fig, "Senaryolar: asıl karar 'kurmak ya da kurmamak'; tasarım senaryolara dayanıklı",
             "Her senaryo için kapasite MILP'i (tam yıl, yatırım kararı ikili). Sağ: satırdaki tasarım, sütundaki senaryonun optimumuna göre NPV kaybı.")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b4_senaryo_tasarimlari.png"); plt.close(fig)


def grafik_sebeke(seb, bmaliyet):
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    renk = {"Baz (58)": g.RENK_HIBRIT, "Yüksek (72)": "#1d4f91"}
    for fiyat, d in seb.groupby("Fiyat", sort=False):
        axs[0].plot(d["Bağlantı [MW]"], d["NPV [M USD]"], color=renk[fiyat], lw=2, marker="o", markeredgecolor="white", label=fiyat)
        for _, r in d.iterrows():
            axs[0].annotate(f"RES {r['RES [MW]']:.0f}" + (f"\nGES {r['GES [MWac]']:.0f}" if r["GES [MWac]"] > 0.5 else "")
                            + (f"\nBESS {r['BESS [MWh]']:.0f}" if r["BESS [MWh]"] > 0.5 else ""),
                            (r["Bağlantı [MW]"], r["NPV [M USD]"]), xytext=(0, 7), textcoords="offset points",
                            ha="center", fontsize=6.5, color=g.IKINCIL)
        xm = (d["Bağlantı [MW]"].to_numpy()[1:] + d["Bağlantı [MW]"].to_numpy()[:-1]) / 2
        kay = -2.2 if fiyat.startswith("Baz") else 2.2
        axs[1].bar(xm + kay, d["Bağlantı maliyeti öncesi marjinal değer [M USD/MW]"].dropna(), 4, color=renk[fiyat], label=fiyat)
    axs[0].axhline(0, color=g.MUREKKEP, lw=0.8)
    axs[0].set_xlabel("Şebeke bağlantı kapasitesi [MW]"); axs[0].set_ylabel("Kurulursa en iyi tasarımın NPV'si [M USD]")
    axs[0].set_title("Her bağlantı boyutu için kapasiteler yeniden optimize edildi", loc="left"); axs[0].legend(fontsize=8)
    axs[1].axhline(bmaliyet, color=g.MUREKKEP, lw=1, ls="--")
    axs[1].text(31, bmaliyet, f"bağlantının kendi maliyeti\n≈ {bmaliyet:.2f} M USD/MW", va="bottom", fontsize=7.5, color=g.MUREKKEP)
    axs[1].set_xlabel("Bağlantı aralığı [MW]"); axs[1].set_ylabel("1 MW ek bağlantının değeri [M USD/MW, BD]")
    axs[1].set_title("Bağlantı maliyeti öncesi marjinal değer", loc="left")
    axs[1].set_ylim(0, 0.65); axs[1].legend(fontsize=8, loc="upper center", ncols=2)
    for a in axs:
        g.eksen_sade(a)
    g.baslik(fig, "Şebeke bağlantısının marjinal değeri: katkı payı için teklif tavanı",
             "Sağ: çubuk − kesikli çizgi = TEİAŞ yarışmasında MW başına ödenebilecek azami katkı payı (bugünkü değer). Kanibalizasyon devam.")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b4_sebeke_boyutu.png"); plt.close(fig)


def grafik_izgara(iz, opt_baz):
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    M = iz.to_numpy() - iz.to_numpy().max()
    im = ax.imshow(M, aspect="auto", cmap="Blues_r", origin="lower", vmax=0)
    ax.set_xticks(range(len(iz.columns)), iz.columns); ax.set_yticks(range(len(iz.index)), iz.index)
    ax.set_xlabel("GES [MWac]"); ax.set_ylabel("BESS enerji [MWh] (güç = enerji / 4)")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.1f}", ha="center", va="center", fontsize=7, color="white" if M[i, j] < M.min() * 0.5 else g.MUREKKEP)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.outline.set_visible(False)
    cb.set_label("En iyi hücreye göre NPV farkı [M USD]", color=g.IKINCIL)
    for k in ax.spines.values():
        k.set_visible(False)
    g.baslik(fig, "Optimum ne kadar düz? GES ve batarya eklemenin NPV maliyeti",
             f"RES {opt_baz['RES [MW]']:.1f} MW sabit, 50 MW bağlantı, baz senaryo; 24 temsilî gün. Hücre: en iyi tasarıma göre NPV farkı.")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "b4_ges_bess_npv_izgara.png"); plt.close(fig)


# =============================================================================
def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    h = Hazirlik()
    log(f"Temsilî hava yılı: {h.u.hava_yillari[h.w]} (10 yıl ortalama KF'ye ölçeklendi)")
    b1 = basamak1(h)
    b2 = basamak2(h)
    opt_baz, b3 = basamak3(h)
    b4 = basamak4(h, opt_baz)
    ozet = {"b1": b1, "b2": b2, "optimal_baz": opt_baz, "ayrintili": b4["ayrintili"],
            "baglanti_maliyeti_npv": b4["baglanti_maliyeti_npv"]}
    Path(CIKTI / "ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1, default=float))
    log(f"\nToplam süre: {(time.time() - t0) / 60:.1f} dk")


if __name__ == "__main__":
    main()
