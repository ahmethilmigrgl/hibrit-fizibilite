"""
v3 D2 — Bakım ve güvenilirlik analizi (çevrimdışı, 200 tekrar): üç saha (Ezine, Gürün, Susurluk), sahanın v2 tasarımındaki
türbin sayısı (14) ve SA yerleşimi.

Çıktılar (outputs/v3D/):
    D2_stratejiler.csv      — strateji × saha: kullanılabilirlik (zaman/enerji, P10–P90), kayıp üretim/gelir, O&M, toplam maliyet
    D2_ariza_dogrulama.csv  — simüle edilen arıza oranları ↔ girdi oranları (alt sistem × sınıf)
    D2_cizelge.csv          — önleyici bakım çizelgesi: MILP ↔ bahar kampanyası ↔ eşit dağıtım (kayıp gelir ve enerji, aylık dağılım)
    D2_stok.csv             — kalem × S: kayıp gelir, tutma maliyeti, toplam; D2_stok_olcek.csv: çiftlik büyüklüğüne göre S*
    D2_mevsim.csv           — arızanın ayına göre beklenen hava beklemesi (vinçli değişim)
    D2_opex_mutabakat.csv   — O&M kalemleri ve v1 sabit varsayımı (35.000 $/MW-yıl) ile fark
    D2_ozet.json
Çalıştırma: .venv/bin/python src/v3_D2_bakim_analizi.py
"""

import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, deger
from src.bakim import des, stok
from src.bakim.analiz import bakim_analizi
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.veri import _standart_yil, profil_df_den
from src.saha import saha_cfg, saha_olustur
from src.uretim import genel
from src.yerlesim import analiz as Y

SAHALAR = [("Çanakkale-Ezine", 39.79, 26.33), ("Sivas-Gürün", 38.92, 37.42), ("Balıkesir-Susurluk", 39.85, 28.15)]
N = 14
CIKTI = CIKTILAR / "v3D"


