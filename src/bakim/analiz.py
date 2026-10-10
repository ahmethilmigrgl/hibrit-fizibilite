"""
Bakım ve güvenilirlik hattı (analiz motoru için): önleyici bakım çizelgesi (MILP) → yedek parça stoku (simülasyon tabanlı
optimizasyon) → üç stratejinin ayrık olay simülasyonu (ortak rastgele sayılar) → kullanılabilirlik ve O&M gideri.
"""

from __future__ import annotations

import time

import numpy as np

from src.bakim import cizelge, des, stok
from src.bakim.hava import mevsimsel_bekleme

STRATEJI_AD = {
    "duzeltici": ("Yalnız düzeltici", "Corrective only"),
    "takvim": ("Takvim bazlı önleyici", "Time-based preventive"),
    "durum": ("Durum bazlı (CMS)", "Condition-based (CMS)"),
}


def bakim_analizi(
    N: int,
    P_mw: float,
    pay: np.ndarray,
    kf_yillar: np.ndarray,
    v_yillar: np.ndarray,
    fiyat: np.ndarray,
    p: dict,
    omur: int,
    R: int | None = None,
    tohum: int | None = None,
    stratejiler=("duzeltici", "takvim", "durum"),
    mevsim: bool = True,
) -> dict:
    t0 = time.perf_counter()
    R = R or p["tekrar_motor"]
    tohum = p["tohum"] if tohum is None else tohum
    sure = {}
    pay = np.asarray(pay, float)
    # 1) önleyici bakım çizelgesi
    on, hv = p["onleyici"], p["hava"]
    c, pg, e = cizelge.gunluk_parametreler(v_yillar, kf_yillar * P_mw, fiyat, on["is_saati"], hv["tirmanma_limiti"], tuple(hv["vardiya"]))
    K = on["ekip_sayisi_cizelge"]
    milp = cizelge.coz(pay, c, pg, K)
    bahar = cizelge.bahar_kampanyasi(pay, c, pg, K)
    esit = cizelge.esit_dagitim(pay, c, pg, K)
    E_k = lambda gun: float(sum(pay[i] * e[gun[i]] for i in range(N)))
    cz = {
        "milp_gun": milp["gun"].tolist(),
        "bahar_gun": bahar["gun"].tolist(),
        "milp_maliyet": milp["maliyet"],
        "bahar_maliyet": bahar["maliyet"],
        "esit_maliyet": esit["maliyet"],
        "milp_mwh": E_k(milp["gun"]),
        "bahar_mwh": E_k(bahar["gun"]),
        "esit_mwh": E_k(esit["gun"]),
        "kazanc_bahar": bahar["maliyet"] - milp["maliyet"],
        "kazanc_esit": esit["maliyet"] - milp["maliyet"],
        "aylik_milp": cizelge.aylik_takvim(milp["gun"]),
        "aylik_bahar": cizelge.aylik_takvim(bahar["gun"]),
        "gunluk_kayip": c.round(1).tolist(),
        "gunluk_sure": pg.tolist(),
        "durum": milp["durum"],
        "bosluk": milp["bosluk"],
        "kapasite_ihlali": cizelge.kapasite_ihlali(milp["gun"], pg, K),
        "sure_s": milp["sure_s"],
    }
    sure["cizelge_s"] = time.perf_counter() - t0
    # 2) yedek parça stoku (seçili stratejide)
    t1 = time.perf_counter()
    g0 = des.Girdi(N, P_mw, pay, kf_yillar, v_yillar, fiyat, omur, p, p["strateji"], milp["gun"], {})
    so = stok.optimize(g0, R, tohum)
    S_opt = {ad: v["S"] for ad, v in so.items()}
    sure["stok_s"] = time.perf_counter() - t1
    # 3) stratejiler (aynı tohumlar)
    t2 = time.perf_counter()
    st = {}
    for s in stratejiler:
        g = des.Girdi(N, P_mw, pay, kf_yillar, v_yillar, fiyat, omur, p, s, milp["gun"], S_opt)
        r = des.simule(g, R, tohum)
        st[s] = r
    sure["des_s"] = time.perf_counter() - t2
    MW = N * P_mw
    tablo = []
    for s, r in st.items():
        toplam = r["opex_usd_yil"] + r["kayip_gelir_yil"]
        tablo.append(
            {
                "strateji": s,
                "ad_tr": STRATEJI_AD[s][0],
                "ad_en": STRATEJI_AD[s][1],
                "A_zaman": float(r["A_zaman"].mean()),
                "A_enerji": float(r["A_enerji"].mean()),
                "A_enerji_p10": float(np.percentile(r["A_enerji"], 10)),
                "A_enerji_p90": float(np.percentile(r["A_enerji"], 90)),
                "A_enerji_yil_sd": float(r["A_enerji_yil"].std(1).mean()),
                "kayip_mwh_yil": float(r["kayip_mwh_yil"].mean()),
                "kayip_gelir_yil": float(r["kayip_gelir_yil"].mean()),
                "om_usd_yil": float(r["opex_usd_yil"].mean()),
                "om_usd_mw_yil": float(r["opex_usd_mw_yil"].mean()),
                "toplam_maliyet_yil": float(toplam.mean()),
                "toplam_maliyet_p10": float(np.percentile(toplam, 10)),
                "toplam_maliyet_p90": float(np.percentile(toplam, 90)),
            }
        )
    secili = st[p["strateji"]] if p["strateji"] in st else st[stratejiler[-1]]
    bek = np.array([b[:4] for b in secili["beklemeler"]], float) if secili["beklemeler"] else np.zeros((0, 4))
    aylik_bekleme = [float(bek[bek[:, 0] == m, 1].mean() / 24) if (bek[:, 0] == m).any() else None for m in range(12)]
    mevsimsel = None
    if mevsim:
        a = p["alt_sistemler"]["disli_kutusu"]
        mevsimsel = (
            mevsimsel_bekleme(
                v_yillar,
                hv["tirmanma_limiti"],
                tuple(hv["vardiya"]),
                p["lojistik"]["kaldirma_pencere_h"],
                a["kaldirma_limiti"],
                a["sure_h"][2],
            )
            .round(2)
            .tolist()
        )
    sure["toplam_s"] = time.perf_counter() - t0
    return {
        "strateji": p["strateji"],
        "A_enerji": float(secili["A_enerji"].mean()),
        "A_enerji_dagilim": np.histogram(secili["A_enerji"], bins=20),
        "A_enerji_ornek": secili["A_enerji"].round(5).tolist(),
        "A_enerji_kisa": float(secili["A_enerji_kisa"].mean()),
        "A_yil_sd": float(secili["A_enerji_yil"].std(1).mean()),
        "A_tekrar_sd": float(secili["A_enerji"].std(ddof=1)),
        "om_usd_mw_yil": float(secili["opex_usd_mw_yil"].mean()),
        "gider_kalemleri": {k: v * p["genel_gider_carpani"] for k, v in secili["gider"].items()}
        | {"diger_sabit": p["diger_sabit_usd_mw_yil"] * MW},
        "stratejiler": tablo,
        "cizelge": cz,
        "stok": {
            ad: {"S": v["S"], "tablo": v["tablo"], "parca_degeri": v["parca_degeri"], "tedarik_gun": v["tedarik_gun"]}
            for ad, v in so.items()
        },
        "ariza_orani": secili["ariza_orani"],
        "aylik_hava_bekleme_gun_sim": aylik_bekleme,
        "mevsimsel_hava_bekleme_gun": mevsimsel,
        "R": R,
        "sure": sure,
    }
