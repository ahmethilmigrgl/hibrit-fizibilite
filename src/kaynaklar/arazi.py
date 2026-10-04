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
    z = np.load(KIYI)
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


def rakim(noktalar: list[tuple[float, float]]) -> list[float]:
    """Open-Meteo yükseklik API'si (100 nokta/istek), disk önbellekli."""
    onb = json.loads(RAKIM_ONBELLEK.read_text()) if RAKIM_ONBELLEK.exists() else {}
    anahtar = [f"{e:.4f},{b:.4f}" for e, b in noktalar]
    eksik = [k for k in dict.fromkeys(anahtar) if k not in onb]
    for i in range(0, len(eksik), 100):
        parca = eksik[i : i + 100]
        r = requests.get("https://api.open-meteo.com/v1/elevation", timeout=60,
                         params={"latitude": ",".join(k.split(",")[0] for k in parca), "longitude": ",".join(k.split(",")[1] for k in parca)})
        r.raise_for_status()
        onb.update(dict(zip(parca, r.json()["elevation"])))
    RAKIM_ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    RAKIM_ONBELLEK.write_text(json.dumps(onb))
    return [float(onb[k]) for k in anahtar]
