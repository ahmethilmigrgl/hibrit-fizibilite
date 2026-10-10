"""
v3 D1 — Türbin yerleşimi yöntemlerinin karşılaştırması: (a) MILP (Glover), (b) genetik algoritma ve benzetimli tavlama +
yerel arama, (c) düzenli ızgara ve v2 GWA açgözlü kuralı (+ açgözlü yardımcı).

Sahalar: Ezine, Gürün, Susurluk (yerleşim yarıçapı 2 km, sahanın kendi türbini); N ∈ {12, 20}.
Her yöntem aynı aday kümesi ve kısıtlarla çalışır; sezgiseller 5 tohumla (tekrarlanabilirlik). Tüm sonuçlar AYNI referans
modelle (PyWake Bastankhah, 36 yön × 1 m/s, komşu santraller dahil) yeniden değerlendirilir; duyarlılık için Jensen/Park.
Çıktılar: outputs/v3D/D1_yontem_karsilastirma.csv (koşu başına), D1_yontem_ozet.csv (yöntem × saha × N özeti)
Çalıştırma: OMP_NUM_THREADS=1 .venv/bin/python src/v3_D1_yontem_karsilastirma.py
"""

import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import pandas as pd

from src.ayarlar import CIKTILAR, deger
from src.saha import saha_cfg, saha_olustur
from src.uretim import genel
from src.yerlesim import analiz as Y

SAHALAR = [("Çanakkale-Ezine", 39.79, 26.33), ("Sivas-Gürün", 38.92, 37.42), ("Balıkesir-Susurluk", 39.85, 28.15)]
N_LISTE = [12, 20]
TOHUMLAR = [0, 1, 2, 3, 4]
YONTEMLER = [("milp", False), ("ga", True), ("sa", True), ("izgara", False), ("gwa", False), ("acgozlu", False)]


def main() -> None:
    satir = []
    for ad, e, b in SAHALAR:
        s = saha_olustur(ad, e, b)
        cfg = saha_cfg(s)
        cfg["uretim"]["ruzgar"]["toplam_kayip"]["value"] = Y.taban_kayip(cfg)
        df, bilgi = genel.profil_uret(s, cfg, 2014, 2023, "grid", "atlas")
        cr = cfg["uretim"]["ruzgar"]
        bg = Y.hazirla(e, b, df, deger(cr["turbin_modeli"]), deger(cr["gobek_yuksekligi"]), bilgi["kalibrasyon"]["gwa_hiz"], 2.0, cfg)
        n_sigan = Y.azami_turbin(bg, 40)
        print(f"{ad}: {len(bg.adaylar)} aday, en fazla {n_sigan} türbin, yön {bg.akis.yon_kaynagi}, komşu {len(bg.komsu)}", flush=True)
        for N in N_LISTE:
            if N > n_sigan:
                continue
            p = bg.problem(N)
            for yontem, sezgisel in YONTEMLER:
                for tohum in TOHUMLAR if sezgisel else [0]:
                    t0 = time.perf_counter()
                    r = Y.coz(bg, N, yontem, tohum)
                    sure = time.perf_counter() - t0
                    d = Y.degerlendir(bg, r.S)
                    dj = Y.degerlendir(bg, r.S, model="jensen")
                    o = d["ozet"]
                    satir.append(
                        {
                            "saha": ad,
                            "N": N,
                            "yontem": yontem,
                            "yontem_ad": r.yontem,
                            "tohum": tohum,
                            "sure_s": sure,
                            "olurlu": p.olurlu_mu(r.S),
                            "vekil_mwh": r.enerji,
                            "E_mwh": o["E_mwh"],
                            "E_serbest_mwh": o["E_serbest_mwh"],
                            "ic_iz": o["ic_iz"],
                            "dis_iz": o["dis_iz"],
                            "toplam_iz": o["toplam_iz"],
                            "konum_kazanci": o["konum_kazanci"],
                            "jensen_E_mwh": dj["ozet"]["E_mwh"],
                            "jensen_ic_iz": dj["ozet"]["ic_iz"],
                            "milp_bosluk": r.ayrinti.get("bosluk"),
                            "milp_durum": r.ayrinti.get("durum"),
                            "elips_ihlali": r.ayrinti.get("elips_ihlali"),
                        }
                    )
                    x = satir[-1]
                    print(
                        f"  N={N} {yontem:8s} t{tohum} {sure:6.1f}s  E={x['E_mwh']:.0f}  iç iz %{100 * x['ic_iz']:.2f}  olurlu={x['olurlu']}",
                        flush=True,
                    )
    d = pd.DataFrame(satir)
    (CIKTILAR / "v3D").mkdir(parents=True, exist_ok=True)
    d.to_csv(CIKTILAR / "v3D" / "D1_yontem_karsilastirma.csv", index=False, encoding="utf-8-sig", float_format="%.5f")
    en_iyi = d.groupby(["saha", "N"])["E_mwh"].transform("max")
    d["en_iyiye_fark_%"] = 100 * (d["E_mwh"] / en_iyi - 1)
    oz = (
        d.groupby(["saha", "N", "yontem"])
        .agg(
            E_ort=("E_mwh", "mean"),
            E_sd=("E_mwh", "std"),
            en_iyiye_fark_ort=("en_iyiye_fark_%", "mean"),
            en_iyiye_fark_en_kotu=("en_iyiye_fark_%", "min"),
            ic_iz_ort=("ic_iz", "mean"),
            toplam_iz_ort=("toplam_iz", "mean"),
            konum=("konum_kazanci", "mean"),
            jensen_ic_iz=("jensen_ic_iz", "mean"),
            sure_ort=("sure_s", "mean"),
            olurlu=("olurlu", "all"),
        )
        .reset_index()
    )
    oz.to_csv(CIKTILAR / "v3D" / "D1_yontem_ozet.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    genel_oz = d.groupby("yontem").agg(
        fark_ort=("en_iyiye_fark_%", "mean"),
        fark_en_kotu=("en_iyiye_fark_%", "min"),
        sure_ort=("sure_s", "mean"),
        sure_azami=("sure_s", "max"),
    )
    tekr = (
        d[d["yontem"].isin(["ga", "sa"])]
        .groupby(["yontem", "saha", "N"])["E_mwh"]
        .agg(lambda x: 100 * x.std() / x.mean())
        .groupby("yontem")
        .mean()
    )
    genel_oz["tohumlar_arasi_cv_%"] = tekr
    genel_oz.to_csv(CIKTILAR / "v3D" / "D1_yontem_genel.csv", encoding="utf-8-sig", float_format="%.4f")
    print(genel_oz.round(3).to_string())


if __name__ == "__main__":
    main()
