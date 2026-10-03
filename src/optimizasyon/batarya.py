"""
Basamak 1 — Sadece batarya arbitrajı (LP)

Soru: Sabit bir batarya (ör. 10 MW / 40 MWh) bir yıllık saatlik fiyatlarla şarj/deşarj planını nasıl
yapmalı ki gelir − yıpranma maliyeti en büyük olsun? (Öğrenme amaçlı: batarya şebekeden şarj olabilir.)

Kümeler      T = {0, …, n−1}  saatler
Parametreler p_t   fiyat [USD/MWh]
             P     güç sınırı [MW],  E  enerji kapasitesi [MWh]
             η_c, η_d  şarj ve deşarj verimi (η_c · η_d = gidiş-dönüş verimi)
             c_y   yıpranma maliyeti [USD/MWh deşarj]
             s_0   başlangıç şarj durumu [MWh]
Değişkenler  c_t ≥ 0  şarj gücü [MW],  d_t ≥ 0  deşarj gücü [MW],  s_t ≥ 0  şarj durumu (SOC) [MWh]
Amaç         max Σ_t [ p_t · (d_t − c_t) − c_y · d_t ]
Kısıtlar     s_t = s_{t−1} + η_c·c_t − d_t/η_d     (SOC dengesi; t = 0 için s_{−1} = s_0)
             c_t ≤ P,  d_t ≤ P,  s_t ≤ E
             s_{n−1} = s_0                          (yıl sonunda başlangıçtaki enerjiye dön)
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pyomo.environ as pyo


def arbitraj_coz(fiyat: np.ndarray, guc_mw: float, enerji_mwh: float, verim_gd: float,
                 yipranma: float, s0_oran: float = 0.5) -> tuple[pd.DataFrame, dict]:
    t0 = time.time()
    n = len(fiyat)
    eta = float(np.sqrt(verim_gd))          # şarj ve deşarj verimi eşit paylaştırılır

    m = pyo.ConcreteModel(name="Basamak1_Arbitraj")
    # --- Kümeler
    m.T = pyo.RangeSet(0, n - 1)
    # --- Parametreler
    m.p = pyo.Param(m.T, initialize=dict(enumerate(map(float, fiyat))))
    s0 = s0_oran * enerji_mwh
    # --- Karar değişkenleri
    m.c = pyo.Var(m.T, bounds=(0, guc_mw))          # şarj [MW]   (güç sınırı değişken sınırı olarak)
    m.d = pyo.Var(m.T, bounds=(0, guc_mw))          # deşarj [MW]
    m.s = pyo.Var(m.T, bounds=(0, enerji_mwh))      # şarj durumu [MWh] (enerji sınırı)
    # --- Amaç
    m.amac = pyo.Objective(expr=sum(m.p[t] * (m.d[t] - m.c[t]) - yipranma * m.d[t] for t in m.T), sense=pyo.maximize)
    # --- Kısıtlar
    def soc_dengesi(m, t):
        onceki = s0 if t == 0 else m.s[t - 1]
        return m.s[t] == onceki + eta * m.c[t] - m.d[t] / eta
    m.k_soc = pyo.Constraint(m.T, rule=soc_dengesi)
    m.k_son = pyo.Constraint(expr=m.s[n - 1] == s0)

    sonuc = pyo.SolverFactory("appsi_highs").solve(m)
    assert sonuc.solver.termination_condition == pyo.TerminationCondition.optimal

    df = pd.DataFrame({"fiyat": fiyat,
                       "sarj": [pyo.value(m.c[t]) for t in m.T],
                       "desarj": [pyo.value(m.d[t]) for t in m.T],
                       "soc": [pyo.value(m.s[t]) for t in m.T]})
    gelir = float((df.fiyat * (df.desarj - df.sarj)).sum())
    yip = yipranma * float(df.desarj.sum())
    ozet = {
        "Amaç (gelir − yıpranma) [USD]": pyo.value(m.amac),
        "Net arbitraj geliri [USD]": gelir, "Yıpranma maliyeti [USD]": yip,
        "Deşarj [MWh]": float(df.desarj.sum()), "Şarj [MWh]": float(df.sarj.sum()),
        "Eşdeğer tam döngü": float(df.desarj.sum() / enerji_mwh),
        "Ort. şarj fiyatı [USD/MWh]": float((df.fiyat * df.sarj).sum() / max(df.sarj.sum(), 1e-9)),
        "Ort. deşarj fiyatı [USD/MWh]": float((df.fiyat * df.desarj).sum() / max(df.desarj.sum(), 1e-9)),
        "Aynı saatte şarj ve deşarj (saat)": int(((df.sarj > 1e-6) & (df.desarj > 1e-6)).sum()),
        "Çözüm süresi [s]": time.time() - t0,
        "Değişken / kısıt sayısı": f"{3 * n} / {n + 1}",
    }
    return df, ozet
