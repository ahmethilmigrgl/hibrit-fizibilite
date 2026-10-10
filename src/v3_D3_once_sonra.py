"""
v3 D3 — Yerleşim ve bakım eklenmesinin tasarıma, E[NPV]'ye ve karara etkisi (önce/sonra) ve 2 çekirdekte yeni süreler.

Önce : KullaniciVarsayimlari(yerlesim_bakim=False) — v2 davranışı (toplu %12 kayıp, sabit OPEX 35.000 $/MW-yıl)
Sonra: varsayılan — iz kaybı (yerleşim optimizasyonu, komşu santraller) + bakım DES'i (kullanılabilirlik, O&M)
Sonra (sabit O&M): yerleşim açık, bakım modeli "sabit" (v1 OPEX 35.000 $/MW-yıl, kalibrasyondaki kullanılabilirlik) —
O&M modeli farkına duyarlılık
Sonra (v2 tasarımı): v3 modelleri açık, tasarım "önce"nin seçtiği tasarıma sabit — tasarım değişimi ile aynı tasarımda
enerji/O&M etkisini ayırmak için
Sahalar: Ezine, Gürün, Susurluk. Her çalıştırma ayrı alt süreçte, 2 çekirdek benzetimi
(MOTOR_CEKIRDEK=2, OMP_NUM_THREADS=1, VECLIB_MAXIMUM_THREADS=1), soğuk işletme tabloları ve sonuç önbelleği.
Hızlı tarama: profil önbelleği sıcakken (uygulamadaki tipik durum) ve soğukken.
Çıktı: outputs/v3D/D3_once_sonra.csv, D3_sureler.csv
Çalıştırma: .venv/bin/python src/v3_D3_once_sonra.py [--kip once,sonra,sonra_sabit_om,sonra_v2_tasarim]
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
MODLAR = {"once": "yerlesim_bakim=False", "sonra": "", "sonra_sabit_om": 'bakim_modeli="sabit"', "sonra_v2_tasarim": None}
ALT = """
import json, sys, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, {kok!r})
from src.motor import analiz_et, KullaniciVarsayimlari
kv = KullaniciVarsayimlari({kv})
t0 = time.time()
s = analiz_et({{"ad": {ad!r}, "enlem": {e}, "boylam": {b}}}, {mod!r}, kv, onbellek_kullan=False, zaman_asimi=3600)
duvar = time.time() - t0
o = s.ozet
out = {{"duvar_s": duvar, **{{f"adim_{{k}}": v for k, v in s.sure_s.items() if isinstance(v, float)}}}}
if {mod!r} == "tam":
    gy = s.tablolar["gelir_yapilari"]
    y, bk = o.get("yerlesim") or {{}}, o.get("bakim") or {{}}
    out.update({{
        "res_mw": o["tasarim"]["res_mw"], "ges_mw": o["tasarim"]["ges_mw"], "bess_mw": o["tasarim"]["bess_mw"], "bess_mwh": o["tasarim"]["bess_mwh"],
        "res_kf": o["res_kf"], "p50_res_mwh_mw": o["p50_p90_mwh_per_mw"]["res"]["P50"], "p90_10y_res_mwh_mw": o["p50_p90_mwh_per_mw"]["res"]["P90_10y"],
        "milp_npv": o["milp"].get("NPV tahmini [M USD]"), "capex_musd": o["capex_musd"],
        **{{f"{{k}}_e_npv": float(gy.loc[k, "e_npv"]) for k in gy.index}}, **{{f"{{k}}_p_poz": float(gy.loc[k, "p_pozitif"]) for k in gy.index}},
        "en_iyi_yapi": o["en_iyi_yapi"], "e_npv": o["baz"]["e_npv"], "p_pozitif": o["baz"]["p_pozitif"], "cvar5": o["baz"]["cvar5"],
        "basabas": o["basabas_fiyat"], "karar": o["karar"]["karar"],
        "kullanilabilirlik": o.get("kullanilabilirlik"), "om_usd_mw_yil": o.get("om_usd_mw_yil"),
        "N": y.get("N"), "ic_iz": y.get("ic_iz"), "dis_iz": y.get("dis_iz"), "konum_kazanci": y.get("konum_kazanci"), "verim": y.get("verim"),
        "yerlesim_yontemi": y.get("yontem_kodu"), "bakim_strateji": bk.get("strateji"),
        "cizelge_kazanc": (bk.get("cizelge") or {{}}).get("kazanc_bahar"),
    }})
