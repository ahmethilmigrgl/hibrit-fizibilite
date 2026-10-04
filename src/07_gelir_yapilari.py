"""
Aşama 7 — 1c ve 2: Sistem kesintisi + gelir yapıları (tüccar / PPA / YEKDEM) aynı Monte Carlo çerçevesinde;
teşvik (KDV, gümrük) etkisi; 3: önlenen CO2.

Monte Carlo, Aşama 6 stres testiyle aynı tohum ve belirsizlikleri kullanır (doyum senaryoları dahil). Ek olarak:
    Sistem kesintisi  κ_y = κ_0 · senaryo çarpanı · 1,04^(y−2026) · LN(σ = 0,5) ; κ_0 ~ Üçgen(%1; %5; %12)
                      RES gelir kaybı = κ_y · değer faktörü · (1 − tazmin) · (1 − batarya kurtarma) ; tazmin ~ U(0, 1)
    YEKDEM            ilk 10 yıl tüm üretim nominal USD p ~ Üçgen(4,95; 5,8; 6,05) ¢/kWh (reel: ABD enflasyonuyla aşınır)

Çıktılar: outputs/07/gelir_yapilari_*.csv, gelir_yapilari.png, tesvik_etkisi.csv, co2.csv, erteleme_kesintili.csv
Çalıştırma: .venv/bin/python src/07_gelir_yapilari.py  (Aşama 6 stres testi tablolarından sonra)
"""

import copy
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, deger
from src.risk.degerleme import borc_boyutla, irr_vektor, nakit_akislari, ozkaynak
from src.risk.doyum import ornekle_doyum
from src.risk.monte_carlo import ornekle, ucgen_ters
from src.risk.tasarim import Tasarim
from src.risk.yekdem_tablo import yekdem_tablosu

import os
ORTAK_SURUCU = os.environ.get("ORTAK_SURUCU", "1") == "1"      # 0: düzeltme öncesi (bağımsız sürücüler) karşılaştırması
SADECE_G = os.environ.get("SADECE_G", "0") == "1"              # yalnız nihai tasarım seçenekleri (hızlı karşılaştırma)
CIKTI = CIKTILAR / "07" if ORTAK_SURUCU else CIKTILAR / "07" / "ortak_surucu_kapali"
KAYNAK = "Kaynak: kendi modelim (Monte Carlo, doyum + sistem kesintisi). YEKDEM: CK 7189; teşvik: CK 9903; emisyon faktörü: ETKB. Reel 2026 USD."


