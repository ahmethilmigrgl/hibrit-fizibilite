"""
v2 Revizyon R3 — Modern türbin doğrulaması.

1) Modern alt küme: türbin vekilinin rotor çapı ≥ 120 m ya da özgül gücü ≤ 300 W/m² (OSM birim gücü/rotorundan eşlenen
   kütüphane türbini). Bu santrallerde birini dışarıda bırak tahmini (kendi türbinleriyle, A4) gözlenenle karşılaştırılır.
2) "Modern türbin kazancı": her santralde KENDİ kalibre K matrisiyle (aktarım hatası yok) iki KF hesaplanır —
   kendi türbin vekili @ kendi göbeği ve E-141/4200 @ 120 m. Fark, haritadaki hücre KF'sinin santralin gözleneninden neden
   yüksek olabileceğinin salt türbin payıdır. Hücre − gözlenen farkının ne kadarını açıkladığı bölge bazında raporlanır.
3) Türkiye'de gözlenen en yüksek santral KF'leri (üst sınır referansı): P90 ve azami.
Çıktı: outputs/v2R/R3_modern_turbin.csv, R3_turbin_kazanci.csv, R3_ozet.json
Çalıştırma: .venv/bin/python src/v2_R3_modern_turbin.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.atlas.turbinler import kutuphane
from src.ayarlar import CIKTILAR, config_oku
from src.kaynaklar import era5_cds
from src.uretim import kalibrasyon as kal

CIKTI = CIKTILAR / "v2R"


def main() -> None:
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    df, mat = aktarim.atlas()
    lib = kutuphane().set_index("turbine_type")
    cv = pd.read_csv(CIKTILAR / "v2" / "A4_capraz_dogrulama.csv")
    cv = cv[(cv["gmod"] == "yerlesim") & (cv["yontem"] == "gwa_olcekli")].set_index("epias_id")
    satir = []
    for r in df.itertuples():
        i = int(r.epias_id)
        era5 = era5_cds.indir(r.enlem, r.boylam)
        K = mat[i]
        m_kendi = kal.referans_model(era5, cr, r.turbin, float(r.gobek))
        m_mod = kal.referans_model(era5, cr, "E-141/4200", 120.0)
        satir.append(
            {
                "epias_id": i,
                "ad": r.ad,
                "enlem": r.enlem,
                "boylam": r.boylam,
                "turbin": r.turbin,
                "gobek": r.gobek,
                "rotor_m": float(lib.loc[r.turbin, "rotor_diameter"]),
                "ozgul_guc": float(lib.loc[r.turbin, "sp"]),
                "gozlenen_kf_%": 100 * r.gozlenen_kf,
                "kendi_turbin_kf_%": 100 * float(m_kendi.kf_matris(K).mean()),
                "e141_120_kf_%": 100 * float(m_mod.kf_matris(K).mean()),
                "loo_hata_puan": float(cv.loc[i, "kf_hatasi_puan"]) if i in cv.index else np.nan,
            }
        )
    d = pd.DataFrame(satir)
    d["turbin_kazanci_puan"] = d["e141_120_kf_%"] - d["kendi_turbin_kf_%"]
    d["modern"] = (d["rotor_m"] >= 120) | (d["ozgul_guc"] <= 300)
    CIKTI.mkdir(parents=True, exist_ok=True)
    d.to_csv(CIKTI / "R3_turbin_kazanci.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    mod = d[d["modern"]]
    eski = d[~d["modern"]]
    e = mod["loo_hata_puan"]
    ozet = {
        "modern_n": len(mod),
        "modern_turbinler": mod["turbin"].value_counts().to_dict(),
        "modern_loo_ort_hata": float(e.mean()),
        "modern_loo_medyan_mutlak": float(e.abs().median()),
        "modern_loo_rmse": float(np.sqrt((e**2).mean())),
        "diger_loo_ort_hata": float(eski["loo_hata_puan"].mean()),
        "diger_loo_rmse": float(np.sqrt((eski["loo_hata_puan"] ** 2).mean())),
        "modern_gozlenen_medyan": float(mod["gozlenen_kf_%"].median()),
        "modern_e141_kf_medyan": float(mod["e141_120_kf_%"].median()),
        "turbin_kazanci_eski_medyan": float(eski["turbin_kazanci_puan"].median()),
        "turbin_kazanci_eski_p10_p90": [float(eski["turbin_kazanci_puan"].quantile(q)) for q in (0.1, 0.9)],
        "turbin_kazanci_modern_medyan": float(mod["turbin_kazanci_puan"].median()),
        "turbin_kazanci_turbine_gore": d.groupby("turbin")["turbin_kazanci_puan"].median().round(2).to_dict(),
        "gozlenen_kf_p90": float(d["gozlenen_kf_%"].quantile(0.9)),
        "gozlenen_kf_p95": float(d["gozlenen_kf_%"].quantile(0.95)),
        "gozlenen_kf_azami": float(d["gozlenen_kf_%"].max()),
        "gozlenen_kf_azami_santral": d.loc[d["gozlenen_kf_%"].idxmax(), "ad"],
        "e141_kf_p95_santral_konumlari": float(d["e141_120_kf_%"].quantile(0.95)),
        "e141_kf_azami_santral_konumlari": float(d["e141_120_kf_%"].max()),
    }
    (CIKTI / "R3_ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1, default=float))
    pd.set_option("display.width", 220)
    print(
        mod[["ad", "turbin", "gobek", "rotor_m", "ozgul_guc", "gozlenen_kf_%", "kendi_turbin_kf_%", "e141_120_kf_%", "loo_hata_puan"]]
        .round(1)
        .to_string(index=False)
    )
    print(json.dumps(ozet, ensure_ascii=False, indent=1, default=float))
    mod[["ad", "turbin", "rotor_m", "ozgul_guc", "gozlenen_kf_%", "loo_hata_puan", "e141_120_kf_%"]].to_csv(
        CIKTI / "R3_modern_turbin.csv", index=False, encoding="utf-8-sig", float_format="%.2f"
    )


if __name__ == "__main__":
    main()
