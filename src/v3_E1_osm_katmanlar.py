"""
v3 E1 — Türkiye OSM katmanları (çevrimdışı): Geofabrik Türkiye özütünden (ODbL) yol, güç, yerleşim, havalimanı ve koruma
alanı katmanları.

Kaynak: https://download.geofabrik.de/europe/turkey-latest.osm.pbf (OpenStreetMap katkıcıları, ODbL 1.0).
Çıkarılanlar (data/raw/osm_cikti/, git'e girmez):
    yollar.parquet        highway ∈ motorway/trunk/primary/secondary/tertiary (+ _link): yol kimliği, sınıf, düğüm kimlikleri, koordinatlar
    hatlar.parquet        power=line: gerilim [kV] (en büyük), koordinatlar
    trafolar.parquet      power=substation (düğüm ya da alan merkezi): gerilim [kV] (en büyük), ad, işletmeci
    yerlesim.parquet      place ∈ city/town/village/hamlet/suburb/neighbourhood düğümleri + landuse=residential alan köşeleri (seyreltilmiş)
    havalimani.parquet    aeroway=aerodrome (ICAO ya da IATA kodlu): merkez
    koruma.parquet        boundary=protected_area / national_park, leisure=nature_reserve alanları (WKB, sadeleştirilmemiş)
Çalıştırma: .venv/bin/python src/v3_E1_osm_katmanlar.py
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import osmium
import pandas as pd

from src.ayarlar import HAM_VERI

PBF = HAM_VERI / "osm_pbf" / "turkey-latest.osm.pbf"
CIKTI = HAM_VERI / "osm_cikti"
YOL = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
YER = {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter"}


def kv(v: str | None) -> float | None:
    """'154000;34500' → 154,0 kV (en büyük)."""
    if not v:
        return None
    s = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", v)]
    s = [x / 1000 if x > 1000 else x for x in s]
    return max(s) if s else None


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    yol, hat, trafo, yer, hava, yer_alan = [], [], [], [], [], []
    fp = (
        osmium.FileProcessor(str(PBF))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("highway", "power", "place", "landuse", "aeroway"))
    )
    for o in fp:
        t = o.tags
        if o.is_way():
            try:
                xy = [(n.lat, n.lon) for n in o.nodes]
            except osmium.InvalidLocationError:
                continue
            if len(xy) < 2:
                continue
            h = t.get("highway")
            if h in YOL:
                yol.append(
                    {"id": o.id, "sinif": h, "dugum": [n.ref for n in o.nodes], "enlem": [p[0] for p in xy], "boylam": [p[1] for p in xy]}
                )
            elif t.get("power") == "line":
                hat.append({"id": o.id, "kv": kv(t.get("voltage")), "enlem": [p[0] for p in xy], "boylam": [p[1] for p in xy]})
            elif t.get("power") == "substation":
                a = np.array(xy)
                trafo.append(
                    {
                        "id": f"w{o.id}",
                        "enlem": a[:, 0].mean(),
                        "boylam": a[:, 1].mean(),
                        "kv": kv(t.get("voltage")),
                        "ad": t.get("name"),
                        "isletmeci": t.get("operator"),
                        "tur": t.get("substation"),
                    }
                )
            elif t.get("landuse") == "residential":
                a = np.array(xy)[:: max(1, len(xy) // 12)]
                yer_alan.extend({"enlem": p[0], "boylam": p[1], "tur": "residential"} for p in a)
            elif t.get("aeroway") == "aerodrome" and (t.get("icao") or t.get("iata")):
                a = np.array(xy)
                hava.append(
                    {
                        "id": f"w{o.id}",
                        "enlem": a[:, 0].mean(),
                        "boylam": a[:, 1].mean(),
                        "ad": t.get("name"),
                        "icao": t.get("icao"),
                        "iata": t.get("iata"),
                    }
                )
        elif o.is_node():
            if t.get("power") == "substation":
                trafo.append(
                    {
                        "id": f"n{o.id}",
                        "enlem": o.location.lat,
                        "boylam": o.location.lon,
                        "kv": kv(t.get("voltage")),
                        "ad": t.get("name"),
                        "isletmeci": t.get("operator"),
                        "tur": t.get("substation"),
                    }
                )
            elif t.get("place") in YER:
                yer.append({"enlem": o.location.lat, "boylam": o.location.lon, "tur": t.get("place"), "ad": t.get("name")})
            elif t.get("aeroway") == "aerodrome" and (t.get("icao") or t.get("iata")):
                hava.append(
                    {
                        "id": f"n{o.id}",
                        "enlem": o.location.lat,
                        "boylam": o.location.lon,
                        "ad": t.get("name"),
                        "icao": t.get("icao"),
                        "iata": t.get("iata"),
                    }
                )
    print(
        f"geçiş 1: {time.time() - t0:.0f} s; yol {len(yol)}, hat {len(hat)}, trafo {len(trafo)}, yer {len(yer)}+{len(yer_alan)}, hava {len(hava)}",
        flush=True,
    )
    pd.DataFrame(yol).to_parquet(CIKTI / "yollar.parquet")
    pd.DataFrame(hat).to_parquet(CIKTI / "hatlar.parquet")
    pd.DataFrame(trafo).to_parquet(CIKTI / "trafolar.parquet")
    pd.concat([pd.DataFrame(yer), pd.DataFrame(yer_alan)], ignore_index=True).to_parquet(CIKTI / "yerlesim.parquet")
    pd.DataFrame(hava).to_parquet(CIKTI / "havalimani.parquet")
    # koruma alanları (çok poligonlu alan birleştirmesi)
    wkb = osmium.geom.WKBFactory()
    kor = []
    fp2 = osmium.FileProcessor(str(PBF)).with_areas().with_filter(osmium.filter.KeyFilter("boundary", "leisure"))
    for o in fp2:
        if not o.is_area():
            continue
        t = o.tags
        if t.get("boundary") in ("protected_area", "national_park") or t.get("leisure") == "nature_reserve":
            try:
                g = wkb.create_multipolygon(o)
            except RuntimeError:
                continue
            kor.append(
                {
                    "id": o.orig_id(),
                    "ad": t.get("name"),
                    "sinif": t.get("protect_class"),
                    "tur": t.get("boundary") or t.get("leisure"),
                    "koruma_basligi": t.get("protection_title"),
                    "wkb": bytes.fromhex(g),
                }
            )
    pd.DataFrame(kor).to_parquet(CIKTI / "koruma.parquet")
    print(f"koruma alanı {len(kor)}; toplam {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
