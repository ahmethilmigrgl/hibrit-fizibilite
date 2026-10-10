"""
v3 F ön adım Ö2 — Bağlantı mesafesi belirsizliğinin üç sahada etkisi (tam analiz, 2 çekirdek, soğuk önbellek).

Öncesi: outputs/v3E/E6_once_sonra.csv "sonra" satırları (Faz E: en yakın trafo, sabit hat uzunluğu). Sonrası: şebeke CAPEX
beklenen değerle, Monte Carlo'da her senaryoda hat uzunluğu × r (ln r ~ N(μ, σ), data/atlas/baglanti_orani.json).
Çıktı: outputs/v3F/O2_once_sonra.csv
Çalıştırma: .venv/bin/python src/v3_O2_once_sonra.py
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, KOK

EK = """
a = s.saha.get("altyapi") or {}
bg = a.get("baglanti") or {}
bel = bg.get("belirsizlik") or {}
out.update({"baglanti_musd": (bel.get("beklenen_usd") or bg.get("toplam_usd") or 0) / 1e6, "baglanti_p10_musd": (bel.get("p10_usd") or 0) / 1e6,
            "baglanti_p90_musd": (bel.get("p90_usd") or 0) / 1e6, "p10": o["baz"].get("p10"), "p90": o["baz"].get("p90")})
print("SONUC" + json.dumps(out, default=float))
"""


def main() -> None:
    sp = importlib.util.spec_from_file_location("d3", KOK / "src" / "v3_D3_once_sonra.py")
    d3 = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(d3)
    d3.ALT = d3.ALT.replace('print("SONUC" + json.dumps(out, default=float))\n', EK.replace("{", "{{").replace("}", "}}"))
    once = pd.read_csv(CIKTILAR / "v3E" / "E6_once_sonra.csv")
    once = once[once["kip"] == "sonra"].assign(kip="öncesi (en yakın trafo)")
    sonra = []
    for ad, e, b in d3.SAHALAR:
        x = d3.calistir("tam", "sonra", ad, e, b, ("tablolar", "sonuc", "rapor"), "")
        if x:
            sonra.append({"kip": "sonrası (mesafe belirsizliği)", "saha": ad, **x})
            print(
                ad,
                {
                    k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in x.items()
                    if k
                    in (
                        "res_mw",
                        "e_npv",
                        "p_pozitif",
                        "cvar5",
                        "basabas",
                        "karar",
                        "baglanti_musd",
                        "baglanti_p10_musd",
                        "baglanti_p90_musd",
                        "duvar_s",
                    )
                },
                flush=True,
            )
    d = pd.concat([once, pd.DataFrame(sonra)], ignore_index=True)
    (CIKTILAR / "v3F").mkdir(parents=True, exist_ok=True)
    d.to_csv(CIKTILAR / "v3F" / "O2_once_sonra.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    print(
        d[["saha", "kip", "res_mw", "N", "baglanti_musd", "e_npv", "p_pozitif", "cvar5", "basabas", "karar", "duvar_s"]]
        .round(3)
        .to_string()
    )


if __name__ == "__main__":
    main()
