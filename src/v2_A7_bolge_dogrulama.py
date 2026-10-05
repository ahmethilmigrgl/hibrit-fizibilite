"""
v2 Faz A7 — Genelleştirilmiş hattın farklı bölgelerde uçtan uca çalıştırılması ve makullük kontrolü.

Her saha için: saha nesnesi (il/ilçe, tarife bölgesi, otomatik türbin) → Open-Meteo ERA5 + atlas aktarım kuralı ile
üretim profili → kapasite MILP'i (24 temsilî gün; yan hizmet + dengesizlik + YEK-G) → yalnız RES tasarımının deterministik
NPV'si (58 USD/MWh). Makullük: model KF'si, aktarımda kullanılan komşu santrallerin gözlenen KF aralığıyla ve güven
seviyesinin tipik hatasıyla karşılaştırılır.

Çalıştırma: .venv/bin/python src/v2_A7_bolge_dogrulama.py
Çıktı: outputs/v2/A7_bolge_dogrulama.csv
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, KOK
from src.finans.veri import uretim_profili
from src.risk.degerleme import nakit_akislari
from src.risk.tasarim import Tasarim
from src.saha import saha_cfg, saha_olustur, turbin_sec
from src.uretim import genel

# (ad, enlem, boylam) — kalibre santrallerin 10–25 km uzağında, santral üstünde olmayan noktalar (atlas sonrası seçildi)
SAHALAR = [("Sivas-Gürün (iç Anadolu, 1.665 m)", 38.92, 37.42), ("Balıkesir-Susurluk (Marmara içi)", 39.85, 28.15)]


def main(sahalar: list[tuple[str, float, float]] = SAHALAR) -> pd.DataFrame:
    spec = importlib.util.spec_from_file_location("gy", KOK / "src" / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gy)
    atl, _ = aktarim.atlas()
    satir = []
    for ad, en, bo in sahalar:
        s = saha_olustur(ad, en, bo, baglanti_mw=50.0)
        c = saha_cfg(s)
        df, b = genel.profil_uret(s, c, ruzgar_kaynagi="open_meteo", kalibrasyon="atlas")
        kal = b["kalibrasyon"]
        komsu_kf = atl.set_index("ad").loc[kal.get("komsu", []), "gozlenen_kf"] if kal.get("komsu") else pd.Series(dtype=float)
        o = gy.Ortam(cfg=c, uretim=uretim_profili(genel.profil_kaydet(df, s, "atlas", 2014, 2023)))
        r = o.milp({"yh", "dz", "yekg"}, "baz", K=24)
        ta = Tasarim("A", round(48 / o.opt["turbin_gucu"]) * o.opt["turbin_gucu"], 0.0)
        npv_a = nakit_akislari(ta, o.tablo(ta), o.c, o.beklenen_girdi(58.0))["npv"][0] / 1e6
        ts = turbin_sec(s)
        satir.append(
            {
                "saha": ad,
                "il": s.il,
                "ilce": s.ilce,
                "tarife_bolgesi": c["_saha"]["tarife_bolgesi"],
                "turbin": ts["turbin"],
                "gobek": ts["gobek"],
                "gwa_100m": ts["gwa_100m"],
                "guven": kal.get("guven"),
                "komsular": "; ".join(kal.get("komsu", [])),
                "komsu_mesafe_km": kal.get("mesafe_km"),
                "komsu_gozlenen_kf_%": 100 * float(komsu_kf.mean()) if len(komsu_kf) else np.nan,
                "gwa_c": kal.get("c"),
                "res_kf_%": 100 * b["res_kf"],
                "ges_kf_%": 100 * b["ges_kf"],
                "MILP RES [MW]": r["RES [MW]"],
                "MILP GES [MWac]": r["GES [MWac]"],
                "MILP BESS [MW]": r["BESS [MW]"],
                "MILP NPV tahmini [M USD]": r["NPV tahmini [M USD]"],
                "MILP kesinti [%]": r.get("Kesinti [%]", np.nan),
                f"NPV yalnız RES {ta.res_mw:.1f} MW @58 [M USD]": npv_a,
            }
        )
    sonuc = pd.DataFrame(satir)
    (CIKTILAR / "v2").mkdir(parents=True, exist_ok=True)
    sonuc.to_csv(CIKTILAR / "v2" / "A7_bolge_dogrulama.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    print(sonuc.T.to_string())
    return sonuc


if __name__ == "__main__":
    main()
