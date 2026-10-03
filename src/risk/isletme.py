"""
Sabit kapasiteli tasarım için işletme (dispatch) LP'si ve önceden hesaplanan işletme tabloları.

LP (8760 saat, kapasiteler sabit; Aşama 4 Basamak 2'nin gelir yığınlı hali):
    max Σ_t [ (p^y_t − τ)·y_t + (p_t + yekg − τ − c_y)·d_t + p^YH_t·r_t ]
    p^y_t = (1 − φ)·p_t + φ·PPA + yekg      (φ: o yıl PPA'ya bağlı üretim payı)
    y_t + k_t + c_t = A_t ;  y_t + d_t ≤ L ;  c_t + r_t ≤ P ;  d_t + r_t ≤ P
    h·r_t ≤ s_t ≤ E − h·r_t ;  r_t ≤ R_max (yan hizmete katılım koşulu sağlanıyorsa, yoksa 0)
    s_t = s_{t−1} + η c_t − d_t/η (döngüsel)

Önceden hesaplama (Monte Carlo verimliliği):
    Dispatch, fiyat seviyesi L'nin ölçeklenmesine karşı yaklaşık değişmezdir (yalnızca τ ve c_y sabit
    terimleri bozar). Bu yüzden LP, birim seviyeli fiyat şekli q (ortalama 1) × referans seviye ile
    çözülür ve şu "birim" toplamlar saklanır: Σ y·q, Σ d·q, Σ r·a (a: yan hizmet şekli), enerjiler.
    Simülasyonda gelir = L_yıl × (Σ y·q) gibi doğrudan hesaplanır (dispatch sabit, fiyat değişken).
    Izgara: hava yılı (10) × şekil yılı (2) × güneş yakalanma hedefi h × RES çarpanı m × yan hizmet seviyesi a
    × PPA (açık/kapalı). Simülasyonda h, m, a üzerinden çok doğrusal ara değerleme yapılır.
"""

from __future__ import annotations

import itertools
import time

import numpy as np
import pyomo.environ as pyo
from pyomo.contrib import appsi

from src.risk.tasarim import ALANLAR, Tasarim  # noqa: F401 (geriye uyumluluk)


class IsletmeLP:
    """Persistent (parametreleri güncellenebilir) 8760 saatlik dispatch modeli."""

    def __init__(self, t: Tasarim, eta: float, yipranma: float, teias_e: float, yekg: float,
                 rezerv_tavan: float, enerji_saat: float, ppa_fiyat: float, n: int = 8760):
        self.n = n
        m = pyo.ConcreteModel()
        m.T = pyo.RangeSet(0, n - 1)
        m.A = pyo.Param(m.T, mutable=True, initialize=0.0)       # kullanılabilir üretim
        m.p = pyo.Param(m.T, mutable=True, initialize=0.0)       # spot fiyat
        m.a = pyo.Param(m.T, mutable=True, initialize=0.0)       # yan hizmet fiyatı
        m.phi = pyo.Param(mutable=True, initialize=0.0)          # PPA payı
        P, E, L = t.bess_mw, t.bess_mwh, t.sebeke_mw
        R = min(rezerv_tavan, P) if t.yan_hizmet else 0.0
        m.y = pyo.Var(m.T, within=pyo.NonNegativeReals)
        m.k = pyo.Var(m.T, within=pyo.NonNegativeReals)
        m.c = pyo.Var(m.T, bounds=(0, P))
        m.d = pyo.Var(m.T, bounds=(0, P))
        m.r = pyo.Var(m.T, bounds=(0, R))
        m.s = pyo.Var(m.T, bounds=(0, E))
        yk = yekg if t.yekg else 0.0
        m.amac = pyo.Objective(expr=sum(
            ((1 - m.phi) * m.p[i] + m.phi * ppa_fiyat + yk - teias_e) * m.y[i]
            + (m.p[i] + yk - teias_e - yipranma) * m.d[i] + m.a[i] * m.r[i] for i in m.T), sense=pyo.maximize)
        m.k_ur = pyo.Constraint(m.T, rule=lambda m, i: m.y[i] + m.k[i] + m.c[i] == m.A[i])
        m.k_seb = pyo.Constraint(m.T, rule=lambda m, i: m.y[i] + m.d[i] <= L)
        m.k_c = pyo.Constraint(m.T, rule=lambda m, i: m.c[i] + m.r[i] <= P)
        m.k_d = pyo.Constraint(m.T, rule=lambda m, i: m.d[i] + m.r[i] <= P)
        m.k_e1 = pyo.Constraint(m.T, rule=lambda m, i: m.s[i] >= enerji_saat * m.r[i])
        m.k_e2 = pyo.Constraint(m.T, rule=lambda m, i: m.s[i] + enerji_saat * m.r[i] <= E)
        m.k_soc = pyo.Constraint(m.T, rule=lambda m, i: m.s[i] == m.s[(i - 1) % n] + eta * m.c[i] - m.d[i] / eta)
        self.m = m
        self.cozucu = appsi.solvers.Highs()

    def coz(self, A, p, a, phi):
        m = self.m
        for i in range(self.n):
            m.A[i].set_value(float(A[i])); m.p[i].set_value(float(p[i])); m.a[i].set_value(float(a[i]))
        m.phi.set_value(float(phi))
        sonuc = self.cozucu.solve(m)
        assert sonuc.termination_condition == appsi.base.TerminationCondition.optimal
        al = lambda v: np.fromiter((v[i].value for i in range(self.n)), float, self.n)
        return {k: al(getattr(m, k)) for k in ["y", "k", "c", "d", "r"]}


