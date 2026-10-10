"""
v3 D3 — Gerçek Türk santrallerinin OSM yerleşimi için hesaplanan iz kaybının makullüğü: model (Bastankhah / Jensen) ve
ortam türbülansı (TI %8 / %10 / %12) duyarlılığı. Santraller: en çok türbinli kalibre santraller.
Çıktı: outputs/v3D/D3_gercek_santral.csv
Çalıştırma: .venv/bin/python src/v3_D3_gercek_santral.py
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import importlib.util

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.kaynaklar import gwa250
from src.yerlesim import alan as A
from src.yerlesim import iz
from src.yerlesim.analiz import Baglam, komsu_sozlugu, komsu_turbinler
from src.yerlesim.ruzgar_gulu import akis_tablosu, esdeger_hiz
from src.yerlesim.turbin import kutuphane_turbini

SANTRALLER = ["KANGAL RES", "GEYCEK RES", "BALIKESİR RES", "SOMA RES", "YAHYALI RES", "ŞAH RES", "ENERJİSA ÇANAKKALE RES"]


def main() -> None:
    sp = importlib.util.spec_from_file_location("aiz", KOK / "src" / "v3_D1_atlas_iz.py")
    aiz = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(aiz)
    cfg = config_oku()
    ay = deger(cfg["v3"]["yerlesim"])
    _, (d, _) = aiz.cv_veri()
    df, mat = aktarim.atlas()
    konum = pd.read_csv(KOK / "data" / "atlas" / "santral_turbin_konumlari.csv")
    satir = []
    for r in df[df["ad"].isin(SANTRALLER)].itertuples():
        i = int(r.epias_id)
        k = konum[konum["epias_id"] == i]
        m, _, _ = d[i]
        t = kutuphane_turbini(r.turbin, float(r.gobek))
        v = esdeger_hiz(m.v * mat[i][m.ay - 1, m.saat], m.rho)
        akis = akis_tablosu(v, aiz.santral_yon(r.enlem, r.boylam, m.indeks), 36, 0.5, guc=t.guc_mw)
        e0, b0 = float(k["enlem"].mean()), float(k["boylam"].mean())
        x, y = A.yerel_xy(k["enlem"], k["boylam"], e0, b0)
        g = np.array([gwa250.nokta(float(a), float(b)) for a, b in zip(k["enlem"], k["boylam"])])
        kom = komsu_turbinler(e0, b0, ay["komsu_yaricap_km"], ay["komsu_azami"], haric_epias=i)
        if len(kom):
            dmin = np.hypot(kom["x"].to_numpy()[:, None] - x[None], kom["y"].to_numpy()[:, None] - y[None]).min(1)
            kom = kom[dmin > 0.5 * t.D].reset_index(drop=True)
        bg = Baglam(
            e0, b0, t, akis, akis, pd.DataFrame(), pd.DataFrame(), {}, None, None, float(g.mean()), 0.0, kom, 0.1, ay, pd.DataFrame()
        )
        ks = komsu_sozlugu(bg)
        aralik = np.sort(np.hypot(x[:, None] - x[None], y[:, None] - y[None]) + np.eye(len(x)) * 1e9, 1)[:, 0].mean() / t.D
        for model in ("bastankhah", "jensen"):
            for ti in (0.08, 0.10, 0.12) if model == "bastankhah" else (0.10,):
                ref = iz.referans(x, y, g / g.mean(), t, akis, ti, model, ks)
                satir.append(
                    {
                        "santral": r.ad,
                        "turbin_sayisi": len(k),
                        "turbin": r.turbin,
                        "ort_en_yakin_D": aralik,
                        "komsu_turbin": len(kom),
                        "model": model,
                        "TI": ti,
                        "ic_iz": float(1 - ref.E_ic.sum() / ref.E_serbest.sum()),
                        "dis_iz": float(1 - ref.E_toplam.sum() / ref.E_ic.sum()),
                        "gozlenen_kf": r.gozlenen_kf,
                    }
                )
                print(satir[-1], flush=True)
    out = pd.DataFrame(satir)
    (CIKTILAR / "v3D").mkdir(parents=True, exist_ok=True)
    out.to_csv(CIKTILAR / "v3D" / "D3_gercek_santral.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    print(out.pivot_table(index="santral", columns=["model", "TI"], values="ic_iz").round(3).to_string())


if __name__ == "__main__":
    main()
