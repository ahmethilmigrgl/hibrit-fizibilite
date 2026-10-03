"""
Türetilmiş finansal göstergeler.

Başabaş fiyat: NPV'yi sıfır yapan reel yıllık ortalama (baz yük) fiyat seviyesi L [USD/MWh].
Fiyat şekli ve kanibalizasyon varyantı sabit tutulur; yalnızca seviye L değişir (Brent kök bulma).
"""

from __future__ import annotations

from scipy.optimize import brentq

from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.model import BessDispatch, Varsayimlar, proje_degerle
from src.finans.veri import UretimProfili


def basabas_fiyat(konfig: dict, cfg: dict, uretim: UretimProfili, v: Varsayimlar,
                  kanibalizasyon: str = "devam", bess_dispatch: BessDispatch | None = None,
                  alt: float = 5.0, ust: float = 250.0) -> float:
    def npv(L: float) -> float:
        f = fiyat_senaryosu_uret(cfg, uretim, L, kanibalizasyon)
        return proje_degerle(konfig, v, f, uretim, bess_dispatch=bess_dispatch).npv
    return brentq(npv, alt, ust, xtol=0.01)
