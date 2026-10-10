"""
v3 F ön adım Ö1 — v2 motorunda sigorta + arazi çift sayımı: v2 kipinde (yerlesim_bakim=False: RES O&M config'teki
35.000 $/MW-yıl + ayrıca sigorta ve arazi) üç sahada tam analiz, çift sayımlı ve düzeltilmiş (V1_CIFT_SAYIM=1).
v3 varsayılanında (FSA 20 + sahip kalemleri 14, aşağıdan yukarı; sigorta/arazi kapsam dışı) çift sayım yoktur.
Çıktı: outputs/v3F/O1_v2_kontrol.csv
Çalıştırma: .venv/bin/python src/v3_O1_v2_kontrol.py
"""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, KOK


def main() -> None:
    sp = importlib.util.spec_from_file_location("d3", KOK / "src" / "v3_D3_once_sonra.py")
    d3 = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(d3)
    satir = []
    for ad, e, b in d3.SAHALAR:
        for kip, ortam in (("v2 (çift sayımlı)", "0"), ("v2 düzeltilmiş", "1")):
            os.environ["V1_CIFT_SAYIM"] = ortam
            x = d3.calistir("tam", "once", ad, e, b, ("tablolar", "sonuc", "rapor"), "yerlesim_bakim=False, altyapi_maliyetleri=False")
            if x:
                satir.append({"saha": ad, "kip": kip, **{k: x[k] for k in ("res_mw", "bess_mw", "e_npv", "p_pozitif", "cvar5", "basabas", "karar")}})
                print(satir[-1], flush=True)
    os.environ.pop("V1_CIFT_SAYIM", None)
    (CIKTILAR / "v3F").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(satir).to_csv(CIKTILAR / "v3F" / "O1_v2_kontrol.csv", index=False, encoding="utf-8-sig", float_format="%.3f")


if __name__ == "__main__":
    main()
