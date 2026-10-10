"""
v3 E6 — Üç sahada Faz E öncesi/sonrası tam analiz ve süreler (2 çekirdek benzetimi, soğuk önbellek).

    once   : altyapi_maliyetleri=False (sabit 0,12 M$/MW bağlantı, lojistik CAPEX'te ortalama, CBS dışlaması yok) = ön adım sonrası
    sonra  : varsayılan (mesafeye bağlı bağlantı + sahaya göre lojistik farkı + teslim süresi COD'ye + CBS dışlamaları yerleşimde)
Hızlı tarama süresi de (soğuk/sıcak profil önbelleği) ölçülür.
Çıktılar: outputs/v3E/E6_once_sonra.csv, outputs/v3E/E6_sureler.csv
Çalıştırma: .venv/bin/python src/v3_E6_once_sonra.py
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, KOK

EK = """
a = s.saha.get("altyapi") or {}
bg, lj = a.get("baglanti") or {}, a.get("lojistik") or {}
out.update({"baglanti_musd": (bg.get("toplam_usd") or 0) / 1e6 if bg else None, "trafo": (bg.get("hedef_trafo") or {}).get("ad"),
            "trafo_km": (bg.get("hedef_trafo") or {}).get("km"), "lojistik_usd_mw": lj.get("usd_mw"), "teslim_ay": lj.get("teslim_ay"),
            "gecikme_ay": lj.get("gecikme_ay"), "uygun_oran": (a.get("alan") or {}).get("uygun_oran")})
print("SONUC" + json.dumps(out, default=float))
"""


def main() -> None:
    sp = importlib.util.spec_from_file_location("d3", KOK / "src" / "v3_D3_once_sonra.py")
    d3 = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(d3)
    d3.ALT = d3.ALT.replace('print("SONUC" + json.dumps(out, default=float))\n', EK.replace("{", "{{").replace("}", "}}"))
    tam, sure = [], []
    for ad, e, b in d3.SAHALAR:
        for kip, kv in (("once", "altyapi_maliyetleri=False"), ("sonra", "")):
            x = d3.calistir("tam", kip, ad, e, b, ("tablolar", "sonuc", "rapor"), kv)
            if x:
                tam.append({"kip": kip, "saha": ad, **x})
                sure.append({"mod": "tam", "kip": kip, "saha": ad, "duvar_s": x["duvar_s"]})
                print(
                    kip,
                    ad,
                    {
                        k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in x.items()
                        if not k.startswith(("adim_", "yekdem", "tuccar", "ppa"))
                    },
                    flush=True,
                )
        for sicak in (False, True):
            h = d3.calistir("hizli", "sonra", ad, e, b, ("sonuc",) if sicak else ("sonuc", "profil"), "")
            if h:
                sure.append({"mod": "hizli", "kip": "sonra", "saha": ad, "profil_onbellegi": sicak, "duvar_s": h["duvar_s"]})
                print("hızlı", ad, "sıcak" if sicak else "soğuk", round(h["duvar_s"], 1), flush=True)
    (CIKTILAR / "v3E").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(tam).to_csv(CIKTILAR / "v3E" / "E6_once_sonra.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    pd.DataFrame(sure).to_csv(CIKTILAR / "v3E" / "E6_sureler.csv", index=False, encoding="utf-8-sig", float_format="%.2f")


if __name__ == "__main__":
    main()
