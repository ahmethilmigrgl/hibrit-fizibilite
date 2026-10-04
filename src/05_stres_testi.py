"""
Aşama 6 — Bölüm A: yan hizmet (SFK) doyum stres testi

1. Fırsat maliyeti: bataryanın SFK'ya rezerv ayırınca vazgeçtiği spot gelir + yıpranma [USD/MW-saat]
   (doyan piyasada SFK fiyatının ineceği taban).
2. Doyum senaryoları: Türkiye batarya yol haritası × SFK ihtiyacı → SFK fiyat çarpanı (src/risk/doyum.py).
3. Fırsat penceresi: SFK geliri yalnızca ilk N yıl sürerse NPV; başabaş için minimum pencere.
4. Monte Carlo (doyum senaryoları olasılıklarla ağırlıklı): A, C, D, E ve esnek tasarımlar.
5. Erteleme: devreye alma 0-3 yıl gecikirse beklenen NPV; "bekle ve gör" değeri.

Çıktılar: outputs/05_risk/s_*.png, s_*.csv. Eski Monte Carlo sonuçları outputs/05_risk/revizyon_oncesi/.
Çalıştırma: .venv/bin/python src/05_stres_testi.py  (ilk çalıştırmada işletme tabloları ~30-60 dk)
"""

import importlib.util
import json
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, deger
from src.risk.degerleme import AI, irr_vektor, nakit_akislari, ozkaynak
from src.risk.doyum import SENARYO_ADLARI, deterministik_yol, kurulu_yol, ornekle_doyum
from src.risk.isletme import Tasarim
from src.risk.monte_carlo import ornekle

CIKTI = CIKTILAR / "05_risk"
KAYNAK = (
    "Kaynak: kendi modelim (Monte Carlo + Pyomo/HiGHS işletme tabloları). Doyum kalibrasyonu: İngiltere DC (Modo, Timera), "
    "Almanya FCR; Türkiye depolama: EPDK, ETKB, EDEDER. Reel 2026 USD."
)
A_DUSUK = [0.02, 0.05, 0.10]
RENK = {
    "A": g.RENK_RES,
    "C": "#7f6bd1",
    "D": g.RENK_HIBRIT,
    "E": "#1d4f91",
    "F1": g.RENK_GES,
    "F2": "#b8860b",
    "F2a": "#c9a227",
    "F2P": "#8c3b1a",
}
SENARYO_RENK = {"yavas": g.RENK_HIBRIT, "baz": g.RENK_RES, "hizli": g.RENK_GES, "katilamama": g.SOLUK}

