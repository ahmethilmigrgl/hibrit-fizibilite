"""
Tasarım gezgini: önceden hesaplanmış işletme tablolarından (results/gezgin_tablolari.npz) herhangi bir
(türbin sayısı, GES, batarya gücü, batarya süresi) tasarımının deterministik değerlemesi — milisaniyeler içinde.

Yöntem: 4 boyutlu ızgarada çok doğrusal ara değerleme ile tasarımın işletme tablosu kurulur, sonra Monte Carlo ile
aynı vektörize nakit akışı motoru (src/risk/degerleme.py) beklenen değer modunda çalıştırılır.
Pyomo gerektirmez (dashboard bağımlılıkları hafif kalır).

SFK kuralı: batarya gücü 30 MW'ın altındaysa SFK'ya katılamaz (TEİAŞ usul ve esasları) → SFK çarpanı 0.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.ayarlar import deger
from src.finans.model import Varsayimlar, lcoe_hesapla
from src.risk.degerleme import Sabitler, irr_vektor, nakit_akislari
from src.risk.doyum import deterministik_yol
from src.risk.senaryo import a_yolu, h_yolu
from src.risk.tasarim import Tasarim

TURBIN_GUCU = 4.2


def gezgin_yukle(klasor: Path) -> dict:
    """Dashboard tasarım gezgini tablolarını results/ klasöründen yükler."""
    z = np.load(klasor / "gezgin_tablolari.npz")
    gz = {k: z[k] for k in z.files}
    gz["meta"] = json.loads((klasor / "gezgin_meta.json").read_text())
    return gz


def _agirlik(x: float, izgara: np.ndarray):
    x = float(np.clip(x, izgara[0], izgara[-1]))
    j = int(np.clip(np.searchsorted(izgara, x) - 1, 0, len(izgara) - 2))
    t = (x - izgara[j]) / (izgara[j + 1] - izgara[j])
    return [(j, 1 - t), (j + 1, t)]


def ara_tablo(gz: dict, turbin: float, ges: float, p_mw: float, sure: float) -> dict:
    """(türbin, GES, P, süre) ızgarasında 16 köşeli çok doğrusal ara değerleme → tek tasarımlık işletme tablosu."""
    T = 0.0
    for i, wi in _agirlik(turbin, gz["turbin"]):
        for j, wj in _agirlik(ges, gz["ges"]):
            for k, wk in _agirlik(p_mw, gz["bess_mw"]):
                for l_, wl in _agirlik(sure, gz["sure"]):
                    w = wi * wj * wk * wl
                    if w > 0:
                        T = T + w * gz["T"][i, j, k, l_].astype(float)
    return {"T": T[None], "h": gz["h"], "m": gz["m"], "a": gz["a"], "ppa": gz["ppa"]}


@lru_cache(maxsize=8)
def _sabitler(cfg_id: int, seviye: float):
    cfg = _CFG[cfg_id]
    v = Varsayimlar.configten(cfg)
    return v, Sabitler.configten(cfg, v, L_baz=seviye)


_CFG: dict[int, dict] = {}


def sfk_yolu(gz: dict, cfg: dict, yillar: np.ndarray, sfk: str) -> np.ndarray:
    """Seçilen SFK senaryosunun yıllık fiyat çarpanı yolu (2026 = 1)."""
    m = gz["meta"]
    if sfk in ("kapali", "katilamama"):
        return np.zeros(len(yillar))
    if sfk == "asama5":
        return a_yolu(yillar, m["a5_azalma"], m["a5_taban"])
    return deterministik_yol(cfg, sfk, yillar, m["firsat_oran"])


def gezgin_degerle(
    gz: dict,
    cfg: dict,
    turbin: float,
    ges: float,
    p_mw: float,
    e_mwh: float,
    seviye: float = 58.0,
    kanibalizasyon: str = "devam",
    sfk: str = "baz",
    ppa: bool = False,
) -> dict:
    """Kullanıcının seçtiği tasarım ve senaryo için beklenen NPV ve göstergeler (önceden hesaplı tablolardan)."""
    _CFG[id(cfg)] = cfg
    v, c = _sabitler(id(cfg), float(seviye))
    N = v.omur
    yillar = np.arange(deger(cfg["proje"]["baslangic_yili"]), deger(cfg["proje"]["baslangic_yili"]) + N)
    sure = e_mwh / p_mw if p_mw > 0 else 1.0
    tb = ara_tablo(gz, turbin, ges, p_mw, sure)
    sfk_ok = p_mw >= float(gz["sfk_asgari"])
    t = Tasarim(
        "gezgin",
        turbin * TURBIN_GUCU,
        ges,
        p_mw,
        e_mwh if p_mw > 0 else 0.0,
        yan_hizmet=sfk_ok,
        dengesizlik_azaltim=p_mw > 0,
        yekg=True,
        ppa=ppa,
    )
    oran0 = gz["meta"]["oran0"]
    taban = gz["meta"]["kan_taban"] if kanibalizasyon == "devam" else oran0
    a = sfk_yolu(gz, cfg, yillar, sfk) if sfk_ok else np.zeros(N)
    girdi = {
        "h": h_yolu(cfg, yillar, taban, oran0)[None],
        "m": np.ones((1, N)),
        "a": a[None],
        "L": np.full((1, N), float(seviye)),
        "tavan": np.zeros((1, N), bool),
        "ws_ortalama": True,
        **{k: np.ones(1) for k in ["capex_res", "capex_ges", "capex_bess", "opex", "bozunma"]},
    }
    r = nakit_akislari(t, tb, c, girdi)
    gelir_yh = np.atleast_2d(r["gelir_yh"])[0] if np.ndim(r["gelir_yh"]) else np.zeros(N)
    yekg = c.yekg * r["satilan"][0]
    gelir = r["gelir_spot"][0] + r["gelir_bess"][0] + gelir_yh + yekg
    maliyet = gelir - r["vergi"][0] - r["cfads"][0]  # işletme giderleri + dengesizlik + augmentation + söküm
    capex = float(r["capex_top"][0])
    lcoe = lcoe_hesapla(capex * np.array(v.capex_takvimi), maliyet, r["satilan"][0], v.wacc)
    irr = irr_vektor(r["sna"])[0]
    return {
        "npv": float(r["npv"][0]) / 1e6,
        "irr": float(irr),
        "lcoe": lcoe,
        "capex": capex / 1e6,
        "kesinti": float(r["kesilen"][0].sum() / max(r["uretilebilir"][0].sum(), 1e-9)),
        "satilan_gwh": float(r["satilan"][0].mean()) / 1e3,
        "sfk_katilim": sfk_ok,
        "yillar": yillar,
        "gelir": {"spot": r["gelir_spot"][0] / 1e6, "arbitraj": r["gelir_bess"][0] / 1e6, "sfk": gelir_yh / 1e6, "yekg": yekg / 1e6},
        "dengesizlik": r["dengesizlik"][0] / 1e6,
        "favok": r["favok"][0] / 1e6,
    }
