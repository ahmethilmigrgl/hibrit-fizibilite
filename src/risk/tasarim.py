"""
Tasarım tanımı ve işletme tablosu alan adları — pyomo gerektirmeyen hafif modül
(dashboard ve değerleyici bunu içe aktarır; LP'ler src/risk/isletme.py'de).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tasarim:
    ad: str
    res_mw: float
    ges_mw: float
    bess_mw: float = 0.0
    bess_mwh: float = 0.0
    sebeke_mw: float = 50.0
    yan_hizmet: bool = False
    dengesizlik_azaltim: bool = False
    yekg: bool = False
    ppa: bool = False


# İşletme tablosunun son boyutundaki alanlar (src/risk/isletme.py → birim_toplamlar)
ALANLAR = [
    "gelir_ges_q",
    "gelir_res_q",
    "gelir_d_q",
    "E_ges",
    "E_res",
    "E_d",
    "E_c",
    "E_k",
    "E_A",
    "yh_a",
    "rezerv",
    "gelir_ges_qt",
    "gelir_res_qt",
    "gelir_d_qt",
]
