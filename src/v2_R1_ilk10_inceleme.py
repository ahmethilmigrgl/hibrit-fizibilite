"""
v2 Revizyon R1 — Ön tarama ilk 10 hücresinin ve bölge hücrelerinin tanısı.

Her hücre (temsilî nokta) için: GWA (nokta ve 2 km yerleşim), ERA5 100 m hızı, c = GWA/ERA5, sahanın rakım/kıyı/karmaşıklığı,
komşu santraller (mesafe, rakım, kıyıya uzaklık, karmaşıklık, R = K/c, gözlenen KF, türbin), aktarılan K ve hücre KF'si.
Çıktı: outputs/v2R/R1_hucreler.csv, R1_komsular.csv
Çalıştırma: .venv/bin/python src/v2_R1_ilk10_inceleme.py [--bolge trakya|balikesir_biga|ilk10]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src import veri_katmani
from src.atlas import aktarim
from src.ayarlar import CIKTILAR, config_oku
from src.kaynaklar import era5_grid

CIKTI = CIKTILAR / "v2R"
BOLGE = {
    "trakya": (40.8, 42.1, 26.0, 29.0),
    "balikesir_biga": (39.3, 40.5, 26.0, 28.6),
}


def hucre_tanisi(r, cfg: dict) -> tuple[dict, list[dict]]:
    from src.saha import gwa_hizi, saha_olustur

    e, b = float(r.enlem), float(r.boylam)
    s = saha_olustur("tani", e, b)
    g = gwa_hizi(s, cfg)
    z = era5_grid.ac(veri_katmani.yol(f"grid/era5_tr/v1/{era5_grid.dosya_adi(e, b)}"))
    v100 = float(z["u100"].mean())
    tan = aktarim.tanimlayicilar(e, b)
    k = aktarim.komsular(e, b, tan, cfg)
    df, mat = aktarim.atlas()
    ci = aktarim.santral_c()
    K, bilgi = aktarim.tahmin(e, b, v100, "gwa_olcekli", cfg, gwa_hiz=g["hiz"], tan=tan)
    kom = []
    for x in k.itertuples():
        i = int(x.epias_id)
        a = df.set_index("epias_id").loc[i]
        kom.append(
            {
                "hucre": f"{r.hucre_enlem:.2f}_{r.hucre_boylam:.2f}",
                "komsu": x.ad,
                "mesafe_km": x.mesafe_km,
                "komsu_rakim": a["rakim_m"],
                "komsu_kiyi_km": a["kiyi_km"],
                "komsu_karmasiklik": a["karmasiklik"],
                "komsu_gwa_turbin": a["gwa_turbin"],
                "komsu_era5": a["era5_100m"],
                "komsu_c": ci[i],
                "komsu_K_ort": float(mat[i].mean()),
                "komsu_R": float(mat[i].mean() / ci[i]),
                "komsu_gozlenen_kf": a["gozlenen_kf"],
                "komsu_turbin": f"{a['turbin']} @ {a['gobek']:.0f}",
            }
        )
    return (
        {
            "hucre": f"{r.hucre_enlem:.2f}_{r.hucre_boylam:.2f}",
            "il_ilce": f"{r.il} / {r.ilce}",
            "nokta": f"{e:.3f}, {b:.3f}",
            "rakim_m": tan["rakim_m"],
            "kiyi_km": tan["kiyi_km"],
            "karmasiklik": tan["karmasiklik"],
            "gwa_nokta": g["nokta"],
            "gwa_yerlesim": g["hiz"],
            "era5_100m": v100,
            "c_saha": g["hiz"] / v100,
            "R_aktarilan": float(K.mean()) / (g["hiz"] / v100),
            "K_ort": float(K.mean()),
            "guven": bilgi["guven"],
            "komsu_sayisi": len(k),
            "res_kf_%": 100 * r.res_kf,
            "basabas_en_iyi": r.basabas_en_iyi,
        },
        kom,
    )


def main() -> None:
    bolge = sys.argv[sys.argv.index("--bolge") + 1] if "--bolge" in sys.argv else "ilk10"
    cfg = config_oku()
    ot = pd.read_parquet(veri_katmani.yol("atlas/on_tarama.parquet"))
    ot = ot[ot["hata"] == ""]
    if bolge == "ilk10":
        sec = ot.nsmallest(10, "basabas_en_iyi")
    else:
        e0, e1, b0, b1 = BOLGE[bolge]
        sec = ot[ot["hucre_enlem"].between(e0, e1) & ot["hucre_boylam"].between(b0, b1)].sort_values("basabas_en_iyi")
    h, k = [], []
    for r in sec.itertuples():
        a, b = hucre_tanisi(r, cfg)
        h.append(a)
        k.extend(b)
    H, Kd = pd.DataFrame(h), pd.DataFrame(k)
    CIKTI.mkdir(parents=True, exist_ok=True)
    H.to_csv(CIKTI / f"R1_{bolge}_hucreler.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    Kd.to_csv(CIKTI / f"R1_{bolge}_komsular.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.set_option("display.width", 250)
    print(H.round(3).to_string(index=False))
    print(Kd.round(3).to_string(index=False))
    # bölgedeki santraller
    df, _ = aktarim.atlas()
    if bolge in BOLGE:
        e0, e1, b0, b1 = BOLGE[bolge]
        s = df[df["enlem"].between(e0, e1) & df["boylam"].between(b0, b1)]
        print(
            s[["ad", "enlem", "boylam", "rakim_m", "kiyi_km", "karmasiklik", "gwa_turbin", "gozlenen_kf", "turbin", "gobek"]]
            .round(3)
            .to_string(index=False)
        )
    print("ulusal medyan R:", round(float(np.median(aktarim.ulusal_artik())), 3))


if __name__ == "__main__":
    main()
