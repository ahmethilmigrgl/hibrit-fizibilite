"""
Saha tanımlayıcıları (kalibrasyon aktarım kuralı için): rakım, arazi karmaşıklığı göstergesi, kıyıya uzaklık.

- Rakım: Open-Meteo yükseklik API'si (Copernicus DEM GLO-90; anahtarsız, ticari olmayan kullanım), önbellekli.
- Arazi karmaşıklığı: GWA ~1 km ortalama hızının noktanın çevresindeki (±5 km) değişkenlik katsayısı. Düz arazide rüzgâr
  alanı homojendir (düşük); sırt/vadi ardışıklığında GWA'nın mikro ölçek hızlanmaları büyük farklar üretir (yüksek).
  RIX gibi eğim tabanlı ölçülerin rüzgâr alanı karşılığı olarak kullanılan bir vekildir (sınırlama: doğrudan topografya değil).
- Kıyıya uzaklık: Natural Earth 1:10m kıyı çizgisi (kamu malı) köşe noktalarına en kısa büyük çember uzaklığı.
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import requests

from src.ayarlar import HAM_VERI, KOK
from src.kaynaklar import gwa

KIYI = KOK / "data" / "atlas" / "kiyi_tr.npz"
RAKIM_ONBELLEK = HAM_VERI / "open_meteo" / "rakim.json"
RAKIM_GRID = KOK / "data" / "grid" / "rakim_tr" / "v1" / "rakim_002.npz"  # src/v2_C1_rakim_grid.py


def kiyi_hazirla() -> None:
    """Natural Earth kıyı çizgisinden Türkiye ve çevresi (enlem 33–45, boylam 24–46) köşe noktaları (çevrimdışı)."""
    d = json.load(open(HAM_VERI / "natural_earth" / "ne_10m_coastline.geojson"))
    nok = []
    for f in d["features"]:
        g = f["geometry"]
        hatlar = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for h in hatlar:
            a = np.asarray(h)
            a = a[(a[:, 1] > 33) & (a[:, 1] < 45) & (a[:, 0] > 24) & (a[:, 0] < 46)]
            if len(a):
                nok.append(a)
    a = np.vstack(nok)
    np.savez_compressed(KIYI, boylam=a[:, 0].astype(np.float32), enlem=a[:, 1].astype(np.float32))
    _kiyi.cache_clear()


@lru_cache(maxsize=1)
def _kiyi() -> tuple[np.ndarray, np.ndarray]:
    from src import veri_katmani

    z = np.load(veri_katmani.yol("atlas/kiyi_tr.npz"))
    return np.deg2rad(z["enlem"].astype(float)), np.deg2rad(z["boylam"].astype(float))


def kiyi_km(enlem: float, boylam: float) -> float:
    e, b = _kiyi()
    e0, b0 = np.deg2rad(enlem), np.deg2rad(boylam)
    a = np.sin((e - e0) / 2) ** 2 + np.cos(e0) * np.cos(e) * np.sin((b - b0) / 2) ** 2
    return float(12742 * np.arcsin(np.sqrt(a.min())))


def karmasiklik(enlem: float, boylam: float, yaricap_km: float = 5.0) -> float:
    """GWA ortalama hızının ±yarıçap penceresindeki değişkenlik katsayısı (std / ortalama)."""
    p = gwa._yukle()
    i = int((p["ust"] - enlem) / p["adim"])
    j = int((boylam - p["sol"]) / p["adim"])
    di = max(1, int(round(yaricap_km / 111.0 / p["adim"])))
    dj = max(1, int(round(yaricap_km / (111.0 * np.cos(np.deg2rad(enlem))) / p["adim"])))
    w = p["ws_ort"][max(0, i - di) : i + di + 1, max(0, j - dj) : j + dj + 1].astype(float) / p["olcek"]
    w = w[w > 0]
    return float(w.std() / w.mean()) if len(w) > 3 else float("nan")


def _rakim_grid():
    from src import veri_katmani

    yol = veri_katmani.yol("grid/rakim_tr/v1/rakim_002.npz", zorunlu=False)
    return dict(np.load(yol)) if yol is not None else None


def rakim(noktalar: list[tuple[float, float]]) -> list[float]:
    """
    Rakım [m]. Önce yerel 0,02° ızgara (uygulama çalışırken yalnız bu; en yakın komşu), ızgara yoksa ya da nokta ızgara
    dışındaysa Open-Meteo yükseklik API'si (çevrimdışı betikler; 100 nokta/istek, disk önbellekli).
    """
    g = _rakim_grid()
    if g is not None:
        sonuc = []
        for e, b in noktalar:
            i = int((float(g["ust"]) - e) / float(g["adim"]))
            j = int((b - float(g["sol"])) / float(g["adim"]))
            v = int(g["rakim"][i, j]) if 0 <= i < g["rakim"].shape[0] and 0 <= j < g["rakim"].shape[1] else -32768
            if v == -32768:  # kıyı kenarı: 3 × 3 komşuluktaki geçerli değerlerin ortalaması
                w = g["rakim"][max(0, i - 1) : i + 2, max(0, j - 1) : j + 2]
                w = w[w != -32768]
                v = float(w.mean()) if w.size else float("nan")
            sonuc.append(float(v))
        if not any(np.isnan(sonuc)):
            return sonuc
        from src import veri_katmani

        if veri_katmani.yerel_mi():
            return [0.0 if np.isnan(x) else x for x in sonuc]
    return _rakim_api(noktalar)


def _rakim_api(noktalar: list[tuple[float, float]]) -> list[float]:
    """Open-Meteo yükseklik API'si (100 nokta/istek), disk önbellekli — yalnız çevrimdışı."""
    onb = json.loads(RAKIM_ONBELLEK.read_text()) if RAKIM_ONBELLEK.exists() else {}
    anahtar = [f"{e:.4f},{b:.4f}" for e, b in noktalar]
    eksik = [k for k in dict.fromkeys(anahtar) if k not in onb]
    for i in range(0, len(eksik), 100):
        parca = eksik[i : i + 100]
        r = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            timeout=60,
            params={"latitude": ",".join(k.split(",")[0] for k in parca), "longitude": ",".join(k.split(",")[1] for k in parca)},
        )
        r.raise_for_status()
        onb.update(dict(zip(parca, r.json()["elevation"])))
    RAKIM_ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    RAKIM_ONBELLEK.write_text(json.dumps(onb))
    return [float(onb[k]) for k in anahtar]
