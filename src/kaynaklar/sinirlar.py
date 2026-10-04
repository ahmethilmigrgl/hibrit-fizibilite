"""
Türkiye il/ilçe sınırları — geoBoundaries gbOpen TUR (OpenStreetMap kökenli): ADM1 (81 il) CC BY-SA 2.0,
ADM2 (973 ilçe) ODbL 1.0. Atıf: "geoBoundaries (Runfola et al. 2020), © OpenStreetMap contributors".

Çevrimdışı hazırlık (hazirla, shapely gerekir): her ilçe, temsil noktasının içinde kaldığı ile bağlanır; ilçe kimlikleri
GWA ~1 km ızgarasına rasterize edilir → data/atlas/sinirlar_tr.npz (uint16 ilçe kimliği ızgarası + adlar).
Çalışma zamanı (konum, ilce_maskesi): yalnız bu .npz (shapely gerekmez). Kimlik 0 = Türkiye karası dışı (deniz/komşu ülke).
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from src.ayarlar import HAM_VERI, KOK
from src.kaynaklar import gwa

PAKET = KOK / "data" / "atlas" / "sinirlar_tr.npz"
ATIF = "Sınırlar: geoBoundaries (Runfola et al. 2020), © OpenStreetMap katkıcıları (ADM1 CC BY-SA 2.0, ADM2 ODbL 1.0)."


def hazirla() -> None:
    from shapely import contains_xy
    from shapely.geometry import shape

    il = [
        (f["properties"]["shapeName"], shape(f["geometry"])) for f in json.load(open(HAM_VERI / "sinirlar" / "tr_ADM1.geojson"))["features"]
    ]
    ilce = [
        (f["properties"]["shapeName"], shape(f["geometry"])) for f in json.load(open(HAM_VERI / "sinirlar" / "tr_ADM2.geojson"))["features"]
    ]
    ilce_il = []
    for _ad, g in ilce:
        p = g.representative_point()
        ilce_il.append(next((iad for iad, ig in il if ig.contains(p)), "?"))
    G = gwa._yukle()
    n, m = G["ws_ort"].shape
    enl = G["ust"] - (np.arange(n) + 0.5) * G["adim"]
    boy = G["sol"] + (np.arange(m) + 0.5) * G["adim"]
    X, Y = np.meshgrid(boy, enl)
    izgara = np.zeros((n, m), np.uint16)
    for k, (_, g) in enumerate(ilce, start=1):
        x0, y0, x1, y1 = g.bounds
        sat = np.where((enl >= y0) & (enl <= y1))[0]
        sut = np.where((boy >= x0) & (boy <= x1))[0]
        if len(sat) and len(sut):
            alt = (slice(sat.min(), sat.max() + 1), slice(sut.min(), sut.max() + 1))
            ic = contains_xy(g, X[alt], Y[alt])
            izgara[alt][ic] = k
    np.savez_compressed(
        PAKET, izgara=izgara, ilce=np.array([a for a, _ in ilce]), il=np.array(ilce_il), sol=G["sol"], ust=G["ust"], adim=G["adim"]
    )
    _yukle.cache_clear()


@lru_cache(maxsize=1)
def _yukle() -> dict:
    z = np.load(PAKET)
    return {k: z[k] for k in z.files}


def konum(enlem: float, boylam: float) -> dict | None:
    """Noktanın il ve ilçesi; Türkiye karası dışındaysa None."""
    p = _yukle()
    i = int((p["ust"] - enlem) / p["adim"])
    j = int((boylam - p["sol"]) / p["adim"])
    if not (0 <= i < p["izgara"].shape[0] and 0 <= j < p["izgara"].shape[1]):
        return None
    k = int(p["izgara"][i, j])
    return None if k == 0 else {"il": str(p["il"][k - 1]), "ilce": str(p["ilce"][k - 1]), "ilce_no": k}


def ilceler(il: str | None = None) -> list[tuple[str, str]]:
    """(il, ilçe) listesi; il verilirse yalnız o ilin ilçeleri."""
    p = _yukle()
    return sorted((str(a), str(b)) for a, b in zip(p["il"], p["ilce"]) if il is None or a == il)


def ilce_maskesi(il: str, ilce: str) -> np.ndarray:
    p = _yukle()
    k = [i for i, (a, b) in enumerate(zip(p["il"], p["ilce"]), start=1) if a == il and b == ilce]
    if not k:
        raise ValueError(f"İlçe bulunamadı: {il} / {ilce}")
    return np.isin(p["izgara"], k)
