"""
v2 B5-1 — Ezine regresyonu: tam analiz (kalibre mod) v1.0.0 nihai baz vakasına tolerans içinde yakınsıyor mu?

Kalibre mod: CDS ERA5 + v1 ay × saat matrisi, v1 türbini (E-141/120 m), türbin yerleşimi kapalı, v1 nihai tasarımı
(RES 58,8 + 30 MW / 60 MWh, SFK), inşaata hazır proje, v1 ızgarasıyla çalışma anı işletme tabloları.
Bilinen farklar (docs/v2_B_analiz_motoru.md): simülasyon sayısı yakınsamayla seçilir (v1 10.000); COD simülasyon başına
takvim dağılımından çekilir (v1 P50 gecikmesi 1,83 yıl, sabit); COD > 2030 olan simülasyonlarda YEKDEM yok.

Çalıştırma: MOTOR_CEKIRDEK=2 .venv/bin/python src/v2_B5_regresyon.py   → outputs/v2B/B5_regresyon.csv
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR
from src.motor import KullaniciVarsayimlari, analiz_et
from src.saha import ezine

V1 = {
    "yekdem_opsiyon": (-1.659, 42.40, -28.02),
    "tuccar": (-2.111, 41.98, -30.36),
    "ppa": (-6.050, 28.01, -26.01),
}  # outputs/07/baz_vaka.csv


def main() -> pd.DataFrame:
    kv = KullaniciVarsayimlari(
        kalibrasyon="v1",
        ruzgar_kaynagi="cds",
        turbin_yerlesimi=False,
        turbin="E-141/4200",
        gobek=120,
        sabit_tasarim={"res_mw": 58.8, "ges_mw": 0.0, "bess_mw": 30.0, "bess_mwh": 60.0},
        proje_asamasi="insaata_hazir",
    )
    t0 = time.time()
    s = analiz_et(ezine(), "tam", kv, lambda o, m: print(f"  {o:.0%} {m}", flush=True), onbellek_kullan=False, zaman_asimi=7200)
    gy = s.tablolar["gelir_yapilari"]
    satir = []
    for y, (e1, p1, c1) in V1.items():
        r = gy.loc[y]
        satir.append(
            {
                "yapi": y,
                "v1_E[NPV]": e1,
                "v2_E[NPV]": r["e_npv"],
                "fark": r["e_npv"] - e1,
                "v2_se": r["se"],
                "v1_P>0_%": p1,
                "v2_P>0_%": 100 * r["p_pozitif"],
                "v1_CVaR5": c1,
                "v2_CVaR5": r["cvar5"],
                "n": r["n"],
            }
        )
    df = pd.DataFrame(satir)
    (CIKTILAR / "v2B").mkdir(parents=True, exist_ok=True)
    df.to_csv(CIKTILAR / "v2B" / "B5_regresyon.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    (CIKTILAR / "v2B" / "B5_regresyon_sure.json").write_text(
        json.dumps({"toplam_s": time.time() - t0, **{k: v for k, v in s.sure_s.items() if isinstance(v, float)}})
    )
    print(df.round(2).to_string(index=False))
    print("karar:", s.ozet["karar"]["tr"], "| süre", round(time.time() - t0), "s")
    return df


if __name__ == "__main__":
    main()
