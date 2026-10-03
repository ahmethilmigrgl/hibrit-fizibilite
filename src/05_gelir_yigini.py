"""
Aşama 5 — Bölüm A: gelir yığını ve sözleşme senaryolarıyla yeniden optimizasyon

Kombinasyonlar (kapasite MILP'i, tam yıl, kanibalizasyon devam):
    (1) Aşama 4 baz            (2) + yan hizmet + dengesizlik azaltımı + YEK-G
    (3) = (2) + PPA            (4) = (2) + depolamalı lisans          (5) = (2), yüksek fiyat (72)
Her tasarım hızlı değerleyiciyle (src/risk) değerlendirilir: NPV, IRR, öz kaynak IRR, borç, başabaş.
Bataryayı tasarıma sokan yan hizmet fiyatı eşiği ikiye bölmeyle bulunur.
Monte Carlo adayları: outputs/05_risk/adaylar.json

Çalıştırma: .venv/bin/python src/05_gelir_yigini.py  (~10-15 dk)
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.model import Varsayimlar
from src.finans.veri import uretim_profili
from src.optimizasyon.gelir_yigini import gelir_parametreleri
from src.optimizasyon.hibrit import temsili_hava_yili
from src.optimizasyon.kapasite import Segment, ekonomi_hesapla, kapasite_coz
from src.optimizasyon.temsili_gunler import segmentleri_kur
from src.risk.degerleme import Sabitler, borc_boyutla, irr_vektor, nakit_akislari, ozkaynak
from src.risk.isletme import Tasarim, tablo_uret
from src.risk.senaryo import a_yolu, birim_sekiller, h_yolu, yan_hizmet_sekli

CIKTI = CIKTILAR / "05_risk"
KAYNAK = ("Kaynak: kendi modelim (Pyomo + HiGHS). EPİAŞ PTF ve SFK kapasite fiyatları (2025-26), PVGIS, ERA5 (kalibre). "
          "Reel 2026 USD.")
KOMBINASYONLAR = {
    "(1) Aşama 4 baz": (set(), "baz"),
    "(2) + yan hizmet + dengesizlik + YEK-G": ({"yh", "dz", "yekg"}, "baz"),
    "(3) = (2) + PPA": ({"yh", "dz", "yekg", "ppa"}, "baz"),
    "(4) = (2) + depolamalı lisans": ({"yh", "dz", "yekg", "dl"}, "baz"),
    "(5) = (2), yüksek fiyat": ({"yh", "dz", "yekg"}, "yuksek"),
}


def log(*a):
    print(*a, flush=True)


class Ortam:
    def __init__(self):
        self.cfg = config_oku()
        self.u = uretim_profili()
        self.v = Varsayimlar.configten(self.cfg)
        self.c = Sabitler.configten(self.cfg, self.v)
        self.opt = {**{k: deger(x) for k, x in self.cfg["optimizasyon"].items()},
                    "verim_gd": deger(self.cfg["teknoloji"]["bess"]["verim_gidis_donus"])}
        w = temsili_hava_yili(self.u.ges, self.u.res, self.u.hava_yillari)
        self.g = self.u.ges[w] * self.u.ges.mean() / self.u.ges[w].mean()
        self.r = self.u.res[w] * self.u.res.mean() / self.u.res[w].mean()
        self.DF = (1 + self.v.wacc) ** -(self.v.insaat_suresi + np.arange(1, self.v.omur + 1))
        _, self.oran0 = birim_sekiller(self.cfg, self.u, [0.6])
        self.H = [0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70, round(self.oran0, 4)]
        self.sekiller, _ = birim_sekiller(self.cfg, self.u, self.H)
        self.yan = yan_hizmet_sekli(self.cfg)
        self.yillar = np.arange(deger(self.cfg["proje"]["baslangic_yili"]), deger(self.cfg["proje"]["baslangic_yili"]) + self.v.omur)
        yh = self.cfg["gelir_yigini"]["yan_hizmet"]
        self.sabit = dict(eta=float(np.sqrt(self.opt["verim_gd"])), yipranma=self.v.bess_yipranma, teias_e=self.v.teias_enerji,
                          yekg=self.c.yekg, rezerv_tavan=deger(yh["azami_rezerv"]), enerji_saat=deger(yh["enerji_saat"]),
                          ppa_fiyat=self.c.ppa_fiyat)
        self.yh_azalma, self.yh_taban = deger(yh["yillik_azalma"]), deger(yh["taban_oran"])
        self.kan_taban = deger(self.cfg["fiyat_senaryolari"]["kanibalizasyon"])["taban_oran"]

    def milp(self, kalemler, seviye="baz", K=None, yh_carpan=1.0, zaman=1200):
        f = fiyat_senaryosu_uret(self.cfg, self.u, seviye, "devam")
        p = (f.fiyatlar * self.DF[:, None, None]).sum(0) / self.DF.sum()
        eko = ekonomi_hesapla(self.v, float(p.mean()))
        gelir, yanlar = gelir_parametreleri(self.cfg, self.v, eko, f, kalemler, baz_seviye=f.seviye)
        if yanlar is not None:
            yanlar = [y * yh_carpan for y in yanlar]
        seg = segmentleri_kur([p[0], p[1]], self.g, self.r, K, Segment, yanlar)
        r = kapasite_coz(seg, self.v, eko, 50, self.opt, {}, gelir=gelir, zaman_siniri=zaman)
        r.pop("model", None)
        return r

    def tablo(self, t: Tasarim):
        """
        İşletme tablosu (diskte önbellekli: data/processed/isletme_tablolari/). Bataryasız tasarım kapalı formla
        ince ızgarada; bataryalı tasarım LP ile daha seyrek ızgarada hesaplanır (hata Bölüm B'de ölçülür).
        """
        import hashlib, pickle
        pil = t.bess_mw > 0.5
        if pil:
            H = [0.55, 0.62, 0.70, round(self.oran0, 4)]
            M = [0.80, 0.94, 1.08]
            A = [0.25, 0.6, 1.0] if t.yan_hizmet else [1.0]
        else:
            H, M, A = self.H, [0.78, 0.82, 0.86, 0.90, 0.94, 0.98, 1.02, 1.06, 1.10], [1.0]
        pp = [0.0, self.c.ppa_pay] if t.ppa else [0.0]
        anahtar = hashlib.md5(json.dumps([t.res_mw, t.ges_mw, round(t.bess_mw, 3), round(t.bess_mwh, 3), t.sebeke_mw,
                                          t.yan_hizmet, t.yekg, t.ppa, H, M, A, pp, self.sabit], default=float).encode()).hexdigest()[:12]
        klasor = ISLENMIS_VERI / "isletme_tablolari"; klasor.mkdir(exist_ok=True)
        dosya = klasor / f"{anahtar}.pkl"
        if dosya.exists():
            return pickle.loads(dosya.read_bytes())
        sek = self.sekiller if not pil else birim_sekiller(self.cfg, self.u, H)[0]
        tb = tablo_uret(t, self.u.ges, self.u.res, sek, self.yan, H, M, A, pp, 58.0, 1.0, self.sabit, log=log)
        dosya.write_bytes(pickle.dumps(tb))
        return tb

    def beklenen_girdi(self, L=58.0, taban=None, n=1, w=None):
        N = self.v.omur
        h = h_yolu(self.cfg, self.yillar, self.kan_taban if taban is None else taban, self.oran0)
        a = a_yolu(self.yillar, self.yh_azalma, self.yh_taban)
        girdi = {"h": np.tile(h, (n, 1)), "m": np.ones((n, N)), "a": np.tile(a, (n, 1)), "L": np.full((n, N), L),
                 "tavan": np.zeros((n, N), bool), **{k: np.ones(n) for k in ["capex_res", "capex_ges", "capex_bess", "opex", "bozunma"]}}
        if w is None:
            girdi["ws_ortalama"] = True
        else:   # hava yılı w sabit, şekil yılları ortalaması için iki ayrı simülasyon satırı
            girdi.update({"w": np.full((n, N), w[0]), "s": np.full((n, N), w[1])})
        return girdi

    def degerle(self, t: Tasarim, tb, L=58.0):
        """Beklenen değer NPV/IRR + P90'a göre borç + öz kaynak IRR + başabaş fiyat."""
        r = nakit_akislari(t, tb, self.c, self.beklenen_girdi(L))
        # P90 CFADS: her hava yılı (şekil yılları ortalamalı) için CFADS, yıl bazında ortalama − 1,282·σ
        cf = []
        for w in range(tb["T"].shape[0]):
            cf.append(np.mean([nakit_akislari(t, tb, self.c, self.beklenen_girdi(L, w=(w, s)))["cfads"][0] for s in range(2)], axis=0))
        cf = np.array(cf)
        cfads_p90 = cf.mean(0) - 1.2816 * cf.std(0, ddof=1)
        pay = None
        if t.ppa:
            k = np.arange(1, self.v.omur + 1)
            ppa_gelir = np.where(k <= self.c.ppa_vade, self.c.ppa_pay * self.c.ppa_fiyat * (r["E_res"] + r["E_ges"])[0], 0)
            pay = np.clip(ppa_gelir / np.maximum(r["favok"][0] + 1e-9, 1), 0, 1)
        borc = borc_boyutla(cfads_p90, float(r["capex_top"][0]), t, self.cfg, self.c, pay)
        oz = ozkaynak(r, borc, self.c)
        bb = brentq(lambda x: nakit_akislari(t, tb, self.c, self.beklenen_girdi(x))["npv"][0], 5, 250, xtol=0.01)
        return {"NPV [M USD]": r["npv"][0] / 1e6, "Proje IRR [%]": 100 * irr_vektor(r["sna"])[0],
                "Öz kaynak IRR reel [%]": 100 * oz["irr"][0], "Başabaş fiyat [USD/MWh]": bb,
                "Borç (P90) [M USD]": borc["borc_reel"] / 1e6, "Borç / CAPEX [%]": 100 * borc["borc_orani"],
                "Borç vadesi [yıl]": borc["vade"], "CAPEX [M USD]": float(r["capex_top"][0]) / 1e6,
                "Yan hizmet geliri yıl 1 [M USD]": float(np.atleast_2d(r["gelir_yh"])[0, 0]) / 1e6,
                "Batarya spot geliri yıl 1 [M USD]": float(r["gelir_bess"][0, 0]) / 1e6}


def tasarim_of(ad, r, kal):
    return Tasarim(ad, r["RES [MW]"] + r.get("Blok RES [MW]", 0), r["GES [MWac]"] + r.get("Blok GES [MWac]", 0),
                   max(r["BESS [MW]"], 0), max(r["BESS [MWh]"], 0), 50.0 + r.get("Ek bağlantı L2 [MW]", 0),
                   yan_hizmet="yh" in kal and r.get("Yan hizmete katılım", 0) == 1, dengesizlik_azaltim="dz" in kal,
                   yekg="yekg" in kal, ppa="ppa" in kal)


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    o = Ortam()
    satirlar, tasarimlar = [], {}
    for ad, (kal, sev) in KOMBINASYONLAR.items():
        r = o.milp(kal, sev)
        t = tasarim_of(ad, r, kal)
        tb = o.tablo(t)
        dg = o.degerle(t, tb, L=deger(o.cfg["fiyat_senaryolari"]["seviye"])[sev])
        tasarimlar[ad] = (t, r, dg)
        satir = {"Kombinasyon": ad, "Türbin": r["N"], "RES [MW]": t.res_mw, "GES [MWac]": t.ges_mw,
                 "BESS [MW]": t.bess_mw, "BESS [MWh]": t.bess_mwh, "Ek bağlantı [MW]": r.get("Ek bağlantı L2 [MW]", 0),
                 "MILP NPV tahmini [M USD]": r["NPV tahmini [M USD]"], **dg, "Kesinti [%]": r["Kesinti [%]"],
                 "BESS döngü/yıl": r["BESS döngü/yıl"], "Ort. rezerv [MW]": r["Ort. rezerv [MW]"],
                 "Gelir: yan hizmet [M USD/yıl, seviyeli]": r["Yan hizmet geliri [USD/yıl]"] / 1e6,
                 "Gelir: arbitraj [M USD/yıl]": r["Batarya: arbitraj [USD/yıl]"] / 1e6,
                 "Gelir: kesinti kurtarma [M USD/yıl]": r["Batarya: kesinti kurtarma [USD/yıl]"] / 1e6,
                 "Gelir: dengesizlik azaltımı [M USD/yıl]": r["Dengesizlik azaltımı [USD/yıl]"] / 1e6,
                 "MILP süresi [s]": r["Çözüm süresi [s]"], "MIP boşluğu": r["MIP boşluğu"]}
        satirlar.append(satir)
        log(f"{ad}: RES {t.res_mw:.1f} GES {t.ges_mw:.1f} BESS {t.bess_mw:.1f}/{t.bess_mwh:.1f} | NPV {dg['NPV [M USD]']:.2f} "
            f"IRR {dg['Proje IRR [%]']:.2f} öz {dg['Öz kaynak IRR reel [%]']:.2f} başabaş {dg['Başabaş fiyat [USD/MWh]']:.1f} "
            f"borç {dg['Borç (P90) [M USD]']:.1f} | MILP {r['Çözüm süresi [s]']:.0f}s")
    tablo = pd.DataFrame(satirlar)
    tablo.to_csv(CIKTI / "a3_yeniden_optimizasyon.csv", encoding="utf-8-sig", index=False, float_format="%.4f")

    # --- Bataryayı tasarıma sokan yan hizmet fiyatı eşiği (kombinasyon 2, 24 temsilî gün)
    log("\nYan hizmet fiyat eşiği aranıyor...")
    kal2 = {"yh", "dz", "yekg"}
    var_mi = lambda c_: o.milp(kal2, "baz", K=24, yh_carpan=c_)["BESS [MW]"] > 0.5
    alt, ust = 0.0, 1.0
    if var_mi(alt):
        esik = 0.0
    else:
        for _ in range(10):
            orta = (alt + ust) / 2
            alt, ust = (alt, orta) if var_mi(orta) else (orta, ust)
        esik = ust
    f = fiyat_senaryosu_uret(o.cfg, o.u, "baz", "devam")
    yh_lev = float((f.yan_hizmet.mean(axis=(1, 2)) * o.DF).sum() / o.DF.sum())
    yh_2026 = float(o.yan.mean())
    esik_bilgi = {"Eşik çarpanı": esik, "Seviyeli SFK fiyatı (baz yol) [USD/MW-saat]": yh_lev,
                  "Gerekli seviyeli SFK fiyatı [USD/MW-saat]": esik * yh_lev,
                  "2026 SFK seviyesi [USD/MW-saat]": yh_2026,
                  "Gerekli fiyatın 2026 seviyesine oranı": esik * yh_lev / yh_2026}
    log(esik_bilgi)
    # Yan hizmet olmadan dengesizlik + YEK-G batarya getiriyor mu?
    r_dz = o.milp({"dz", "yekg"}, "baz")
    esik_bilgi["Yalnız dengesizlik azaltımı + YEK-G ile BESS [MW]"] = r_dz["BESS [MW]"]
    pd.Series(esik_bilgi).to_csv(CIKTI / "a3_yan_hizmet_esigi.csv", encoding="utf-8-sig", header=["deger"])

    # --- Monte Carlo adayları
    adaylar = {
        "A: RES 58,8 (Aşama 4)": Tasarim("A: RES 58,8 (Aşama 4)", 58.8, 0.0),
        "B: (b) RES 50 + GES 25": Tasarim("B: (b) RES 50 + GES 25", 50.0, 25.0),
    }
    t2 = tasarimlar["(2) + yan hizmet + dengesizlik + YEK-G"][0]
    t3 = tasarimlar["(3) = (2) + PPA"][0]
    adaylar["C: gelir yığınlı optimal"] = Tasarim("C: gelir yığınlı optimal", t2.res_mw, t2.ges_mw, t2.bess_mw, t2.bess_mwh,
                                                 t2.sebeke_mw, t2.yan_hizmet, True, True, False)
    adaylar["D: gelir yığınlı + PPA"] = Tasarim("D: gelir yığınlı + PPA", t3.res_mw, t3.ges_mw, t3.bess_mw, t3.bess_mwh,
                                               t3.sebeke_mw, t3.yan_hizmet, True, True, True)
    adaylar["E: RES 58,8 + PPA"] = Tasarim("E: RES 58,8 + PPA", 58.8, 0.0, ppa=True)
    Path(CIKTI / "adaylar.json").write_text(json.dumps({k: t.__dict__ for k, t in adaylar.items()}, ensure_ascii=False, indent=1))
    grafik_gelir_yigini(tablo)
    log(f"Toplam süre {(time.time() - t0) / 60:.1f} dk")


def grafik_gelir_yigini(tablo):
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axs[0]
    kal = ["Gelir: yan hizmet [M USD/yıl, seviyeli]", "Gelir: arbitraj [M USD/yıl]", "Gelir: kesinti kurtarma [M USD/yıl]",
           "Gelir: dengesizlik azaltımı [M USD/yıl]"]
    renk = ["#7f6bd1", g.RENK_RES, g.RENK_GES, g.RENK_HIBRIT]
    et = [k.split(") ")[0] + ")" for k in tablo["Kombinasyon"]]
    alt = np.zeros(len(tablo))
    for k, r in zip(kal, renk):
        val = tablo[k].clip(lower=0).to_numpy()
        ax.bar(et, val, 0.6, bottom=alt, color=r, label=k.split(": ")[1].split(" [")[0])
        alt += val
    for i, (b, e) in enumerate(zip(tablo["BESS [MW]"], tablo["BESS [MWh]"])):
        ax.text(i, alt[i] + 0.05, f"{b:.0f} MW\n{e:.0f} MWh" if b > 0.5 else "batarya\nyok", ha="center", fontsize=7.5, color=g.MUREKKEP)
    ax.set_ylabel("Batarya geliri [M USD/yıl, seviyelendirilmiş]")
    ax.set_title("Batarya gelir yığını", loc="left"); ax.legend(fontsize=8, loc="upper left")
    ax.set_ylim(0, alt.max() * 1.25 + 0.3)
    g.eksen_sade(ax)
    ax = axs[1]
    ax.barh(et[::-1], tablo["NPV [M USD]"][::-1], color=[g.RENK_HIBRIT if x > 0 else g.SOLUK for x in tablo["NPV [M USD]"][::-1]])
    for i, (npv, bb) in enumerate(zip(tablo["NPV [M USD]"][::-1], tablo["Başabaş fiyat [USD/MWh]"][::-1])):
        ax.text(max(npv, 0) + 0.5, i, f"{npv:+.1f} M$ | başabaş {bb:.0f}", va="center", ha="left", fontsize=8, color=g.MUREKKEP)
    ax.axvline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xlabel("NPV [M USD]"); ax.set_title("Optimal tasarımın NPV'si ve başabaş fiyatı", loc="left")
    lo, hi = tablo["NPV [M USD]"].min(), tablo["NPV [M USD]"].max()
    ax.set_xlim(min(lo, 0) - 12, hi + 18)
    g.eksen_sade(ax, izgara="x")
    g.baslik(fig, "Yan hizmet geliri bataryayı tasarıma sokuyor",
             "Kombinasyonlar: (1) Aşama 4 baz, (2) + yan hizmet + dengesizlik + YEK-G, (3) + PPA, (4) + depolamalı lisans, (5) = (2) yüksek fiyat.")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "a3_batarya_gelir_yigini.png"); plt.close(fig)


if __name__ == "__main__":
    main()
