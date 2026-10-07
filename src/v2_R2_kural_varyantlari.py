"""
v2 Revizyon R2 — Aktarım kuralı varyantlarının birini dışarıda bırak çapraz doğrulaması (yerleşim modu, GWA ölçekli kural).

Varyantlar: kıyı benzerliği (ikili sınıf / sürekli oran / yok), komşu artığının ulusal medyana büzülmesi (n0), R sınırı,
rakım ve karmaşıklık eşikleri. Her santral kendi türbin vekiliyle, talimat/arıza saatleri hariç değerlendirilir
(v2_A4_capraz_dogrulama.py ile aynı). Santral verisi bir kez yüklenir (data/onbellek/cv_veri.pkl).
Çıktı: outputs/v2R/R2_kural_varyantlari.csv
Çalıştırma: .venv/bin/python src/v2_R2_kural_varyantlari.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import copy
import importlib.util
import pickle

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, KOK, config_oku

ONB = KOK / "data" / "onbellek" / "cv_veri.pkl"


def a4():
    sp = importlib.util.spec_from_file_location("a4", KOK / "src" / "v2_A4_capraz_dogrulama.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def veri(cfg):
    if ONB.exists():
        return pickle.loads(ONB.read_bytes())
    m = a4()
    d = m.veriler(cfg)
    df, _ = aktarim.atlas()
    tr = pd.read_csv(KOK / "data" / "atlas" / "santral_turbinleri.csv")
    adet = dict(zip(tr["epias_id"], tr["turbin_adedi"], strict=True))
    gw = {int(r.epias_id): m.saha_gwa(r, "yerlesim", adet) for r in df.itertuples()}
    ONB.parent.mkdir(parents=True, exist_ok=True)
    ONB.write_bytes(pickle.dumps((d, gw)))
    return d, gw


def degerlendir(cfg, d, gw) -> pd.DataFrame:
    df, _ = aktarim.atlas()
    aktarim.ulusal_artik.cache_clear()
    satir = []
    for r in df.itertuples():
        m, g, ok = d[int(r.epias_id)]
        tan = {"rakim_m": r.rakim_m, "karmasiklik": r.karmasiklik, "kiyi_km": r.kiyi_km}
        K, b = aktarim.tahmin(
            r.enlem, r.boylam, r.era5_100m, "gwa_olcekli", cfg, haric=int(r.epias_id), tan=tan, gwa_hiz=gw[int(r.epias_id)]
        )
        kf = m.kf_matris(K)
        satir.append(
            {
                "epias_id": r.epias_id,
                "ad": r.ad,
                "komsu": len(b.get("komsu", [])),
                "hata": 100 * float(kf[ok].mean() - g[ok].mean()),
            }
        )
    return pd.DataFrame(satir)


def ozet(x: pd.DataFrame) -> dict:
    e = x["hata"]
    k = x[x["komsu"] > 0]["hata"]
    return {
        "rmse": float(np.sqrt((e**2).mean())),
        "medyan_mutlak": float(e.abs().median()),
        "p90_mutlak": float(e.abs().quantile(0.9)),
        "ort_hata": float(e.mean()),
        "asiri_tahmin_p90": float(e.quantile(0.9)),  # en kötü %10'luk fazla tahmin
        "komsulu_n": int(len(k)),
        "komsulu_rmse": float(np.sqrt((k**2).mean())) if len(k) else np.nan,
        "tek_komsulu_rmse": float(np.sqrt((x[x["komsu"] == 1]["hata"] ** 2).mean())) if (x["komsu"] == 1).any() else np.nan,
    }


VARYANTLAR = {
    "mevcut (sınıf, büzülme yok)": {},
    "kıyı oranı 0,7": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 0.7},
    "kıyı oranı 1,0": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 1.0},
    "kıyı yok": {"kiyi_benzerlik": False},
    "büzülme n0=1": {"r_buzulme_n0": 1},
    "büzülme n0=2": {"r_buzulme_n0": 2},
    "büzülme n0=3": {"r_buzulme_n0": 3},
    "R sınırı P10–P90": {"r_sinir": "p10_p90"},
    "kıyı oranı 1,0 + n0=1": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 1.0, "r_buzulme_n0": 1},
    "kıyı oranı 1,0 + n0=2": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 1.0, "r_buzulme_n0": 2},
    "kıyı oranı 0,7 + n0=1": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 0.7, "r_buzulme_n0": 1},
    "kıyı oranı 0,7 + n0=2": {"kiyi_benzerlik": "oran", "kiyi_oran_esik": 0.7, "r_buzulme_n0": 2},
    "sınıf + n0=1 + R sınırı": {"r_buzulme_n0": 1, "r_sinir": "p10_p90"},
    "rakım 300 m": {"rakim_farki_m": 300},
    "karmaşıklık 0,03": {"karmasiklik_farki": 0.03},
}


def main() -> None:
    cfg0 = config_oku()
    d, gw = veri(cfg0)
    df, mat = aktarim.atlas()
    ci = aktarim.santral_c()
    Rm = np.array([mat[int(i)].mean() / ci[int(i)] for i in df["epias_id"]])
    p10p90 = [float(np.quantile(Rm, 0.1)), float(np.quantile(Rm, 0.9))]
    print("Santral R ortalamaları: P10–P90", np.round(p10p90, 3), "medyan", round(float(np.median(Rm)), 3))
    satir = []
    for ad, deg in VARYANTLAR.items():
        cfg = copy.deepcopy(cfg0)
        a = cfg["v2"]["aktarim"]["value"]
        for k, v in deg.items():
            a[k] = p10p90 if v == "p10_p90" else v
        x = degerlendir(cfg, d, gw)
        satir.append({"varyant": ad, **ozet(x)})
        print(f"{ad:32s}", {k: round(v, 2) for k, v in satir[-1].items() if k != "varyant"}, flush=True)
    out = pd.DataFrame(satir)
    (CIKTILAR / "v2R").mkdir(parents=True, exist_ok=True)
    out.to_csv(CIKTILAR / "v2R" / "R2_kural_varyantlari.csv", index=False, encoding="utf-8-sig", float_format="%.3f")


if __name__ == "__main__":
    main()
