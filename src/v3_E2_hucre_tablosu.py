"""
v3 E1/E2/E4 — Ön tarama hücreleri (0,25°, 1.464) için altyapı tablosu ve lojistik referansı.

Her hücrenin temsilî kara noktasında (on_tarama.parquet: enlem, boylam):
    bağlantı: gerilim, en yakın uygun trafo merkezi ve uzaklığı, bağlantı + erişim yolu maliyeti (50 MW)
    alan (2 km yarıçap): dışlama kesişimleri, uygun alan oranı, ortalama/en büyük eğim, koruma alanı oranı, göç riski (0/1/2),
                         en yakın yerleşim
    lojistik: 12 türbinlik saha için en ucuz tedarik planı (LP), $/MW, teslim süresi, ana kaynaklar
    mevcut_res: hücrede OSM rüzgâr türbini var mı (çok kriterli doğrulamanın "gerçek geliştirici kararları")
Lojistik referansı = mevcut santralli hücrelerin medyanı → data/atlas/lojistik_referans.json
Çıktı: data/atlas/cbs_hucre.parquet (ODbL türevi bilgiler içerir)
Çalıştırma: .venv/bin/python src/v3_E2_hucre_tablosu.py
"""

import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku

ATLAS = KOK / "data" / "atlas"


def hucre(r: dict) -> dict:
    from src.cbs import baglanti, katmanlar, lojistik
    from src.yerlesim.turbin import kutuphane_turbini

    cfg = config_oku()
    e, b = r["enlem"], r["boylam"]
    out = {"hucre_enlem": r["hucre_enlem"], "hucre_boylam": r["hucre_boylam"]}
    try:
        bg = baglanti.maliyet(e, b, 50.0, cfg)
        out.update(
            {
                "kv": bg["kv"],
                "trafo_ad": bg["hedef_trafo"]["ad"],
                "trafo_kv": bg["hedef_trafo"]["kv"],
                "trafo_km": bg["hedef_trafo"]["km"],
                "trafo_enlem": bg["hedef_trafo"]["enlem"],
                "trafo_boylam": bg["hedef_trafo"]["boylam"],
                "yol_km": (bg["yol_m"] or np.nan) / 1000,
                "baglanti_musd": bg["toplam_usd"] / 1e6,
                "baglanti_usd_mw": bg["usd_mw"],
            }
        )
    except Exception as ex:
        out["hata"] = f"bağlantı {type(ex).__name__}"
    turbin = r.get("turbin") or "E-141/4200"
    gob = {"E-141/4200": 120.0, "E-126/4200": 105.0, "V112/3450": 94.0}.get(turbin, 110.0)
    try:
        al = katmanlar.alan_ozeti(e, b, 2.0, cfg, gob, kutuphane_turbini(turbin, gob).D)
        if al:
            out.update({k: v for k, v in al.items() if k != "dislanan"})
            out.update({f"dis_{k}": v for k, v in al["dislanan"].items()})
    except Exception as ex:
        out["hata"] = out.get("hata", "") + f" alan {type(ex).__name__}"
    try:
        lj = lojistik.saha_lojistigi(e, b, 12, cfg, turbin, 4.2)
        if lj:
            plan = pd.DataFrame(lj["plan"])
            out.update(
                {
                    "lojistik_musd": lj["maliyet_usd"] / 1e6,
                    "lojistik_usd_mw": lj["usd_mw"],
                    "teslim_ay": lj["teslim_ay"],
                    "kaynak_kanat": "; ".join(plan[plan.bilesen == "kanat"]["kaynak"]),
                    "kaynak_kule": "; ".join(plan[plan.bilesen == "kule"]["kaynak"]),
                    "kaynak_nasel": "; ".join(plan[plan.bilesen == "nasel"]["kaynak"]),
                    "liman_km": float(plan[plan.tur == "liman"]["km"].max()) if (plan.tur == "liman").any() else np.nan,
                }
            )
    except Exception as ex:
        out["hata"] = out.get("hata", "") + f" lojistik {type(ex).__name__}"
    return out


def main() -> None:
    ot = pd.read_parquet(ATLAS / "on_tarama.parquet")
    with ProcessPoolExecutor(max_workers=4) as hv:
        satir = list(hv.map(hucre, ot[["hucre_enlem", "hucre_boylam", "enlem", "boylam", "turbin"]].to_dict(orient="records"), chunksize=20))
    d = pd.DataFrame(satir)
    tr = pd.read_csv(ATLAS / "osm_turbinler.csv")
    he = np.round(tr["enlem"] * 4) / 4
    hb = np.round(tr["boylam"] * 4) / 4
    say = pd.Series(1, index=pd.MultiIndex.from_arrays([he, hb])).groupby(level=[0, 1]).sum()
    d["mevcut_res_turbin"] = [int(say.get((round(a * 4) / 4, round(c * 4) / 4), 0)) for a, c in zip(d.hucre_enlem, d.hucre_boylam)]
    d["mevcut_res"] = d["mevcut_res_turbin"] > 0
    d.to_parquet(ATLAS / "cbs_hucre.parquet", index=False)
    m = d[d["mevcut_res"]]
    ref = {
        "usd_mw": float(m["lojistik_usd_mw"].median()),
        "teslim_ay": float(m["teslim_ay"].median()),
        "baglanti_usd_mw_medyan_mevcut": float(m["baglanti_usd_mw"].median()),
        "hucre_sayisi": int(len(m)),
        "aciklama": "Mevcut RES santrallerinin bulunduğu ön tarama hücrelerinin medyanı (12 türbin, 4,2 MW): RES CAPEX'in (1,15 M$/MW) varsaydığı tipik teslim maliyeti ve süresi",
    }
    (ATLAS / "lojistik_referans.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1))
    print(json.dumps(ref, ensure_ascii=False, indent=1))
    print(d.describe().T.round(2).to_string())
    print("hata", d.get("hata", pd.Series(dtype=str)).notna().sum())


if __name__ == "__main__":
    main()
