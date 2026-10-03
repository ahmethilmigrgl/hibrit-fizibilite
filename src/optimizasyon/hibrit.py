"""
Basamak 2 — Sabit hibrit santral (GES + RES) + batarya, ortak şebeke bağlantısı (LP)

Kümeler      T  saatler
Parametreler A_t   kullanılabilir üretim = GES_MW·g_t + RES_MW·r_t [MW]
             p_t   fiyat [USD/MWh],  L  şebeke bağlantı kapasitesi [MW]
             P, E  batarya güç [MW] ve enerji [MWh],  η_c, η_d  verimler,  c_y  yıpranma [USD/MWh]
Değişkenler  y_t   santralden doğrudan şebekeye [MW]       k_t  kesinti [MW]
             c_t   santralden bataryaya şarj [MW]          g_t  şebekeden şarj [MW] (yalnızca izin varsa)
             d_t   bataryadan deşarj [MW]                  s_t  şarj durumu [MWh]
             x_t = y_t + d_t  şebekeye verilen [MW]
Amaç         max Σ_t [ (p_t − τ_e) · (y_t + d_t) − p_t · g_t − c_y · d_t ]   (τ_e: TEİAŞ enerji bedeli, Basamak 2'de 0)
Kısıtlar     y_t + k_t + c_t = A_t                    (üretim dengesi: üretim satılır, kesilir ya da şarj edilir)
             y_t + d_t ≤ L                            (şebeke kısıtı; dual değeri = bağlantının o saatteki gölge fiyatı)
             g_t ≤ L,  g_t = 0 (şebekeden şarj kapalıysa)
             s_t = s_{t−1} + η_c·(c_t + g_t) − d_t/η_d   (SOC dengesi),  s_{n−1} = s_{−1} = s_0
             c_t + g_t ≤ P,  d_t ≤ P,  s_t ≤ E
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib import appsi


def _model_kur(n: int, L: float, P: float, E: float, eta: float, yipranma: float, sebekeden: bool,
               teias_e: float = 0.0, s0_oran: float = 0.5) -> pyo.ConcreteModel:
    m = pyo.ConcreteModel(name="Basamak2_Hibrit")
    # --- Kümeler
    m.T = pyo.RangeSet(0, n - 1)
    # --- Parametreler (değiştirilebilir: aynı model farklı fiyat/üretimle tekrar çözülebilir)
    m.A = pyo.Param(m.T, mutable=True, initialize=0.0)
    m.p = pyo.Param(m.T, mutable=True, initialize=0.0)
    s0 = s0_oran * E
    # --- Karar değişkenleri
    m.y = pyo.Var(m.T, within=pyo.NonNegativeReals)
    m.k = pyo.Var(m.T, within=pyo.NonNegativeReals)
    m.c = pyo.Var(m.T, bounds=(0, P))
    m.g = pyo.Var(m.T, bounds=(0, L if sebekeden else 0))
    m.d = pyo.Var(m.T, bounds=(0, P))
    m.s = pyo.Var(m.T, bounds=(0, E))
    # --- Amaç
    m.amac = pyo.Objective(expr=sum((m.p[t] - teias_e) * (m.y[t] + m.d[t]) - m.p[t] * m.g[t] - yipranma * m.d[t]
                                    for t in m.T),
                           sense=pyo.maximize)
    # --- Kısıtlar
    m.k_uretim = pyo.Constraint(m.T, rule=lambda m, t: m.y[t] + m.k[t] + m.c[t] == m.A[t])
    m.k_sebeke = pyo.Constraint(m.T, rule=lambda m, t: m.y[t] + m.d[t] <= L)
    m.k_sarj_guc = pyo.Constraint(m.T, rule=lambda m, t: m.c[t] + m.g[t] <= P)
    m.k_soc = pyo.Constraint(m.T, rule=lambda m, t: m.s[t] == (s0 if t == 0 else m.s[t - 1])
                             + eta * (m.c[t] + m.g[t]) - m.d[t] / eta)
    m.k_son = pyo.Constraint(expr=m.s[n - 1] == s0)
    return m


class HibritDispatch:
    """Sabit kapasiteli hibrit + batarya için tekrar kullanılabilir (persistent) dispatch çözücüsü."""

    def __init__(self, n: int, L: float, P: float, E: float, verim_gd: float, yipranma: float,
                 sebekeden: bool = False, dual: bool = False, teias_e: float = 0.0):
        self.n, self.L, self.P, self.E = n, L, P, E
        self.m = _model_kur(n, L, P, E, float(np.sqrt(verim_gd)), yipranma, sebekeden, teias_e)
        if dual:
            self.m.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
        self.cozucu = appsi.solvers.Highs()
        self.cozucu.config.load_solution = True

    def coz(self, uretim: np.ndarray, fiyat: np.ndarray) -> dict[str, np.ndarray]:
        for t in range(self.n):
            self.m.A[t].set_value(float(uretim[t]))
            self.m.p[t].set_value(float(fiyat[t]))
        sonuc = self.cozucu.solve(self.m)
        assert sonuc.termination_condition == appsi.base.TerminationCondition.optimal, sonuc.termination_condition
        al = lambda v: np.fromiter((v[t].value for t in range(self.n)), float, self.n)
        cikti = {"y": al(self.m.y), "k": al(self.m.k), "c": al(self.m.c), "g": al(self.m.g),
                 "d": al(self.m.d), "s": al(self.m.s), "amac": pyo.value(self.m.amac)}
        if hasattr(self.m, "dual"):
            self.cozucu.load_vars()
            dualler = self.cozucu.get_duals(cons_to_load=[self.m.k_sebeke[t] for t in range(self.n)])
            cikti["sebeke_golge"] = np.array([abs(dualler[self.m.k_sebeke[t]]) for t in range(self.n)])
        return cikti


def hibrit_coz(G: np.ndarray, R: np.ndarray, fiyat: np.ndarray, L: float, P: float, E: float,
               verim_gd: float, yipranma: float, sebekeden: bool = False) -> tuple[pd.DataFrame, dict]:
    """Basamak 2: tek bir yıl için çöz, bataryasız durumla karşılaştır, gölge fiyatları döndür."""
    t0 = time.time()
    n = len(fiyat)
    A = G + R
    r = HibritDispatch(n, L, P, E, verim_gd, yipranma, sebekeden, dual=True).coz(A, fiyat)
    df = pd.DataFrame({"fiyat": fiyat, "ges": G, "res": R, "kullanilabilir": A, "dogrudan": r["y"], "kesinti": r["k"],
                       "sarj": r["c"], "sebekeden_sarj": r["g"], "desarj": r["d"], "soc": r["s"],
                       "sebekeye": r["y"] + r["d"], "sebeke_golge": r["sebeke_golge"]})
    # Bataryasız referans
    sat0 = np.minimum(A, L)
    gelir0 = float((sat0 * fiyat).sum())
    gelir1 = float((df.sebekeye * fiyat).sum() - (df.sebekeden_sarj * fiyat).sum())
    ozet = {
        "Bataryasız gelir [USD]": gelir0, "Bataryalı gelir [USD]": gelir1, "Ek gelir [USD]": gelir1 - gelir0,
        "Yıpranma [USD]": yipranma * float(df.desarj.sum()),
        "Ek gelir − yıpranma [USD]": gelir1 - gelir0 - yipranma * float(df.desarj.sum()),
        "Bataryasız kesinti [MWh]": float((A - sat0).sum()), "Bataryalı kesinti [MWh]": float(df.kesinti.sum()),
        "Kurtarılan kesinti [MWh]": float((A - sat0).sum() - df.kesinti.sum()),
        "Zamanda kaydırılan enerji (deşarj) [MWh]": float(df.desarj.sum()),
        "Şarjın kesintiden gelen payı [%]": float(100 * ((A - sat0).sum() - df.kesinti.sum()) / max(df.sarj.sum(), 1e-9)),
        "Yakalanan fiyat bataryasız [USD/MWh]": gelir0 / sat0.sum(),
        "Yakalanan fiyat bataryalı [USD/MWh]": gelir1 / float(df.sebekeye.sum() - df.sebekeden_sarj.sum()),
        "Eşdeğer tam döngü": float(df.desarj.sum() / E),
        "Şebeke dolu saat (bataryalı)": int((df.sebekeye > L - 1e-6).sum()),
        "Gölge fiyatı > 0 saat": int((df.sebeke_golge > 1e-6).sum()),
        "Çözüm süresi [s]": time.time() - t0,
    }
    return df, ozet


def temsili_hava_yili(ges: np.ndarray, res: np.ndarray, yillar: list[int]) -> int:
    """GES ve RES yıllık KF'si 10 yıl ortalamasına (standartlaştırılmış uzaklıkla) en yakın hava yılının indeksi."""
    g, r = ges.mean(axis=1), res.mean(axis=1)
    uzaklik = ((g - g.mean()) / g.std()) ** 2 + ((r - r.mean()) / r.std()) ** 2
    return int(np.argmin(uzaklik))


