"""
Ada tespiti ve şebeke erişimi notu (Revizyon R4).

Sınır ızgarasında (0,01°, ilçe kimlikleri) 8-komşulu bağlı bileşenler: en büyük bileşen anakara (Trakya ızgarada Boğaz
üzerinden bağlı görünür), diğerleri ada. Ince kıstakla bağlı yarımadalar ve köprüyle bağlı adalar config'te
`v2.adalar.kara_bagli` listesinde (il/ilçe) — bunlar ada sayılmaz. Bilinen adaların bağlantı durumu `v2.adalar.durum`'da
(kaynaklı; doğrulanamayan kısımlar açıkça belirtilir).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from src.ayarlar import config_oku, deger


@lru_cache(maxsize=1)
def _bilesenler() -> tuple[np.ndarray, int]:
    from scipy import ndimage

    from src.kaynaklar import sinirlar

    p = sinirlar._yukle()
    lab, n = ndimage.label(p["izgara"] > 0, structure=np.ones((3, 3)))
    alan = ndimage.sum(np.ones_like(lab), lab, index=range(1, n + 1))
    return lab, int(np.argmax(alan)) + 1


def ada_bilgisi(enlem: float, boylam: float) -> dict | None:
    """Nokta bir adadaysa {il, ilce, alan_km2, durum}; anakara ya da kara bağlantılıysa None."""
    from src.kaynaklar import sinirlar

    p = sinirlar._yukle()
    lab, ana = _bilesenler()
    i = int((p["ust"] - enlem) / p["adim"])
    j = int((boylam - p["sol"]) / p["adim"])
    if not (0 <= i < lab.shape[0] and 0 <= j < lab.shape[1]) or lab[i, j] in (0, ana):
        return None
    k = sinirlar.konum(enlem, boylam)
    a = deger(config_oku()["v2"]["adalar"])
    anahtar = f"{k['il']}/{k['ilce']}"
    if anahtar in a["kara_bagli"]:
        return None
    alan = float((lab == lab[i, j]).sum() * (111 * p["adim"]) ** 2 * np.cos(np.radians(enlem)))
    return {"il": k["il"], "ilce": k["ilce"], "alan_km2": alan, "durum": a["durum"].get(anahtar, a["varsayilan_durum"])}
