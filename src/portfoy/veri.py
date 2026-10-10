"""Portföy paketini okur (data/atlas/portfoy; src/v3_F1_adaylar.py)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from src import veri_katmani
from src.portfoy.model import Veri


@lru_cache(maxsize=1)
def yukle() -> Veri:
    tas = pd.read_csv(veri_katmani.yol("atlas/portfoy/tasarimlar.csv"))
    ad = pd.read_csv(veri_katmani.yol("atlas/portfoy/adaylar.csv"))
    z = np.load(veri_katmani.yol("atlas/portfoy/npv.npz"))
    V = z["npv"].astype(float)[tas["satir"].to_numpy()]
    loj = pd.read_parquet(veri_katmani.yol("atlas/portfoy/lojistik.parquet"))
    return Veri(tas=tas.reset_index(drop=True), ad=ad, V=V, lojistik=loj)


@lru_cache(maxsize=1)
def ortak() -> dict:
    z = np.load(veri_katmani.yol("atlas/portfoy/npv.npz"))
    return {k: z[k] for k in ("L10", "capex_res", "w10", "senaryo")}
