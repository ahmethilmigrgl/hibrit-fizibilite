"""Analiz sonucu: JSON'a serileştirilebilir özet + tablolar (parquet) + grafik verileri."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


def _temiz(x):
    if isinstance(x, dict):
        return {str(k): _temiz(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_temiz(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return _temiz(x.tolist())
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


@dataclass
class Sonuc:
    mod: str
    saha: dict
    varsayimlar: dict
    ozet: dict = field(default_factory=dict)
    tablolar: dict[str, pd.DataFrame] = field(default_factory=dict)
    grafikler: dict = field(default_factory=dict)  # grafik verileri (listeler)
    nedenler: list[dict] = field(default_factory=list)  # [{"tr": ..., "en": ...}]
    uyarilar: list[dict] = field(default_factory=list)
    sure_s: dict = field(default_factory=dict)
    veri_surumu: str = ""

    def json(self) -> str:
        d = {
            k: getattr(self, k)
            for k in ("mod", "saha", "varsayimlar", "ozet", "grafikler", "nedenler", "uyarilar", "sure_s", "veri_surumu")
        }
        d["tablolar"] = {k: v.reset_index().to_dict(orient="records") for k, v in self.tablolar.items()}
        return json.dumps(_temiz(d), ensure_ascii=False)

    def kaydet(self, klasor: Path) -> None:
        klasor.mkdir(parents=True, exist_ok=True)
        (klasor / "sonuc.json").write_text(self.json(), encoding="utf-8")
        for k, v in self.tablolar.items():
            v.to_parquet(klasor / f"{k}.parquet")