def yukle(ad):
    spec = importlib.util.spec_from_file_location(ad, Path(__file__).parent / f"{ad}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


st = yukle("05_stres_testi")
gy, mc = st.gy, st.mc


def log(*a):
    print(*a, flush=True)


def kesinti_ornekle(cfg, n, yillar, senaryo, rng, batarya: bool, kurtarma: float, deger_faktoru: float, yekdem: bool = False,
                    carp_ozel=None):
    """
    Tüccar/PPA: kayıp = κ · değer faktörü · (1 − tazmin) · (1 − batarya kurtarma payı (gelir))
    YEKDEM: talimatla verilmeyen enerjiye YEK farkı ödenmez (YEK Yön. md. 18: ödeme UEVM üzerinden); DGP'de tazmin
    edilen kısım yalnız PTF kadardır → kayıp = κ · (1 − tazmin · PTF_talimat/YEKF) · (1 − batarya kurtarma payı (enerji));
    kurtarılan enerji yine YEKDEM fiyatından ödendiği için kurtarma payı enerji payıdır (%35).
    """
    k = deger(cfg["kesinti"])
    k0 = ucgen_ters(rng.random(n), *k["oran_ucgen"])
    carp = np.array([k["senaryo_carpani"][s] for s in senaryo])
    gurultu = np.exp(k["yil_sd"] * rng.standard_normal((n, len(yillar))) - 0.5 * k["yil_sd"] ** 2)
    carp = carp[:, None] if carp_ozel is None else carp_ozel      # ortak sürücü: (1 − emilen pay_y) / (1 − emilen pay_2026)
    kappa = np.clip(k0[:, None] * carp * (1 + k["gunes_buyume"]) ** (yillar - 2026)[None] * gurultu, 0, 0.3)
    tazmin = rng.uniform(*k["tazmin_orani"], n)
    if yekdem:
        kur = 0.35 if batarya else 0.0
        return {"kesinti_gelir": kappa * (1 - tazmin * deger_faktoru)[:, None] * (1 - kur),
                "kesinti_enerji": kappa * (1 - kur), "kappa": kappa, "tazmin": tazmin}
    kur = kurtarma if batarya else 0.0
    return {"kesinti_gelir": kappa * deger_faktoru * (1 - tazmin)[:, None] * (1 - kur),
            "kesinti_enerji": kappa * (1 - (0.35 if batarya else 0.0)), "kappa": kappa, "tazmin": tazmin}


def borc_hesapla(o, t, tb, c, cfg, ek: dict, L: float, a_yol):
    """P90 CFADS (hava yılları) ile heykelsi borç; ek: phi/ppa_fiyat/kesinti beklenen değerleri (1 × N)."""
    o.a_ozel = a_yol
    def gir(w=None):
        x = o.beklenen_girdi(L, w=w)
        x.update({k_: v for k_, v in ek.items()})
        return x
    cf = np.array([np.mean([nakit_akislari(t, tb, c, gir((w, s)))["cfads"][0] for s in range(2)], axis=0)
                   for w in range(tb["T"].shape[0])])
    cfads_p90 = cf.mean(0) - 1.2816 * cf.std(0, ddof=1)
    r = nakit_akislari(t, tb, c, gir())
    o.a_ozel = None
    pay = None
    if t.ppa:
        phi = np.asarray(ek.get("phi", np.where(np.arange(1, o.v.omur + 1) <= c.ppa_vade, c.ppa_pay, 0.0)))
        fiyat = np.asarray(ek.get("ppa_fiyat", c.ppa_fiyat)).reshape(-1)[: o.v.omur] if np.ndim(ek.get("ppa_fiyat", 0)) else c.ppa_fiyat
        pay = np.clip(phi * fiyat * (r["E_res"] + r["E_ges"])[0] / np.maximum(r["favok"][0], 1), 0, 1)
    return borc_boyutla(cfads_p90, float(r["capex_top"][0]), t, cfg, c, pay)


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    o = gy.Ortam()
    cfg = o.cfg
    stc = cfg["stres_testi"]
    ad = {k: Tasarim(**v) for k, v in json.loads((CIKTILAR / "05_risk" / "adaylar.json").read_text()).items()}
    A_, C_, D_, E_ = (ad[k] for k in ad if k[0] in "ACDE")
    es = deger(stc["esnek_tasarimlar"])["asamali"]
    F2a = replace(C_, ad="F2a", bess_mw=es["ilk_mw"], bess_mwh=es["ilk_mwh"])
    F2aP = replace(F2a, ppa=True)
    kesl = pd.read_csv(CIKTILAR / "07" / "kesinti_batarya_kurtarma.csv", index_col=0)
    kurtarma = float(kesl.loc["30 MW / 52,5 MWh", "Batarya kurtarma payı [%]"]) / 100
    oran_ref = deger(cfg["kesinti"])["oran_2026"]
    deger_faktoru = float(kesl.loc["Bataryasız", "Kayıp [M USD]"] / (oran_ref * kesl.loc["Bataryasız", "Kesintisiz gelir [M USD]"]))
    firsat_oran = float(pd.read_csv(CIKTILAR / "05_risk" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
    log(f"Kesinti: batarya kurtarma {kurtarma:.1%}, değer faktörü {deger_faktoru:.2f}, SFK tabanı {firsat_oran:.3f}")

    tb = {"A": o.tablo(A_), "E": o.tablo(E_), "F2a": st.doyum_tablosu(o, F2a), "F2aP": st.doyum_tablosu(o, F2aP),
          "C": st.doyum_tablosu(o, C_), "D": st.doyum_tablosu(o, D_)}
    # YEKDEM'e özgü tablolar: deşarj da YEKDEM fiyatından → arbitraj teşviki yok (Ö1 düzeltmesi)
    F2Y60 = replace(F2a, ad="F2Y60", bess_mw=30, bess_mwh=60)
    C_y = replace(C_, bess_mw=40, bess_mwh=70, ppa=True)   # YEKDEM büyütme hedefi (önceden hesaplı tablo)
    G = replace(C_, ad="G", bess_mw=30, bess_mwh=60)      # nihai tasarım: tam 30 MW SFK rezervi için 2 saat (Ö1)
    tb["G"] = st.doyum_tablosu(o, G)
    tb.update({"AY": yekdem_tablosu(o, replace(A_, ppa=True)), "F2aY": yekdem_tablosu(o, F2a),
               "F2Y60": yekdem_tablosu(o, F2Y60), "CY": yekdem_tablosu(o, C_y)})

    # YEKDEM sabitleri ve config kopyası (banka koşulları)
    yk = deger(cfg["yekdem"])
    N, n = o.v.omur, deger(cfg["monte_carlo"]["senaryo_sayisi"])
    tohum = deger(cfg["monte_carlo"]["tohum"])
    Kmax = 3
    yil_ext = np.arange(o.yillar[0], o.yillar[0] + N + Kmax)
    pi = deger(cfg["finans"]["abd_enflasyonu"])
    rng = np.random.default_rng(tohum + 7)
    yk_nom = 10 * ucgen_ters(rng.random(n), yk["taban_usd_sent"], yk["tepe_usd_sent"], yk["tavan_usd_sent"])   # USD/MWh nominal
    yk_reel = yk_nom[:, None] / (1 + pi) ** (yil_ext - 2026)[None]
    c_y = replace(o.c, ppa_pay=1.0, ppa_vade=yk["sure_yil"], ppa_fiyat=float(yk_reel[:, :yk["sure_yil"]].mean()))
    cfg_y = copy.deepcopy(cfg)
    cfg_y["gelir_yigini"]["ppa"]["dscr"]["value"] = yk["dscr"]
    cfg_y["gelir_yigini"]["ppa"]["borc_vadesi"]["value"] = yk["borc_vadesi"]

    # (ad, tasarım, tablo, Sabitler, cfg, aşamalı büyütme (küçük, büyük, büyük tablo) ya da None, gelir yapısı)
    AY = replace(A_, ad="RES 58,8 — YEKDEM", ppa=True)
    F2Y = replace(F2aP, ad="F2Y")
    F2Ys = replace(F2Y, ad="F2Ys"); F2Y60s = replace(F2Y60, ppa=True); CYs = replace(C_y, ad="CYs")
    secenek = {
        "A: RES 58,8 — tüccar": (A_, "A", o.c, cfg, None, "tüccar"),
        "E: RES 58,8 — PPA": (E_, "E", o.c, cfg, None, "ppa"),
        "AY: RES 58,8 — YEKDEM": (AY, "AY", c_y, cfg_y, None, "yekdem"),
        "AYe: RES 58,8 — YEKDEM, sınırlar endeksli": (AY, "AY", c_y, cfg_y, None, "yekdem_e"),
        "F2: öneri tasarımı — tüccar": (F2a, "F2a", o.c, cfg, (F2a, C_, "C"), "tüccar"),
        "F2P: öneri tasarımı — PPA": (F2aP, "F2aP", o.c, cfg, (F2aP, D_, "D"), "ppa"),
        "F2Y: öneri tasarımı — YEKDEM": (F2Y, "F2aY", c_y, cfg_y, (F2Y, C_y, "CY"), "yekdem"),
        "F2Ye: öneri tasarımı — YEKDEM, USD sınırları endeksli varsayımı": (F2Y, "F2aY", c_y, cfg_y, (F2Y, C_y, "CY"), "yekdem_e"),
        # Nihai tasarım (Ö1 sonrası): RES 58,8 + 30 MW / 60 MWh, büyütmesiz — nihai baz vaka bunlardan
        "G: nihai tasarım — tüccar": (G, "G", o.c, cfg, None, "tüccar"),
        "GP: nihai tasarım — PPA": (replace(G, ppa=True), "G", o.c, cfg, None, "ppa"),
        "GY: nihai tasarım — YEKDEM nominal": (replace(G, ppa=True), "F2Y60", c_y, cfg_y, None, "yekdem"),
        "GYe: nihai tasarım — YEKDEM endeksli": (replace(G, ppa=True), "F2Y60", c_y, cfg_y, None, "yekdem_e"),
        "GYo: nihai tasarım — YEKDEM yıllık opsiyon (nominal) + tüccar": (replace(G, ppa=True), "F2Y60", c_y, cfg_y, None, "yekdem_opsiyon"),
        "GYoe: nihai tasarım — YEKDEM yıllık opsiyon (endeksli) + tüccar": (replace(G, ppa=True), "F2Y60", c_y, cfg_y, None, "yekdem_opsiyon_e"),
        # YEKDEM altında batarya boyutu duyarlılığı (büyütmesiz)
        "BY1: YEKDEM, batarya 30/52,5 (büyütmesiz)": (F2Ys, "F2aY", c_y, cfg_y, None, "yekdem"),
        "BY2: YEKDEM, batarya 30/60 (büyütmesiz)": (F2Y60s, "F2Y60", c_y, cfg_y, None, "yekdem"),
        "BY3: YEKDEM, batarya 40/70 (büyütmesiz)": (CYs, "CY", c_y, cfg_y, None, "yekdem"),
        "BY1e: YEKDEM endeksli, batarya 30/52,5 (büyütmesiz)": (F2Ys, "F2aY", c_y, cfg_y, None, "yekdem_e"),
        "BY2e: YEKDEM endeksli, batarya 30/60 (büyütmesiz)": (F2Y60s, "F2Y60", c_y, cfg_y, None, "yekdem_e"),
        "BY3e: YEKDEM endeksli, batarya 40/70 (büyütmesiz)": (CYs, "CY", c_y, cfg_y, None, "yekdem_e"),
    }
    yk_e = np.repeat(yk_nom[:, None], len(yil_ext), axis=1)       # TAHMİN varyantı: taban/tavan ABD enflasyonuyla endeksli (reel sabit)

    if SADECE_G:
        secenek = {k: v for k, v in secenek.items() if k.startswith("G")}
    ornek = ornekle(cfg, n, yil_ext, o.oran0, tohum)
    girdi_ext = ornek["girdi"]
    dy = ornekle_doyum(cfg, n, yil_ext, firsat_oran, tohum)
    girdi_ext["a"] = dy["a"]
    senaryo = dy["senaryo"]
    # --- Ortak sürücü (Türkiye batarya yayılımı → SFK fiyatı, sistem kesintisi, öğle kanibalizasyonu)
    os_ = deger(cfg["ortak_surucu"])
    carp_ozel = None
    if ORTAK_SURUCU:
        emme = lambda mw, yil: np.clip(mw * os_["sure_saat"] * os_["fazla_gun"] * os_["verim"]
                                       / (os_["fazla_2026_twh"] * 1e6 * (1 + os_["fazla_buyume"]) ** (yil - 2026)), 0, 1)
        a_abs = emme(dy["kurulu_mw"], yil_ext[None, :])
        a26 = float(emme(1000.0, 2026))                               # 2026'da ~1 GW kurulu (EDEDER/sektör)
        carp_ozel = (1 - a_abs) / (1 - a26)
        girdi_ext["h"] = girdi_ext["h"] + (o.oran0 - girdi_ext["h"]) * a_abs * os_["kanibalizasyon_geri_alma"]
        log(f"Ortak sürücü: emilen öğle fazlası payı 2030 ort. {a_abs[:, 2].mean():.1%}, 2035 ort. {a_abs[:, 7].mean():.1%}")
    kw = dict(carp_ozel=carp_ozel)
    kes_b = kesinti_ornekle(cfg, n, yil_ext, senaryo, np.random.default_rng(tohum + 11), True, kurtarma, deger_faktoru, **kw)
    kes_0 = kesinti_ornekle(cfg, n, yil_ext, senaryo, np.random.default_rng(tohum + 11), False, kurtarma, deger_faktoru, **kw)
    kes_yb = kesinti_ornekle(cfg, n, yil_ext, senaryo, np.random.default_rng(tohum + 11), True, kurtarma, deger_faktoru, yekdem=True, **kw)
    kes_y0 = kesinti_ornekle(cfg, n, yil_ext, senaryo, np.random.default_rng(tohum + 11), False, kurtarma, deger_faktoru, yekdem=True, **kw)
    # --- YEKDEM yıllık opsiyonu: karar t−1 yılının 30 Kasım'ında, o gün bilinen bilgiyle (YEK Yön. md. 4/2, 5/1, 8/1)
    fs_ = deger(cfg["monte_carlo"]["fiyat_sureci"]); mu_hat = deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"])["medyan"]
    yo = deger(cfg["yekdem_opsiyon"])
    L_ext = girdi_ext["L"]
    def yekdem_karar(yol, kd):
        """(n × N) katılım: YEKDEM reel fiyatı > beklenen tüccar geliri/MWh × (1 + arbitraj kaybı payı), yalnız ilk 10 işletme yılı."""
        kol = np.arange(kd, kd + N)
        onceki = np.where(kol[None, :] >= 1, L_ext[:, np.clip(kol - 1, 0, None)],
                          mu_hat * (49.0 / mu_hat) ** (fs_["phi"] ** 2))          # 2027: 2026 seviyesinden tahmin
        tahmin = np.exp(np.log(mu_hat) + fs_["phi"] * (np.log(onceki) - np.log(mu_hat)))
        return (yol[:, kol] > tahmin * yo["esik_carpani"]) & (k_[None, :] <= yk["sure_yil"])
    sec_kes = lambda pil, yapi: (kes_yb if pil else kes_y0) if yapi.startswith("yekdem") else (kes_b if pil else kes_0)
    log(f"Kesinti oranı κ (2028): ortalama {kes_0['kappa'][:, 0].mean():.1%}, P90 {np.percentile(kes_0['kappa'][:, 0], 90):.1%}")
    baz_yol = st.deterministik_yol(cfg, "baz", o.yillar, firsat_oran)
    k_ = np.arange(1, N + 1)

    satir, npv_tum, erteleme, npv_k_tum, katilim = [], {}, {}, {}, {}
    for ad_, (t, tbk, c, cf, asamali, yapi) in secenek.items():
        pil = t.bess_mw > 0.5
        for kesinti in ([False, True] if ad_.startswith("F2P") else [True]):
            npvk = {}
            for kd in range(Kmax + 1):
                gk = st.kes(girdi_ext, kd, N)
                gk["capex_bess"] = girdi_ext["capex_bess"] * (1 - deger(stc["bess_capex_dususu"])) ** kd
                if kesinti:
                    ks = sec_kes(pil, yapi)
                    gk["kesinti_gelir"] = ks["kesinti_gelir"][:, kd:kd + N]; gk["kesinti_enerji"] = ks["kesinti_enerji"][:, kd:kd + N]
                if yapi.startswith("yekdem_opsiyon"):
                    yol = yk_reel if yapi == "yekdem_opsiyon" else yk_e
                    katil = yekdem_karar(yol, kd)
                    gk["phi"] = katil.astype(float); gk["ip"] = katil.astype(int); gk["ppa_fiyat"] = yol[:, kd:kd + N]
                    gk["desarj_sozlesmeli"] = True
                    if kesinti:
                        ky, km = (kes_yb, kes_b) if pil else (kes_y0, kes_0)
                        gk["kesinti_gelir"] = np.where(katil, ky["kesinti_gelir"][:, kd:kd + N], km["kesinti_gelir"][:, kd:kd + N])
                        gk["kesinti_enerji"] = np.where(katil, ky["kesinti_enerji"][:, kd:kd + N], km["kesinti_enerji"][:, kd:kd + N])
                    if kd == 0:
                        katilim[ad_] = katil[:, :yk["sure_yil"]].mean(0)
                elif yapi.startswith("yekdem"):
                    yol = yk_reel if yapi == "yekdem" else yk_e
                    gk["phi"] = np.where(k_ <= yk["sure_yil"], 1.0, 0.0); gk["ppa_fiyat"] = yol[:, kd:kd + N]
                    gk["desarj_sozlesmeli"] = True
                if yapi == "ppa":
                    gk["tuccar_dispatch"] = True
                if asamali:
                    gk, _ = st.asamali_girdi(o, gk, asamali[0], asamali[1], tb[asamali[2]], es, kd)
                r = nakit_akislari(t, tb[tbk], c, gk)
                npvk[kd] = r["npv"] * (1 + o.v.wacc) ** -kd
                if kd == 0:
                    r0 = r
            etiket = ad_ + ("" if kesinti else " (kesintisiz)")
            npv_tum[etiket] = npvk[0]
            npv_k_tum[etiket] = npvk
            erteleme[etiket] = {k: v.mean() / 1e6 for k, v in npvk.items()}
            # Borç: baz (baz doyum + 58 + beklenen kesinti) ve muhafazakâr (SFK yok + 45)
            ek = {}
            if kesinti:
                ks = sec_kes(pil, yapi)
                ek = {"kesinti_gelir": ks["kesinti_gelir"][:, :N].mean(0)[None], "kesinti_enerji": ks["kesinti_enerji"][:, :N].mean(0)[None]}
            if yapi.startswith("yekdem_opsiyon"):
                yol = yk_reel if yapi == "yekdem_opsiyon" else yk_e
                pk = np.r_[katilim[ad_], np.zeros(N - yk["sure_yil"])]
                ek.update({"phi": pk, "ip": (pk > 0.5).astype(int)[None], "ppa_fiyat": yol[:, :N].mean(0)[None], "desarj_sozlesmeli": True})
            elif yapi.startswith("yekdem"):
                yol = yk_reel if yapi == "yekdem" else yk_e
                ek.update({"phi": np.where(k_ <= yk["sure_yil"], 1.0, 0.0), "ppa_fiyat": yol[:, :N].mean(0)[None], "desarj_sozlesmeli": True})
            if yapi == "ppa":
                ek["tuccar_dispatch"] = True
            borc_b = borc_hesapla(o, t, tb[tbk], c, cf, ek, 58.0, baz_yol)
            borc_m = borc_hesapla(o, t, tb[tbk], c, cf, ek, 45.0, np.zeros(N))
            oz_b, oz_m = ozkaynak(r0, borc_b, c), ozkaynak(r0, borc_m, c)
            npv = r0["npv"]
            kotu = np.sort(npv)[: int(0.05 * n)]
            satir.append({"Seçenek": etiket, "Gelir yapısı": yapi, "Beklenen NPV [M USD]": npv.mean() / 1e6,
                          "P(NPV > 0) [%]": 100 * (npv > 0).mean(), "CVaR %5 [M USD]": kotu.mean() / 1e6,
                          "Proje IRR P50 [%]": 100 * np.nanpercentile(irr_vektor(r0["sna"]), 50),
                          "Borç kapasitesi, baz [M USD]": borc_b["borc_reel"] / 1e6, "Borç vadesi [yıl]": borc_b["vade"],
                          "P(DSCR < 1), baz borç [%]": 100 * (oz_b["dscr_min"] < 1).mean(),
                          "Borç kapasitesi, muhafazakâr [M USD]": borc_m["borc_reel"] / 1e6,
                          "P(DSCR < 1), muhafazakâr borç [%]": 100 * (oz_m["dscr_min"] < 1).mean(),
                          "Öz kaynak IRR P50, muhafazakâr [%]": 100 * np.nanpercentile(oz_m["irr"], 50),
                          "Satılan enerji P50 [GWh/yıl]": np.percentile(r0["satilan"][:, :10].mean(1), 50) / 1e3,
                          "Batarya deşarj geliri, ilk 10 yıl [M USD/yıl]": r0["gelir_bess"][:, :10].mean() / 1e6,
                          "SFK geliri, ilk 10 yıl [M USD/yıl]": np.atleast_2d(r0["gelir_yh"])[:, :10].mean() / 1e6 if pil else 0.0})
            log(f"  {etiket}: E[NPV] {npv.mean() / 1e6:.2f} | P {100 * (npv > 0).mean():.0f}% | CVaR {kotu.mean() / 1e6:.1f}")
    tablo = pd.DataFrame(satir)
    if katilim:
        pd.DataFrame(katilim, index=pd.Index(range(1, len(next(iter(katilim.values()))) + 1), name="İşletme yılı")).round(4).to_csv(
            CIKTI / "yekdem_opsiyon_katilim.csv", encoding="utf-8-sig")
    tablo.to_csv(CIKTI / "gelir_yapilari_metrikler.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    pd.DataFrame(erteleme).T.to_csv(CIKTI / "erteleme_kesintili.csv", encoding="utf-8-sig", float_format="%.3f")
    np.savez_compressed(CIKTI / "gelir_yapilari_npv_erteleme.npz",
                        **{f"{k.split(':')[0]}_k{kd}": (v / 1e6).astype(np.float32) for k, d in npv_k_tum.items() if "kesintisiz" not in k
                           for kd, v in d.items()})
    np.savez_compressed(CIKTI / "gelir_yapilari_npv.npz", **{k.split(":")[0]: (v / 1e6).astype(np.float32) for k, v in npv_tum.items()})
    pd.set_option("display.width", 250)
    log("\n" + tablo.round(2).to_string(index=False))

    tesvik = tesvik_etkisi(o, cfg, G, tb["G"])
    co2 = co2_hesapla(cfg, tablo)
    grafik(tablo, npv_tum)
    return tablo, tesvik, co2


def tesvik_etkisi(o, cfg, t, tb):
    """Teşvik belgesi yoksa: KDV ön finansmanı (TL devreden KDV'nin reel aşınmasıyla) ve batarya gümrük vergisi."""
    ts = deger(cfg["tesvik"])
    v = o.v
    capex = (t.res_mw * v.capex_res + t.bess_mw * v.capex_bess_guc + t.bess_mwh * v.capex_bess_enerji + t.sebeke_mw * v.capex_sebeke)
    bess = t.bess_mw * v.capex_bess_guc + t.bess_mwh * v.capex_bess_enerji
    r = nakit_akislari(t, tb, o.c, o.beklenen_girdi(58.0))
    gelir = (r["gelir_spot"] + r["gelir_bess"] + np.atleast_2d(r["gelir_yh"]))[0]
    kdv = ts["kdv_orani"] * ts["kdv_kapsami"] * capex
    nb = v.insaat_suresi
    # İnşaatta ödenen KDV (takvime göre), işletmede çıkış KDV'si (gelirin %20'si) ile mahsup; bakiye reel olarak aşınır
    bakiye, pv_kayip = 0.0, 0.0
    for j, pay in enumerate(v.capex_takvimi):
        bakiye = bakiye * (1 - ts["kdv_reel_asinma"]) + kdv * pay
        pv_kayip += kdv * pay / (1 + v.wacc) ** (j + 1)
    for k in range(v.omur):
        bakiye *= (1 - ts["kdv_reel_asinma"])
        mahsup = min(bakiye, ts["kdv_orani"] * gelir[k])
        bakiye -= mahsup
        pv_kayip -= mahsup / (1 + v.wacc) ** (nb + k + 1)
    gumruk = [g_ * ts["batarya_ekipman_payi"] * bess for g_ in ts["gumruk_batarya"]]
    df = pd.DataFrame({"Kalem": ["Ödenen KDV (inşaat) [M USD]", "KDV'nin net bugünkü maliyeti (aşınma dahil) [M USD]",
                                 "KDV aşınmasız olsaydı net maliyet [M USD]",
                                 "Batarya gümrük vergisi (alt / orta / üst) [M USD]", "Vergi indirimi (elektrik üretimine uygulanmaz)"],
                       "Değer": [kdv / 1e6, pv_kayip / 1e6, np.nan,
                                 " / ".join(f"{x / 1e6:.2f}" for x in gumruk), 0.0]})
    # aşınmasız karşılaştırma
    bakiye, pv0 = 0.0, 0.0
    for j, pay in enumerate(v.capex_takvimi):
        bakiye += kdv * pay; pv0 += kdv * pay / (1 + v.wacc) ** (j + 1)
    for k in range(v.omur):
        mahsup = min(bakiye, ts["kdv_orani"] * gelir[k]); bakiye -= mahsup; pv0 -= mahsup / (1 + v.wacc) ** (nb + k + 1)
    df.loc[2, "Değer"] = pv0 / 1e6
    df.to_csv(CIKTI / "tesvik_etkisi.csv", encoding="utf-8-sig", index=False)
    log("\nTeşvik etkisi:\n" + df.to_string(index=False))
    return df


def co2_hesapla(cfg, tablo):
    k = deger(cfg["karbon"])
    sat = float(tablo.loc[tablo["Seçenek"].str.startswith("GY:"), "Satılan enerji P50 [GWh/yıl]"].iloc[0])
    yil = np.arange(30)
    ef_sabit = k["sebeke_ef_2024"]
    ef_yol = ef_sabit * (1 - k["ef_yillik_azalma"]) ** (yil + 2)       # 2028'den itibaren
    df = pd.DataFrame({"Kalem": ["Satılan enerji (P50, ilk 10 yıl ort.) [GWh/yıl]", "Şebeke emisyon faktörü 2024 (RES, birleşik marj) [tCO2/MWh]",
                                 "Önlenen CO2, yıllık (sabit faktör) [bin t]", "Önlenen CO2, 30 yıl (sabit faktör) [milyon t]",
                                 "Önlenen CO2, 30 yıl (faktör yılda %2 azalır) [milyon t]", "Eşdeğer hane sayısı (2.824 kWh/hane-yıl) [bin]",
                                 "Gönüllü karbon kredisi geliri [USD/yıl]"],
                       "Değer": [sat, ef_sabit, sat * ef_sabit, sat * ef_sabit * 30 / 1e3, (sat * ef_yol).sum() / 1e3,
                                 sat * 1e6 / k["hane_tuketimi_kwh"] / 1e3, 0.0]})
    df.to_csv(CIKTI / "co2.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    log("\nCO2:\n" + df.round(2).to_string(index=False))
    return df


def grafik(tablo, npv_tum):
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 4.8))
    renk = {"tüccar": g.RENK_RES, "ppa": g.RENK_HIBRIT, "yekdem": "#7f6bd1", "yekdem_e": "#b9aef0", "yekdem_opsiyon": "#c0392b", "yekdem_opsiyon_e": "#f1948a"}
    ax = axs[0]
    for ad_, x in npv_tum.items():
        if "kesintisiz" in ad_ or ad_.startswith(("BY", "AYe", "F2")):
            continue
        yapi = tablo.loc[tablo["Seçenek"] == ad_, "Gelir yapısı"].iloc[0]
        xs = np.sort(x / 1e6)
        ax.plot(xs, np.arange(1, len(xs) + 1) / len(xs), color=renk[yapi], lw=2, ls="-" if ad_.startswith("G") else ":", label=ad_)
    ax.axvline(0, color=g.MUREKKEP, lw=0.8, ls="--")
    ax.set_xlabel("NPV [M USD]"); ax.set_ylabel("Birikimli olasılık"); ax.legend(fontsize=7.5, loc="lower right")
    ax.set_title("NPV dağılımı (düz: nihai tasarım, noktalı: yalnız RES)", loc="left"); g.eksen_sade(ax, izgara="both")
    ax = axs[1]
    t = tablo[~tablo["Seçenek"].str.contains("kesintisiz") & ~tablo["Seçenek"].str.startswith(("BY", "AYe", "F2"))]
    for _, r in t.iterrows():
        ax.scatter(r["CVaR %5 [M USD]"], r["Beklenen NPV [M USD]"], s=110, color=renk[r["Gelir yapısı"]],
                   marker="o" if r["Seçenek"].startswith("G") else "s", edgecolor="white", zorder=3)
        ax.annotate(f"{r['Seçenek'].split(':')[0]}  DSCR<1: %{r['P(DSCR < 1), muhafazakâr borç [%]']:.0f}",
                    (r["CVaR %5 [M USD]"], r["Beklenen NPV [M USD]"]), xytext=(7, -3), textcoords="offset points", fontsize=7.5)
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_xlabel("CVaR %5 [M USD]"); ax.set_ylabel("Beklenen NPV [M USD]"); ax.set_title("Risk-getiri ve DSCR ihlali (muhafazakâr borç)", loc="left")
    xl = ax.get_xlim(); ax.set_xlim(xl[0], xl[1] + (xl[1] - xl[0]) * 0.35)
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "Gelir yapısı: YEKDEM'in yıllık opsiyonu tüccardan iyi; 10 yıl sabit YEKDEM ve PPA geride", "Model takvimi (COD 2028); doyum senaryoları + sistem kesintisi dahil, 10.000 simülasyon. Mavi: tüccar, yeşil: PPA, mor: YEKDEM (açık mor: sınırlar endeksli varsayımı).")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "gelir_yapilari.png"); plt.close(fig)


def grafik_yeniden():
    """Grafiği kayıtlı çıktılardan (metrikler + NPV örnekleri) simülasyonu tekrarlamadan yeniden çizer."""
    tablo = pd.read_csv(CIKTI / "gelir_yapilari_metrikler.csv")
    z = np.load(CIKTI / "gelir_yapilari_npv.npz")
    npv_tum = {ad_: z[ad_.split(":")[0]].astype(float) * 1e6 for ad_ in tablo["Seçenek"] if ad_.split(":")[0] in z}
    grafik(tablo, npv_tum)


if __name__ == "__main__":
    grafik_yeniden() if "--grafik" in sys.argv else main()