def saha_girdileri(ad, e, b):
    s = saha_olustur(ad, e, b)
    cfg = saha_cfg(s)
    cfg["uretim"]["ruzgar"]["toplam_kayip"]["value"] = Y.taban_kayip(cfg)
    df, bilgi = genel.profil_uret(s, cfg, 2014, 2023, "grid", "atlas")
    cr = cfg["uretim"]["ruzgar"]
    bg = Y.hazirla(e, b, df, deger(cr["turbin_modeli"]), deger(cr["gobek_yuksekligi"]), bilgi["kalibrasyon"]["gwa_hiz"], 2.0, cfg)
    r = Y.coz(bg, N, "sa")
    d = Y.degerlendir(bg, r.S)
    res = Y.profil_duzelt(df["res_kf"].to_numpy(), d["saatlik_oran"], d["saatlik_kf_cift"], Y.taban_kayip(cfg))
    sr = pd.Series(res, index=df.index)
    yil = sorted(set(df.index.year))
    kf = np.vstack([_standart_yil(sr.loc[str(y)]) for y in yil])
    v = np.vstack([_standart_yil(df.loc[str(y), "v_kalibre"]) for y in yil])
    u = profil_df_den(df)
    f = fiyat_senaryosu_uret(cfg, u, "baz", "devam")
    fiyat = f.fiyatlar.mean(axis=tuple(range(f.fiyatlar.ndim - 1)))
    pay = (d["turbinler"]["E_mwh"] / d["turbinler"]["E_mwh"].mean()).to_numpy()
    return cfg, bg.turbin.P_mw, pay, kf, v, fiyat


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    st_s, ar_s, cz_s, sk_s, mv_s, op_s, olc_s = [], [], [], [], [], [], []
    ozet = {}
    for ad, e, b in SAHALAR:
        cfg, P, pay, kf, v, fiyat = saha_girdileri(ad, e, b)
        p = deger(cfg["v3"]["bakim"])
        omur = int(deger(cfg["proje"]["omur"]))
        r = bakim_analizi(N, P, pay, kf, v, fiyat, p, omur, R=p["tekrar"])
        for x in r["stratejiler"]:
            st_s.append({"saha": ad, **x})
        for k, val in r["ariza_orani"].items():
            a, kat = k.split("|")
            kat = int(kat)
            if a == "sifirlama":
                girdi = p["sifirlama"]["lam"]
            else:
                girdi = p["alt_sistemler"][a][["lam_kucuk", "lam_buyuk", "lam_degisim"][kat]]
            ar_s.append(
                {"saha": ad, "alt_sistem": a, "sinif": kat, "simule": val, "girdi": girdi, "oran": val / girdi if girdi else np.nan}
            )
        cz = r["cizelge"]
        cz_s.append(
            {
                "saha": ad,
                **{k: v_ for k, v_ in cz.items() if not isinstance(v_, list)},
                "aylik_milp": cz["aylik_milp"],
                "aylik_bahar": cz["aylik_bahar"],
            }
        )
        for kalem, x in r["stok"].items():
            for t in x["tablo"]:
                sk_s.append({"saha": ad, "kalem": kalem, **t, "secilen": t["S"] == x["S"]})
        for m, val in enumerate(r["mevsimsel_hava_bekleme_gun"]):
            mv_s.append({"saha": ad, "ay": m + 1, "beklenen_hava_beklemesi_gun": val, "sim_ort_gun": r["aylik_hava_bekleme_gun_sim"][m]})
        MW = N * P
        for k, val in r["gider_kalemleri"].items():
            op_s.append({"saha": ad, "kalem": k, "usd_yil": val, "usd_mw_yil": val / MW})
        op_s.append({"saha": ad, "kalem": "TOPLAM (model)", "usd_yil": r["om_usd_mw_yil"] * MW, "usd_mw_yil": r["om_usd_mw_yil"]})
        op_s.append({"saha": ad, "kalem": "v1 sabit varsayım", "usd_yil": 35000 * MW, "usd_mw_yil": 35000.0})
        # çiftlik büyüklüğüne göre önerilen stok (havuzlamaya hazırlık: aynı stok daha çok türbine hizmet ederse)
        for n_ in (14, 28, 56, 112):
            g = des.Girdi(n_, P, np.ones(n_), kf, v, fiyat, omur, p, p["strateji"], None, {})
            so = stok.optimize(g, 60, p["tohum"])
            olc_s.append({"saha": ad, "turbin": n_, **{k: x["S"] for k, x in so.items()}})
        ozet[ad] = {
            "A_enerji": r["A_enerji"],
            "A_enerji_kisa": r["A_enerji_kisa"],
            "om_usd_mw_yil": r["om_usd_mw_yil"],
            "stok": {k: x["S"] for k, x in r["stok"].items()},
            "cizelge_kazanc_bahar": cz["kazanc_bahar"],
            "cizelge_kazanc_esit": cz["kazanc_esit"],
            "sure": r["sure"],
        }
        print(ad, json.dumps(ozet[ad], ensure_ascii=False, default=float), flush=True)
    pd.DataFrame(st_s).to_csv(CIKTI / "D2_stratejiler.csv", index=False, encoding="utf-8-sig", float_format="%.5f")
    pd.DataFrame(ar_s).to_csv(CIKTI / "D2_ariza_dogrulama.csv", index=False, encoding="utf-8-sig", float_format="%.5f")
    pd.DataFrame(cz_s).to_csv(CIKTI / "D2_cizelge.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.DataFrame(sk_s).to_csv(CIKTI / "D2_stok.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.DataFrame(olc_s).to_csv(CIKTI / "D2_stok_olcek.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(mv_s).to_csv(CIKTI / "D2_mevsim.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    pd.DataFrame(op_s).to_csv(CIKTI / "D2_opex_mutabakat.csv", index=False, encoding="utf-8-sig", float_format="%.1f")
    (CIKTI / "D2_ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1, default=float))
    print(
        pd.DataFrame(st_s)[["saha", "strateji", "A_zaman", "A_enerji", "kayip_gelir_yil", "om_usd_mw_yil", "toplam_maliyet_yil"]]
        .round(4)
        .to_string()
    )
    print(pd.DataFrame(olc_s).to_string())


if __name__ == "__main__":
    main()
