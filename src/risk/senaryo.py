"""
Monte Carlo ve deterministik değerleme için fiyat şekilleri, yollar ve işletme tablolarının hazırlanması.
"""

from __future__ import annotations

import numpy as np

from src.ayarlar import deger
from src.finans.fiyat_senaryosu import _derinlik, _gunes_orani
from src.finans.veri import UretimProfili, fiyat_sekil_yillari, yan_hizmet_sekil_yillari


def birim_sekiller(cfg: dict, u: UretimProfili, h_izgara: np.ndarray) -> tuple[dict, float]:
    """
    Her şekil yılı s ve güneş yakalanma hedefi h için birim fiyat şekli q (ortalama 1).
    Aşama 3 ile aynı kural: her şekil yılı kendi başlangıç oranından (oran0 − h) kadar düşürülür.
    Döndürür: ({(s, h): q}, oran0)
    """
    sekil, _ = fiyat_sekil_yillari(*deger(cfg["fiyat_senaryolari"]["sekil_donemi"]))
    g = u.ges.mean(axis=0)
    g = g / g.max()
    oran0 = float(np.mean([_gunes_orani(s_, g, 0.0) for s_ in sekil]))
    out = {}
    for s, sh in enumerate(sekil):
        for h in h_izgara:
            hedef = _gunes_orani(sh, g, 0.0) - (oran0 - h)
            d = _derinlik(sh, g, hedef)
            q = sh * (1 - d * g)
            out[(s, h)] = np.clip(q / q.mean(), 0.0, None)
    return out, oran0


def yan_hizmet_sekli(cfg: dict) -> np.ndarray:
    """(2, 8760) yan hizmet kapasite fiyatı, 2026 seviyesinde [USD/MW-saat]."""
    return yan_hizmet_sekil_yillari(deger(cfg["gelir_yigini"]["yan_hizmet"]["urun"]))


def h_yolu(cfg: dict, yillar: np.ndarray, taban: float, oran0: float) -> np.ndarray:
    """Kanibalizasyon: güneş yakalanma hedefi taban_yili'na kadar doğrusal iner (taban ≥ oran0 → sabit)."""
    ty = deger(cfg["fiyat_senaryolari"]["kanibalizasyon"])["taban_yili"]
    oran = oran0 + (taban - oran0) * (yillar - 2026) / (ty - 2026)
    return np.clip(oran, min(taban, oran0), oran0)


def a_yolu(yillar: np.ndarray, azalma: float, taban: float) -> np.ndarray:
    """Yan hizmet fiyat çarpanı (2026 = 1): yıllık azalma, taban oranında durur."""
    return np.maximum((1 - azalma) ** (yillar - 2026), taban)
