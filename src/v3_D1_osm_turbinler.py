"""
v3 D1 — Türkiye OSM türbin paketi (komşu santral iz etkisi için): data/atlas/osm_turbinler.csv (ODbL türevi).

Kaynak: data/raw/osm/res_turbinler_overpass.json (Overpass, power=generator + generator:source=wind düğümleri; v2 Faz C0).
Her türbin için iz hesabında kullanılacak rotor çapı D, göbek H ve anma gücü P:
    1) atlas santraline aitse (data/atlas/santral_turbin_konumlari.csv ile 30 m içinde eşleşme): santralin türbin vekili
       (data/atlas/santral_turbinleri.csv; windpowerlib kütüphanesinden D),
    2) değilse OSM etiketleri (rotor:diameter, height:hub, generator:output:electricity),
    3) eksik kalanlar config v2.santral_turbin sınıf varsayılanlarından: D = √(4P / (π · SP_sınıf)), H = sınıf göbeği;
       birim güç bilinmiyorsa atlas santrallerinin medyanı.
Çalıştırma: .venv/bin/python src/v3_D1_osm_turbinler.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.atlas.turbinler import kutuphane, mw_coz, sayi_coz
from src.ayarlar import HAM_VERI, KOK, config_oku, deger
from src.yerlesim.alan import yerel_xy


def main() -> None:
    cfg = config_oku()
    el = json.loads((HAM_VERI / "osm" / "res_turbinler_overpass.json").read_text())["elements"]
    d = pd.DataFrame(
        [
            {
                "osm_id": e["id"],
                "enlem": e["lat"],
                "boylam": e["lon"],
                "mw_osm": mw_coz(e.get("tags", {}).get("generator:output:electricity")),
                "rotor_osm": sayi_coz(e.get("tags", {}).get("rotor:diameter")),
                "gobek_osm": sayi_coz(e.get("tags", {}).get("height:hub")),
            }
            for e in el
            if e["type"] == "node"
        ]
    )
    konum = pd.read_csv(KOK / "data" / "atlas" / "santral_turbin_konumlari.csv")
    tur = pd.read_csv(KOK / "data" / "atlas" / "santral_turbinleri.csv").set_index("epias_id")
    lib = kutuphane().set_index("turbine_type")
    # 30 m içindeki atlas türbin konumuyla eşleştir
    d["epias_id"] = np.nan
    x, y = yerel_xy(d["enlem"], d["boylam"], 39.0, 32.0)
    xk, yk = yerel_xy(konum["enlem"], konum["boylam"], 39.0, 32.0)
    from scipy.spatial import cKDTree

    dist, j = cKDTree(np.c_[xk, yk]).query(np.c_[x, y])
    d.loc[dist <= 30, "epias_id"] = konum["epias_id"].to_numpy()[j[dist <= 30]]
    sinif = deger(cfg["v2"]["santral_turbin"])["siniflar"]
    medyan_mw = float(tur["birim_mw"].median())
    satir = []
    for r in d.itertuples():
        if r.epias_id == r.epias_id and int(r.epias_id) in tur.index:
            t = tur.loc[int(r.epias_id)]
            D = float(lib.loc[t["turbin"], "rotor_diameter"]) if t["turbin"] in lib.index else np.nan
            H, P, kaynak = float(t["gobek"]), float(t["birim_mw"]), "atlas_vekil"
        else:
            P = r.mw_osm if r.mw_osm == r.mw_osm and r.mw_osm else np.nan
            D = r.rotor_osm if r.rotor_osm == r.rotor_osm and r.rotor_osm else np.nan
            H = r.gobek_osm if r.gobek_osm == r.gobek_osm and r.gobek_osm else np.nan
            kaynak = "osm_etiket" if P == P else "varsayilan"
        if P != P:
            P = medyan_mw
        s = next(k for k in sinif if P <= k["mw_ust"])
        if D != D or not (40 <= D <= 180):
            D = float(np.sqrt(4 * P * 1e6 / (np.pi * s["ozgul_guc"])))
            kaynak += "+sinif_D"
        if H != H or not (40 <= H <= 170):
            H = float(s["gobek"])
        satir.append(
            {
                "osm_id": r.osm_id,
                "enlem": round(r.enlem, 6),
                "boylam": round(r.boylam, 6),
                "epias_id": int(r.epias_id) if r.epias_id == r.epias_id else None,
                "P_mw": round(P, 3),
                "D_m": round(D, 1),
                "H_m": round(H, 1),
                "kaynak": kaynak,
            }
        )
    out = pd.DataFrame(satir)
    out["epias_id"] = out["epias_id"].astype("Int64")
    yol = KOK / "data" / "atlas" / "osm_turbinler.csv"
    out.to_csv(yol, index=False, encoding="utf-8-sig")
    print(f"{len(out)} türbin → {yol} ({yol.stat().st_size / 1e3:.0f} kB)")
    print(out["kaynak"].value_counts().to_string())
    print(out[["P_mw", "D_m", "H_m"]].describe().round(1).to_string())


if __name__ == "__main__":
    main()
