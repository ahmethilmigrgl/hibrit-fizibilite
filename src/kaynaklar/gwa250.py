"""
Global Wind Atlas 3 — 250 m Türkiye 100 m ortalama hız, 1° karolar (CC BY 4.0). Uygulama yalnız gereken karoyu indirir.

Çevrimdışı: karolari_hazirla() 250 m GeoTIFF'ten data/grid/gwa_tr/v1/karolar/ üretir (rasterio gerekir).
Çalışma zamanı: nokta(), pencere() yalnız numpy + hf_veri (karo yoksa 1 km pakete düşer).
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from src.ayarlar import HAM_VERI, KOK
from src.kaynaklar import gwa, hf_veri

ADIM = 0.0025  # 250 m (derece)
KARO = 1.0  # 1° karo
KLASOR = KOK / "data" / "grid" / "gwa_tr" / "v1" / "karolar"


def _karo_adi(e0: int, b0: int) -> str:
    return f"{e0}_{b0}.npz"


def karolari_hazirla() -> int:
    import rasterio

    with rasterio.open(HAM_VERI / "gwa" / "wind-speed_100.tif") as r:
        a = r.read(1)
        t = r.transform
    KLASOR.mkdir(parents=True, exist_ok=True)
    sayi = 0
    sol, ust = t.c, t.f
    for e0 in range(int(math.floor(ust - a.shape[0] * ADIM)), int(math.ceil(ust))):
        for b0 in range(int(math.floor(sol)), int(math.ceil(sol + a.shape[1] * ADIM))):
            i0 = int(round((ust - (e0 + KARO)) / ADIM))
            i1 = int(round((ust - e0) / ADIM))
            j0 = int(round((b0 - sol) / ADIM))
            j1 = int(round((b0 + KARO - sol) / ADIM))
            i0c, i1c, j0c, j1c = max(i0, 0), min(i1, a.shape[0]), max(j0, 0), min(j1, a.shape[1])
            if i0c >= i1c or j0c >= j1c:
                continue
            k = np.zeros((i1 - i0, j1 - j0), np.uint16)
            parca = a[i0c:i1c, j0c:j1c]
            k[i0c - i0 : i0c - i0 + parca.shape[0], j0c - j0 : j0c - j0 + parca.shape[1]] = np.where(
                np.isfinite(parca), np.round(parca * 100), 0
            )
            if k.max() == 0:
                continue
            np.savez_compressed(KLASOR / _karo_adi(e0, b0), ws=k, ust=np.float64(e0 + KARO), sol=np.float64(b0), adim=np.float64(ADIM))
            sayi += 1
    _karo.cache_clear()
    return sayi


@lru_cache(maxsize=16)
def _karo(e0: int, b0: int) -> dict | None:
    try:
        p = hf_veri.dosya(f"gwa_tr/v1/karolar/{_karo_adi(e0, b0)}")
    except (FileNotFoundError, OSError):
        return None
    z = np.load(p)
    return {k: z[k] for k in z.files}


def nokta(enlem: float, boylam: float) -> float:
    """250 m hücrede 100 m ortalama hız [m/s]; karo yoksa 1 km pakete düşer."""
    k = _karo(int(math.floor(enlem)), int(math.floor(boylam)))
    if k is not None:
        i = int((k["ust"] - enlem) / k["adim"])
        j = int((boylam - k["sol"]) / k["adim"])
        v = float(k["ws"][min(i, k["ws"].shape[0] - 1), min(j, k["ws"].shape[1] - 1)]) / 100
        if v > 0:
            return v
    return gwa.nokta(enlem, boylam)["ws_ort"]


def pencere(enlem: float, boylam: float, yaricap_km: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nokta çevresinde yarıçap içindeki 250 m hücrelerin (enlem, boylam, hız) dizileri (karolar birleştirilir)."""
    de = yaricap_km / 111.0
    db = yaricap_km / (111.0 * math.cos(math.radians(enlem)))
    E, B, V = [], [], []
    for e0 in range(int(math.floor(enlem - de)), int(math.floor(enlem + de)) + 1):
        for b0 in range(int(math.floor(boylam - db)), int(math.floor(boylam + db)) + 1):
            k = _karo(e0, b0)
            if k is None:
                continue
            n, m = k["ws"].shape
            ii = np.arange(n)
            jj = np.arange(m)
            ke = k["ust"] - (ii + 0.5) * k["adim"]
            kb = k["sol"] + (jj + 0.5) * k["adim"]
            si = np.where(np.abs(ke - enlem) <= de)[0]
            sj = np.where(np.abs(kb - boylam) <= db)[0]
            if len(si) == 0 or len(sj) == 0:
                continue
            ee, bb = np.meshgrid(ke[si], kb[sj], indexing="ij")
            vv = k["ws"][np.ix_(si, sj)] / 100.0
            E.append(ee.ravel())
            B.append(bb.ravel())
            V.append(vv.ravel())
    if not E:
        return np.array([]), np.array([]), np.array([])
    E, B, V = np.concatenate(E), np.concatenate(B), np.concatenate(V)
    d = _km(enlem, boylam, E, B)
    s = (d <= yaricap_km) & (V > 0)
    return E[s], B[s], V[s]


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def turbin_yerlesimi(enlem: float, boylam: float, yaricap_km: float = 2.0, adet: int = 12, asgari_aralik_m: float = 500.0) -> dict:
    """
    Basit türbin yerleşimi: yarıçap içindeki en rüzgârlı 250 m hücreler, birbirinden en az 'asgari aralık' uzak (yaklaşık
    4 rotor çapı), 'adet' türbin. İz (wake) etkisi, erişim yolu, arazi eğimi/kullanımı ve izinler modellenmez.
    Döndürür: konumlar, hücre hızları, ortalama hız (GWA düzeltmesinde nokta hızı yerine kullanılır).
    """
    E, B, V = pencere(enlem, boylam, yaricap_km)
    if len(V) == 0:
        return {
            "konumlar": [(enlem, boylam)],
            "hizlar": [nokta(enlem, boylam)],
            "ortalama": nokta(enlem, boylam),
            "nokta": nokta(enlem, boylam),
        }
    sira = np.argsort(V)[::-1]
    secim: list[int] = []
    for i in sira:
        if all(_km(E[i], B[i], E[j], B[j]) * 1000 >= asgari_aralik_m for j in secim):
            secim.append(i)
        if len(secim) == adet:
            break
    return {
        "konumlar": [(float(E[i]), float(B[i])) for i in secim],
        "hizlar": [float(V[i]) for i in secim],
        "ortalama": float(np.mean(V[secim])),
        "nokta": nokta(enlem, boylam),
        "pencere_ortalama": float(V.mean()),
    }
