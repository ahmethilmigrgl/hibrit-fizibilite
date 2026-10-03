"""
Basamak 3 — Kapasite optimizasyonu (MILP): RES türbin sayısı (tamsayı), GES MWac, batarya MW ve MWh.

Zaman, "segment"lere bölünür (tam yıl: her fiyat-yılı bir segment; temsilî günler: her gün bir segment).
Her segmentin ağırlığı w_s = temsil ettiği yıl payı (Σ_s w_s · |segment| = 8760). Batarya her
segmentte döngüseldir (segment sonu SOC = başlangıç SOC).

Kümeler      S segmentler;  T_s  segment s'nin saatleri
Parametreler p̂_t   seviyelendirilmiş fiyat (ömür boyu iskonto ağırlıklı ortalama) [USD/MWh]
             g_t, r_t  GES ve RES KF (seviyelendirilmiş degradasyon çarpanlarıyla)
             L  bağlantı [MW];  m = 4,2 MW/türbin;  η_c, η_d;  c_y yıpranma;  τ_e TEİAŞ enerji bedeli
             a_X  her kalemin "yıllık eşdeğer" maliyeti (CAPEX vergi ve zamanlama düzeltmeli + sabit giderler)
Değişkenler  N ∈ ℤ, 0 ≤ N ≤ N_max   türbin sayısı
             G ≥ 0  GES [MWac],  P ≥ 0  batarya gücü [MW],  E ≥ 0  batarya enerjisi [MWh]
             y_t, k_t, c_t, d_t, s_t ≥ 0  (Basamak 2 ile aynı anlam)
Amaç         max  Σ_s w_s Σ_{t∈T_s} [ (p̂_t − τ_e)·(y_t + d_t) − c_y·d_t ]
                  − a_RES·m·N − a_GES·G − a_P·P − a_E·E − a_L·L
                  − (dengesizlik + eşzamanlılık düzeltmesi; kapasitelerle doğrusal)
Kısıtlar     y_t + k_t + c_t = G·g_t + m·N·r_t      (üretim dengesi)
             y_t + d_t ≤ L                           (şebeke)
             c_t ≤ P,  d_t ≤ P,  s_t ≤ E             (batarya güç/enerji)
             s_t = s_{t−1} + η_c c_t − d_t/η_d,  s_{son} döngüsel  (SOC)
             1·P ≤ E ≤ 6·P                           (batarya süresi 1-6 saat)
             G ≤ G_max (arazi);  opsiyonel: G ≤ oran·m·N (yardımcı kaynak), P ≥ G + m·N (depolamalı tesis)

Yıllık eşdeğer ve vergi (proje_degerle ile aynı zaman çizelgesi):
    S_isl  = Σ_{k=1..N} DF(nb+k)                 (işletme yıllarının iskonto çarpanları toplamı)
    C_pv   = Σ_y takvim_y · DF(y+1)              (1 USD CAPEX'in bugünkü değeri)
    z      = Σ_{k=1..10} (1/10) · DF(nb+k)        (1 USD CAPEX'in amortisman vergi kalkanı tabanı)
    NPV ≈ (1−t)·S_isl·[yıllık (gelir − gider)] − Σ CAPEX·(C_pv − t·z)
    ⇒ vergi öncesi eşdeğer yıllık sermaye maliyeti  a_cap = (C_pv − t·z) / ((1−t)·S_isl)
    Amaç değeri × (1−t) × S_isl ≈ NPV (zarar mahsubu ve kesintinin dengesizliğe etkisi ihmal edilir).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pyomo.environ as pyo

from src.finans.model import Varsayimlar


@dataclass
class Segment:
    fiyat: np.ndarray
    ges: np.ndarray
    res: np.ndarray
    agirlik: float          # yıl payı (bir saatin yıllık ağırlığı)


@dataclass
class Ekonomi:
    S_isl: float
    a_cap: float            # 1 USD CAPEX → yıllık eşdeğer (vergi öncesi eşdeğer)
    vergi_carpani: float    # (1 − t) · S_isl : yıllık eşdeğer → NPV
    f_ges: float            # seviyelendirilmiş degradasyon çarpanları
    f_res: float
    a_res: float            # USD/MW-yıl (CAPEX + sabit gider + sigorta)
    a_ges: float
    a_bess_p: float         # USD/MW-yıl
    a_bess_e: float         # USD/MWh-yıl (CAPEX + augmentation + yenileme + söküm + O&M)
    a_sebeke: float         # USD/MW-yıl (bağlantı CAPEX + TEİAŞ kapasite + sigorta)
    teias_e: float
    p_ort: float            # seviyelendirilmiş ortalama fiyat (eşzamanlılık düzeltmesi için)


def ekonomi_hesapla(v: Varsayimlar, p_ort: float) -> Ekonomi:
    r, t, nb, N = v.wacc, v.vergi, v.insaat_suresi, v.omur
    DF = lambda y: (1 + r) ** -y
    k = np.arange(1, N + 1)
    S_isl = float(DF(nb + k).sum())
    C_pv = float(sum(sch * DF(y + 1) for y, sch in enumerate(v.capex_takvimi)))
    z = float((DF(nb + np.arange(1, 11)) / 10).sum())
    a_cap = (C_pv - t * z) / ((1 - t) * S_isl)
    f_ges = float(((1 - v.degr_ges) ** (k - 1) * DF(nb + k)).sum() / S_isl)
    f_res = float(((1 - v.degr_res) ** (k - 1) * DF(nb + k)).sum() / S_isl)
    son = DF(nb + N) / S_isl
    # Batarya: augmentation (8, 16, 28. yıllar) + 20. yılda yenileme + söküm (vergiden düşülür → vergi öncesi gider)
    aug_pv_e = sum(v.augmentation["oran"] * (1 - v.augmentation["maliyet_dususu_yillik"]) ** y * DF(nb + y)
                   for y in list(v.augmentation["yillar"]) + [y + v.omur_bess for y in v.augmentation["yillar"]]
                   if y <= N and y != v.omur_bess)
    yen = (1 - v.bess_yenileme["maliyet_dususu_yillik"]) ** v.omur_bess * DF(nb + v.omur_bess) if v.bess_yenileme["aktif"] else 0.0
    cc = v.capex_carpani
    a_bess_e = (v.capex_bess_enerji * cc * (a_cap + v.sigorta_oran + v.opex_bess_oran)
                + v.capex_bess_enerji * cc * (aug_pv_e + yen) / S_isl + v.sokum["bess"] * son)
    a_bess_p = v.capex_bess_guc * cc * (a_cap + v.sigorta_oran + v.opex_bess_oran) + v.capex_bess_guc * cc * yen / S_isl
    a_res = v.capex_res * cc * (a_cap + v.sigorta_oran) + v.opex_res + v.arazi_res + v.sokum["res"] * son
    a_ges = v.capex_ges * cc * (a_cap + v.sigorta_oran) + v.opex_ges + v.arazi_ges + v.sokum["ges"] * son
    a_sebeke = v.capex_sebeke * cc * (a_cap + v.sigorta_oran) + v.teias_kapasite
    return Ekonomi(S_isl, a_cap, (1 - t) * S_isl, f_ges, f_res, a_res, a_ges, a_bess_p, a_bess_e, a_sebeke,
                   v.teias_enerji, p_ort)


def kapasite_coz(segmentler: list[Segment], v: Varsayimlar, eko: Ekonomi, L: float, opt: dict,
                 duzen: dict, sabit: dict | None = None, zaman_siniri: float = 600, yatirim: str = "zorunlu") -> dict:
    """
    MILP'i kurar ve çözer. sabit: {"N": .., "G": .., "P": .., "E": ..} verilirse ilgili kapasite sabitlenir
    (ızgara taramaları ve değerlendirme için). Döndürür: kapasiteler, amaç, NPV tahmini, süre, MIP boşluğu.
    yatirim: "zorunlu" → proje kurulur (b = 1); "serbest" → ikili b ∈ {0,1} ile "hiç kurmamak" da seçenektir
    (bağlantı maliyeti yalnızca b = 1 ise oluşur; kapasiteler b = 0 iken 0'a zorlanır).
    """
    t0 = time.time()
    m_t = opt["turbin_gucu"]
    eta = float(np.sqrt(v_verim := opt["verim_gd"]))
    sure_min, sure_max = opt["bess_sure_aralik"]
    yip = v.bess_yipranma

    m = pyo.ConcreteModel(name="Basamak3_Kapasite")
    # --- Kümeler: (segment, saat) çiftleri
    idx = [(s, h) for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))]
    m.I = pyo.Set(initialize=idx, dimen=2)
    # --- Kapasite değişkenleri
    m.N = pyo.Var(within=pyo.NonNegativeIntegers, bounds=(0, opt["turbin_azami"]))
    m.G = pyo.Var(bounds=(0, opt["ges_azami_mw"]))
    m.P = pyo.Var(bounds=(0, None))
    m.E = pyo.Var(bounds=(0, None))
    m.b = pyo.Var(within=pyo.Binary)                  # yatırım kararı (1 = proje kurulur)
    if yatirim == "zorunlu":
        m.b.fix(1)
    # --- Saatlik değişkenler
    m.y = pyo.Var(m.I, within=pyo.NonNegativeReals)
    m.k = pyo.Var(m.I, within=pyo.NonNegativeReals)
    m.c = pyo.Var(m.I, within=pyo.NonNegativeReals)
    m.d = pyo.Var(m.I, within=pyo.NonNegativeReals)
    m.s = pyo.Var(m.I, within=pyo.NonNegativeReals)

    g = {(s, h): float(seg.ges[h]) * eko.f_ges for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    r = {(s, h): float(seg.res[h]) * eko.f_res for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    p = {(s, h): float(seg.fiyat[h]) for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    w = {s: seg.agirlik for s, seg in enumerate(segmentler)}

    # Doğrusal gelir düzeltmeleri (kapasite başına, yıllık): dengesizlik (gelir oranı) ve RES eşzamanlılık
    gelir_ges_mw = sum(w[s] * p[s, h] * g[s, h] for s, h in idx)       # 1 MW GES'in kesintisiz geliri
    gelir_res_mw = sum(w[s] * p[s, h] * r[s, h] for s, h in idx)
    uretim_res_mw = sum(w[s] * r[s, h] for s, h in idx)
    duz_ges = v.dengesizlik["ges"] * gelir_ges_mw
    duz_res = v.dengesizlik["res"] * gelir_res_mw + v.eszamanlilik_res * eko.p_ort * uretim_res_mw

    # --- Amaç (yıllık eşdeğer, vergi öncesi eşdeğer USD)
    gelir = sum(w[s] * ((p[s, h] - eko.teias_e) * (m.y[s, h] + m.d[s, h]) - yip * m.d[s, h]) for s, h in idx)
    maliyet = ((eko.a_res + duz_res) * m_t * m.N + (eko.a_ges + duz_ges) * m.G
               + eko.a_bess_p * m.P + eko.a_bess_e * m.E + eko.a_sebeke * L * m.b)
    m.amac = pyo.Objective(expr=gelir - maliyet, sense=pyo.maximize)

    # --- Kısıtlar
    m.k_uretim = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] + m.k[s, h] + m.c[s, h] == m.G * g[s, h] + m_t * m.N * r[s, h])
    m.k_sebeke = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] + m.d[s, h] <= L)
    m.k_sarj = pyo.Constraint(m.I, rule=lambda m, s, h: m.c[s, h] <= m.P)
    m.k_desarj = pyo.Constraint(m.I, rule=lambda m, s, h: m.d[s, h] <= m.P)
    m.k_enerji = pyo.Constraint(m.I, rule=lambda m, s, h: m.s[s, h] <= m.E)
    son = {s: len(seg.fiyat) - 1 for s, seg in enumerate(segmentler)}
    m.k_soc = pyo.Constraint(m.I, rule=lambda m, s, h: m.s[s, h] == m.s[s, (h - 1) if h > 0 else son[s]]
                             + eta * m.c[s, h] - m.d[s, h] / eta)
    # Yatırım yapılmazsa (b = 0) hiçbir kapasite kurulamaz
    m.k_b_N = pyo.Constraint(expr=m.N <= opt["turbin_azami"] * m.b)
    m.k_b_G = pyo.Constraint(expr=m.G <= opt["ges_azami_mw"] * m.b)
    m.k_b_P = pyo.Constraint(expr=m.P <= 4 * L * m.b)
    m.k_sure_alt = pyo.Constraint(expr=m.E >= sure_min * m.P)
    m.k_sure_ust = pyo.Constraint(expr=m.E <= sure_max * m.P)
    if duzen.get("yardimci_kaynak", {}).get("aktif"):
        m.k_yardimci = pyo.Constraint(expr=m.G <= duzen["yardimci_kaynak"]["oran"] * m_t * m.N)
    if duzen.get("depolamali"):
        m.k_depolamali = pyo.Constraint(expr=m.P >= m.G + m_t * m.N)
    for ad, deg_ in (sabit or {}).items():
        getattr(m, ad).fix(deg_)

    from pyomo.contrib import appsi
    coz = appsi.solvers.Highs()
    coz.config.time_limit = zaman_siniri
    coz.config.mip_gap = opt.get("mip_bosluk", 1e-3)
    sonuc = coz.solve(m)
    sure = time.time() - t0
    amac = pyo.value(m.amac)
    sinir = sonuc.best_objective_bound
    bosluk = abs(sinir - amac) / max(abs(amac), 1e-9) if sinir is not None and np.isfinite(sinir) else float("nan")

    E_val, P_val = pyo.value(m.E), pyo.value(m.P)
    top_d = sum(w[s] * pyo.value(m.d[s, h]) for s, h in idx)
    top_k = sum(w[s] * pyo.value(m.k[s, h]) for s, h in idx)
    top_a = sum(w[s] * (pyo.value(m.G) * g[s, h] + m_t * pyo.value(m.N) * r[s, h]) for s, h in idx)
    return {
        "Yatırım": int(round(pyo.value(m.b))), "N": int(round(pyo.value(m.N))), "RES [MW]": m_t * round(pyo.value(m.N)), "GES [MWac]": pyo.value(m.G),
        "BESS [MW]": P_val, "BESS [MWh]": E_val, "BESS süresi [h]": E_val / P_val if P_val > 1e-6 else 0.0,
        "Amaç (yıllık eşdeğer) [M USD]": amac / 1e6, "NPV tahmini [M USD]": amac * eko.vergi_carpani / 1e6,
        "Kesinti [%]": 100 * top_k / max(top_a, 1e-9), "BESS döngü/yıl": top_d / E_val if E_val > 1e-6 else 0.0,
        "Çözüm süresi [s]": sure, "MIP boşluğu": bosluk, "Çözücü durumu": str(sonuc.termination_condition), "Değişken sayısı": 5 * len(idx) + 4,
        "Kısıt sayısı": 6 * len(idx) + 2, "model": m,
    }
