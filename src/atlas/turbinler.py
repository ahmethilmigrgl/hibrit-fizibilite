"""
Santral türbin vekili: OSM türbin etiketlerinden (birim güç, üretici, rotor, göbek) windpowerlib kütüphanesindeki en yakın
güç eğrisine eşleme. Kalibrasyonda her santral kendi vekiliyle modellenir; böylece eski/küçük türbinlerin düşük verimi
"düşük rüzgâr" olarak k'ya girip yeni sahaya taşınmaz.

Kural (config v2.santral_turbin):
    SP_hedef = P / (π D² / 4)              rotor çapı OSM'de varsa
             = sınıf varsayılanı           yoksa (birim güç sınıfına göre)
    aday: kütüphanede güç eğrili, |P_lib / P − 1| ≤ tolerans (üretici biliniyorsa önce onun türbinleri)
    skor = |ln(SP_lib / SP_hedef)| + w · |ln(P_lib / P)|  → en küçük
    göbek: OSM height:hub, yoksa sınıf varsayılanı
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import config_oku, deger


@lru_cache(maxsize=1)
def kutuphane() -> pd.DataFrame:
    import windpowerlib

    d = pd.read_csv(os.path.join(os.path.dirname(windpowerlib.__file__), "oedb", "turbine_data.csv"))
    d = d[d["has_power_curve"] == True].copy()  # noqa: E712 (pandas maskesi)
    # Güç eğrisi 20 m/s'den önce biten türbinler (ör. kütüphanedeki V90/2000: 16,5 m/s) çıkarılır: rüzgârlı sahada
    # yüksek hız saatleri sıfır üretime düşer ve kalibrasyon k'yı arama sınırına iter.
    pc = pd.read_csv(os.path.join(os.path.dirname(windpowerlib.__file__), "oedb", "power_curves.csv")).set_index("turbine_type")
    son = pc.apply(lambda r: max((float(c) for c, v in r.items() if v == v and v > 0), default=0.0), axis=1)
    d = d[d["turbine_type"].map(son).fillna(0) >= 20.0].copy()
    d["p_mw"] = d["nominal_power"] / 1e6
    d["sp"] = d["nominal_power"] / (np.pi * (d["rotor_diameter"] / 2) ** 2)
    return d[["turbine_type", "manufacturer", "p_mw", "rotor_diameter", "sp"]].reset_index(drop=True)


def mw_coz(etiket: str | None) -> float | None:
    """OSM generator:output:electricity → MW ('3 MW', '2,375 MW', '2300 kW'); 'yes' ve boş → None."""
    if not etiket:
        return None
    m = re.match(r"^\s*([\d.,]+)\s*(MW|kW|W)?", str(etiket), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    birim = (m.group(2) or "MW").lower()
    v = v / 1000 if birim == "kw" else v / 1e6 if birim == "w" else v
    return v if 0.1 <= v <= 10 else None


def sayi_coz(etiket: str | None) -> float | None:
    if not etiket:
        return None
    m = re.match(r"^\s*([\d.,]+)", str(etiket))
    return float(m.group(1).replace(",", ".")) if m else None


def esle(birim_mw: float, uretici: str | None = None, rotor_m: float | None = None, gobek_m: float | None = None, cfg=None) -> dict:
    """Birim güç (+ isteğe bağlı üretici, rotor, göbek) → kütüphane türbini ve göbek."""
    st = deger((cfg or config_oku())["v2"]["santral_turbin"])
    sinif = next(s for s in st["siniflar"] if birim_mw < s["mw_ust"])
    sp_hedef = birim_mw * 1e6 / (np.pi * (rotor_m / 2) ** 2) if rotor_m else sinif["ozgul_guc"]
    k = kutuphane()
    aday = k[(k["p_mw"] / birim_mw - 1).abs() <= st["guc_toleransi"]]
    if aday.empty:
        aday = k
    skor = (np.log(aday["sp"] / sp_hedef)).abs() + st["guc_agirligi"] * (np.log(aday["p_mw"] / birim_mw)).abs()
    sec = aday.loc[skor.idxmin()]
    onek = st["uretici_onek"].get(uretici or "", [])
    if onek:  # üreticinin türbini ancak özgül gücü hedefe yakınsa (kütüphanede o üreticinin eski platformları eksik olabilir)
        u = aday["turbine_type"].str.startswith(tuple(onek)) & (np.log(aday["sp"] / sp_hedef).abs() <= st["uretici_sp_toleransi"])
        if u.any():
            sec = aday.loc[skor[u].idxmin()]
    return {
        "turbin": sec["turbine_type"],
        "gobek": float(gobek_m) if gobek_m else float(sinif["gobek"]),
        "sp_hedef": float(sp_hedef),
        "sp_secilen": float(sec["sp"]),
        "kural": ("rotor" if rotor_m else "sinif")
        + ("+uretici" if onek and sec["turbine_type"].startswith(tuple(onek)) else "")
        + ("+gobek_osm" if gobek_m else ""),
    }
