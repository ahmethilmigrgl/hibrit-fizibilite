"""
Sahaya bağlı altyapı maliyetlerinin motora uygulanması (v3 E2/E4).

    teknoloji.sebeke.capex  ← bağlantı maliyeti (mesafe, gerilim) / bağlantı gücü          (v1: sabit 120.000 $/MW)
    teknoloji.res.capex     ← + (sahanın lojistik maliyeti − referans) [$/MW]               (RES CAPEX teslim edilmiş türbin varsayar)
    COD dağılımı            ← + max(0, teslim süresi − referans) [ay]                         (tam analizde; türbin tedariki kritik yolda)
Referans: mevcut RES santrallerinin bulunduğu ön tarama hücrelerinin medyanı (data/atlas/lojistik_referans.json).
Veri paketi yoksa hiçbir şey değişmez (uyarı listesine not düşülür).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache

from src.ayarlar import deger


@lru_cache(maxsize=1)
def referans() -> dict | None:
    from src import veri_katmani

    p = veri_katmani.yol("atlas/lojistik_referans.json", zorunlu=False)
    return None if p is None else json.loads(p.read_text())


def hesapla(enlem: float, boylam: float, baglanti_mw: float, cfg: dict, yaricap_km: float = 2.0) -> dict:
    from src.cbs import baglanti, katmanlar, lojistik

    cr = cfg["uretim"]["ruzgar"]
    tg = float(deger(cfg["optimizasyon"]["turbin_gucu"]))
    model = str(deger(cr["turbin_modeli"]))
    gobek = float(deger(cr["gobek_yuksekligi"]))
    out: dict = {"baglanti": None, "lojistik": None, "alan": None, "notlar": []}
    try:
        out["baglanti"] = baglanti.maliyet(enlem, boylam, baglanti_mw, cfg)
    except Exception as ex:  # veri yok
        out["notlar"].append(f"bağlantı: {type(ex).__name__}")
    N = max(1, math.ceil(baglanti_mw / tg))
    try:
        lj = lojistik.saha_lojistigi(enlem, boylam, N, cfg, model, tg)
        if lj is not None:
            ref = referans()
            lj["referans_usd_mw"] = ref["usd_mw"] if ref else None
            lj["referans_teslim_ay"] = ref["teslim_ay"] if ref else None
            lj["fark_usd_mw"] = lj["usd_mw"] - ref["usd_mw"] if ref else 0.0
            lj["gecikme_ay"] = max(0.0, lj["teslim_ay"] - ref["teslim_ay"]) if ref else 0.0
            for p in lj["plan"]:
                p["rota"] = lojistik.rota(p["kaynak"], lj["dugum"])[::25]
        out["lojistik"] = lj
    except Exception as ex:
        out["notlar"].append(f"lojistik: {type(ex).__name__}")
    try:
        from src.yerlesim.turbin import kutuphane_turbini

        D = kutuphane_turbini(model, gobek).D
        out["alan"] = katmanlar.alan_ozeti(enlem, boylam, yaricap_km, cfg, gobek, D)
    except Exception as ex:
        out["notlar"].append(f"alan: {type(ex).__name__}")
    return out


def uygula(cfg: dict, a: dict, baglanti_mw: float) -> None:
    from src.saha import _ata

    if a.get("baglanti"):
        bel = a["baglanti"].get("belirsizlik")  # Ö2: mesafe belirsizliği varsa beklenen değer (Monte Carlo senaryo başına çarpan)
        _ata(cfg, "teknoloji.sebeke.capex", (bel["beklenen_usd"] if bel else a["baglanti"]["toplam_usd"]) / baglanti_mw)
    lj = a.get("lojistik")
    if lj and lj.get("fark_usd_mw") is not None:
        _ata(cfg, "teknoloji.res.capex", float(deger(cfg["teknoloji"]["res"]["capex"])) + lj["fark_usd_mw"])
