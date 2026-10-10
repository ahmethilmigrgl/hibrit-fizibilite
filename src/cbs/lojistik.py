"""
Lojistik ve tedarik zinciri (v3 E4).

Ağır nakliye ağı (çevrimdışı, src/v3_E4_nakliye_agi.py): OSM otoyol/devlet/il yolu (+ ikincil yol ×1,5 ceza, %10'u aşan
eğimli kesitler ×1,5) → sadeleştirilmiş çizge; her tedarik kaynağından (liman, yerli üretici) tüm düğümlere en kısa
(etkin) yol: data/grid/lojistik_tr/v1/ag.npz.

Ulaştırma modeli (LP; Faz F'de çoklu saha ve üretici kapasiteleriyle aynı fonksiyon kullanılır):
    Kümeler      C bileşenler (kanat, kule, nasel, göbek), S kaynaklar, J sahalar
    Parametreler c_{c,s,j} birim (türbin seti) teslim maliyeti = adet_c · [sefer sabit + izin/eskort + τ · m_c · d_{s,j}]
                           + (s liman ise) adet_c · navlun_c + yerli fiyat farkı;  D_{c,j} talep (türbin sayısı);  K_{c,s} kapasite
    Değişken     x_{c,s,j} ≥ 0 (türbin seti)
    Amaç         min Σ c_{c,s,j} x_{c,s,j}
    Kısıtlar     Σ_s x_{c,s,j} = D_{c,j}  ∀c,j (talep);   Σ_j x_{c,s,j} ≤ K_{c,s}  ∀c,s (kapasite);   x = 0 (s, c'yi sağlamıyorsa)
Teslim süresi: seçilen her bileşen için tedarik süresi (yerli/ithal) + yol süresi (km / km_gün); proje = en uzun bileşen.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import config_oku, deger

BILESENLER = ("kanat", "kule", "nasel", "gobek")


@lru_cache(maxsize=1)
def ag() -> dict | None:
    from src import veri_katmani

    p = veri_katmani.yol("grid/lojistik_tr/v1/ag.npz", zorunlu=False)
    if p is None:
        return None
    z = np.load(p, allow_pickle=False)
    from scipy.spatial import cKDTree

    d = {k: z[k] for k in z.files}
    lat0 = 39.0
    d["agac"] = cKDTree(np.c_[d["enlem"], d["boylam"] * np.cos(np.radians(lat0))])
    return d


@lru_cache(maxsize=1)
def kaynaklar() -> pd.DataFrame:
    from src import veri_katmani

    return pd.read_csv(veri_katmani.yol("atlas/tedarik_kaynaklari.csv"))


def mesafeler(enlem: float, boylam: float, cfg: dict | None = None) -> dict | None:
    """Her kaynaktan sahaya etkin yol mesafesi [km] (ağ + ağ dışı son kısım × çarpan) ve en yakın düğüm."""
    a = ag()
    if a is None:
        return None
    cfg = cfg or config_oku()
    t = deger(cfg["v3"]["lojistik"])["tasima"]
    dd, i = a["agac"].query([enlem, boylam * np.cos(np.radians(39.0))])
    son_km = float(dd) * 111.32 * t["ag_disi_carpan"]
    km = a["mesafe"][:, i].astype(float) + son_km
    adlar = [str(x) for x in a["kaynak_ad"]]
    return {"km": dict(zip(adlar, km)), "dugum": int(i), "son_km": son_km}


def rota(kaynak_ad: str, dugum: int) -> list[tuple[float, float]]:
    """Kaynaktan düğüme ağ üzerindeki rota (enlem, boylam) listesi (öncül dizisinden)."""
    a = ag()
    k = [str(x) for x in a["kaynak_ad"]].index(kaynak_ad)
    pred = a["oncul"][k]
    yol, j = [], int(dugum)
    for _ in range(200000):
        yol.append((float(a["enlem"][j]), float(a["boylam"][j])))
        if pred[j] < 0:
            break
        j = int(pred[j])
    return yol[::-1]


def birim_maliyet(cfg: dict, km: dict[str, float], turbin_modeli: str = "") -> pd.DataFrame:
    """(bileşen, kaynak) başına türbin seti teslim maliyeti [$] ve teslim süresi [ay]."""
    L = deger(cfg["v3"]["lojistik"])
    t = L["tasima"]
    K = kaynaklar()
    satir = []
    for c, b in L["bilesenler"].items():
        for r in K.itertuples():
            if not r.dogrulandi or c not in str(r.bilesenler).split(";") or r.ad not in km:
                continue
            if "Nordex" in r.ad and not turbin_modeli.upper().startswith("N"):
                continue  # Nordex nasel montajı yalnız Nordex türbinleri için
            liman = r.tur == "liman"
            d = km[r.ad]
            tasima = b["adet"] * (t["sefer_sabit_usd"] + t["izin_eskort_usd"] + t["usd_t_km"] * b["kutle_t"] * d)
            ek = b["adet"] * b["ithal_navlun_usd"] if liman else b["adet"] * L["yerli_fiyat_farki"]
            sure = (b["ithal_sure_ay"] if liman else b["yerli_sure_ay"]) + d / t["km_gun"] / 30.0
            satir.append(
                {
                    "bilesen": c,
                    "kaynak": r.ad,
                    "tur": r.tur,
                    "km": d,
                    "tasima_usd": tasima,
                    "ek_usd": ek,
                    "birim_usd": tasima + ek,
                    "sure_ay": sure,
                }
            )
    return pd.DataFrame(satir)


def ulastirma(
    birim: dict[tuple[str, str, int], float], talep: dict[tuple[str, int], float], kapasite: dict[tuple[str, str], float]
) -> dict:
    """Genel ulaştırma LP'si (HiGHS, scipy.linprog). birim: (bileşen, kaynak, saha) → $/set; talep: (bileşen, saha) → set."""
    from scipy.optimize import linprog

    anahtar = list(birim)
    c = np.array([birim[k] for k in anahtar])
    A_eq, b_eq = [], []
    for (bc, j), D in talep.items():
        A_eq.append([1.0 if (k[0] == bc and k[2] == j) else 0.0 for k in anahtar])
        b_eq.append(D)
    A_ub, b_ub = [], []
    for (bc, s), cap in kapasite.items():
        satir = [1.0 if (k[0] == bc and k[1] == s) else 0.0 for k in anahtar]
        if any(satir):
            A_ub.append(satir)
            b_ub.append(cap)
    r = linprog(c, A_ub=A_ub or None, b_ub=b_ub or None, A_eq=A_eq, b_eq=b_eq, bounds=(0, None), method="highs")
    if not r.success:
        raise RuntimeError(f"Ulaştırma LP'si çözülemedi: {r.message}")
    x = {k: float(v) for k, v in zip(anahtar, r.x) if v > 1e-9}
    return {"x": x, "maliyet": float(r.fun), "dual_talep": list(r.eqlin.marginals)}


