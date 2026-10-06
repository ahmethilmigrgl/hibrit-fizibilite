"""
v2 B5 — Analiz motoru doğrulaması:
  (2) hızlı tarama ile tam analizin tutarlılığı (Ezine, Sivas-Gürün, Balıkesir-Susurluk)
  (3) beş farklı karakterde sahada hızlı tarama (kıyı rüzgârlı, iç Anadolu rüzgârlı, güneşli güney, düşük rüzgârlı, dağlık)
  (4) süre ölçümleri: 2 çekirdek simülasyonu (süreç havuzu 2, BLAS/OpenMP tek iş parçacığı), soğuk / ılık / sıcak önbellek
Çalıştırma: MOTOR_CEKIRDEK=2 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python src/v2_B5_dogrulama.py [tutarlilik|tarama|sure]
Çıktı: outputs/v2B/B5_*.csv
"""

import os
import resource
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, HAM_VERI
from src.motor import KullaniciVarsayimlari, analiz_et, ortak, tablolar

CIKTI = CIKTILAR / "v2B"
TUTARLILIK = [("Çanakkale-Ezine", 39.79, 26.33), ("Sivas-Gürün", 38.92, 37.42), ("Balıkesir-Susurluk", 39.85, 28.15)]
BES_SAHA = [
    ("Kıyı rüzgârlı: İzmir-Karaburun", 38.63, 26.51),
    ("İç Anadolu rüzgârlı: Sivas-Kangal", 39.08, 37.40),
    ("Güneşli güney: Karaman", 37.18, 33.22),
    ("Düşük rüzgârlı: Ankara-Polatlı", 39.58, 32.15),
    ("Dağlık: Erzurum-Palandöken", 39.86, 41.27),
]


def cpu() -> float:
    r, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime + c.ru_utime + c.ru_stime


def calis(ad, e, b, mod, kv=None, onbellek=False):
    c0, t0 = cpu(), time.perf_counter()
    s = analiz_et({"ad": ad, "enlem": e, "boylam": b}, mod, kv or KullaniciVarsayimlari(), onbellek_kullan=onbellek)
    return s, time.perf_counter() - t0, cpu() - c0