def birim_toplamlar(y, k, c, d, r, A, G, q, a_norm, tavan_q: float) -> np.ndarray:
    """Bir yıllık dispatch'ten saklanan birim toplamlar (fiyat seviyesi 1 ve yan hizmet seviyesi 1 için)."""
    pay_g = np.divide(G, A, out=np.zeros_like(A), where=A > 0)
    yg, yr = y * pay_g, y * (1 - pay_g)
    return np.array([
        (yg * q).sum(), (yr * q).sum(), (d * q).sum(),                      # 0-2: spot gelir (L = 1)
        yg.sum(), yr.sum(), d.sum(), c.sum(), k.sum(), A.sum(),             # 3-8: enerjiler [MWh]
        (r * a_norm).sum(), r.sum(),                                        # 9-10: yan hizmet (seviye = 1), rezerv MWh
        (yg * np.minimum(q, tavan_q)).sum(), (yr * np.minimum(q, tavan_q)).sum(),
        (d * np.minimum(q, tavan_q)).sum(),                                 # 11-13: düzenleyici tavanlı spot gelir
    ])


def tablo_uret(t: Tasarim, ges: np.ndarray, res: np.ndarray, sekiller: dict, yan_sekil: np.ndarray,
               h_izgara, m_izgara, a_izgara, ppa_izgara, L_ref: float, a_ref: float, sabitler: dict,
               tavan_q: float = 0.70, log=None) -> dict:
    """
    sekiller[(s, h)] = birim fiyat şekli q (ortalama 1), yan_sekil (2, 8760) yan hizmet şekli (ortalama 1).
    Döndürür: {"T": dizi (W, S, H, M, Aa, Pp, alan), "izgara": ...}
    """
    W, S = ges.shape[0], 2
    H, M, Aa, Pp = len(h_izgara), len(m_izgara), len(a_izgara), len(ppa_izgara)
    Tb = np.zeros((W, S, H, M, Aa, Pp, len(ALANLAR)))
    pil = t.bess_mw > 0.5
    lp = IsletmeLP(t, **sabitler) if pil else None
    t0, sayac = time.time(), 0
    for w, s, ih, im, ia, ip in itertools.product(range(W), range(S), range(H), range(M), range(Aa), range(Pp)):
        G = t.ges_mw * ges[w]
        A = G + t.res_mw * m_izgara[im] * res[w]
        q = sekiller[(s, h_izgara[ih])]
        p = L_ref * q
        a_n = yan_sekil[s]
        phi = ppa_izgara[ip]
        if pil:
            r = lp.coz(A, p, a_ref * a_izgara[ia] * a_n, phi)
            y, k, c, d, rr = r["y"], r["k"], r["c"], r["d"], r["r"]
        else:   # bataryasız: kapalı form (ekonomik kesinti dahil)
            satis = ((1 - phi) * p + phi * sabitler["ppa_fiyat"] + (sabitler["yekg"] if t.yekg else 0)) > sabitler["teias_e"]
            y = np.where(satis, np.minimum(A, t.sebeke_mw), 0.0)
            k = A - y; c = d = rr = np.zeros_like(A)
        Tb[w, s, ih, im, ia, ip] = birim_toplamlar(y, k, c, d, rr, A, G, q, a_n, tavan_q)
        sayac += 1
    if log:
        log(f"  {t.ad}: {sayac} işletme durumu, {time.time() - t0:.0f} s")
    return {"T": Tb, "h": np.array(h_izgara), "m": np.array(m_izgara), "a": np.array(a_izgara), "ppa": np.array(ppa_izgara)}
