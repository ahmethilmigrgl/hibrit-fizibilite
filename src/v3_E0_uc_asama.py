"""
v3 Ö4 — Üç sahada üç aşamalı karşılaştırma: Faz D öncesi (v2) / Faz D sonrası / ön adım (Ö1–Ö2) sonrası.

İlk iki aşama outputs/v3D/D3_once_sonra.csv'den ("once", "sonra"); üçüncüsü bu betikte aynı yöntemle (ayrı alt süreç,
2 çekirdek benzetimi, soğuk önbellek) yeniden çalıştırılır. Ayrıca ön adım sonrası kodla FSA yerine kendi bakımı
(isletme_modeli="kendi") duyarlılığı.
Çıktı: outputs/v3E/E0_uc_asama.csv
Çalıştırma: .venv/bin/python src/v3_E0_uc_asama.py
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
    eski = pd.read_csv(CIKTILAR / "v3D" / "D3_once_sonra.csv")
    eski = eski[eski["kip"].isin(["once", "sonra"])].assign(
        asama=lambda x: x["kip"].map({"once": "1 Faz D öncesi (v2)", "sonra": "2 Faz D sonrası"})
    )
    yeni = []
    for ad, e, b in d3.SAHALAR:
        for asama, kv in (("3 Ön adım sonrası (FSA)", ""), ("3b Ön adım sonrası, kendi bakımı", 'isletme_modeli="kendi"')):
            x = d3.calistir("tam", "on_adim", ad, e, b, ("tablolar", "sonuc", "rapor"), kv)
            if x:
                yeni.append({"kip": "on_adim", "asama": asama, "saha": ad, **x})
                print(
                    asama,
                    ad,
                    {
                        k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in x.items()
                        if k
                        in (
                            "res_mw",
                            "N",
                            "e_npv",
                            "basabas",
                            "karar",
                            "isletme_usd_mw_yil",
                            "kullanilabilirlik",
                            "kayip_toplam",
                            "duvar_s",
                        )
                    },
                    flush=True,
                )
    out = pd.concat([eski, pd.DataFrame(yeni)], ignore_index=True).sort_values(["saha", "asama"])
    (CIKTILAR / "v3E").mkdir(parents=True, exist_ok=True)
    out.to_csv(CIKTILAR / "v3E" / "E0_uc_asama.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    print(
        out[
            [
                "saha",
                "asama",
                "res_mw",
                "bess_mw",
                "N",
                "om_usd_mw_yil",
                "isletme_usd_mw_yil",
                "kullanilabilirlik",
                "e_npv",
                "p_pozitif",
                "basabas",
                "karar",
            ]
        ]
        .round(3)
        .to_string()
    )


if __name__ == "__main__":
    main()
