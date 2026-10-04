"""
Global Wind Atlas (DTU / Dünya Bankası, CC BY 4.0) — Türkiye 100 m rüzgâr iklimi, uygulamaya gömülebilir paket (v2).

Çevrimdışı hazırlık (hazirla): GWA API'sinden indirilen 250 m (0,0025°) GeoTIFF'ler 4 × 4 bloklarla ~1 km'ye (0,01°)
indirgenir. Katmanlar: ortalama hız (blok ortalaması), blok içi en yüksek hız (sırt/tepe noktalarını kaybetmemek için),
Weibull A ve k (blok ortalaması). uint16 ölçekli (×100), sıkıştırılmış .npz → data/atlas/gwa_tr_1km.npz.

Çalışma zamanı: nokta(enlem, boylam) ve duzeltme_katsayisi(...) yalnız bu dosyayı okur (rasterio gerekmez).

GWA düzeltmesi: ERA5 0,25° (~25 × 28 km) hücrenin alan ortalamasıdır; GWA ise WAsP ile mikro ölçekte (250 m) arazi
ve pürüzlülüğe indirgenmiş uzun dönem ortalamadır. Karmaşık arazide bir sırt üstündeki nokta, hücre ortalamasından çok
daha rüzgârlıdır (hızlanma); vadideki nokta daha az. Bu yüzden saatlik ERA5 hızı noktada c = GWA_ort / ERA5_ort ile
ölçeklenir. c, ortalamayı düzeltir; gün içi ve mevsimsel şekli düzeltmez (bunu yalnız santral kalibrasyonu yapar).
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.ayarlar import HAM_VERI, KOK

PAKET = KOK / "data" / "atlas" / "gwa_tr_1km.npz"
HAM = HAM_VERI / "gwa"
OLCEK = 100.0
ATIF = (
    "Global Wind Atlas 3.0, a free, web-based application developed, owned and operated by the Technical University "
    "of Denmark (DTU). The Global Wind Atlas 3.0 is released in partnership with the World Bank Group, utilizing data "
    "provided by Vortex, using funding provided by the Energy Sector Management Assistance Program (ESMAP). "
    "For additional information: https://globalwindatlas.info"
)


def _blok(a: np.ndarray, n: int, islem: str) -> np.ndarray:
    h, w = (a.shape[0] // n) * n, (a.shape[1] // n) * n
    b = a[:h, :w].reshape(h // n, n, w // n, n)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(b, axis=(1, 3)) if islem == "maks" else np.nanmean(b, axis=(1, 3))


def hazirla(n: int = 4) -> Path:
    """250 m GWA rasterlerinden ~1 km paket üretir (çevrimdışı; rasterio gerekir)."""
    import rasterio

    katman = {}
    with rasterio.open(HAM / "wind-speed_100.tif") as r:
        ws = r.read(1).astype(np.float32)
        t = r.transform
    katman["ws_ort"], katman["ws_maks"] = _blok(ws, n, "ort"), _blok(ws, n, "maks")
    for ad, dosya in [("weibull_A", "combined-Weibull-A_100.tif"), ("weibull_k", "combined-Weibull-k_100.tif")]:
        with rasterio.open(HAM / dosya) as r:
            katman[ad] = _blok(r.read(1).astype(np.float32), n, "ort")
    paket = {k: np.where(np.isfinite(v), np.round(v * OLCEK), 0).astype(np.uint16) for k, v in katman.items()}
    PAKET.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PAKET, **paket, sol=np.float64(t.c), ust=np.float64(t.f), adim=np.float64(t.a * n), olcek=np.float64(OLCEK))
    nokta.cache_clear()
    _yukle.cache_clear()
    return PAKET


@lru_cache(maxsize=1)
def _yukle() -> dict:
    z = np.load(PAKET)
    return {k: z[k] for k in z.files}


@lru_cache(maxsize=4096)
def nokta(enlem: float, boylam: float) -> dict[str, float]:
    """Noktanın ~1 km hücresindeki GWA değerleri (100 m): ortalama hız, hücre içi en yüksek hız, Weibull A ve k."""
    p = _yukle()
    i = int((p["ust"] - enlem) / p["adim"])
    j = int((boylam - p["sol"]) / p["adim"])
    if not (0 <= i < p["ws_ort"].shape[0] and 0 <= j < p["ws_ort"].shape[1]):
        raise ValueError(f"Nokta GWA Türkiye paketinin dışında: {enlem}, {boylam}")
    d = {k: float(p[k][i, j]) / float(p["olcek"]) for k in ("ws_ort", "ws_maks", "weibull_A", "weibull_k")}
    if d["ws_ort"] <= 0:
        raise ValueError(f"Noktada GWA verisi yok (deniz ya da kapsam dışı): {enlem}, {boylam}")
    return d


def duzeltme_katsayisi(enlem: float, boylam: float, era5_v100_ort: float, sinirlar: tuple[float, float] = (0.6, 1.8)) -> float:
    """
    GWA düzeltme katsayısı c = GWA 100 m ortalama hız / ERA5 100 m ortalama hız (aynı nokta). Aşırı değerler sınırlanır:
    çok yüksek c genellikle ERA5'in sahil/dağ hücresinde deniz ya da vadi ağırlığından gelir ve tek katsayıyla düzeltilemez.
    """
    c = nokta(enlem, boylam)["ws_ort"] / era5_v100_ort
    return float(np.clip(c, *sinirlar))


def aday_noktalar(
    maske: np.ndarray, sol: float, ust: float, adim: float, adet: int = 5, katman: str = "ws_ort"
) -> list[tuple[float, float, float]]:
    """Verilen GWA ızgarası maskesi içinde (ör. ilçe) en rüzgârlı 'adet' hücrenin (enlem, boylam, hız) listesi."""
    p = _yukle()
    v = np.where(maske, p[katman] / p["olcek"], -1.0)
    sira = np.argsort(v, axis=None)[::-1][:adet]
    i, j = np.unravel_index(sira, v.shape)
    return [(float(p["ust"] - (ii + 0.5) * p["adim"]), float(p["sol"] + (jj + 0.5) * p["adim"]), float(v[ii, jj])) for ii, jj in zip(i, j)]
