"""
v2 Revizyon R5 — Tam analiz hızlandırmasının öncesi/sonrası (2 çekirdek benzetimi, soğuk işletme tabloları).

Önce: Pyomo işletme LP'si (MOTOR_LP=pyomo) + tam yıl MILP (MOTOR_TAM_MILP=tamyil; 240 s sınırı).
Sonra: highspy işletme LP'si (aynı formülasyon, sıcak başlangıç) + 96 temsilî günlük MILP (config v2.motor.tam_milp_temsili_gun).
Her çalıştırma ayrı alt süreçte (ortam değişkenleri + temiz önbellek). Sonuçlar: adım süreleri, tasarım, gelir yapılarının
E[NPV]/P(NPV>0)/CVaR5, başabaş fiyatı, karar.
Çıktı: outputs/v2R/R5_tam_hiz.csv
Çalıştırma: .venv/bin/python src/v2_R5_tam_hiz.py [--sadece sonra]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import os
import shutil
import subprocess

import pandas as pd

from src.ayarlar import CIKTILAR, KOK

SAHALAR = [("Çanakkale-Ezine", 39.79, 26.33), ("Sivas-Gürün", 38.92, 37.42), ("Balıkesir-Susurluk", 39.85, 28.15)]
MODLAR = {"once": {"MOTOR_LP": "pyomo", "MOTOR_TAM_MILP": "tamyil"}, "sonra": {"MOTOR_LP": "highspy", "MOTOR_TAM_MILP": "temsili"}}
ALT = """
import json, sys, time
sys.path.insert(0, {kok!r})
from src.motor import analiz_et, KullaniciVarsayimlari
t0 = time.time()
s = analiz_et({{"ad": {ad!r}, "enlem": {e}, "boylam": {b}}}, "tam", KullaniciVarsayimlari(), onbellek_kullan=False, zaman_asimi=3600)
o = s.ozet
gy = s.tablolar["gelir_yapilari"]
print("SONUC" + json.dumps({{
    "duvar_s": time.time() - t0,
    **{{f"adim_{{k}}": v for k, v in s.sure_s.items() if isinstance(v, float)}},
    "res_mw": o["tasarim"]["res_mw"], "ges_mw": o["tasarim"]["ges_mw"], "bess_mw": o["tasarim"]["bess_mw"], "bess_mwh": o["tasarim"]["bess_mwh"],
    "milp_npv": o["milp"].get("NPV tahmini [M USD]"),
    **{{f"{{y}}_e_npv": float(gy.loc[y, "e_npv"]) for y in gy.index}},
    **{{f"{{y}}_p_poz": float(gy.loc[y, "p_pozitif"]) for y in gy.index}},
    **{{f"{{y}}_cvar5": float(gy.loc[y, "cvar5"]) for y in gy.index}},
    "se": o["baz"]["se"], "n": o["baz"]["n"],
    "basabas": o["basabas_fiyat"], "karar": o["karar"]["karar"],
}}, default=float))
"""


def main() -> None:
    modlar = [sys.argv[sys.argv.index("--sadece") + 1]] if "--sadece" in sys.argv else list(MODLAR)
    yol = CIKTILAR / "v2R" / "R5_tam_hiz.csv"
    satir = pd.read_csv(yol).to_dict("records") if yol.exists() and "--sadece" in sys.argv else []
    satir = [r for r in satir if r["mod"] not in modlar]
    for mod in modlar:
        for ad, e, b in SAHALAR:
            for d in ("tablolar", "sonuc", "rapor"):
                shutil.rmtree(KOK / "data" / "onbellek" / d, ignore_errors=True)
            env = {**os.environ, "MOTOR_CEKIRDEK": "2", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", **MODLAR[mod]}
            kod = ALT.format(kok=str(KOK), ad=ad, e=e, b=b)
            r = subprocess.run([str(KOK / ".venv" / "bin" / "python"), "-c", kod], env=env, capture_output=True, text=True, timeout=7200)
            sat = next((x for x in r.stdout.splitlines() if x.startswith("SONUC")), None)
            if sat is None:
                print(mod, ad, "HATA", r.stderr[-800:], flush=True)
                continue
            satir.append({"mod": mod, "saha": ad, **json.loads(sat[5:])})
            print(
                mod,
                ad,
                {k: (round(v, 2) if isinstance(v, float) else v) for k, v in satir[-1].items() if k not in ("mod", "saha")},
                flush=True,
            )
            (CIKTILAR / "v2R").mkdir(parents=True, exist_ok=True)
            pd.DataFrame(satir).to_csv(yol, index=False, encoding="utf-8-sig", float_format="%.4f")


if __name__ == "__main__":
    main()