def tutarlilik() -> pd.DataFrame:
    satir = []
    for ad, e, b in TUTARLILIK:
        h, th, _ = calis(ad, e, b, "hizli")
        t, tt, _ = calis(ad, e, b, "tam")
        hm, to = h.ozet["milp"], t.ozet
        tas = h.tablolar["tasarimlar"].set_index("tasarim")
        satir.append(
            {
                "saha": ad,
                "guven": h.ozet["guven"]["seviye"],
                "hizli_tasarim": f"RES {hm['RES [MW]']:.1f} / GES {hm['GES [MWac]']:.0f} / BESS {hm['BESS [MW]']:.0f}/{hm['BESS [MWh]']:.0f}",
                "tam_tasarim": f"RES {to['tasarim']['res_mw']:.1f} / GES {to['tasarim']['ges_mw']:.0f} / BESS {to['tasarim']['bess_mw']:.0f}/{to['tasarim']['bess_mwh']:.0f}",
                "hizli_optimum_npv_deterministik": hm["NPV tahmini [M USD]"],
                "tam_milp_npv_deterministik": to["milp"].get("NPV tahmini [M USD]"),
                "hizli_en_iyi_standart": tas["npv_musd"][~tas.index.str.startswith("Optimum")].idxmax(),
                "hizli_karar": h.ozet["en_iyi_tasarim"],
                "tam_yedek_tasarim": to.get("yedek_tasarim"),
                "tam_E[NPV]_en_iyi_yapi": to["baz"]["e_npv"],
                "tam_en_iyi_yapi": to["en_iyi_yapi"],
                "tam_karar": to["karar"]["karar"],
                "hizli_s": th,
                "tam_s": tt,
            }
        )
    df = pd.DataFrame(satir)
    df.to_csv(CIKTI / "B5_tutarlilik.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    print(df.round(2).T.to_string())
    return df


def tarama() -> pd.DataFrame:
    satir = []
    for ad, e, b in BES_SAHA:
        s, sure, _ = calis(ad, e, b, "hizli")
        o = s.ozet
        tas = s.tablolar["tasarimlar"].set_index("tasarim")
        satir.append(
            {
                "saha": ad,
                "il/ilçe": f"{s.saha['il']}/{s.saha['ilce']}",
                "tarife": s.saha["tarife_bolgesi"],
                "turbin": f"{s.saha['turbin']['turbin']}@{s.saha['turbin']['gobek']}",
                "gwa_100m": round(s.saha["turbin"]["gwa_100m"], 2),
                "guven": o["guven"]["seviye"],
                "res_kf_%": 100 * o["res_kf"],
                "ges_kf_%": 100 * o["ges_kf"],
                "res_yakalanma": o["yakalanma_res"],
                "ges_yakalanma": o["yakalanma_ges"],
                "lcoe_res": o["lcoe_res"],
                "lcoe_ges": o["lcoe_ges"],
                "basabas_res": o["basabas_res"],
                "basabas_ges": o["basabas_ges"],
                "npv_RES": tas.loc["RES", "npv_musd"] if "RES" in tas.index else None,
                "npv_GES": tas.loc["GES", "npv_musd"],
                "npv_RES+GES": tas.loc["RES + GES", "npv_musd"] if "RES + GES" in tas.index else None,
                "optimum": f"RES {o['milp']['RES [MW]']:.0f}/GES {abs(o['milp']['GES [MWac]']):.0f}/BESS {o['milp']['BESS [MW]']:.0f}",
                "karar": o["en_iyi_tasarim"],
                "optimum_npv": o["milp"]["NPV tahmini [M USD]"],
                "uyarilar": "; ".join(u["kod"] for u in s.uyarilar),
                "sure_s": sure,
            }
        )
    df = pd.DataFrame(satir)
    df.to_csv(CIKTI / "B5_bes_saha.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    print(df.round(2).T.to_string())
    return df


def sure() -> pd.DataFrame:
    """Taze bir sahada (önbelleği olmayan): soğuk (tüm indirmeler + tablolar), ılık (profil/tablo önbellekte), sıcak (sonuç önbelleği)."""
    ad, e, b = "Süre ölçümü: Çanakkale-Bozcaada karşısı (Geyikli)", 39.80, 26.18
    for d in (ortak.PROFIL_ONBELLEK, tablolar.KLASOR):
        if d.exists():
            shutil.rmtree(d)
    for p in list((HAM_VERI / "pvgis").glob("*geyikli*")) + list((HAM_VERI / "open_meteo").glob("om_era5_39.8000_26.1800*")):
        p.unlink()
    satir = []
    for mod in ("hizli", "tam"):
        for etiket, onb in (("soğuk", False), ("ılık", False), ("sıcak (sonuç önbelleği)", True)):
            if etiket.startswith("sıcak"):
                calis(ad, e, b, mod, onbellek=True)  # önbelleğe yaz
            s, t, c = calis(ad, e, b, mod, onbellek=onb)
            satir.append(
                {
                    "mod": mod,
                    "durum": etiket,
                    "duvar_s": t,
                    "cpu_s": c,
                    **{f"adim_{k}": v for k, v in s.sure_s.items() if isinstance(v, float)},
                }
            )
            print(satir[-1], flush=True)
    df = pd.DataFrame(satir)
    df.to_csv(CIKTI / "B5_sure.csv", index=False, encoding="utf-8-sig", float_format="%.1f")
    return df


if __name__ == "__main__":
    CIKTI.mkdir(parents=True, exist_ok=True)
    print("Çekirdek:", os.environ.get("MOTOR_CEKIRDEK"), "| OMP:", os.environ.get("OMP_NUM_THREADS"))
    {"tutarlilik": tutarlilik, "tarama": tarama, "sure": sure}[sys.argv[1]]()
