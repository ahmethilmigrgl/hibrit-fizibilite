"""
Gelir yığını parametrelerinin kapasite MILP'i için hazırlanması (seviyelendirme).

Kapasite modeli tek bir "temsilî yıl" kullandığı için zamanla değişen kalemler, işletme yıllarının
iskonto çarpanlarıyla (DF_k) ağırlıklı ortalamaya çevrilir:
    yan hizmet fiyatı  p̂^YH_t = Σ_k DF_k · p^YH_{k,t} / Σ_k DF_k       (yıllık azalma + taban dahil)
    PPA payı           φ̂ = φ · Σ_{k ≤ vade} DF_k / Σ_k DF_k            (vade sonunda PPA biter)
    PPA fiyatı         sabit reel (baz seviye × (1 − iskonto))
    ön lisans edinme   tek seferlik maliyet → yıllık eşdeğer: edinme × a_cap (CAPEX gibi)
"""

from __future__ import annotations

import numpy as np

from src.ayarlar import deger
from src.finans.fiyat_senaryosu import FiyatSenaryosu
from src.finans.model import Varsayimlar
from src.optimizasyon.kapasite import Ekonomi


def gelir_parametreleri(cfg: dict, v: Varsayimlar, eko: Ekonomi, f: FiyatSenaryosu, kalemler: set[str],
                        baz_seviye: float | None = None) -> tuple[dict, list[np.ndarray] | None]:
    """
    kalemler ⊆ {"yh", "dz", "yekg", "ppa", "dl"}. Döndürür: (MILP 'gelir' sözlüğü, segment yan hizmet fiyatları).
    """
    gy = cfg["gelir_yigini"]
    DF = (1 + v.wacc) ** -(v.insaat_suresi + np.arange(1, v.omur + 1))
    gelir, yanlar = {}, None
    if "yh" in kalemler:
        y = gy["yan_hizmet"]
        gelir["yh"] = {"azami": deger(y["azami_rezerv"]), "asgari": deger(y["asgari_guc"]), "h": deger(y["enerji_saat"])}
        yan_lev = (f.yan_hizmet * DF[:, None, None]).sum(0) / DF.sum()          # (S, 8760)
        yanlar = [yan_lev[0], yan_lev[1]]
    if "dz" in kalemler:
        d = gy["dengesizlik_azaltim"]
        gelir["dz"] = {"azami_oran": deger(d["azami_oran"]), "doyum_orani": deger(d["doyum_orani"])}
    if "yekg" in kalemler:
        gelir["yekg"] = deger(gy["yekg"])
    if "ppa" in kalemler:
        pp = gy["ppa"]
        vade = deger(pp["vade"])
        L0 = baz_seviye if baz_seviye is not None else deger(cfg["fiyat_senaryolari"]["seviye"])["baz"]
        # P90/P50 ≈ 0,93-0,95 (Aşama 3) → saatlik pay ≈ 0,70 × 0,94
        phi = deger(pp["pay"]) * 0.94
        gelir["ppa"] = {"phi": phi * DF[:vade].sum() / DF.sum(), "fiyat": L0 * (1 - deger(pp["iskonto"])),
                        "phi_saatlik": phi, "vade": vade}
    if "dl" in kalemler:
        gelir["dl"] = {"edinme_yillik": deger(gy["depolamali_lisans"]["edinme_maliyeti"]) * eko.a_cap}
    return gelir, yanlar
