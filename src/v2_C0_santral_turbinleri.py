"""
v2 Faz C ön adım — Atlas santrallerinin türbinleri (çevrimdışı; OSM Overpass, anahtarsız).

1) Türkiye'deki OSM rüzgâr türbini düğümleri (power=generator, generator:source=wind) ve santral ilişkilerinin/poligonlarının
   üyeleri indirilir (data/raw/osm/, bir kez).
2) Türbin → santral: ilişki üyeliği; değilse santral poligonu içinde; değilse (OSM'siz/elle eşleşen santraller) santral
   noktasına ≤ 2,5 km ve başka santrale atanmamış türbinler.
3) Santral başına: türbin sayısı, birim güç (OSM etiketlerinin medyanı; yoksa EPİAŞ azami kapasite / türbin sayısı),
   üretici, rotor, göbek → kütüphane vekili (src/atlas/turbinler.py).
Çıktılar (data/atlas, ODbL türevi): santral_turbinleri.csv, santral_turbin_konumlari.csv

Çalıştırma: .venv/bin/python src/v2_C0_santral_turbinleri.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import time
from collections import Counter

import numpy as np
import pandas as pd
import requests
from matplotlib.path import Path as Yol

from src.atlas import turbinler as T
from src.ayarlar import HAM_VERI, KOK, config_oku, deger

OSM = HAM_VERI / "osm"
ATLAS = KOK / "data" / "atlas"
UC = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
AJAN = {"User-Agent": "hibrit-fizibilite/2.0 (portfolio research)"}


def overpass(sorgu: str, dosya: Path) -> list:
    if not dosya.exists():
        for _ in range(3):
            for u in UC:
                r = requests.post(u, data={"data": sorgu}, headers=AJAN, timeout=300)
                if r.ok and r.text.lstrip().startswith("{"):
                    dosya.write_text(r.text)
                    return r.json()["elements"]
            time.sleep(30)
        raise RuntimeError("Overpass yanıt vermedi")
    return json.loads(dosya.read_text())["elements"]


def _km(e1, b1, e2, b2):
    return 6371 * np.hypot(np.radians(e2 - e1), np.radians(b2 - b1) * np.cos(np.radians((e1 + e2) / 2)))


def main() -> None:
    turb = overpass(
        '[out:json][timeout:240];area["ISO3166-1"="TR"][admin_level=2]->.tr;'
        'node["power"="generator"]["generator:source"="wind"](area.tr);out body;',
        OSM / "res_turbinler_overpass.json",
    )
    santral = json.loads((OSM / "res_tr_overpass.json").read_text())["elements"]
    rel = ",".join(str(x["id"]) for x in santral if x["type"] == "relation")
    way = ",".join(str(x["id"]) for x in santral if x["type"] == "way")
    uyeler = overpass(
        f"[out:json][timeout:240];(relation(id:{rel});way(id:{way}););out body geom;", OSM / "res_santral_uyeler_overpass.json"
    )
    td = pd.DataFrame(
        [
            {
                "id": t["id"],
                "enlem": t["lat"],
                "boylam": t["lon"],
                "mw": T.mw_coz(t["tags"].get("generator:output:electricity")),
                "uretici": t["tags"].get("manufacturer"),
                "rotor": T.sayi_coz(t["tags"].get("rotor:diameter")),
                "gobek": T.sayi_coz(t["tags"].get("height:hub")),
            }
            for t in turb
        ]
    ).set_index("id")
    td["osm_id"] = None
    # 1) üyelik, 2) poligon içi
    for el in uyeler:
        oid = ("r" if el["type"] == "relation" else "w") + str(el["id"])
        if el["type"] == "relation":
            dugum = [m["ref"] for m in el.get("members", []) if m["type"] == "node" and m["ref"] in td.index]
            td.loc[dugum, "osm_id"] = td.loc[dugum, "osm_id"].fillna(oid)
            halkalar = [m["geometry"] for m in el.get("members", []) if m["type"] == "way" and m.get("role") == "outer" and "geometry" in m]
        else:
            halkalar = [el["geometry"]] if "geometry" in el else []
        for h in halkalar:
            if len(h) < 3:
                continue
            yol = Yol([(p["lon"], p["lat"]) for p in h])
            bos = td["osm_id"].isna()
            ic = yol.contains_points(td.loc[bos, ["boylam", "enlem"]].to_numpy())
            td.loc[td.index[bos][ic], "osm_id"] = oid
    a = pd.read_csv(ATLAS / "kalibrasyon_atlasi.csv")
    a = a[a["k_sabit"].notna()]
    satir, konum = [], []
    for r in a.itertuples():
        t = td[td["osm_id"] == r.osm_id] if isinstance(r.osm_id, str) else td.iloc[0:0]
        kaynak = "osm_uyelik"
        if t.empty:  # 3) yakın, atanmamış türbinler
            d = _km(r.enlem, r.boylam, td["enlem"].to_numpy(), td["boylam"].to_numpy())
            t = td[(d <= 2.5) & td["osm_id"].isna()]
            kaynak = "yakin_2_5km" if not t.empty else "yok"
        n = len(t)
        mw_etiket = t["mw"].dropna()
        kap = r.kapasite_azami_mw if r.kapasite_azami_mw == r.kapasite_azami_mw else r.osm_mw
        alt, ust = deger(config_oku()["v2"]["santral_turbin"])["birim_makul"]
        if len(mw_etiket):
            birim, bk = float(mw_etiket.median()), "osm_etiket"
        elif n and kap == kap and alt <= kap / n <= ust:
            birim, bk = float(kap / n), "kapasite/adet"
        else:
            birim, bk = None, "varsayilan (etiketli santral medyanı)"
        uretici = Counter(t["uretici"].dropna()).most_common(1)[0][0] if t["uretici"].notna().any() else None
        rotor = float(t["rotor"].median()) if t["rotor"].notna().any() else None
        gobek = float(t["gobek"].median()) if t["gobek"].notna().any() else None
        satir.append(
            {
                "epias_id": int(r.epias_id),
                "ad": r.ad,
                "osm_id": r.osm_id,
                "turbin_kaynagi": kaynak,
                "turbin_adedi": n,
                "birim_mw": round(birim, 3) if birim is not None else None,
                "birim_kaynagi": bk,
                "uretici": uretici,
                "rotor_osm": rotor,
                "gobek_osm": gobek,
            }
        )
        for q in t.itertuples():
            konum.append({"epias_id": int(r.epias_id), "enlem": round(q.enlem, 5), "boylam": round(q.boylam, 5)})
    df = pd.DataFrame(satir)
    medyan = float(df.loc[df["birim_kaynagi"] == "osm_etiket", "birim_mw"].median())
    df["birim_mw"] = df["birim_mw"].fillna(medyan)
    es = pd.DataFrame(
        [
            T.esle(
                r.birim_mw,
                r.uretici,
                r.rotor_osm if r.rotor_osm == r.rotor_osm else None,
                r.gobek_osm if r.gobek_osm == r.gobek_osm else None,
            )
            for r in df.itertuples()
        ]
    )
    df = pd.concat([df, es], axis=1)
    df.to_csv(ATLAS / "santral_turbinleri.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.DataFrame(konum).to_csv(ATLAS / "santral_turbin_konumlari.csv", index=False, encoding="utf-8-sig")
    print(df["turbin_kaynagi"].value_counts().to_string(), "\n")
    print(df["birim_kaynagi"].value_counts().to_string(), "\n")
    print(df["turbin"].value_counts().to_string(), "\n")
    print(df[["turbin_adedi", "birim_mw", "gobek"]].describe().round(2).to_string())


if __name__ == "__main__":
    main()
