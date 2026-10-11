"""
Portföy paketini okur (data/atlas/portfoy; src/v3_F1_adaylar.py).

duzeltme=True (varsayılan): optimize edicinin lanetine karşı Bayesçi büzülme uygulanır (data/atlas/portfoy/lanet.json;
src/v3_G1_optimizer_laneti.py): her adayın RES KF tahmini, tahmin belirsizliğine göre bölgesel ortalamaya doğru büzülür
ve tasarım NPV'leri V + κ (q − 1) ile düzeltilir.
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from src import veri_katmani
from src.portfoy.model import Veri


@lru_cache(maxsize=2)
def yukle(duzeltme: bool = True) -> Veri:
    tas = pd.read_csv(veri_katmani.yol("atlas/portfoy/tasarimlar.csv"))
    ad = pd.read_csv(veri_katmani.yol("atlas/portfoy/adaylar.csv"))
    z = np.load(veri_katmani.yol("atlas/portfoy/npv.npz"))
    V = z["npv"].astype(float)[tas["satir"].to_numpy()]
    loj = pd.read_parquet(veri_katmani.yol("atlas/portfoy/lojistik.parquet"))
    p = veri_katmani.yol("atlas/portfoy/lanet.json", zorunlu=False)
    if duzeltme and p is not None:
        ln = json.loads(p.read_text(encoding="utf-8"))
        q = tas["kod"].map(ln["q"]).fillna(1.0).to_numpy()
        k = tas["satir"].map({int(a): b for a, b in ln["kappa_satir"].items()}).fillna(0.0).to_numpy()
        d = k * (q - 1)
        tas = tas.assign(e_npv=tas["e_npv"] + d, cvar5=tas["cvar5"] + d)
        V = V + d[:, None]
    return Veri(tas=tas.reset_index(drop=True), ad=ad, V=V, lojistik=loj)


@lru_cache(maxsize=1)
def ortak() -> dict:
    z = np.load(veri_katmani.yol("atlas/portfoy/npv.npz"))
    return {k: z[k] for k in ("L10", "capex_res", "w10", "senaryo")}
