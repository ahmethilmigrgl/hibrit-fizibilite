"""
v3 E1 — Türkiye 250 m CBS katman gridi (GWA ve eğim karolarıyla hizalı 1° karolar, 0,0025°) ve trafo merkezi tablosu.

Girdi: src/v3_E1_osm_katmanlar.py çıktıları (data/raw/osm_cikti/), data/atlas/goc_koridorlari.json.
Her 250 m hücre için (öklidyen mesafe dönüşümü, 0,3° kenar payıyla; metre cinsinden, 10 m adımlı uint16):
    yerlesim   en yakın yerleşim (place düğümü ya da konut alanı köşesi)
    otoyol     motorway (+link);  devlet: trunk/primary (+link);  ikincil: secondary (+link)
    hat        herhangi bir iletim hattı (power=line)
    havalimani ICAO/IATA kodlu havalimanı merkezi
    koruma     OSM koruma alanı içinde mi (0/1)
    goc        göç riski sınıfı (0 yok, 1 orta, 2 yüksek; yaklaşık katman)
Çıktılar: data/grid/cbs_tr/v1/{e}_{b}.npz (git'e girmez); data/atlas/trafo_merkezleri.csv, havalimanlari.csv (ODbL)
Çalıştırma: .venv/bin/python src/v3_E1_cbs_grid.py
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import HAM_VERI, KOK

OSM = HAM_VERI / "osm_cikti"
KLASOR = KOK / "data" / "grid" / "cbs_tr" / "v1"
ATLAS = KOK / "data" / "atlas"
ADIM = 0.0025
PAY = 0.3
N = 400
KATMAN_YOL = {
    "otoyol": {"motorway", "motorway_link"},
    "devlet": {"trunk", "primary", "trunk_link", "primary_link"},
    "ikincil": {"secondary", "secondary_link"},
}


def _nokta_dizisi() -> dict[str, np.ndarray]:
    """Her katman için (enlem, boylam) nokta dizisi (çizgiler ~100 m aralıkla örneklenir)."""

    def cizgi(df: pd.DataFrame) -> np.ndarray:
        out = []
        for e, b in zip(df["enlem"], df["boylam"]):
            e, b = np.asarray(e), np.asarray(b)
            d = np.hypot(np.diff(e), np.diff(b) * np.cos(np.radians(e[:-1])))
            k = np.maximum(np.ceil(d / 0.001), 1).astype(int)
            for i in range(len(d)):
                t = np.linspace(0, 1, k[i], endpoint=False)
                out.append(np.c_[e[i] + t * (e[i + 1] - e[i]), b[i] + t * (b[i + 1] - b[i])])
            out.append(np.c_[e[-1:], b[-1:]])
        return np.vstack(out) if out else np.zeros((0, 2))

    yol = pd.read_parquet(OSM / "yollar.parquet")
    p = {ad: cizgi(yol[yol["sinif"].isin(s)]) for ad, s in KATMAN_YOL.items()}
    p["hat"] = cizgi(pd.read_parquet(OSM / "hatlar.parquet"))
    y = pd.read_parquet(OSM / "yerlesim.parquet")
    p["yerlesim"] = y[["enlem", "boylam"]].to_numpy()
    h = pd.read_parquet(OSM / "havalimani.parquet")
    p["havalimani"] = h[["enlem", "boylam"]].to_numpy()
    return p


NOKTA: dict = {}
KORUMA = None
GOC = None


def _baslat():
    global NOKTA, KORUMA, GOC
    NOKTA = _nokta_dizisi()
    import shapely

    k = pd.read_parquet(OSM / "koruma.parquet")
    KORUMA = [g for g in shapely.from_wkb(k["wkb"].to_numpy()) if g is not None and g.is_valid]
    GOC = json.loads((ATLAS / "goc_koridorlari.json").read_text())["koridorlar"]


def karo(eb: tuple[int, int]) -> str:
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from scipy.ndimage import distance_transform_edt

    e0, b0 = eb
    yol = KLASOR / f"{e0}_{b0}.npz"
    if yol.exists():
        return "var"
    pay_n = int(PAY / ADIM)
    M = N + 2 * pay_n
    ust, sol = e0 + 1 + PAY, b0 - PAY
    dy = ADIM * 111320.0
    dx = ADIM * 111320.0 * np.cos(np.radians(e0 + 0.5))
    out = {}
    for ad, P in NOKTA.items():
        s = (P[:, 0] < ust) & (P[:, 0] > ust - M * ADIM) & (P[:, 1] > sol) & (P[:, 1] < sol + M * ADIM)
        if not s.any():
            out[ad] = np.full((N, N), 65535, np.uint16)
            continue
        i = ((ust - P[s, 0]) / ADIM).astype(int)
        j = ((P[s, 1] - sol) / ADIM).astype(int)
        m = np.ones((M, M), bool)
        m[i, j] = False
        d = distance_transform_edt(m, sampling=(dy, dx))[pay_n : pay_n + N, pay_n : pay_n + N]
        out[ad] = np.clip(np.round(d / 10), 0, 65535).astype(np.uint16)
    import shapely

    kutu = shapely.box(b0, e0, b0 + 1, e0 + 1)
    gs = [g for g in KORUMA if g.intersects(kutu)]
    tr = from_origin(b0, e0 + 1, ADIM, ADIM)
    out["koruma"] = (
        rasterize([(g, 1) for g in gs], out_shape=(N, N), transform=tr, fill=0, dtype="uint8") if gs else np.zeros((N, N), np.uint8)
    )
    # göç riski: hücre merkezinin koridor eksenine uzaklığı
    ee = e0 + 1 - (np.arange(N) + 0.5) * ADIM
    bb = b0 + (np.arange(N) + 0.5) * ADIM
    E, B = np.meshgrid(ee, bb, indexing="ij")
    risk = np.zeros((N, N), np.uint8)
    for k in GOC:
        ax = np.array(k["eksen"])
        dmin = np.full((N, N), np.inf)
        for (a1, c1), (a2, c2) in pairwise(ax):
            cosf = np.cos(np.radians(0.5 * (a1 + a2)))
            px, py = (B - c1) * cosf, E - a1
            vx, vy = (c2 - c1) * cosf, a2 - a1
            t = np.clip((px * vx + py * vy) / max(vx * vx + vy * vy, 1e-12), 0, 1)
            dmin = np.minimum(dmin, np.hypot(px - t * vx, py - t * vy) * 111.32)
        risk = np.maximum(risk, np.where(dmin <= k["yuksek_km"], 2, np.where(dmin <= k["orta_km"], 1, 0)).astype(np.uint8))
    out["goc"] = risk
    np.savez_compressed(yol, **out, ust=np.float64(e0 + 1), sol=np.float64(b0), adim=np.float64(ADIM))
    return "tamam"


def trafo_tablosu() -> pd.DataFrame:
    t = pd.read_parquet(OSM / "trafolar.parquet")
    t = t[t["tur"].fillna("") != "minor_distribution"]
    t = t.assign(kv=t["kv"].astype(float)).round({"enlem": 5, "boylam": 5})
    t.to_csv(ATLAS / "trafo_merkezleri.csv", index=False, encoding="utf-8-sig")
    h = pd.read_parquet(OSM / "havalimani.parquet").round({"enlem": 5, "boylam": 5})
    h.to_csv(ATLAS / "havalimanlari.csv", index=False, encoding="utf-8-sig")
    return t


def main() -> None:
    KLASOR.mkdir(parents=True, exist_ok=True)
    t = trafo_tablosu()
    print("trafo merkezi", len(t), "gerilimi bilinen", int(t["kv"].notna().sum()), "≥154 kV", int((t["kv"] >= 154).sum()), flush=True)
    egim = KOK / "data" / "grid" / "egim_tr" / "v1"
    isler = sorted({tuple(int(x) for x in p.stem.split("_")) for p in egim.glob("*.npz")})
    with ProcessPoolExecutor(max_workers=4, initializer=_baslat) as hv:
        s = list(hv.map(karo, isler))
    print({k: s.count(k) for k in set(s)})


if __name__ == "__main__":
    main()