spec = importlib.util.spec_from_file_location("gy", Path(__file__).parent / "05_gelir_yigini.py")
gy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gy)
spec = importlib.util.spec_from_file_location("mc", Path(__file__).parent / "05_monte_carlo.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def log(*a):
    print(*a, flush=True)


def kisa(ad):
    return ad.split(":")[0]


def doyum_tablosu(o, t: Tasarim) -> dict:
    """Yan hizmet çarpanı ızgarası 0 (katılım yok) … 1 olacak şekilde birleştirilmiş işletme tablosu."""
    if t.bess_mw < 0.5 or not t.yan_hizmet:
        return o.tablo(t)
    sifir = o.tablo(replace(t, yan_hizmet=False))  # a = 0: rezerv yok
    dusuk = o.tablo(t, A_ozel=A_DUSUK)
    ust = o.tablo(t)  # 0,25 / 0,6 / 1,0 (Aşama 5 önbelleği)
    T = np.concatenate([sifir["T"], dusuk["T"], ust["T"]], axis=4)
    return {**ust, "T": T, "a": np.array([0.0] + A_DUSUK + list(ust["a"]))}


def firsat_maliyeti(o, t: Tasarim, tb: dict, L: float = 58.0) -> dict:
    """
    SFK fırsat maliyeti [USD/MW-saat] — doymuş piyasada fiyatın ineceği taban.

    (1) Piyasa tabanı (kullanılan): tipik bağımsız bataryanın (Türkiye ön lisans ortalaması ~1,1 saat, şebekeden şarj)
        SFK'ya rezerv ayırınca vazgeçtiği arbitraj kârı (yıpranma sonrası) / (P × 8.760). Aşama 4 Basamak 1 arbitraj
        LP'si, iki fiyat şekli yılı × baz seviye, 1 ve 2 saatlik bataryalar arasında doğrusal.
    (2) Bilgi için: bu projenin (santralden şarj olan) bataryasının fırsat maliyeti — a = 0 ile a = 0,02 arasındaki
        spot + dengesizlik değeri farkı / ayrılan rezerv. Çok düşükse proje bataryası "inframarjinal": fiyat tabana
        inse de SFK'da kalır.
    """
    from src.finans.veri import fiyat_sekil_yillari
    from src.optimizasyon.batarya import arbitraj_coz

    st = o.cfg["stres_testi"]
    sekil, _ = fiyat_sekil_yillari(*deger(o.cfg["fiyat_senaryolari"]["sekil_donemi"]))
    kar = {}
    for saat in (1.0, 2.0):
        kar[saat] = np.mean(
            [
                arbitraj_coz(L * q / q.mean(), 10.0, 10.0 * saat, o.opt["verim_gd"], o.v.bess_yipranma)[1]["Amaç (gelir − yıpranma) [USD]"]
                for q in sekil
            ]
        ) / (10.0 * 8760)
    sure = deger(st["marjinal_batarya_suresi"])
    cb = kar[1.0] + (kar[2.0] - kar[1.0]) * (sure - 1.0)
    T = tb["T"][:, :, -1, 1, :, 0].mean((0, 1))  # (a, alan): tüm hava ve şekil yılları, h = başlangıç, m = 0,94
    v, c = o.v, o.c

    def deger_(x):
        spot = L * (x[AI["gelir_ges_q"]] + x[AI["gelir_res_q"]] + x[AI["gelir_d_q"]])
        satis = x[AI["E_ges"]] + x[AI["E_res"]] + x[AI["E_d"]]
        serbest = max(t.bess_mw - x[AI["rezerv"]] / 8760, 0)
        dz = c.dz_azami * min(serbest / (c.dz_doyum * t.res_mw), 1) * v.dengesizlik["res"] * L * x[AI["gelir_res_q"]]
        return spot - v.teias_enerji * satis - v.bess_yipranma * x[AI["E_d"]] + dz

    proje_cb = (deger_(T[0]) - deger_(T[1])) / T[1, AI["rezerv"]]
    p0 = float(o.yan.mean())
    return {
        "Fırsat maliyeti [USD/MW-saat]": cb,
        "2026 SFK seviyesi [USD/MW-saat]": p0,
        "Fırsat maliyeti / 2026 seviyesi": cb / p0,
        "1 saatlik bağımsız batarya arbitraj kârı [USD/MW-saat]": kar[1.0],
        "2 saatlik bağımsız batarya arbitraj kârı [USD/MW-saat]": kar[2.0],
        "Proje bataryasının kendi fırsat maliyeti [USD/MW-saat]": proje_cb,
    }


def deterministik_npv(o, t, tb, a_yol, L=58.0):
    o.a_ozel = a_yol
    r = nakit_akislari(t, tb, o.c, o.beklenen_girdi(L))
    o.a_ozel = None
    return float(r["npv"][0]) / 1e6


def kes(girdi: dict, k: int, N: int) -> dict:
    """Uzatılmış (takvim) girdilerden k yıl ertelenmiş projenin N işletme yılını keser."""
    return {kk: (v[:, k : k + N] if (np.ndim(v) == 2) else v) for kk, v in girdi.items()}


def asamali_girdi(o, gk: dict, kucuk: Tasarim, buyuk: Tasarim, tb_buyuk: dict, es: dict, k: int) -> dict:
    """Aşamalı yatırım: karar yılı sonunda SFK çarpanı ≥ eşik ise sonraki yıllarda büyük tasarımın işletmesi + ek CAPEX/O&M."""
    n, N = gk["L"].shape
    ky = es["karar_yili"]
    buyut = gk["a"][:, ky - 1] >= es["esik"]
    maske = np.zeros((n, N), bool)
    maske[:, ky:] = buyut[:, None]
    v = o.v
    ek_capex = (buyuk.bess_mw - kucuk.bess_mw) * v.capex_bess_guc + (buyuk.bess_mwh - kucuk.bess_mwh) * v.capex_bess_enerji
    dusus = (1 - deger(o.cfg["stres_testi"]["bess_capex_dususu"])) ** (v.insaat_suresi + ky + k)
    ek = np.zeros((n, N))
    ek[:, ky] = ek_capex * gk["capex_bess"] * dusus
    ek[:, ky + 1 :] = (v.opex_bess_oran * ek_capex * gk["capex_bess"] * dusus)[:, None]
    ek *= buyut[:, None]
    return {**gk, "tablo2": tb_buyuk, "maske2": maske, "ek_gider": ek}, buyut


def borc_boyutla_L(o, t, tb, L):
    """mc.borc_deterministik'in fiyat seviyesi parametreli hâli (P90 CFADS, hava yılları dağılımından)."""
    from src.risk.degerleme import borc_boyutla

    cf = np.array(
        [
            np.mean([nakit_akislari(t, tb, o.c, o.beklenen_girdi(L, w=(w, s)))["cfads"][0] for s in range(2)], axis=0)
            for w in range(tb["T"].shape[0])
        ]
    )
    cfads_p90 = cf.mean(0) - 1.2816 * cf.std(0, ddof=1)
    r = nakit_akislari(t, tb, o.c, o.beklenen_girdi(L))
    pay = None
    if t.ppa:
        k = np.arange(1, o.v.omur + 1)
        ppa_gelir = np.where(k <= o.c.ppa_vade, o.c.ppa_pay * o.c.ppa_fiyat * (r["E_res"] + r["E_ges"])[0], 0)
        pay = np.clip(ppa_gelir / np.maximum(r["favok"][0], 1), 0, 1)
    return borc_boyutla(cfads_p90, float(r["capex_top"][0]), t, o.cfg, o.c, pay)


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    eski = CIKTI / "revizyon_oncesi"
    eski.mkdir(exist_ok=True)
    for f in ["b_metrikler.csv", "b_varyans_katkisi.csv", "b_npv_dagilim_cdf.png", "b_risk_getiri.png", "b_dscr_dagilimi.png"]:
        if (CIKTI / f).exists() and not (eski / f).exists():
            shutil.copy(CIKTI / f, eski / f)
    t0 = time.time()
    o = gy.Ortam()
    cfg, st = o.cfg, o.cfg["stres_testi"]
    ad = {k: Tasarim(**v) for k, v in json.loads((CIKTI / "adaylar.json").read_text()).items()}
    A_, C_, D_, E_ = (ad[k] for k in ad if k[0] in "ACDE")
    es = deger(st["esnek_tasarimlar"])
    F1 = replace(
        C_, ad="F1: uzun süreli batarya (40 MW / 160 MWh)", bess_mw=es["uzun_sureli"]["bess_mw"], bess_mwh=es["uzun_sureli"]["bess_mwh"]
    )
    F2a = replace(C_, ad="F2a: küçük batarya (30 MW / 52,5 MWh)", bess_mw=es["asamali"]["ilk_mw"], bess_mwh=es["asamali"]["ilk_mwh"])
    F2 = replace(F2a, ad="F2: aşamalı (30 → 40 MW)")
    F2P = replace(F2a, ad="F2P: aşamalı + PPA (30 → 40 MW)", ppa=True)
    tasarimlar = {"A": A_, "C": C_, "D": D_, "E": E_, "F1": F1, "F2a": F2a, "F2": F2, "F2P": F2P}
    asamali = {"F2": (F2a, C_, "C"), "F2P": (F2P, D_, "D")}  # (ilk tasarım, büyütülmüş tasarım, büyük tablo)

    log("İşletme tabloları (önbellekli)...")
    tb = {}
    for k, t in tasarimlar.items():
        if k == "F2":
            continue
        tb[k] = doyum_tablosu(o, t)
        log(f"  {k}: hazır ({(time.time() - t0) / 60:.1f} dk)")
    tb["F2"] = tb["F2a"]

    # ---------------- 1. Fırsat maliyeti
    fm = firsat_maliyeti(o, C_, tb["C"])
    firsat_oran = fm["Fırsat maliyeti / 2026 seviyesi"]
    pd.Series(fm).to_csv(CIKTI / "s_firsat_maliyeti.csv", encoding="utf-8-sig", header=["deger"])
    log("Fırsat maliyeti: " + ", ".join(f"{k} {v:.3f}" for k, v in fm.items()))

    # ---------------- 2. Senaryo yolları (deterministik)
    yillar = o.yillar
    yollar = {s: deterministik_yol(cfg, s, yillar, firsat_oran) for s in SENARYO_ADLARI}
    pd.DataFrame({"yil": yillar, **{SENARYO_ADLARI[s]: y for s, y in yollar.items()}}).to_csv(
        CIKTI / "s_sfk_carpan_yollari.csv", encoding="utf-8-sig", index=False, float_format="%.4f"
    )

    # ---------------- 3. Fırsat penceresi (deterministik, baz fiyat 58)
    log("Fırsat penceresi...")
    k_ = np.arange(1, o.v.omur + 1)
    Ns = list(range(0, 16))
    pencere, pencere0 = {}, {}
    for k in ["C", "D", "F1", "F2a"]:
        pencere[k] = [deterministik_npv(o, tasarimlar[k], tb[k], np.where(k_ <= N, 1.0, firsat_oran)) for N in Ns]
        # Karamsar varyant: pencere kapanınca SFK geliri tamamen biter (taban 0)
        pencere0[k] = [deterministik_npv(o, tasarimlar[k], tb[k], np.where(k_ <= N, 1.0, 0.0)) for N in Ns]
    ref = {"A": deterministik_npv(o, A_, tb["A"], np.zeros(o.v.omur)), "E": deterministik_npv(o, E_, tb["E"], np.zeros(o.v.omur))}
    pdf = pd.DataFrame({"N [yıl]": Ns, **{tasarimlar[k].ad: v for k, v in pencere.items()}})
    pdf.to_csv(CIKTI / "s_pencere.csv", encoding="utf-8-sig", index=False, float_format="%.3f")

    def kesisim(y, esik):
        y = np.array(y) - esik
        if y[0] >= 0:
            return 0.0
        j = np.argmax(y >= 0)
        return float("nan") if y[j] < 0 else Ns[j - 1] + (-y[j - 1]) / (y[j] - y[j - 1])

    min_pencere = []
    for k in pencere:
        karsi = "E" if tasarimlar[k].ppa else "A"
        min_pencere.append(
            {
                "Tasarım": tasarimlar[k].ad,
                "NPV (N=0) [M USD]": pencere[k][0],
                **{f"NPV (N={N}) [M USD]": pencere[k][N] for N in deger(st["pencere_yillari"]) if N > 0},
                "Minimum pencere: NPV ≥ 0 [yıl]": kesisim(pencere[k], 0.0),
                "Minimum pencere: bataryasız alternatiften iyi [yıl]": kesisim(pencere[k], ref[karsi]),
                "Minimum pencere (taban 0): NPV ≥ 0 [yıl]": kesisim(pencere0[k], 0.0),
                "Minimum pencere (taban 0): bataryasız alternatiften iyi [yıl]": kesisim(pencere0[k], ref[karsi]),
                "Bataryasız alternatif": f"{karsi}: {ref[karsi]:.2f} M USD",
            }
        )
    min_pencere = pd.DataFrame(min_pencere)
    min_pencere.to_csv(CIKTI / "s_minimum_pencere.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log(min_pencere.round(2).to_string(index=False))

    # Deterministik senaryo NPV'leri
    det = []
    for k, t in tasarimlar.items():
        if k in ("F2", "F2P"):
            continue
        det.append({"Tasarım": t.ad, **{SENARYO_ADLARI[s]: deterministik_npv(o, t, tb[k], y) for s, y in yollar.items()}})
    det = pd.DataFrame(det)
    det.to_csv(CIKTI / "s_senaryo_npv_deterministik.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log(det.round(2).to_string(index=False))

    # Baz doyum yolunda deterministik özet (NPV, IRR, başabaş fiyat, P90 borç) — statik tasarımlar
    ozet = []
    o.a_ozel = yollar["baz"]
    for k in ["A", "C", "D", "E", "F1", "F2a"]:
        ozet.append({"Tasarım": tasarimlar[k].ad, **o.degerle(tasarimlar[k], tb[k])})
    F2aP = replace(F2a, ad="F2aP: küçük batarya + PPA (30 MW / 52,5 MWh)", ppa=True)
    ozet.append({"Tasarım": F2aP.ad, **o.degerle(F2aP, doyum_tablosu(o, F2aP))})
    o.a_ozel = None
    ozet = pd.DataFrame(ozet)
    ozet.to_csv(CIKTI / "s_deterministik_baz_doyum.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log("\nBaz doyum, deterministik:\n" + ozet.iloc[:, :8].round(2).to_string(index=False))

    # ---------------- 4. Monte Carlo (doyum) + 5. erteleme
    n = deger(cfg["monte_carlo"]["senaryo_sayisi"])
    tohum = deger(cfg["monte_carlo"]["tohum"])
    Kmax = max(deger(st["erteleme_yillari"]))
    N = o.v.omur
    yil_ext = np.arange(yillar[0], yillar[0] + N + Kmax)
    ornek = ornekle(cfg, n, yil_ext, o.oran0, tohum)
    girdi_ext, sur = ornek["girdi"], ornek["suruculer"]
    dy = ornekle_doyum(cfg, n, yil_ext, firsat_oran, tohum)
    girdi_ext["a"] = dy["a"]
    senaryo = dy["senaryo"]
    sur["Fiyat yolu (iskontolu ort.)"] = (girdi_ext["L"][:, :N] * (1.07 ** -(np.arange(N) + 3))).sum(1)
    log(f"{n} simülasyon; senaryo payları: " + ", ".join(f"{s} {np.mean(senaryo == s):.2f}" for s in dy["adlar"]))

    # Borç: baz doyum senaryosunun merkezî yoluyla, P90 üretim (Aşama 5 yöntemi)
    o.a_ozel = yollar["baz"]
    borclar = {k: mc.borc_deterministik(o, t, tb[k]) for k, t in tasarimlar.items()}
    # Muhafazakâr borç: SFK geliri yok ve düşük fiyat senaryosu (45 $/MWh) ile P90 üretim
    o.a_ozel = np.zeros(N)
    borclar_m = {k: borc_boyutla_L(o, t, tb[k], 45.0) for k, t in tasarimlar.items()}
    o.a_ozel = None

    dusus = deger(st["bess_capex_dususu"])
    npv_k, sonuc, buyutme = {}, {}, None
    for k, t in tasarimlar.items():
        npv_k[k] = {}
        for kd in deger(st["erteleme_yillari"]):
            gk = kes(girdi_ext, kd, N)
            gk["capex_bess"] = girdi_ext["capex_bess"] * (1 - dusus) ** kd
            if k in asamali:
                kucuk, buyuk, tb_ad = asamali[k]
                gk, buyut = asamali_girdi(o, gk, kucuk, buyuk, tb[tb_ad], es["asamali"], kd)
                if kd == 0 and k == "F2":
                    buyutme = buyut
            r = nakit_akislari(t, tb[k], o.c, gk)
            npv_k[k][kd] = r["npv"] * (1 + o.v.wacc) ** -kd
            if kd == 0:
                oz = ozkaynak(r, borclar[k], o.c)
                ozm = ozkaynak(r, borclar_m[k], o.c)
                sonuc[k] = {
                    "npv": r["npv"],
                    "irr": irr_vektor(r["sna"]),
                    "oz_irr": oz["irr"],
                    "dscr_min": oz["dscr_min"],
                    "enerji": r["satilan"],
                    "dscr_min_m": ozm["dscr_min"],
                    "oz_irr_m": ozm["irr"],
                }
    log(f"Monte Carlo + erteleme: {(time.time() - t0) / 60:.1f} dk")

    satir, sen_npv = [], []
    for k, t in tasarimlar.items():
        s_ = sonuc[k]
        mt = mc.metrikler(s_["npv"], s_["irr"], s_["oz_irr"], s_["dscr_min"], s_["enerji"])
        npv = s_["npv"]
        kosullu = {s: npv[senaryo == s].mean() for s in dy["adlar"]}
        pay = {s: np.mean(senaryo == s) for s in dy["adlar"]}
        evppi_doyum = sum(pay[s] * max(kosullu[s], 0) for s in dy["adlar"]) - max(npv.mean(), 0)
        satir.append(
            {
                "Tasarım": t.ad,
                **{
                    kk: mt[kk]
                    for kk in [
                        "Beklenen NPV [M USD]",
                        "NPV P10 [M USD]",
                        "NPV P50 [M USD]",
                        "NPV P90 [M USD]",
                        "P(NPV > 0) [%]",
                        "CVaR %5 [M USD]",
                        "Proje IRR P50 [%]",
                        "P(herhangi bir yılda DSCR < 1) [%]",
                        "EVPI [M USD]",
                    ]
                },
                "EVPPI doyum senaryosu [M USD]": evppi_doyum / 1e6,
                "EVPPI fiyat [M USD]": mc.evppi(npv, sur["Fiyat yolu (iskontolu ort.)"]) / 1e6,
                "Borç (P90, baz doyum) [M USD]": borclar[k]["borc_reel"] / 1e6,
                "Öz kaynak IRR P50 [%]": 100 * np.nanpercentile(s_["oz_irr"], 50),
                "Muhafazakâr borç [M USD]": borclar_m[k]["borc_reel"] / 1e6,
                "P(DSCR < 1), muhafazakâr borç [%]": 100 * (s_["dscr_min_m"] < 1).mean(),
                "Öz kaynak IRR P50, muhafazakâr borç [%]": 100 * np.nanpercentile(s_["oz_irr_m"], 50),
            }
        )
        sen_npv.append({"Tasarım": t.ad, **{SENARYO_ADLARI[s]: kosullu[s] / 1e6 for s in dy["adlar"]}})
    np.savez_compressed(
        CIKTI / "s_npv_ornekleri.npz", senaryo=senaryo, **{k: (sonuc[k]["npv"] / 1e6).astype(np.float32) for k in tasarimlar}
    )
    metr = pd.DataFrame(satir)
    metr.to_csv(CIKTI / "s_metrikler.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    sen_npv = pd.DataFrame(sen_npv)
    sen_npv.to_csv(CIKTI / "s_senaryo_npv.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log("\n" + metr.round(2).to_string(index=False))
    log("\nSenaryoya göre E[NPV]:\n" + sen_npv.round(2).to_string(index=False))
    log(f"Aşamalı tasarımda büyütme olasılığı: {100 * buyutme.mean():.1f}%")

    # Erteleme ve "bekle-gör": k yıl sonra doyum senaryosu gözlenmiş olur → o senaryoda en iyi tasarım ya da hiç
    ert = []
    for kd in deger(st["erteleme_yillari"]):
        row = {"Erteleme [yıl]": kd}
        for k, t in tasarimlar.items():
            row[t.ad] = npv_k[k][kd].mean() / 1e6
        en_iyi_simdi = max(npv_k[k][kd].mean() for k in tasarimlar)
        bekle = sum(np.mean(senaryo == s) * max(max(npv_k[k][kd][senaryo == s].mean() for k in tasarimlar), 0) for s in dy["adlar"])
        row["En iyi tasarım (bilgisiz) [M USD]"] = max(en_iyi_simdi, 0) / 1e6
        row["Bekle-gör: senaryo bilinerek seçim [M USD]"] = bekle / 1e6
        ert.append(row)
    ert = pd.DataFrame(ert)
    ert.to_csv(CIKTI / "s_erteleme.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log("\nErteleme:\n" + ert.round(2).to_string(index=False))

    # Varyans katkısı (doyum sürücüleri dahil)
    sur_all = {**{k: (v[:, :] if np.ndim(v) == 2 else v) for k, v in sur.items() if not k.startswith("Yan hizmet")}, **dy["suruculer"]}
    sur_all["Hava (ort. RES yılı)"] = o.u.res.mean(1)[girdi_ext["w"][:, :N]].mean(1)
    katki = pd.DataFrame(
        {
            tasarimlar[k].ad: {s: 100 * mc.birinci_derece(sonuc[k]["npv"], v) for s, v in sur_all.items()}
            for k in ["A", "C", "D", "F1", "F2P"]
        }
    ).round(2)
    katki.to_csv(CIKTI / "s_varyans_katkisi.csv", encoding="utf-8-sig")
    log("\nVaryans katkısı [%]:\n" + katki.to_string())

    grafikler(o, cfg, st, yil_ext, girdi_ext, dy, yollar, yillar, pdf, ref, min_pencere, metr, sonuc, tasarimlar, ert, sen_npv, fm)
    log(f"Toplam süre {(time.time() - t0) / 60:.1f} dk")


def grafikler(o, cfg, st, yil_ext, girdi_ext, dy, yollar, yillar, pdf, ref, min_pencere, metr, sonuc, tasarimlar, ert, sen_npv, fm):
    # 1) Doyum senaryoları
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 4.6))
    ax = axs[0]
    yy = np.arange(2025, 2036)
    sc = deger(st["senaryolar"])
    theta = float(np.mean(deger(st["sfk_uygun_pay"])))
    D = deger(st["sfk_ihtiyaci"]) * (1 + deger(st["ihtiyac_buyume"])) ** (yy - 2026)
    for s in ["yavas", "baz", "hizli"]:
        ax.plot(yy, theta * kurulu_yol(sc[s]["kurulu_mw"], yy) / 1e3, color=SENARYO_RENK[s], lw=2, label=SENARYO_ADLARI[s])
    ax.plot(yy, D / 1e3, color=g.MUREKKEP, lw=1.2, ls="--", label="SFK ihtiyacı")
    ax.plot(yy, deger(st["doyum_tam"]) * D / 1e3, color=g.SOLUK, lw=1, ls=":", label=f"Tam doyum ({deger(st['doyum_tam']):.0f} × ihtiyaç)")
    ax.set_yscale("log")
    ax.set_ylabel("SFK'ya teklif veren batarya [GW, log]")
    ax.set_title("Batarya yol haritası ve SFK ihtiyacı", loc="left")
    ax.legend(fontsize=7.5)
    g.eksen_sade(ax, izgara="both")
    ax = axs[1]
    a = dy["a"][:, : len(yillar)]
    ax.fill_between(
        yillar, np.percentile(a, 10, 0), np.percentile(a, 90, 0), color=g.RENK_RES, alpha=0.15, lw=0, label="Monte Carlo P10–P90"
    )
    for s, y in yollar.items():
        ax.plot(yillar, y, color=SENARYO_RENK[s], lw=2, label=SENARYO_ADLARI[s])
    ax.axhline(fm["Fırsat maliyeti / 2026 seviyesi"], color=g.MUREKKEP, lw=0.8, ls=":")
    ax.text(
        2039.5,
        fm["Fırsat maliyeti / 2026 seviyesi"] + 0.02,
        f"taban: fırsat maliyeti {fm['Fırsat maliyeti [USD/MW-saat]']:.1f} $/MW-saat".replace(".", ","),
        ha="right",
        fontsize=7.5,
        color=g.IKINCIL,
    )
    ax.set_xlim(yillar[0], 2040)
    ax.set_ylim(-0.03, 1.05)
    ax.set_ylabel("SFK fiyatı / 2026 seviyesi")
    ax.set_title("SFK fiyat çarpanı (işletme yılları)", loc="left")
    ax.legend(fontsize=7.5)
    g.eksen_sade(ax, izgara="both")
    g.baslik(
        fig,
        "Doyum: SFK piyasası küçük, batarya boru hattı büyük",
        "Batarya ihtiyacın 0,8 katını aşınca fiyat düşmeye başlar, 2 katında fırsat maliyetine iner (İngiltere/Almanya kalibrasyonu).",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_doyum_senaryolari.png")
    plt.close(fig)

    # 2) Fırsat penceresi
    fig, ax = plt.subplots(figsize=(10, 4.8))
    Ns = pdf["N [yıl]"]
    for k in ["C", "D", "F1", "F2a"]:
        t = tasarimlar[k]
        ax.plot(Ns, pdf[t.ad], color=RENK[k], lw=2, marker="o", ms=3.5, label=t.ad)
    ax.axhline(ref["A"], color=RENK["A"], lw=1.2, ls="--")
    ax.axhline(ref["E"], color=RENK["E"], lw=1.2, ls=":")
    ax.text(
        15.2, ref["A"] + 0.4, f"A: yalnız RES ({ref['A']:.1f})".replace(".", ","), ha="right", va="bottom", fontsize=7.5, color=g.IKINCIL
    )
    ax.text(15.2, ref["E"] - 0.4, f"E: RES + PPA ({ref['E']:.1f})".replace(".", ","), ha="right", va="top", fontsize=7.5, color=g.IKINCIL)
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xlabel("SFK geliri süren yıl sayısı N (sonra fırsat maliyeti tabanı)")
    ax.set_ylabel("NPV [M USD]")
    ax.legend(fontsize=7.5, loc="upper left")
    g.eksen_sade(ax, izgara="both")
    r = min_pencere.set_index("Tasarım")
    alt = "; ".join(f"{kisa(i)} {v:.1f}".replace(".", ",") for i, v in r["Minimum pencere (taban 0): NPV ≥ 0 [yıl]"].items())
    g.baslik(
        fig,
        "Fırsat penceresi: SFK geliri kaç yıl sürmeli?",
        "Pencere boyunca SFK 2026 seviyesinde, sonra fırsat maliyeti tabanında. Taban sıfır olsa bile NPV ≥ 0 için gereken yıl: "
        + alt
        + ". Baz fiyat 58 $/MWh.",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_firsat_penceresi.png")
    plt.close(fig)

    # 3) Risk-getiri (yeni) + revizyon öncesi konumlar
    fig, ax = plt.subplots(figsize=(10, 5.2))
    eski_dosya = CIKTI / "revizyon_oncesi" / "b_metrikler.csv"
    if eski_dosya.exists():
        eski = pd.read_csv(eski_dosya)
        for _, r_ in eski.iterrows():
            k = kisa(r_["Tasarım"])
            if k in ("C", "D"):
                ax.scatter(r_["CVaR %5 [M USD]"], r_["Beklenen NPV [M USD]"], s=90, facecolor="none", edgecolor=RENK[k], lw=1.5)
                ax.annotate(
                    f"{k} (Aşama 5, doyumsuz)",
                    (r_["CVaR %5 [M USD]"], r_["Beklenen NPV [M USD]"]),
                    xytext=(8, 0),
                    textcoords="offset points",
                    fontsize=7.5,
                    color=g.IKINCIL,
                    va="center",
                )
    ofset = {"C": (-8, 6, "right"), "F2": (0, 10, "center"), "D": (0, -16, "center"), "F2P": (8, -3, "left")}
    for _, r_ in metr.iterrows():
        k = kisa(r_["Tasarım"])
        if k == "F2a":  # F2 ile neredeyse aynı nokta (büyütmesiz hâli); tabloda var
            continue
        ax.scatter(r_["CVaR %5 [M USD]"], r_["Beklenen NPV [M USD]"], s=110, color=RENK[k], edgecolor="white", lw=1.5, zorder=3)
        dx, dy, ha = ofset.get(k, (7, -3, "left"))
        ax.annotate(
            f"{k}  %{r_['P(NPV > 0) [%]']:.0f}",
            (r_["CVaR %5 [M USD]"], r_["Beklenen NPV [M USD]"]),
            xytext=(dx, dy),
            ha=ha,
            textcoords="offset points",
            fontsize=8,
            color=g.MUREKKEP,
        )
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xlabel("CVaR %5 [M USD] (sağ = daha az risk)")
    ax.set_ylabel("Beklenen NPV [M USD]")
    g.eksen_sade(ax, izgara="both")
    leg = "  ".join(f"{kisa(t.ad)}: {t.ad.split(': ')[1]}" for k_, t in tasarimlar.items() if k_ != "F2a")
    g.baslik(
        fig,
        "Doyum sonrası risk-getiri: batarya avantajının çoğu kayboluyor",
        "Dolu: doyum senaryolu Monte Carlo (etiket: P(NPV>0)). Boş: Aşama 5.",
    )
    fig.text(0.01, 0.885, leg, fontsize=6.8, color=g.IKINCIL, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_risk_getiri.png")
    plt.close(fig)

    # 4) Senaryoya göre E[NPV]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    kol = [c for c in sen_npv.columns if c != "Tasarım"]
    x = np.arange(len(sen_npv))
    w_ = 0.8 / len(kol)
    for j, c in enumerate(kol):
        s = [k for k, v in SENARYO_ADLARI.items() if v == c][0]
        ax.bar(x + (j - (len(kol) - 1) / 2) * w_, sen_npv[c], w_ * 0.92, color=SENARYO_RENK[s], label=c)
    ax.set_xticks(x, [kisa(a) for a in sen_npv["Tasarım"]])
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_ylabel("Koşullu E[NPV] [M USD]")
    ax.legend(fontsize=8, ncols=4, loc="upper right")
    g.eksen_sade(ax)
    g.baslik(
        fig,
        "Doyum senaryosuna göre beklenen NPV",
        "Her çubuk: o senaryodaki simülasyonların ortalaması (fiyat, hava, CAPEX belirsizliği dahil).",
    )
    fig.text(0.01, 0.885, leg, fontsize=6.8, color=g.IKINCIL, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_senaryo_npv.png")
    plt.close(fig)

    # 5) Erteleme
    fig, ax = plt.subplots(figsize=(12, 4.6))
    for k, t in tasarimlar.items():
        if k in ("F2a",):
            continue
        ax.plot(ert["Erteleme [yıl]"], ert[t.ad], color=RENK[k], lw=2, marker="o", ms=4, label=t.ad)
    ax.plot(
        ert["Erteleme [yıl]"],
        ert["Bekle-gör: senaryo bilinerek seçim [M USD]"],
        color=g.MUREKKEP,
        lw=1.5,
        ls="--",
        marker="s",
        ms=4,
        label="Bekle-gör: doyum senaryosu bilinerek en iyi seçim",
    )
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xticks(ert["Erteleme [yıl]"])
    ax.set_xlabel("Devreye alma ertelemesi [yıl]")
    ax.set_ylabel("Beklenen NPV, 2026 değeri [M USD]")
    ax.legend(fontsize=7.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    g.eksen_sade(ax, izgara="both")
    g.baslik(
        fig,
        "Erteleme: beklemek bilgi kazandırır ama SFK penceresini kaçırır",
        "Ertelenen projede batarya CAPEX'i yılda %4 ucuzlar; fiyat ve doyum yolları takvime göre kayar.",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_erteleme.png")
    plt.close(fig)

    # 6) CDF
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for k, s_ in sonuc.items():
        if k == "F2a":
            continue
        xs = np.sort(s_["npv"] / 1e6)
        ax.plot(xs, np.arange(1, len(xs) + 1) / len(xs), color=RENK[k], lw=2, label=tasarimlar[k].ad)
    ax.axvline(0, color=g.MUREKKEP, lw=0.8, ls="--")
    ax.set_xlabel("NPV [M USD]")
    ax.set_ylabel("Birikimli olasılık")
    ax.legend(fontsize=7.5, loc="lower right")
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "NPV dağılımı (doyum senaryolu Monte Carlo)", "Sağdaki eğri daha iyi; kesişen eğriler risk iştahına bağlı seçim demek.")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "s_npv_cdf.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
