"""
Şebeke bağlantı ve erişim maliyeti (v3 E2), config v3.baglanti.

    gerilim V = kural(kurulu bağlantı gücü)            (≤ 30 MW 34,5 kV; ≤ 300 MW 154 kV; üstü 380/400 kV)
    hedef     = gerilimi ≥ max(V, 154) olan en yakın OSM trafo merkezi (34,5 kV bağlantı TEİAŞ TM'nin OG barasına)
    maliyet   = proje TM(V) + fider(V) + d_TM · güzergâh çarpanı · hat($/km, V) + max(0, d_yol − dahil) · güzergâh çarpanı · yol($/km)
d_yol: ağır nakliyeye uygun en yakın yola (otoyol/devlet/il yolu; yoksa ikincil yol × ceza) uzaklık.
TEİAŞ bağlantı kapasitesi ve tahsis katkı payı dahil değildir.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import config_oku, deger


@lru_cache(maxsize=1)
def trafolar() -> pd.DataFrame:
    from src import veri_katmani

    t = pd.read_csv(veri_katmani.yol("atlas/trafo_merkezleri.csv"))
    return t[t["kv"].notna()].reset_index(drop=True)


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def gerilim(mw: float, cfg: dict) -> float:
    return next(float(k["kv"]) for k in deger(cfg["v3"]["baglanti"])["gerilim_kurali"] if mw <= k["mw_ust"])


def en_yakin_trafo(enlem: float, boylam: float, kv_asgari: float) -> dict:
    t = trafolar()
    t = t[t["kv"] >= kv_asgari - 1e-6]
    d = _km(enlem, boylam, t["enlem"].to_numpy(), t["boylam"].to_numpy())
    i = int(np.argmin(d))
    r = t.iloc[i]
    return {
        "ad": r["ad"] if isinstance(r["ad"], str) else "(adsız)",
        "kv": float(r["kv"]),
        "enlem": float(r["enlem"]),
        "boylam": float(r["boylam"]),
        "km": float(d[i]),
    }


def yol_mesafesi_m(enlem: float, boylam: float, cfg: dict) -> tuple[float | None, str]:
    from src.cbs import katmanlar

    d = katmanlar.degerler(enlem, boylam)
    if d is None:
        return None, "veri yok"
    c = deger(cfg["v3"]["cbs"])
    agir = float(np.nanmin([d["otoyol"][0], d["devlet"][0]]))
    ikincil = float(d["ikincil"][0]) * c["kosullu_yol_ceza"]
    return (agir, "otoyol/devlet/il yolu") if agir <= ikincil else (ikincil, "ikincil yol (×ceza)")


def maliyet(enlem: float, boylam: float, mw: float, cfg: dict | None = None) -> dict:
    cfg = cfg or config_oku()
    b = deger(cfg["v3"]["baglanti"])
    V = gerilim(mw, cfg)
    anahtar = "34.5" if V < 100 else ("154" if V < 300 else "400")
    hedef = en_yakin_trafo(enlem, boylam, max(V, 154.0) if V < 300 else 380.0)
    hat_km = hedef["km"] * b["guzergah_carpani"]
    yol_m, yol_tur = yol_mesafesi_m(enlem, boylam, cfg)
    yol_km = 0.0 if yol_m is None else max(0.0, yol_m / 1000 - b["yol_dahil_km"]) * b["guzergah_carpani"]
    kalem = {
        "proje_trafo_merkezi": b["trafo_merkezi_usd"][anahtar],
        "fider": b["fider_usd"][anahtar],
        "baglanti_hatti": hat_km * b["hat_usd_km"][anahtar],
        "erisim_yolu": yol_km * b["yol_usd_km"],
    }
    top = float(sum(kalem.values()))
    return {
        "kv": V,
        "hedef_trafo": hedef,
        "hat_km": hat_km,
        "yol_m": yol_m,
        "yol_turu": yol_tur,
        "erisim_yolu_km": yol_km,
        "kalemler_usd": kalem,
        "toplam_usd": top,
        "usd_mw": top / mw,
        "v1_usd_mw": float(deger(cfg["teknoloji"]["sebeke"]["capex"])),
        "belirsizlik": belirsizlik(kalem, mw, cfg),
    }


def oran_parametreleri() -> dict | None:
    """Atanan / model hat uzunluğu oranının log-normal parametreleri (src/v3_O2_baglanti_orani.py)."""
    import json

    from src import veri_katmani

    p = veri_katmani.yol("atlas/baglanti_orani.json", zorunlu=False)
    return None if p is None else json.loads(p.read_text())


def belirsizlik(kalem: dict, mw: float, cfg: dict) -> dict | None:
    """Bağlantı mesafesi belirsizliği: hat kalemi r ~ LN(μ, σ) ile ölçeklenir (TEİAŞ kapasiteye göre farklı trafo atayabilir).
    C(r) = sabit kalemler + r · hat maliyeti. Beklenen değer E[r] = exp(μ + σ²/2)."""
    if not deger(cfg["v3"]["baglanti"]).get("belirsizlik", {}).get("aktif", False):
        return None
    o = oran_parametreleri()
    if o is None:
        return None
    mu, s = o["mu_ln"], o["sigma_ln"]
    hat = kalem["baglanti_hatti"]
    sabit = float(sum(kalem.values()) - hat)
    C = lambda r: sabit + hat * r
    beklenen = C(np.exp(mu + s**2 / 2))
    return {
        "mu_ln": mu,
        "sigma_ln": s,
        "n_gozlem": o["n"],
        "sabit_usd": sabit,
        "hat_usd": hat,
        "beklenen_usd": float(beklenen),
        "beklenen_usd_mw": float(beklenen / mw),
        "p10_usd": float(C(np.exp(mu - 1.2816 * s))),
        "p50_usd": float(C(np.exp(mu))),
        "p90_usd": float(C(np.exp(mu + 1.2816 * s))),
    }


def carpan_ornekle(bel: dict | None, n: int, tohum: int) -> np.ndarray:
    """Senaryo başına bağlantı CAPEX çarpanı C(r_s) / E[C] (ortalaması ≈ 1); belirsizlik yoksa birler."""
    if not bel:
        return np.ones(n)
    r = np.exp(np.random.default_rng(tohum).normal(bel["mu_ln"], bel["sigma_ln"], n))
    return (bel["sabit_usd"] + bel["hat_usd"] * r) / bel["beklenen_usd"]