def saha_lojistigi(enlem: float, boylam: float, N: int, cfg: dict | None = None, turbin_modeli: str = "", P_mw: float = 4.2) -> dict | None:
    """Tek saha: en ucuz tedarik planı (LP), maliyet [$, $/MW], teslim süresi [ay], seçilen rotalar."""
    cfg = cfg or config_oku()
    m = mesafeler(enlem, boylam, cfg)
    if m is None or N <= 0:
        return None
    bm = birim_maliyet(cfg, m["km"], turbin_modeli)
    L = deger(cfg["v3"]["lojistik"])
    birim = {(r.bilesen, r.kaynak, 0): r.birim_usd for r in bm.itertuples()}
    talep = {(c, 0): float(N) for c in L["bilesenler"]}
    kap = {(c, s): float(v) for s, v in L["kapasite_turbin_yil"].items() for c in L["bilesenler"]}
    r = ulastirma(birim, talep, kap)
    plan = []
    for (c, s, _), x in r["x"].items():
        b = bm[(bm.bilesen == c) & (bm.kaynak == s)].iloc[0]
        plan.append(
            {"bilesen": c, "kaynak": s, "tur": b["tur"], "set": x, "km": b["km"], "birim_usd": b["birim_usd"], "sure_ay": b["sure_ay"]}
        )
    plan = pd.DataFrame(plan)
    return {
        "maliyet_usd": r["maliyet"],
        "usd_mw": r["maliyet"] / (N * P_mw),
        "teslim_ay": float(plan["sure_ay"].max()),
        "plan": plan.to_dict(orient="records"),
        "dugum": m["dugum"],
        "son_km": m["son_km"],
        "alternatifler": bm.to_dict(orient="records"),
    }
