"""
v3 E5 — Uygulama haritası için sadeleştirilmiş altyapı katmanları (isteğe bağlı yüklenir).

    data/atlas/katman_agir_yol.geojson   otoyol/devlet/il yolu (OSM, ~300 m tolerans sadeleştirme, sınıf özelliğiyle)   ODbL
    data/atlas/katman_hat.geojson        ≥ 154 kV iletim hatları (OSM, sadeleştirilmiş, gerilim özelliğiyle)             ODbL
    data/atlas/katman_koruma.geojson     OSM koruma alanları (sadeleştirilmiş)                                           ODbL
    data/atlas/katman_goc.geojson        göç koridorları (yüksek/orta risk tamponları; yaklaşık)                         CC BY 4.0
Çalıştırma: .venv/bin/python src/v3_E5_harita_katmanlari.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, mapping

from src.ayarlar import HAM_VERI, KOK

ATLAS = KOK / "data" / "atlas"
OSM = HAM_VERI / "osm_cikti"


def yaz(ad: str, ozellikler: list[dict]) -> None:
    p = ATLAS / ad
    p.write_text(json.dumps({"type": "FeatureCollection", "features": ozellikler}, ensure_ascii=False, separators=(",", ":")))
    print(ad, len(ozellikler), f"{p.stat().st_size / 1e6:.2f} MB")


def yuvarla(g):
    return shapely.set_precision(g, 0.0001)


def main() -> None:
    y = pd.read_parquet(OSM / "yollar.parquet")
    y = y[y["sinif"].isin(["motorway", "trunk", "primary"])]
    f = []
    for sinif, grp in y.groupby("sinif"):
        cizgi = [LineString(list(zip(b, e))) for e, b in zip(grp["enlem"], grp["boylam"]) if len(e) > 1]
        g = shapely.line_merge(shapely.union_all(cizgi)).simplify(0.003)
        f.append({"type": "Feature", "properties": {"sinif": sinif}, "geometry": mapping(yuvarla(g))})
    yaz("katman_agir_yol.geojson", f)
    h = pd.read_parquet(OSM / "hatlar.parquet")
    h = h[h["kv"].fillna(0) >= 154]
    f = []
    for kv, grp in h.groupby(h["kv"].clip(upper=400).round(-1)):
        cizgi = [LineString(list(zip(b, e))) for e, b in zip(grp["enlem"], grp["boylam"]) if len(e) > 1]
        g = shapely.line_merge(shapely.union_all(cizgi)).simplify(0.003)
        f.append({"type": "Feature", "properties": {"kv": float(kv)}, "geometry": mapping(yuvarla(g))})
    yaz("katman_hat.geojson", f)
    k = pd.read_parquet(OSM / "koruma.parquet")
    f = []
    for r in k.itertuples():
        g = shapely.from_wkb(r.wkb)
        if g is None or g.is_empty:
            continue
        g = g.simplify(0.002)
        if g.is_empty or g.area < 1e-6:
            continue
        f.append({"type": "Feature", "properties": {"ad": r.ad or "", "tur": r.tur or ""}, "geometry": mapping(yuvarla(g))})
    yaz("katman_koruma.geojson", f)
    goc = json.loads((ATLAS / "goc_koridorlari.json").read_text())
    f = []
    for c in goc["koridorlar"]:
        ax = np.array(c["eksen"])
        cos = np.cos(np.radians(ax[:, 0].mean()))
        hat = LineString(list(zip(ax[:, 1] * cos, ax[:, 0])))
        for sev, km in (("orta", c["orta_km"]), ("yuksek", c["yuksek_km"])):
            if km <= 0:
                continue
            p = hat.buffer(km / 111.32, quad_segs=8)
            p = shapely.transform(p, lambda xy, cos=cos: np.c_[xy[:, 0] / cos, xy[:, 1]])
            f.append({"type": "Feature", "properties": {"ad": c["ad"], "risk": sev, "kaynak": c["kaynak"]}, "geometry": mapping(yuvarla(p.simplify(0.01)))})
    yaz("katman_goc.geojson", f)


if __name__ == "__main__":
    main()
