"""
v3 E6 — Faz E doğrulamaları ve ön tarama karşılaştırması.

1. Bağlantı maliyeti: YEKA RES-2025 TEİAŞ bağlantı görüşlerindeki hat uzunlukları ve gerilimlerle formülün verdiği maliyet
   (proje başına) + aynı ildeki hücrelerde modelin bulduğu trafo uzaklıkları; v1 sabit 120 bin $/MW ile karşılaştırma.
2. Lojistik: CAPEX içindeki payın dağılımı; kule taşımasının kule maliyetine oranı (Cotrell vd. 2014: < %8).
3. Ön tarama: v2 (outputs/v3E/on_tarama_v2.parquet) → v3 altyapısız (outputs/v3E/on_tarama_v3_altyapisiz.parquet) →
   v3 (data/atlas/on_tarama.parquet): başabaş dağılımı, değişimin ayrıştırılması, ekonomik ilk 10.
Çıktılar: outputs/v3E/E6_baglanti_dogrulama.csv, E6_on_tarama_karsilastirma.csv, E6_ilk10_ekonomik.csv, E6_dogrulama.json
Çalıştırma: .venv/bin/python src/v3_E6_dogrulama.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger

ATLAS = KOK / "data" / "atlas"
CIKTI = CIKTILAR / "v3E"


def baglanti_dogrulama(cfg: dict) -> tuple[pd.DataFrame, dict]:
    b = deger(cfg["v3"]["baglanti"])
    y = pd.read_csv(ATLAS / "teias_yeka_baglanti.csv")
    hc = pd.read_parquet(ATLAS / "cbs_hucre.parquet").merge(
        pd.read_parquet(ATLAS / "on_tarama.parquet")[["hucre_enlem", "hucre_boylam", "il"]], on=["hucre_enlem", "hucre_boylam"]
    )
    satir = []
    for r in y.itertuples():
        k = "400" if r.kv >= 300 else "154"
        hat = r.hat_km * b["hat_usd_km"][k]  # görüşteki uzunluk güzergâh uzunluğudur → çarpan uygulanmaz
        top = b["trafo_merkezi_usd"][k] + b["fider_usd"][k] + hat
        il = r.il.split("/")[0]
        h = hc[hc["il"] == il]
        satir.append(
            {
                "proje": r.proje,
                "mw": r.mw,
                "kv": r.kv,
                "hat_km_teias": r.hat_km,
                "maliyet_musd": top / 1e6,
                "usd_mw": top / r.mw,
                "v1_usd_mw": 120000.0,
                "il_hucre_trafo_km_medyan": float(h["trafo_km"].median()) if len(h) else np.nan,
                "il_hucre_hat_km_medyan": float(h["trafo_km"].median() * b["guzergah_carpani"]) if len(h) else np.nan,
            }
        )
    d = pd.DataFrame(satir)
    oz = {
        "yeka_usd_mw_aralik": [float(d["usd_mw"].min()), float(d["usd_mw"].max())],
        "yeka_hat_km_medyan": float(d["hat_km_teias"].median()),
        "model_hucre_trafo_km_medyan": float(hc["trafo_km"].median()),
        "model_hucre_hat_km_medyan": float(hc["trafo_km"].median() * b["guzergah_carpani"]),
        "model_baglanti_usd_mw_50mw": [float(x) for x in hc["baglanti_usd_mw"].quantile([0.1, 0.5, 0.9])],
        "mevcut_res_hucre_trafo_km_medyan": float(hc.loc[hc["mevcut_res"], "trafo_km"].median()),
    }
    return d, oz


def lojistik_dogrulama(cfg: dict) -> dict:
    L = deger(cfg["v3"]["lojistik"])
    hc = pd.read_parquet(ATLAS / "cbs_hucre.parquet")
    capex = float(deger(cfg["teknoloji"]["res"]["capex"]))
    pay = hc["lojistik_usd_mw"] / capex
    k = L["bilesenler"]["kule"]
    t = L["tasima"]
    # 4,2 MW türbin, 360 t çelik kule; kule fiyatı ≈ 2.000 $/t (TAHMİN, çelik kule imalat) → 0,72 M$
    kule_usd = 360 * 2000.0
    kule_tasima = k["adet"] * (t["sefer_sabit_usd"] + t["izin_eskort_usd"] + t["usd_t_km"] * k["kutle_t"] * 400)
    return {
        "lojistik_capex_payi": [float(x) for x in pay.quantile([0.1, 0.5, 0.9])],
        "lojistik_usd_mw": [float(x) for x in hc["lojistik_usd_mw"].quantile([0.1, 0.5, 0.9])],
        "teslim_ay": [float(x) for x in hc["teslim_ay"].quantile([0.1, 0.5, 0.9])],
        "kule_400km_tasima_payi": kule_tasima / (kule_usd + kule_tasima),
        "not": "Cotrell vd. (2014): kule taşıması, kule sermaye + taşıma maliyetinin %8'inden az. Kule fiyatı 2.000 $/t TAHMİN.",
    }


def on_tarama_karsilastirma() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    k = ["hucre_enlem", "hucre_boylam"]
    v2 = pd.read_parquet(CIKTI / "on_tarama_v2.parquet")
    v3 = pd.read_parquet(ATLAS / "on_tarama.parquet")
    p0 = CIKTI / "on_tarama_v3_altyapisiz.parquet"
    a0 = pd.read_parquet(p0) if p0.exists() else None
    d = v2[[*k, "il", "ilce", "ada", "guven", "res_kf", "basabas_en_iyi", "en_iyi_tasarim", "hata"]].rename(
        columns={"basabas_en_iyi": "bb_v2", "en_iyi_tasarim": "tas_v2", "hata": "hata_v2"}
    )
    if a0 is not None:
        d = d.merge(a0[[*k, "basabas_en_iyi"]].rename(columns={"basabas_en_iyi": "bb_altyapisiz"}), on=k, how="left")
    d = d.merge(
        v3[[*k, "basabas_en_iyi", "en_iyi_tasarim", "sebeke_capex_usd_mw", "res_capex_usd_mw", "hata"]].rename(
            columns={"basabas_en_iyi": "bb_v3", "en_iyi_tasarim": "tas_v3", "hata": "hata_v3"}
        ),
        on=k,
    )
    ok = (d["hata_v2"] == "") & (d["hata_v3"] == "") & d["bb_v2"].notna() & d["bb_v3"].notna()
    d["fark"] = d["bb_v3"] - d["bb_v2"]
    if "bb_altyapisiz" in d:
        d["fark_isletme_kayip"] = d["bb_altyapisiz"] - d["bb_v2"]
        d["fark_altyapi"] = d["bb_v3"] - d["bb_altyapisiz"]
    m = d[ok & ~d["ada"].fillna(False)]
    oz = {
        "hucre": int(len(m)),
        "bb_v2_medyan": float(m["bb_v2"].median()),
        "bb_v3_medyan": float(m["bb_v3"].median()),
        "fark_yuzdelik": [float(x) for x in m["fark"].quantile([0.1, 0.5, 0.9])],
        "spearman_v2_v3": float(m["bb_v2"].rank().corr(m["bb_v3"].rank())),
        "esik_alti_58_v2": int((m["bb_v2"] <= 58).sum()),
        "esik_alti_58_v3": int((m["bb_v3"] <= 58).sum()),
    }
    if "fark_altyapi" in m:
        oz["fark_isletme_kayip_yuzdelik"] = [float(x) for x in m["fark_isletme_kayip"].quantile([0.1, 0.5, 0.9])]
        oz["fark_altyapi_yuzdelik"] = [float(x) for x in m["fark_altyapi"].quantile([0.1, 0.5, 0.9])]
    i2, i3 = m.nsmallest(10, "bb_v2"), m.nsmallest(10, "bb_v3")
    oz["ilk10_ortak"] = len(set(i2.index) & set(i3.index))
    ilk = pd.concat(
        [
            i2[["il", "ilce", "res_kf", "guven", "bb_v2", "bb_v3"]].assign(liste="v2", sira=range(1, 11)),
            i3[["il", "ilce", "res_kf", "guven", "bb_v2", "bb_v3", "sebeke_capex_usd_mw"]].assign(liste="v3", sira=range(1, 11)),
        ]
    )
    return d, ilk, oz


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    b, ob = baglanti_dogrulama(cfg)
    b.to_csv(CIKTI / "E6_baglanti_dogrulama.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    ol = lojistik_dogrulama(cfg)
    d, ilk, oo = on_tarama_karsilastirma()
    d.to_csv(CIKTI / "E6_on_tarama_karsilastirma.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    ilk.to_csv(CIKTI / "E6_ilk10_ekonomik.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    oz = {"baglanti": ob, "lojistik": ol, "on_tarama": oo}
    (CIKTI / "E6_dogrulama.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1))
    print(b.round(2).to_string())
    print(json.dumps(oz, ensure_ascii=False, indent=1))
    print(ilk.round(2).to_string())


if __name__ == "__main__":
    main()
