"""
v3 kapanış — ERA5 yön gridi paketlendikten sonra Faz D kontrolü: Ezine, Gürün, Susurluk tam analizi (2 çekirdek, soğuk
önbellek) önceki sonuçla (outputs/v3F/O2_once_sonra.csv "sonrası": santral hücresi ham ERA5 yönü) karşılaştırılır.
Çıktı: outputs/v3G/G3_yon_grid_kontrol.csv
Çalıştırma: .venv/bin/python src/v3_G3_yon_grid_kontrol.py
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, KOK


def main() -> None:
    sp = importlib.util.spec_from_file_location("d3", KOK / "src" / "v3_D3_once_sonra.py")
    d3 = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(d3)
    once = pd.read_csv(CIKTILAR / "v3F" / "O2_once_sonra.csv")
    once = once[once["kip"].str.startswith("sonrası")]
    kol = ["res_mw", "N", "ic_iz", "konum_kazanci", "verim", "e_npv", "p_pozitif", "basabas", "karar"]
    satir = []
    for ad, e, b in d3.SAHALAR:
        x = d3.calistir("tam", "sonra", ad, e, b, ("tablolar", "sonuc", "rapor"), "")
        o = once[once["saha"] == ad].iloc[0]
        for k in kol:
            satir.append({"saha": ad, "olcu": k, "once_yon_hucre": o[k], "sonra_yon_grid": x[k] if x else None})
        print(ad, {k: (o[k], x[k]) for k in kol} if x else "HATA", flush=True)
    d = pd.DataFrame(satir)
    (CIKTILAR / "v3G").mkdir(parents=True, exist_ok=True)
    d.to_csv(CIKTILAR / "v3G" / "G3_yon_grid_kontrol.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