else:
    out.update({{"res_kf": o["res_kf"], "milp_res": o["milp"].get("RES [MW]"), "milp_npv": o["milp"].get("NPV tahmini [M USD]"),
                 "basabas_en_iyi": o.get("basabas_en_iyi")}})
print("SONUC" + json.dumps(out, default=float))
"""


def calistir(mod: str, kip: str, ad: str, e: float, b: float, temizle: tuple, kv: str | None = None) -> dict | None:
    for d in temizle:
        shutil.rmtree(KOK / "data" / "onbellek" / d, ignore_errors=True)
    env = {**os.environ, "MOTOR_CEKIRDEK": "2", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    kod = ALT.format(kok=str(KOK), ad=ad, e=e, b=b, mod=mod, kv=kv if kv is not None else MODLAR[kip])
    r = subprocess.run([str(KOK / ".venv" / "bin" / "python"), "-c", kod], env=env, capture_output=True, text=True, timeout=7200)
    sat = next((x for x in r.stdout.splitlines() if x.startswith("SONUC")), None)
    if sat is None:
        print(mod, kip, ad, "HATA", r.stderr[-1500:], flush=True)
        return None
    return json.loads(sat[5:])


def main() -> None:
    CIKTI = CIKTILAR / "v3D"
    CIKTI.mkdir(parents=True, exist_ok=True)
    kipler = sys.argv[sys.argv.index("--kip") + 1].split(",") if "--kip" in sys.argv else list(MODLAR)
    y1, y2 = CIKTI / "D3_once_sonra.csv", CIKTI / "D3_sureler.csv"
    tam = [r for r in (pd.read_csv(y1).to_dict("records") if y1.exists() else []) if r["kip"] not in kipler]
    sure = [r for r in (pd.read_csv(y2).to_dict("records") if y2.exists() else []) if r["kip"] not in kipler]
    for ad, e, b in SAHALAR:
        for kip in kipler:
            kv = None
            if kip == "sonra_v2_tasarim":
                o = next(r for r in tam if r["kip"] == "once" and r["saha"] == ad)
                kv = "sabit_tasarim=" + repr({k: float(o[k]) for k in ("res_mw", "ges_mw", "bess_mw", "bess_mwh")})
            x = calistir("tam", kip, ad, e, b, ("tablolar", "sonuc", "rapor"), kv)
            if x:
                tam.append({"kip": kip, "saha": ad, **x})
                sure.append(
                    {"mod": "tam", "kip": kip, "saha": ad, "duvar_s": x["duvar_s"], **{k: v for k, v in x.items() if k.startswith("adim_")}}
                )
                print(
                    "tam",
                    kip,
                    ad,
                    {k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items() if not k.startswith("adim_")},
                    flush=True,
                )
            for sicak in (False, True) if kip in ("once", "sonra") else ():
                h = calistir("hizli", kip, ad, e, b, ("sonuc",) if sicak else ("sonuc", "profil"))
                if h:
                    sure.append(
                        {
                            "mod": "hizli",
                            "kip": kip,
                            "saha": ad,
                            "profil_onbellegi": sicak,
                            "duvar_s": h["duvar_s"],
                            **{k: v for k, v in h.items() if k.startswith("adim_")},
                        }
                    )
                    print("hızlı", kip, ad, "sıcak" if sicak else "soğuk", round(h["duvar_s"], 1), flush=True)
            pd.DataFrame(tam).to_csv(y1, index=False, encoding="utf-8-sig", float_format="%.4f")
            pd.DataFrame(sure).to_csv(y2, index=False, encoding="utf-8-sig", float_format="%.2f")


if __name__ == "__main__":
    main()
