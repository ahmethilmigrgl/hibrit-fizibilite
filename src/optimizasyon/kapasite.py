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
    yan: np.ndarray | None = None   # yan hizmet kapasite fiyatı [USD/MW-saat] (seviyelendirilmiş)


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
                 duzen: dict, sabit: dict | None = None, zaman_siniri: float = 600, yatirim: str = "zorunlu",
                 gelir: dict | None = None) -> dict:
    """
    MILP'i kurar ve çözer. sabit: {"N","G","P","E", ("N2","G2")} verilirse ilgili kapasite sabitlenir.
    yatirim: "zorunlu" → b = 1; "serbest" → ikili b ile "hiç kurmamak" da seçenek.
    gelir (Aşama 5 gelir yığını; hepsi opsiyonel):
        yh   = {"azami": MW, "asgari": MW, "h": saat}      → yan hizmet rezervi r_t (Segment.yan fiyatıyla)
        dz   = {"azami_oran": .., "doyum_orani": ..}        → bataryayla RES dengesizlik maliyeti azaltımı u
        yekg = USD/MWh                                       → yenilenebilir satışa ek gelir
        ppa  = {"phi": seviyelendirilmiş pay, "fiyat": seviyelendirilmiş PPA fiyatı}
        dl   = {"edinme_yillik": USD/MW-yıl}                 → depolamalı lisans bloğu (N2, G2; bağlantı = P)
    """
    gelir = gelir or {}
    yh, dz, ppa, dl = gelir.get("yh"), gelir.get("dz"), gelir.get("ppa"), gelir.get("dl")
    yekg = gelir.get("yekg", 0.0)
    t0 = time.time()
    m_t = opt["turbin_gucu"]
    eta = float(np.sqrt(opt["verim_gd"]))
    sure_min, sure_max = opt["bess_sure_aralik"]
    yip = v.bess_yipranma

    m = pyo.ConcreteModel(name="Kapasite")
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
    m.y = pyo.Var(m.I, within=pyo.NonNegativeReals)   # santralden doğrudan şebekeye
    m.k = pyo.Var(m.I, within=pyo.NonNegativeReals)   # kesinti
    m.c = pyo.Var(m.I, within=pyo.NonNegativeReals)   # ana santralden şarj
    m.d = pyo.Var(m.I, within=pyo.NonNegativeReals)   # deşarj
    m.s = pyo.Var(m.I, within=pyo.NonNegativeReals)   # şarj durumu

    g = {(s, h): float(seg.ges[h]) * eko.f_ges for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    r = {(s, h): float(seg.res[h]) * eko.f_res for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    p = {(s, h): float(seg.fiyat[h]) for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
    w = {s: seg.agirlik for s, seg in enumerate(segmentler)}
    saat_top = sum(w[s] for s, h in idx)                                 # = 8760

    # Doğrusal gelir düzeltmeleri (kapasite başına, yıllık): dengesizlik ve RES eşzamanlılık (PPA payı hariç)
    phi = ppa["phi"] if ppa else 0.0
    gelir_ges_mw = sum(w[s] * p[s, h] * g[s, h] for s, h in idx)
    gelir_res_mw = sum(w[s] * p[s, h] * r[s, h] for s, h in idx)
    uretim_res_mw = sum(w[s] * r[s, h] for s, h in idx)
    dengesizlik_res_mw = v.dengesizlik["res"] * gelir_res_mw            # 1 MW RES'in yıllık dengesizlik maliyeti
    duz_ges = v.dengesizlik["ges"] * gelir_ges_mw
    duz_res = dengesizlik_res_mw + (1 - phi) * v.eszamanlilik_res * eko.p_ort * uretim_res_mw

    # Santralden doğrudan satış fiyatı: (1 − φ)·spot + φ·PPA + YEK-G ; deşarj: spot + YEK-G (santral enerjisi)
    p_y = {i: (1 - phi) * p[i] + (phi * ppa["fiyat"] if ppa else 0.0) + yekg for i in idx}
    p_d = {i: p[i] + yekg for i in idx}

    gelir_ifade = sum(w[s] * ((p_y[s, h] - eko.teias_e) * m.y[s, h] + (p_d[s, h] - eko.teias_e - yip) * m.d[s, h])
                      for s, h in idx)
    maliyet = ((eko.a_res + duz_res) * m_t * m.N + (eko.a_ges + duz_ges) * m.G
               + eko.a_bess_p * m.P + eko.a_bess_e * m.E + eko.a_sebeke * L * m.b)

    # --- Yan hizmet: rezerv r_t, ikili z (asgari güç şartı)
    if yh:
        m.r = pyo.Var(m.I, within=pyo.NonNegativeReals)
        m.z = pyo.Var(within=pyo.Binary)
        pyan = {(s, h): float(seg.yan[h]) for s, seg in enumerate(segmentler) for h in range(len(seg.fiyat))}
        gelir_ifade = gelir_ifade + sum(w[s] * pyan[s, h] * m.r[s, h] for s, h in idx)
        m.k_r_tavan = pyo.Constraint(m.I, rule=lambda m, s, h: m.r[s, h] <= yh["azami"] * m.z)
        m.k_r_asgari = pyo.Constraint(expr=m.P >= yh["asgari"] * m.z)
    # --- Dengesizlik azaltımı u (doygunlaşan): u ≤ oran·RES maliyeti, u ≤ eğim·(P − ort. rezerv)
    if dz:
        m.u = pyo.Var(within=pyo.NonNegativeReals)
        # Batarya gücü RES gücünün doyum_orani'na ulaşınca azaltım azami orana doyar → eğim [USD/yıl per MW]
        egim = dz["azami_oran"] * dengesizlik_res_mw / dz["doyum_orani"]
        m.k_u1 = pyo.Constraint(expr=m.u <= dz["azami_oran"] * dengesizlik_res_mw * m_t * m.N)
        r_ort = (sum(w[s] * m.r[s, h] for s, h in idx) / saat_top) if yh else 0
        m.k_u2 = pyo.Constraint(expr=m.u <= egim * (m.P - r_ort))
        gelir_ifade = gelir_ifade + m.u
    # --- Depolamalı lisans bloğu: N2 türbin + G2 GES, üretimi yalnızca bataryaya; ek bağlantı = P
    if dl:
        m.N2 = pyo.Var(within=pyo.NonNegativeIntegers, bounds=(0, opt["turbin_azami"]))
        m.G2 = pyo.Var(bounds=(0, opt["ges_azami_mw"]))
        m.c2 = pyo.Var(m.I, within=pyo.NonNegativeReals)
        m.k2 = pyo.Var(m.I, within=pyo.NonNegativeReals)
        m.k_blok_uretim = pyo.Constraint(m.I, rule=lambda m, s, h: m.c2[s, h] + m.k2[s, h] == m.G2 * g[s, h] + m_t * m.N2 * r[s, h])
        m.L2 = pyo.Var(within=pyo.NonNegativeReals)                          # depolamalı lisansla gelen ek bağlantı
        m.k_L2 = pyo.Constraint(expr=m.L2 <= m.P)                             # ek bağlantı ≤ depolama gücü
        m.k_blok_oran = pyo.Constraint(expr=m_t * m.N2 + m.G2 <= m.L2)       # RES/GES ≤ depolama gücü (oran ≤ 1)
        maliyet = maliyet + (eko.a_res + duz_res) * m_t * m.N2 + (eko.a_ges + duz_ges) * m.G2 \
            + (eko.a_sebeke + dl["edinme_yillik"]) * m.L2
    m.amac = pyo.Objective(expr=gelir_ifade - maliyet, sense=pyo.maximize)

    # --- Kısıtlar
    sarj = (lambda m, s, h: m.c[s, h] + m.c2[s, h]) if dl else (lambda m, s, h: m.c[s, h])
    rr = (lambda m, s, h: m.r[s, h]) if yh else (lambda m, s, h: 0)
    m.k_uretim = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] + m.k[s, h] + m.c[s, h] == m.G * g[s, h] + m_t * m.N * r[s, h])
    # Yan hizmet rezervi şebeke kısıtına girmez: yukarı yönlü aktivasyon anında santralin doğrudan
    # çıkışı rezerv kadar kısılarak yer açılır (aktivasyon enerjisi küçük; bkz. docs/05).
    if dl:   # santral doğrudan L'yi aşamaz; bataryanın deşarjı ek bağlantı L2 üzerinden de verilebilir
        m.k_sebeke_ana = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] <= L)
        m.k_sebeke = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] + m.d[s, h] <= L + m.L2)
    else:
        m.k_sebeke = pyo.Constraint(m.I, rule=lambda m, s, h: m.y[s, h] + m.d[s, h] <= L)
    m.k_sarj = pyo.Constraint(m.I, rule=lambda m, s, h: sarj(m, s, h) + rr(m, s, h) <= m.P)
    m.k_desarj = pyo.Constraint(m.I, rule=lambda m, s, h: m.d[s, h] + rr(m, s, h) <= m.P)
    hh = yh["h"] if yh else 0.0
    m.k_enerji = pyo.Constraint(m.I, rule=lambda m, s, h: m.s[s, h] + hh * rr(m, s, h) <= m.E)
    if yh:
        m.k_enerji_alt = pyo.Constraint(m.I, rule=lambda m, s, h: m.s[s, h] >= hh * m.r[s, h])
    son = {s: len(seg.fiyat) - 1 for s, seg in enumerate(segmentler)}
    m.k_soc = pyo.Constraint(m.I, rule=lambda m, s, h: m.s[s, h] == m.s[s, (h - 1) if h > 0 else son[s]]
                             + eta * sarj(m, s, h) - m.d[s, h] / eta)
    m.k_sure_alt = pyo.Constraint(expr=m.E >= sure_min * m.P)
    m.k_sure_ust = pyo.Constraint(expr=m.E <= sure_max * m.P)
    m.k_b_N = pyo.Constraint(expr=m.N <= opt["turbin_azami"] * m.b)
    m.k_b_G = pyo.Constraint(expr=m.G <= opt["ges_azami_mw"] * m.b)
    m.k_b_P = pyo.Constraint(expr=m.P <= 4 * L * m.b)
    if duzen.get("yardimci_kaynak", {}).get("aktif"):
        m.k_yardimci = pyo.Constraint(expr=m.G <= duzen["yardimci_kaynak"]["oran"] * m_t * m.N)
    if duzen.get("depolamali"):
        m.k_depolamali = pyo.Constraint(expr=m.P >= m.G + m_t * m.N)
    for ad, deg_ in (sabit or {}).items():
        if hasattr(m, ad):
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

    val = lambda x: float(pyo.value(x))
    E_val, P_val = val(m.E), val(m.P)
    W = np.array([w[s] for s, h in idx]); P_ = np.array([p[i] for i in idx])
    hv = lambda var: np.array([var[i].value for i in idx])
    y_, d_, c_, k_ = hv(m.y), hv(m.d), hv(m.c), hv(m.k)
    r_ = hv(m.r) if yh else np.zeros(len(idx))
    A_ = np.array([val(m.G) * g[i] + m_t * val(m.N) * r[i] for i in idx])
    # Bataryasız karşı olgu: aynı üretim, kesinti = max(A − L, 0) + ekonomik kesinti (p < τ)
    sat0 = np.where(P_ > eko.teias_e, np.minimum(A_, L), 0.0)
    k0 = A_ - sat0
    kurtar = np.minimum(c_, k0)
    oz = {
        "Yatırım": int(round(val(m.b))), "N": int(round(val(m.N))), "RES [MW]": m_t * round(val(m.N)),
        "GES [MWac]": val(m.G), "BESS [MW]": P_val, "BESS [MWh]": E_val,
        "BESS süresi [h]": E_val / P_val if P_val > 1e-6 else 0.0,
        "Amaç (yıllık eşdeğer) [M USD]": amac / 1e6, "NPV tahmini [M USD]": amac * eko.vergi_carpani / 1e6,
        "Kesinti [%]": 100 * float((W * k_).sum()) / max(float((W * A_).sum()), 1e-9),
        "BESS döngü/yıl": float((W * d_).sum()) / E_val if E_val > 1e-6 else 0.0,
        "Çözüm süresi [s]": sure, "MIP boşluğu": bosluk, "Çözücü durumu": str(sonuc.termination_condition),
        # Batarya gelir ayrıştırması (yıllık, USD): deşarj geliri − yıpranma, kaynağına göre
        "BESS deşarj geliri [USD/yıl]": float((W * d_ * (P_ - eko.teias_e - yip)).sum()),
        "BESS şarj fırsat maliyeti [USD/yıl]": float((W * (c_ - kurtar) * (P_ - eko.teias_e)).sum()),
        "Kurtarılan kesinti [MWh/yıl]": float((W * kurtar).sum()),
        "Yan hizmet geliri [USD/yıl]": float((W * r_ * np.array([segmentler[s].yan[h] for s, h in idx])).sum()) if yh else 0.0,
        "Ort. rezerv [MW]": float((W * r_).sum() / saat_top),
        "Yan hizmete katılım": int(round(val(m.z))) if yh else 0,
        "Dengesizlik azaltımı [USD/yıl]": val(m.u) if dz else 0.0,
        "Blok RES [MW]": m_t * round(val(m.N2)) if dl else 0.0, "Blok GES [MWac]": val(m.G2) if dl else 0.0,
        "Ek bağlantı L2 [MW]": val(m.L2) if dl else 0.0, "N2": int(round(val(m.N2))) if dl else 0,
        "model": m,
    }
    # Deşarj gelirinin kesinti / arbitraj ayrımı: şarjın kesintiden gelen payıyla orantılı
    sarj_top = float((W * c_).sum()) + (float((W * hv(m.c2)).sum()) if dl else 0.0)
    pay = float((W * kurtar).sum() + ((W * hv(m.c2)).sum() if dl else 0.0)) / max(sarj_top, 1e-9)
    net = oz["BESS deşarj geliri [USD/yıl]"]
    oz["Batarya: kesinti kurtarma [USD/yıl]"] = pay * net
    oz["Batarya: arbitraj [USD/yıl]"] = (1 - pay) * net - oz["BESS şarj fırsat maliyeti [USD/yıl]"]
    return oz
