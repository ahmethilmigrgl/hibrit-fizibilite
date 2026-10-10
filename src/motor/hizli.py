"""
Hızlı tarama (hedef ≤ 90 s): profiller, kapasite faktörleri ve RES güven bandı, 1 yıllık P50/P90, tamamlayıcılık,
yakalanan fiyat ve yakalanma oranı, teknoloji bazında LCOE ve başabaş fiyat, standart tasarımların deterministik NPV'si,
temsilî günlerle hızlı kapasite optimizasyonu ve kural tabanlı "neden" açıklamaları.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd

from src.ayarlar import deger
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.metrikler import basabas_fiyat
from src.finans.model import proje_degerle
from src.motor.ortak import Hazirlik, ortam, sfk_milp_carpani
from src.motor.varsayimlar import KullaniciVarsayimlari

Z90 = 1.2816


def _fiyat(h: Hazirlik, kv: KullaniciVarsayimlari):
    seviye = kv.fiyat_seviyesi if kv.fiyat_seviyesi is not None else kv.fiyat_senaryosu
    return fiyat_senaryosu_uret(h.cfg, h.u, seviye, kv.kanibalizasyon), seviye


def uretim_ozeti(h: Hazirlik) -> tuple[dict, pd.DataFrame, dict]:
    df, g = h.profil, h.guven
    kf_r, kf_g = float(df["res_kf"].mean()), float(df["ges_kf"].mean())
    yil = df.groupby(df.index.year)[["res_kf", "ges_kf"]].mean() * 8760  # MWh/MW-yıl
    sig_model_r = 1.4826 * g["medyan_puan"] / 100 * 8760  # gözlenen medyan mutlak hatadan sağlam σ
    sig_model_g = deger(h.cfg["v2"]["motor"])["gunes_model_hatasi"] * yil["ges_kf"].mean()
    p = {}
    for t, sm in (("res", sig_model_r), ("ges", sig_model_g)):
        s = yil[f"{t}_kf"]
        p[t] = {
            "P50": float(s.mean()),
            "P90_1y": float(s.mean() - Z90 * math.sqrt(s.std(ddof=1) ** 2 + sm**2)),
            "P90_10y": float(s.mean() - Z90 * math.sqrt(s.std(ddof=1) ** 2 / 10 + sm**2)),
            "yillar_arasi_sd": float(s.std(ddof=1)),
        }
    tsi = (df.index.hour + 3) % 24
    gun = df.groupby(tsi)[["res_kf", "ges_kf"]].mean()
    ay = df.groupby(df.index.month)[["res_kf", "ges_kf"]].mean()
    ozet = {
        "res_kf": kf_r,
        "ges_kf": kf_g,
        "res_kf_bandi_medyan": [kf_r - g["medyan_puan"] / 100, kf_r + g["medyan_puan"] / 100],
        "res_kf_bandi_p90": [kf_r - g["p90_puan"] / 100, kf_r + g["p90_puan"] / 100],
        "p50_p90_mwh_per_mw": p,
        "saatlik_korelasyon": float(df["res_kf"].corr(df["ges_kf"])),
        "gunici_korelasyon": float(gun["res_kf"].corr(gun["ges_kf"])),
        "mevsimsel_korelasyon": float(ay["res_kf"].corr(ay["ges_kf"])),
        "res_ogleden_sonra_pay": float(gun["res_kf"].loc[12:17].mean() / gun["res_kf"].mean()),
    }
    grafik = {
        "gunici": {"saat": gun.index.tolist(), "res": gun["res_kf"].round(4).tolist(), "ges": gun["ges_kf"].round(4).tolist()},
        "aylik": {"ay": ay.index.tolist(), "res": ay["res_kf"].round(4).tolist(), "ges": ay["ges_kf"].round(4).tolist()},
        "yillik_mwh_per_mw": {"yil": yil.index.tolist(), "res": yil["res_kf"].round(1).tolist(), "ges": yil["ges_kf"].round(1).tolist()},
    }
    return ozet, yil, grafik


def standart_tasarimlar(h: Hazirlik, f, iz=None) -> list[dict]:
    """iz: (v3) türbin sayısı → iç iz kaybı oranı; verilirse her tasarımın RES profili (1 − iz(N)) ile ölçeklenir."""
    L = h.saha.baglanti_mw
    tg = deger(h.cfg["optimizasyon"]["turbin_gucu"])
    res_ust = h.saha.azami_res_mw if h.saha.azami_res_mw is not None else deger(h.cfg["optimizasyon"]["turbin_azami"]) * tg
    ges_ust = h.saha.azami_ges_mw if h.saha.azami_ges_mw is not None else deger(h.cfg["optimizasyon"]["ges_azami_mw"])
    n = lambda mw: min(math.floor(min(mw, res_ust) / tg + 1e-9), int(res_ust // tg)) * tg
    adaylar = [
        ("RES", n(L), 0.0),
        ("RES fazla kurulum (%30)", n(1.3 * L), 0.0),
        ("RES + GES", n(L), min(0.5 * L, ges_ust)),
        ("GES", 0.0, min(L, ges_ust)),
    ]
    sonuc = []
    for ad, r, g_ in adaylar:
        if r + g_ <= 0:
            continue
        k = {"res_mw": r, "ges_mw": g_, "sebeke_mw": L}
        u = h.u
        if iz is not None and r > 0:
            from src.motor.v3 import res_olcekli

            u = res_olcekli(h.u, 1 - iz(round(r / tg)))
        s = proje_degerle(k, h.v, f, u)
        sonuc.append(
            {
                "tasarim": ad,
                "res_mw": r,
                "ges_mw": g_,
                "bess_mw": 0.0,
                "bess_mwh": 0.0,
                "npv_musd": s.npv / 1e6,
                "irr": s.irr,
                "kesinti_%": s.ozet["Kesinti oranı [%]"],
                "lcoe_res": s.lcoe.get("res"),
                "lcoe_ges": s.lcoe.get("ges"),
                "lcoe_hibrit": s.lcoe.get("hibrit_satilan"),
                "capex_musd": s.ozet["CAPEX [M USD]"],
                "res_yakalanan": s.ozet["RES yakalanan [USD/MWh]"],
                "ges_yakalanan": s.ozet["GES yakalanan [USD/MWh]"],
                "ort_ptf": s.ozet["Ort. PTF [USD/MWh]"],
                "_k": k,
                "_u": u,
            }
        )
    return sonuc


def nedenler(tas: pd.DataFrame, uo: dict, milp: dict | None, bas: dict, f_seviye: float, guven: dict) -> list[dict]:
    t = tas.set_index("tasarim")
    n: list[dict] = []
    if "RES" in t.index and "RES + GES" in t.index:
        d_kes = t.loc["RES + GES", "kesinti_%"] - t.loc["RES", "kesinti_%"]
        d_npv = t.loc["RES + GES", "npv_musd"] - t.loc["RES", "npv_musd"]
        n.append(
            {
                "tr": f"GES eklemek (+{t.loc['RES + GES', 'ges_mw']:.0f} MW) kesintiyi {d_kes:+.1f} puan değiştiriyor ve NPV'yi {d_npv:+.1f} M$ "
                f"değiştiriyor (güneş yakalanma oranı {t.loc['RES + GES', 'ges_yakalanan'] / t.loc['RES + GES', 'ort_ptf']:.2f}).",
                "en": f"Adding solar (+{t.loc['RES + GES', 'ges_mw']:.0f} MW) changes curtailment by {d_kes:+.1f} pts and NPV by {d_npv:+.1f} M$ "
                f"(solar capture rate {t.loc['RES + GES', 'ges_yakalanan'] / t.loc['RES + GES', 'ort_ptf']:.2f}).",
            }
        )
    if "RES" in t.index and "RES fazla kurulum (%30)" in t.index:
        d_npv = t.loc["RES fazla kurulum (%30)", "npv_musd"] - t.loc["RES", "npv_musd"]
        n.append(
            {
                "tr": f"Bağlantıya %30 fazla RES kurmak kesintiyi %{t.loc['RES fazla kurulum (%30)', 'kesinti_%']:.1f}'e çıkarıyor; NPV farkı {d_npv:+.1f} M$.",
                "en": f"Over-building wind by 30% raises curtailment to {t.loc['RES fazla kurulum (%30)', 'kesinti_%']:.1f}%; NPV difference {d_npv:+.1f} M$.",
            }
        )
    if bas.get("res") is not None:
        n.append(
            {
                "tr": f"RES'in başabaş ortalama fiyatı {bas['res']:.1f} $/MWh; seçilen senaryo {f_seviye:.0f} $/MWh.",
                "en": f"Wind break-even average price is {bas['res']:.1f} $/MWh; selected scenario {f_seviye:.0f} $/MWh.",
            }
        )
    if milp is not None and tas["npv_musd"].max() <= 0:
        n.append(
            {
                "tr": f"Seçilen fiyat senaryosunda hiçbir standart tasarım pozitif NPV vermiyor (en iyisi {tas['npv_musd'].max():+.1f} M$). "
                "Sonucu en çok fiyat beklentisi, CAPEX ve sözleşmeli gelir değiştirir; başabaş fiyatı bunun ölçüsüdür.",
                "en": f"No standard design has a positive NPV in the selected price scenario (best {tas['npv_musd'].max():+.1f} M$). "
                "Price expectations, CAPEX and contracted revenue move this most; the break-even price measures it.",
            }
        )
    if milp is not None:
        if milp["BESS [MW]"] > 0.5:
            n.append(
                {
                    "tr": f"Hızlı optimizasyon {milp['BESS [MW]']:.0f} MW / {milp['BESS [MWh]']:.0f} MWh batarya seçti; batarya değeri ağırlıkla SFK kapasite ödemesinden.",
                    "en": f"The quick optimisation chose a {milp['BESS [MW]']:.0f} MW / {milp['BESS [MWh]']:.0f} MWh battery; its value comes mainly from SFK capacity payments.",
                }
            )
        else:
            n.append({"tr": "Hızlı optimizasyon batarya seçmedi.", "en": "The quick optimisation chose no battery."})
    n.append(
        {
            "tr": f"Rüzgâr tahmininin güven seviyesi: {guven['seviye']} (tipik kapasite faktörü hatası ±{guven['medyan_puan']:.1f}, %90'da ±{guven['p90_puan']:.1f} puan).",
            "en": f"Wind estimate confidence: {guven['seviye']} (typical capacity-factor error ±{guven['medyan_puan']:.1f}, 90% ±{guven['p90_puan']:.1f} pts).",
        }
    )
    if uo["res_ogleden_sonra_pay"] > 1.15:
        n.append(
            {
                "tr": f"Rüzgâr öğleden sonra güçleniyor (12–17 TSİ ortalamanın {uo['res_ogleden_sonra_pay']:.2f} katı): güneşle aynı saatlerde tepe yapıyor.",
                "en": f"Wind strengthens in the afternoon (12–17 local time {uo['res_ogleden_sonra_pay']:.2f}× the mean): it peaks with solar.",
            }
        )
    return n


def tam_analize_deger(basabas: float | None, fiyat_: float, milp_npv: float, cfg: dict) -> dict:
    """
    "Tam analize değer mi?" (yatırım kararı DEĞİL): en iyi standart tasarımın başabaş fiyatının senaryo fiyatına oranı
    config v2.uygulama.tam_analize_deger eşikleriyle; temsilî gün optimumu pozitifse her durumda "deger".
    """
    e = deger(cfg["v2"]["uygulama"])["tam_analize_deger"]
    oran = basabas / fiyat_ if basabas else float("inf")
    if milp_npv > 0 or oran <= e["evet"]:
        k = "deger"
    elif oran <= e["sinirda"]:
        k = "sinirda"
    else:
        k = "degmez"
    metin = {
        "deger": ("Tam analize değer", "Worth a full analysis"),
        "sinirda": ("Sınırda: tam analiz varsayımlara duyarlı olacak", "Borderline: a full analysis will be assumption-sensitive"),
        "degmez": ("Bu varsayımlarla tam analize değmez", "Not worth a full analysis under these assumptions"),
    }[k]
    return {
        "karar": k,
        "tr": metin[0],
        "en": metin[1],
        "basabas_orani": None if not math.isfinite(oran) else oran,
        "esikler": e,
    }


def hizli_tarama(h: Hazirlik, kv: KullaniciVarsayimlari, ilerleme=None) -> dict:
    ilerleme = ilerleme or (lambda *_: None)
    sure, t0 = {}, time.perf_counter()
    v3b, iz = None, None
    if h.v3:  # v3 Faz D: tablo kullanılabilirliği/O&M + tasarım başına önceden hesaplanmış iz kaybı
        from src.motor.v3 import hizli_hazirla, iz_hizli

        h, v3b = hizli_hazirla(h, kv)
        iz = iz_hizli
    uo, yil, graf = uretim_ozeti(h)
    f, seviye = _fiyat(h, kv)
    f_seviye = float(f.seviye)
    sure["uretim_s"] = time.perf_counter() - t0
    ilerleme(0.35, "Standart tasarımlar değerleniyor")
    t1 = time.perf_counter()
    tas = standart_tasarimlar(h, f, iz)
    bas = {}
    for ad, anahtar in (("RES", "res"), ("GES", "ges")):
        x_ = next((x for x in tas if x["tasarim"] == ad), None)
        k = x_["_k"] if x_ else None
        try:
            bas[anahtar] = basabas_fiyat(k, h.cfg, x_["_u"], h.v, kv.kanibalizasyon) if k else None
        except ValueError:
            bas[anahtar] = None
    en_iyi_std = max(tas, key=lambda x: x["npv_musd"])
    if en_iyi_std["tasarim"] in ("RES", "GES"):
        bas["en_iyi"] = bas[en_iyi_std["tasarim"].lower()]
    else:
        try:
            bas["en_iyi"] = basabas_fiyat(en_iyi_std["_k"], h.cfg, en_iyi_std["_u"], h.v, kv.kanibalizasyon)
        except ValueError:
            bas["en_iyi"] = None
    sure["tasarimlar_s"] = time.perf_counter() - t1
    ilerleme(0.6, "Temsilî günlerle hızlı kapasite optimizasyonu")
    t2 = time.perf_counter()
    o = ortam(h)
    if iz is not None:
        o.opt["iz_verim"] = [1.0 - iz(n) for n in range(int(o.opt["turbin_azami"]) + 1)]
    kal = {"dz", "yekg"} | ({"yh"} if kv.sfk_katilimi else set())
    milp = o.milp(kal, seviye if isinstance(seviye, str) else float(seviye), K=24, zaman=120, yh_carpan=sfk_milp_carpani(o))
    tas.append(
        {
            "tasarim": "Optimum (temsilî gün, +batarya)"
            if milp["RES [MW]"] + milp["GES [MWac]"] + milp["BESS [MW]"] >= 1.0
            else "Optimum (temsilî gün): kurulum yok",
            "res_mw": milp["RES [MW]"],
            "ges_mw": milp["GES [MWac]"],
            "bess_mw": milp["BESS [MW]"],
            "bess_mwh": milp["BESS [MWh]"],
            "npv_musd": milp["NPV tahmini [M USD]"],
            "irr": np.nan,
            "kesinti_%": milp.get("Kesinti [%]", np.nan),
        }
    )
    sure["optimizasyon_s"] = time.perf_counter() - t2
    tablo = pd.DataFrame([{k: v for k, v in x.items() if k not in ("_k", "_u")} for x in tas])
    deger_mi = tam_analize_deger(bas.get("en_iyi"), f_seviye, milp.get("NPV tahmini [M USD]", -1.0), h.cfg)
    ozet = {
        **uo,
        "fiyat_seviyesi": f_seviye,
        "basabas_res": bas.get("res"),
        "basabas_ges": bas.get("ges"),
        "en_iyi_standart": en_iyi_std["tasarim"],
        "basabas_en_iyi": bas.get("en_iyi"),
        "tam_analize_deger": deger_mi,
        "lcoe_res": next((x["lcoe_res"] for x in tas if x["tasarim"] == "RES"), None),
        "lcoe_ges": next((x["lcoe_ges"] for x in tas if x["tasarim"] == "GES"), None),
        "yakalanma_res": next((float(x["res_yakalanan"] / x["ort_ptf"]) for x in tas if x["tasarim"] == "RES"), None),
        "yakalanma_ges": next((float(x["ges_yakalanan"] / x["ort_ptf"]) for x in tas if x["tasarim"] == "GES"), None),
        "en_iyi_tasarim": tablo.loc[tablo["npv_musd"].idxmax(), "tasarim"] if tablo["npv_musd"].max() > 0 else "Pozitif NPV'li tasarım yok",
        "milp": {
            k: milp[k] for k in ("RES [MW]", "GES [MWac]", "BESS [MW]", "BESS [MWh]", "NPV tahmini [M USD]", "İz verimi") if k in milp
        },
    }
    if v3b is not None:
        tg = deger(h.cfg["optimizasyon"]["turbin_gucu"])
        n_res = round(next((x["res_mw"] for x in tas if x["tasarim"] == "RES"), 0.0) / tg)
        ozet["v3_hizli"] = {
            "kullanilabilirlik": v3b["kullanilabilirlik"],
            "om_usd_mw_yil": v3b["om_usd_mw_yil"],
            "iz_kaybi_res": iz(n_res) if n_res else 0.0,
            "N_res": n_res,
            "kaynak": v3b["kaynak"],
        }
    return {
        "ozet": ozet,
        "tablolar": {"tasarimlar": tablo, "yillik_uretim": yil},
        "grafikler": graf,
        "nedenler": nedenler(tablo, uo, milp, bas, f_seviye, h.guven),
        "sure": sure,
    }