def dispatch_kancasi(verim_gd: float, yipranma: float, teias_e: float, sebekeden: bool = False):
    """
    Aşama 3 proje_degerle için batarya kancası: her (fiyat-yılı grubu, hava yılı, şekil yılı) için 8760 saatlik
    dispatch LP'si çözülür. Fiyatı aynı olan yıllar (ör. kanibalizasyon tabanına ulaştıktan sonraki yıllar)
    tek grupta toplanır ve grubun ilk yılının (degrade) üretimiyle çözülen plan gruptaki tüm yıllara uygulanır.
    Grupta sonraki yıllarda degradasyon nedeniyle üretim biraz düşük olduğundan şarj, o saatteki
    kullanılabilir üretimle sınırlanır (küçük yaklaşım; bkz. docs/04).
    Döndürür: (x, d, c) — şebekeye verilen, deşarj, santralden şarj; şekil (N, W, S, 8760).
    """
    def kanca(Gx, Rx, P4, konfig, v):
        N, W, _, T = Gx.shape
        S = P4.shape[2]
        A = (Gx + Rx)[:, :, 0, :]                                       # (N, W, T)
        x = np.zeros((N, W, S, T)); d = np.zeros_like(x); c = np.zeros_like(x)
        cozucu = HibritDispatch(T, konfig.sebeke_mw, konfig.bess_mw, konfig.bess_mwh, verim_gd, yipranma,
                                sebekeden, teias_e=teias_e)
        # Fiyat-yılı grupları: ardışık özdeş fiyat dizileri
        gruplar, bas = [], 0
        for n in range(1, N + 1):
            if n == N or not np.array_equal(P4[n, 0], P4[bas, 0]):
                gruplar.append((bas, n)); bas = n
        for (b, e) in gruplar:
            for w in range(W):
                for s in range(S):
                    r = cozucu.coz(A[b, w], P4[b, 0, s])
                    for n in range(b, e):
                        cc = np.minimum(r["c"], A[n, w])
                        x[n, w, s] = np.minimum(np.clip(A[n, w] - r["k"] - cc, 0, None) + r["d"], konfig.sebeke_mw)
                        d[n, w, s] = r["d"]; c[n, w, s] = cc
        return x, d, c
    return kanca
