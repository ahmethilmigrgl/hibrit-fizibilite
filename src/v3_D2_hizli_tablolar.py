"""
v3 D1/D2 — Hızlı tarama için önceden hesaplanmış tablolar: türbin sayısına göre iç iz kaybı ve kullanılabilirlik / O&M.

Örnek sahalar: Ezine, Gürün, Susurluk + atlas santrallerinden coğrafi olarak yayılmış 9 nokta (her biri sahanın kendi
türbin seçimi ve profiliyle; yerleşim yarıçapı 2 km). Her saha için:
    iz: vekil modelle açgözlü (iç içe) yerleşimin iç iz kaybı, N = 1..24
    bakım: N ∈ {4, 8, 12, 16, 20, 24} için ayrık olay simülasyonu (config stratejisi, 30 tekrar)
Çıktı: data/atlas/v3_hizli_tablolar.csv (N başına medyan, P10, P90) ve outputs/v3D/D2_hizli_tablolar_saha.csv
Çalıştırma: .venv/bin/python src/v3_D2_hizli_tablolar.py
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, KOK, deger
from src.bakim.analiz import bakim_analizi
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.veri import _standart_yil, profil_df_den
from src.saha import saha_cfg, saha_olustur
from src.uretim import genel
from src.yerlesim import analiz as Y

SAHALAR = [("Çanakkale-Ezine", 39.79, 26.33), ("Sivas-Gürün", 38.92, 37.42), ("Balıkesir-Susurluk", 39.85, 28.15)]
N_BAKIM = [4, 8, 12, 16, 20, 24]


def ornek_sahalar() -> list[tuple]:
    df, _ = aktarim.atlas()
    d = df.sort_values("boylam").iloc[::10]
    return SAHALAR + [(f"atlas {r.ad}", round(r.enlem + 0.03, 3), round(r.boylam + 0.03, 3)) for r in d.itertuples()][:9]


def main() -> None:
    iz_s, bk_s = [], []
    for ad, e, b in ornek_sahalar():
        try:
            s = saha_olustur(ad, e, b)
        except ValueError:
            continue
        cfg = saha_cfg(s)
        cfg["uretim"]["ruzgar"]["toplam_kayip"]["value"] = Y.taban_kayip(cfg)  # izsiz, kullanılabilirlik hariç taban profil
        df, bilgi = genel.profil_uret(s, cfg, 2014, 2023, "grid", "atlas")
        cr = cfg["uretim"]["ruzgar"]
        gref = bilgi["kalibrasyon"].get("gwa_hiz") or bilgi["kalibrasyon"].get("c", 1.0)
        bg = Y.hazirla(e, b, df, deger(cr["turbin_modeli"]), deger(cr["gobek_yuksekligi"]), gref, 2.0, cfg)
        eg = Y.iz_egrisi(bg, 24)
        for r in eg.itertuples():
            iz_s.append({"saha": ad, "turbin": deger(cr["turbin_modeli"]), "N": r.N, "ic_iz": r.ic_iz, "konum": r.konum})
        u = profil_df_den(df)
        v = np.vstack([_standart_yil(df.loc[str(y), "v_kalibre"]) for y in range(2014, 2024)])
        f = fiyat_senaryosu_uret(cfg, u, "baz", "devam")
        fiyat = f.fiyatlar.mean(axis=tuple(range(f.fiyatlar.ndim - 1)))
        P = bg.turbin.P_mw
        p = deger(cfg["v3"]["bakim"])
        for N in N_BAKIM:
            r = bakim_analizi(N, P, np.ones(N), u.res, v, fiyat, p, 30, R=30, stratejiler=(p["strateji"],), mevsim=False)
            bk_s.append(
                {
                    "saha": ad,
                    "N": N,
                    "A_enerji": r["A_enerji"],
                    "A_yil_sd": r["A_yil_sd"],
                    "A_tekrar_sd": r["A_tekrar_sd"],
                    "om_usd_mw_yil": r["om_usd_mw_yil"],
                }
            )
        print(ad, "iz N=12 %", round(100 * eg.loc[12, "ic_iz"], 2), "A", round(bk_s[-3]["A_enerji"], 4), flush=True)
    iz = pd.DataFrame(iz_s)
    bk = pd.DataFrame(bk_s)
    (CIKTILAR / "v3D").mkdir(parents=True, exist_ok=True)
    iz.merge(bk, on=["saha", "N"], how="left").to_csv(
        CIKTILAR / "v3D" / "D2_hizli_tablolar_saha.csv", index=False, encoding="utf-8-sig", float_format="%.5f"
    )
    q = lambda x, k: x.quantile(k)
    t = iz.groupby("N")["ic_iz"].agg(
        ic_iz_medyan="median", ic_iz_p10=lambda x: q(x, 0.1), ic_iz_p90=lambda x: q(x, 0.9), saha_sayisi="count"
    )
    b2 = bk.groupby("N")[["A_enerji", "A_yil_sd", "A_tekrar_sd", "om_usd_mw_yil"]].median()
    b2 = b2.reindex(range(0, 25)).interpolate(limit_direction="both")
    out = t.join(b2, how="left").reset_index()
    out.to_csv(KOK / "data" / "atlas" / "v3_hizli_tablolar.csv", index=False, encoding="utf-8-sig", float_format="%.5f")
    print(out.round(4).to_string())


if __name__ == "__main__":
    main()
