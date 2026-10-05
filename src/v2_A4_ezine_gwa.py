"""
v2 Faz A4 (Ezine özel) — Santralleri yok sayıp yalnız GWA düzeltmesiyle Ezine'nin v1 kalibre sonucundan sapması.

Karşılaştırılan modlar (aynı ERA5 = CDS, aynı türbin E-141/120 m):
    v1    — v1 ay × saat kalibrasyon matrisi (Enerjisa Çanakkale RES ile)
    gwa   — yalnız GWA ortalama düzeltmesi (sabit katsayı; meltem kaynaklı gün içi şekil yok)
    yok   — ham ERA5
Çıktılar: KF, gün içi profil, ayrıca hibrit sonuçlar (kapasite MILP'i: tasarım, şebeke kesintisi, batarya; 24 temsilî gün,
yan hizmet + dengesizlik + YEK-G) ve v1 baz tasarımın (RES 58,8 + 30/60) deterministik NPV'si.

Çalıştırma: .venv/bin/python src/v2_A4_ezine_gwa.py
Çıktı: outputs/v2/A4_ezine_gwa.csv, outputs/v2/A4_ezine_gunici.png
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import src.gorsel as g
from src.ayarlar import CIKTILAR, KOK
from src.finans.veri import uretim_profili
from src.risk.degerleme import nakit_akislari
from src.risk.tasarim import Tasarim
from src.saha import ezine, saha_cfg
from src.uretim import genel

CIKTI = CIKTILAR / "v2"


def main() -> None:
    spec = importlib.util.spec_from_file_location("gy", KOK / "src" / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gy)
    s = ezine()
    c = saha_cfg(s)
    sonuc, gunici = [], {}
    for mod in ["v1", "gwa", "yok"]:
        df, b = genel.profil_uret(s, c, ruzgar_kaynagi="cds", kalibrasyon=mod)
        tsi = (df.index.hour + 3) % 24
        gunici[mod] = df["res_kf"].groupby(tsi).mean()
        o = gy.Ortam(cfg=c, uretim=uretim_profili(genel.profil_kaydet(df, s, f"ezine_{mod}", 2014, 2023)))
        r = o.milp({"yh", "dz", "yekg"}, "baz", K=24)
        t = Tasarim("G", 58.8, 0.0, 30.0, 60.0, yan_hizmet=True, dengesizlik_azaltim=True, yekg=True)
        npv_g = nakit_akislari(t, o.tablo(t), o.c, o.beklenen_girdi(58.0))["npv"][0] / 1e6
        npv_a = nakit_akislari(Tasarim("A", 58.8, 0.0), o.tablo(Tasarim("A", 58.8, 0.0)), o.c, o.beklenen_girdi(58.0))["npv"][0] / 1e6
        sonuc.append(
            {
                "mod": mod,
                "c_veya_k_ort": b["kalibrasyon"].get("c", np.nan),
                "res_kf_%": 100 * b["res_kf"],
                "gunici_genlik_puan": 100 * float(gunici[mod].max() - gunici[mod].min()),
                "ogleden_sonra_14_18_kf_%": 100 * float(gunici[mod].loc[14:18].mean()),
                "gece_0_6_kf_%": 100 * float(gunici[mod].loc[0:6].mean()),
                "MILP RES [MW]": r["RES [MW]"],
                "MILP GES [MWac]": r["GES [MWac]"],
                "MILP BESS [MW]": r["BESS [MW]"],
                "MILP BESS [MWh]": r["BESS [MWh]"],
                "MILP kesinti [%]": r.get("Kesinti [%]", np.nan),
                "MILP NPV tahmini [M USD]": r["NPV tahmini [M USD]"],
                "NPV yalnız RES 58,8 @58 [M USD]": npv_a,
                "NPV RES 58,8 + 30/60 @58 [M USD]": npv_g,
            }
        )
    df = pd.DataFrame(sonuc).set_index("mod")
    CIKTI.mkdir(parents=True, exist_ok=True)
    df.to_csv(CIKTI / "A4_ezine_gwa.csv", encoding="utf-8-sig", float_format="%.4f")
    pd.set_option("display.width", 250)
    print(df.round(3).T.to_string())
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for mod, renk, ad in [
        ("v1", g.RENK_RES, "v1 kalibre (santral, ay × saat)"),
        ("gwa", g.RENK_GES, "Yalnız GWA düzeltmesi"),
        ("yok", g.SOLUK, "Ham ERA5"),
    ]:
        ax.plot(gunici[mod].index, 100 * gunici[mod].to_numpy(), color=renk, lw=2, label=ad)
    ax.set_xlabel("Saat (TSİ)")
    ax.set_ylabel("RES kapasite faktörü [%]")
    ax.legend()
    g.eksen_sade(ax)
    g.baslik(
        fig,
        "Ezine: yalnız GWA düzeltmesi meltem kaynaklı gün içi şekli kaybediyor",
        "E-141/4200, 120 m; CDS ERA5 2014–2023, 10 yıl ortalaması.",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig, "Kaynak: ERA5 (Copernicus), Global Wind Atlas 3.0, EPİAŞ (v1 kalibrasyonu). Kendi hesaplamam.")
    fig.savefig(CIKTI / "A4_ezine_gunici.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
