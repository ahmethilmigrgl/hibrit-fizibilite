"""
Nihai baz vaka (config.yaml → nihai_baz_vaka): tüm ana sayıların tek kaynağı.

Monte Carlo (doyum + sistem kesintisi + takvim kayması) dağılımlarından, nihai tasarım ve COD için: E[NPV], P(NPV>0),
CVaR %5, P10/P90 ve azami edinim primi (= max(E[NPV], 0)). Edinim primi parametresi NPV'den düşülür.
Girdi: outputs/07/gelir_yapilari_npv_erteleme.npz, gelir_yapilari_metrikler.csv (src/07_gelir_yapilari.py).
Çıktı: outputs/07/baz_vaka.csv, results/baz_vaka.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger

CIKTI = CIKTILAR / "07"
YAPILAR = {"yekdem_nominal": ("GY", "YEKDEM, nominal koridor (baz vaka)"), "yekdem_endeksli": ("GYe", "YEKDEM, endeksli koridor"),
           "ppa": ("GP", "PPA (%70 P90, 12 yıl)"), "tuccar": ("G", "Tüccar")}


def main():
    cfg = config_oku()
    b = deger(cfg["nihai_baz_vaka"])
    k, prim = int(b["erteleme_yil"]), float(b["edinim_primi_musd"])
    z = np.load(CIKTI / "gelir_yapilari_npv_erteleme.npz")
    met = pd.read_csv(CIKTI / "gelir_yapilari_metrikler.csv").set_index("Seçenek")
    satir = []
    for anahtar in [b["gelir_yapisi"]] + list(b["karsilastirma"]):
        kod, ad = YAPILAR[anahtar]
        x = z[f"{kod}_k{k}"].astype(float) - prim
        kotu = np.sort(x)[: int(0.05 * len(x))]
        m = met[met.index.str.startswith(f"{kod}:")].iloc[0]
        satir.append({"Senaryo": ad, "Baz vaka": anahtar == b["gelir_yapisi"], "COD": b["cod"],
                      "Beklenen NPV [M USD]": x.mean(), "P(NPV > 0) [%]": 100 * (x > 0).mean(), "CVaR %5 [M USD]": kotu.mean(),
                      "NPV P10 [M USD]": np.percentile(x, 10), "NPV P90 [M USD]": np.percentile(x, 90),
                      "Azami edinim primi [M USD]": max(x.mean() + prim, 0.0),
                      "E[NPV], COD 2028 (model takvimi) [M USD]": float(z[f"{kod}_k0"].mean()) - prim,
                      "Borç kapasitesi, muhafazakâr [M USD]": m["Borç kapasitesi, muhafazakâr [M USD]"],
                      "P(DSCR < 1), muhafazakâr borç [%] (COD 2028)": m["P(DSCR < 1), muhafazakâr borç [%]"],
                      "SFK geliri, ilk 10 yıl [M USD/yıl]": m["SFK geliri, ilk 10 yıl [M USD/yıl]"]})
    df = pd.DataFrame(satir)
    df.to_csv(CIKTI / "baz_vaka.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    (KOK / "results").mkdir(exist_ok=True)
    df.to_csv(KOK / "results" / "baz_vaka.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    pd.set_option("display.width", 250)
    print(df.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
