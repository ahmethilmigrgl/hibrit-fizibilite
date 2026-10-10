"""
Tam analiz (hedef ≤ 10 dk): tam yıl MILP kapasite optimizasyonu (ya da kullanıcının sabit tasarımı), çalışma anı işletme
tabloları, gelir yapıları karşılaştırması (tüccar / YEKDEM yıllık opsiyonu / PPA), proje aşamasına göre COD dağılımı,
yakınsayan Monte Carlo ve v1 karar kuralının genişletilmiş haliyle otomatik öneri ve tetikleyiciler.
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

from src.ayarlar import KOK, deger
from src.motor import mc as MC
from src.motor import tablolar
from src.motor.hizli import _fiyat, uretim_ozeti
from src.motor.ortak import Hazirlik, ortam, sfk_milp_carpani
from src.motor.varsayimlar import KullaniciVarsayimlari
from src.risk.degerleme import nakit_akislari
from src.risk.tasarim import Tasarim

YAPI_AD = {
    "tuccar": ("Tüccar", "Merchant"),
    "yekdem_opsiyon": ("YEKDEM yıllık opsiyonu + tüccar", "YEKDEM annual option + merchant"),
    "ppa": ("PPA (%70 P90, 12 yıl)", "PPA (70% P90, 12 yr)"),
}
ASAMA_ANAHTAR = {"insaata_hazir": "insaata_hazir_B1_cod", "on_lisans": "gelistirme_B1_cod"}


def kucuk() -> bool:
    """Yalnız testler için (MOTOR_KUCUK=1): 24 temsilî günlük MILP, küçük tablo ızgarası, 500 senaryoluk Monte Carlo."""
    return os.environ.get("MOTOR_KUCUK") == "1"


def tasarim_sec(h: Hazirlik, o, kv: KullaniciVarsayimlari, seviye, f=None) -> tuple[Tasarim, dict]:
    asgari_sfk = deger(h.cfg["gelir_yigini"]["yan_hizmet"]["asgari_guc"])
    if kv.sabit_tasarim:
        d = {k: float(kv.sabit_tasarim.get(k, 0.0)) for k in ("res_mw", "ges_mw", "bess_mw", "bess_mwh")}
        milp = None
    else:
        kal = {"dz", "yekg"} | ({"yh"} if kv.sfk_katilimi else set())
        o.opt["mip_bosluk"] = 0.005  # tam analiz: %0,5 MIP boşluğu (v1 %0,1); değer farkı ihmal edilebilir, süre kısalır
        yh_c = sfk_milp_carpani(o)
        mot = deger(h.cfg["v2"]["motor"])
        if kucuk():
            milp = o.milp(kal, seviye, K=24, zaman=240, yh_carpan=yh_c)
        elif os.environ.get("MOTOR_TAM_MILP") == "tamyil":  # karşılaştırma için eski yol (240 s sınırında %0,5'e ulaşmıyor)
            milp = o.milp(kal, seviye, K=None, zaman=240, yh_carpan=yh_c)
        else:
            # R5: tasarım seçimi temsilî günlerle (kesin optimum, ≤ ~15 s); değerleme 10 hava yılı × 8760 saatlik işletme
            # tablolarıyla Monte Carlo'da. Tam yıl (2 × 8760 saat) MILP'i 240 s'de %2 boşlukla zaman sınırına çarpıyordu.
            milp = o.milp(kal, seviye, K=mot["tam_milp_temsili_gun"], zaman=240, yh_carpan=yh_c)
        d = {
            "res_mw": milp["RES [MW]"],
            "ges_mw": round(milp["GES [MWac]"], 1),
            "bess_mw": round(milp["BESS [MW]"], 1),
            "bess_mwh": round(milp["BESS [MWh]"], 1),
        }
        if d["res_mw"] + d["ges_mw"] + d["bess_mw"] < 1.0 and f is not None:
            # MILP "kurulum yok" dedi (sabit maliyetler hiçbir kapasiteyle karşılanamıyor). Monte Carlo'nun anlamlı bir
            # soruyu yanıtlaması için standart tasarımların en iyisi değerlenir: "kursak ne olur?"
            from src.motor.hizli import standart_tasarimlar

            en_iyi = max(standart_tasarimlar(h, f), key=lambda x: x["npv_musd"])
            d = {k: float(en_iyi[k]) for k in ("res_mw", "ges_mw", "bess_mw", "bess_mwh")}
            d["yedek_tasarim"] = en_iyi["tasarim"]
    yh = kv.sfk_katilimi and d["bess_mw"] >= asgari_sfk - 1e-6
    t = Tasarim(
        "Seçilen tasarım",
        d["res_mw"],
        d["ges_mw"],
        d["bess_mw"],
        d["bess_mwh"],
        sebeke_mw=h.saha.baglanti_mw,
        yan_hizmet=yh,
        dengesizlik_azaltim=True,
        yekg=True,
    )
    return t, {"milp": milp, **d}


def fiyat_egimi(o, t: Tasarim, tb: dict, L: float) -> float:
    """Deterministik NPV'nin fiyat seviyesine eğimi [M USD / (USD/MWh)] (L ± 1)."""
    f = lambda x: nakit_akislari(t, tb, o.c, o.beklenen_girdi(x))["npv"][0] / 1e6
    return (f(L + 1) - f(L - 1)) / 2


def basabas(e_npv: float, L: float, egim: float) -> float | None:
    """Monte Carlo E[NPV]'yi sıfırlayan yaklaşık beklenen fiyat seviyesi (deterministik eğimle doğrusal)."""
    return None if egim <= 0 else float(L - e_npv / egim)


def karar(met: dict, capex: float, cfg: dict) -> dict:
    k = deger(cfg["v2"]["motor"])["karar"]
    e, p, cv = met["e_npv"], met["p_pozitif"], met["cvar5"]
    if e > 0 and p >= k["yatirim_p_asgari"] and cv >= k["yatirim_cvar_capex_orani"] * capex:
        return {
            "karar": "yatirim",
            "tr": "Yatırım yap (koşullu FID hazırlığı)",
            "en": "Invest (prepare a conditional FID)",
            "azami_prim": e,
        }
    if e > 0:
        return {
            "karar": "sinirli_teklif",
            "tr": f"Durum tespiti + en fazla {e:.1f} M$ primle bağlayıcı olmayan teklif",
            "en": f"Due diligence + non-binding offer with a premium of at most {e:.1f} M$",
            "azami_prim": e,
        }
    return {"karar": "rafa_kaldir", "tr": "Rafa kaldır, tetikleyicileri izle", "en": "Shelve and monitor triggers", "azami_prim": 0.0}


def tam_analiz(h: Hazirlik, kv: KullaniciVarsayimlari, ilerleme=None) -> dict:
    ilerleme = ilerleme or (lambda *_: None)
    sure = {}
    t0 = time.perf_counter()
    f, seviye = _fiyat(h, kv)
    on = s3 = None
    if h.v3:  # v3 Faz D: iz verimi eğrisi + tablo kullanılabilirliği/O&M ile MILP
        from src.motor.v3 import tam_once

        ilerleme(0.1, "Rüzgâr gülü, aday konumlar ve iz verimi eğrisi")
        on = tam_once(h, kv)
        sure["v3_iz_egrisi_s"] = on["sure_s"]
        o = ortam(on["hA"])
        o.opt["iz_verim"] = on["verim"]
        h_milp = on["hA"]
    else:
        o = ortam(h)
        h_milp = h
    ilerleme(0.15, "Tam yıl kapasite optimizasyonu (MILP)")
    t1_ = time.perf_counter()
    t, tas = tasarim_sec(h_milp, o, kv, seviye if isinstance(seviye, str) else float(seviye), f)
    sure["optimizasyon_s"] = time.perf_counter() - t1_
    if h.v3:
        from src.motor.v3 import tam_sonra

        tg = deger(h.cfg["optimizasyon"]["turbin_gucu"])
        DF = o.DF
        p8760 = ((f.fiyatlar * DF[:, None, None]).sum(0) / DF.sum()).mean(0)
        s3 = tam_sonra(h, kv, on, int(round(t.res_mw / tg)), p8760, ilerleme)
        sure.update(s3["sure"])
        h = s3["h"]
        o = ortam(h)
    uo, yil, graf = uretim_ozeti(h)
    sigma = MC.res_sigma(h.guven)
    ilerleme(0.3, "İşletme (dispatch) tabloları üretiliyor")
    t1 = time.perf_counter()
    yapilar = [y for y in ("tuccar", "yekdem_opsiyon", "ppa") if y in kv.gelir_yapilari]
    if "yekdem_opsiyon" in yapilar and "tuccar" not in yapilar:
        yapilar = ["tuccar", *yapilar]  # COD 2030 sonrası YEKDEM'siz durum için gerekli
    seviye_tablo = "v1" if kv.kalibrasyon == "v1" else ("kucuk" if kucuk() else "hafif")
    tb_T = tablolar.tablo(o, t, seviye_tablo, sigma=sigma or 0.06)
    tb_Y = tablolar.tablo(o, t, seviye_tablo, yekdem=True, sigma=sigma or 0.06) if "yekdem_opsiyon" in yapilar else None
    sure["tablolar_s"] = time.perf_counter() - t1
    ilerleme(0.7, "Monte Carlo")
    t2 = time.perf_counter()
    cod_ay = np.load(KOK / "results" / "takvim_cod_ornekleri.npz")[ASAMA_ANAHTAR[kv.proje_asamasi]].astype(float)
    r = MC.yakinsayan_mc(o, t, tb_T, tb_Y, yapilar, cod_ay, sigma, kv.sfk_katilimi, ilerleme=ilerleme)
    sure["monte_carlo_s"] = time.perf_counter() - t2
    met = r["metrik"]
    en_iyi = max((y for y in met if y in kv.gelir_yapilari), key=lambda y: met[y]["e_npv"])
    capex = r["ek"][en_iyi]["capex_musd"]
    k = karar(met[en_iyi], capex, h.cfg)
    egim = fiyat_egimi(o, t, tb_T, float(f.seviye))
    bb = basabas(met[en_iyi]["e_npv"], float(f.seviye), egim)
    x = r["npv"][en_iyi]
    sfk_kosullu = {s: float(x[r["senaryo"] == s].mean()) for s in np.unique(r["senaryo"])}
    # Güven seviyesinin etkisi: rüzgâr model çarpanının (m ~ LogNormal(σ), σ güven seviyesinden) alt/orta/üst üçte birinde E[NPV]
    q1, q2 = np.quantile(r["m"], [1 / 3, 2 / 3])
    guven_etkisi = {
        "sigma": sigma,
        "m_esik": [float(q1), float(q2)],
        "e_npv_alt": float(x[r["m"] <= q1].mean()),
        "e_npv_orta": float(x[(r["m"] > q1) & (r["m"] <= q2)].mean()),
        "e_npv_ust": float(x[r["m"] > q2].mean()),
        "kf_degisim_alt_ust": [float(np.mean(r["m"][r["m"] <= q1]) - 1), float(np.mean(r["m"][r["m"] > q2]) - 1)],
    }
    tetik = []
    if bb is not None:
        tetik.append(
            {
                "tr": f"Uzun vadeli beklenen fiyat ≳ {bb:.0f} $/MWh (Monte Carlo başabaşı, fiyata eğim {egim:.2f} M$ / ($/MWh); senaryo {f.seviye:.0f})",
                "en": f"Long-term expected price ≳ {bb:.0f} $/MWh (Monte Carlo break-even, price slope {egim:.2f} M$ per $/MWh; scenario {f.seviye:.0f})",
            }
        )
    if met[en_iyi]["e_npv"] < 0:
        tetik.append(
            {
                "tr": f"CAPEX'te ≳ %{100 * -met[en_iyi]['e_npv'] / capex:.0f} düşüş (yaklaşık; vergi kalkanı hariç)",
                "en": f"CAPEX reduction of ≳ {100 * -met[en_iyi]['e_npv'] / capex:.0f}% (approximate; excluding tax shield)",
            }
        )
    if t.yan_hizmet:
        tetik.append(
            {
                "tr": "SFK piyasasının doyum hızı: yavaş doyumda E[NPV] "
                + f"{sfk_kosullu.get('yavas', np.nan):+.1f} M$, hızlıda {sfk_kosullu.get('hizli', np.nan):+.1f} M$",
                "en": "SFK saturation pace: E[NPV] "
                + f"{sfk_kosullu.get('yavas', np.nan):+.1f} M$ if slow, {sfk_kosullu.get('hizli', np.nan):+.1f} M$ if fast",
            }
        )
    if tas.get("yedek_tasarim"):
        tetik.insert(
            0,
            {
                "tr": f"Optimizasyon bu varsayımlarla hiçbir kapasiteyi kârlı bulmadı; değerlenen tasarım en iyi standart tasarım "
                f"({tas['yedek_tasarim']}). Önce fiyat beklentisi ya da CAPEX değişmeli.",
                "en": f"The optimisation found no profitable capacity under these assumptions; the valued design is the best standard "
                f"design ({tas['yedek_tasarim']}). Price expectations or CAPEX would need to change first.",
            },
        )
    tetik.append(
        {
            "tr": f"Rüzgâr verisi: saha ölçümü (güven seviyesi {h.guven['seviye']}, tipik KF hatası ±{h.guven['medyan_puan']:.1f} puan)",
            "en": f"Wind data: on-site measurement (confidence {h.guven['seviye']}, typical CF error ±{h.guven['medyan_puan']:.1f} pts)",
        }
    )
    cod_tarih = lambda ay: (pd.Timestamp("2026-10-01") + pd.DateOffset(months=int(round(ay)))).strftime("%Y-%m")
    takvim = {
        "proje_asamasi": kv.proje_asamasi,
        "cod_p50": cod_tarih(np.percentile(cod_ay, 50)),
        "cod_p80": cod_tarih(np.percentile(cod_ay, 80)),
        "p_cod_2030_oncesi": float((cod_ay <= MC.YEKDEM_SON_AY).mean()),
    }
    gelir_tablo = pd.DataFrame(
        [
            {"yapi": y, "ad_tr": YAPI_AD[y][0], "ad_en": YAPI_AD[y][1], **met[y], "irr_p50": r["ek"][y].get("irr_p50")}
            for y in met
            if y in kv.gelir_yapilari
        ]
    ).set_index("yapi")
    hist = {y: np.histogram(v_, bins=40)[0].tolist() for y, v_ in r["npv"].items()}
    kenar = {y: np.histogram(v_, bins=40)[1].round(2).tolist() for y, v_ in r["npv"].items()}
    ozet = {
        **uo,
        "tasarim": {kk: tas[kk] for kk in ("res_mw", "ges_mw", "bess_mw", "bess_mwh")},
        "yedek_tasarim": tas.get("yedek_tasarim"),  # MILP "kurulum yok" dediyse değerlenen standart tasarım
        "sfk_katilimi": t.yan_hizmet,
        "milp": {
            kk: tas["milp"][kk]
            for kk in ("RES [MW]", "GES [MWac]", "BESS [MW]", "BESS [MWh]", "NPV tahmini [M USD]", "Kesinti [%]")
            if tas["milp"] and kk in tas["milp"]
        },
        "en_iyi_yapi": en_iyi,
        "baz": met[en_iyi],
        "karar": k,
        "basabas_fiyat": bb,
        "fiyat_egimi": egim,
        "takvim": takvim,
        "capex_musd": capex,
        "sfk_kosullu_e_npv": sfk_kosullu,
        "guven_etkisi": guven_etkisi,
        "res_sigma": sigma,
        "tablo_izgarasi": seviye_tablo,
        "yekdem_katilim": r["ek"].get("yekdem_opsiyon", {}).get("katilim_yil"),
        "fiyat_seviyesi": float(f.seviye),
        "yerlesim": s3["yerlesim"] if s3 else None,
        "bakim": s3["bakim"] if s3 else None,
        "kullanilabilirlik": s3.get("kullanilabilirlik") if s3 else None,
        "isletme": s3.get("isletme") if s3 else None,
        "kayip": s3.get("kayip") if s3 else None,
        "om_usd_mw_yil": deger(h.cfg["teknoloji"]["res"]["opex_sabit"]),
        "v3": bool(s3),
    }
    graf.update({"npv_histogram": {"sayi": hist, "kenar": kenar}, "yakinsama": r["yakinsama"]})
    nedenler = [
        {
            "tr": f"Seçilen tasarım: RES {t.res_mw:.1f} MW, GES {t.ges_mw:.0f} MW, batarya {t.bess_mw:.0f} MW / {t.bess_mwh:.0f} MWh "
            + ("(tam yıl MILP)" if tas["milp"] else "(kullanıcı tasarımı)"),
            "en": f"Selected design: wind {t.res_mw:.1f} MW, solar {t.ges_mw:.0f} MW, battery {t.bess_mw:.0f} MW / {t.bess_mwh:.0f} MWh "
            + ("(full-year MILP)" if tas["milp"] else "(user design)"),
        },
        {
            "tr": f"En iyi gelir yapısı: {YAPI_AD[en_iyi][0]} — E[NPV] {met[en_iyi]['e_npv']:+.1f} M$ (±{met[en_iyi]['se']:.2f} standart hata), "
            f"P(NPV>0) %{100 * met[en_iyi]['p_pozitif']:.0f}, CVaR %5 {met[en_iyi]['cvar5']:.1f} M$",
            "en": f"Best revenue structure: {YAPI_AD[en_iyi][1]} — E[NPV] {met[en_iyi]['e_npv']:+.1f} M$ (±{met[en_iyi]['se']:.2f} SE), "
            f"P(NPV>0) {100 * met[en_iyi]['p_pozitif']:.0f}%, CVaR 5% {met[en_iyi]['cvar5']:.1f} M$",
        },
        {
            "tr": f"Takvim ({kv.proje_asamasi}): COD P50 {takvim['cod_p50']}, P80 {takvim['cod_p80']}; YEKDEM için COD ≤ 2030 olasılığı %{100 * takvim['p_cod_2030_oncesi']:.0f}",
            "en": f"Schedule ({kv.proje_asamasi}): COD P50 {takvim['cod_p50']}, P80 {takvim['cod_p80']}; probability of COD ≤ 2030 for YEKDEM {100 * takvim['p_cod_2030_oncesi']:.0f}%",
        },
        {"tr": f"Karar: {k['tr']}", "en": f"Decision: {k['en']}"},
    ]
    if s3 and s3["yerlesim"] and s3["yerlesim"].get("alan_yetersiz"):
        y_ = s3["yerlesim"]
        tetik.insert(
            0,
            {
                "tr": f"Tasarımdaki {y_['N_istenen']} türbin {y_['yaricap_km']:.1f} km yarıçaplı alana asgari aralıkla sığmıyor; en fazla {y_['N']} "
                "türbin yerleştirildi ve üretim bu yerleşimin verimiyle hesaplandı. Yarıçapı büyütün ya da türbin sayısını azaltın.",
                "en": f"The design's {y_['N_istenen']} turbines do not fit in the {y_['yaricap_km']:.1f} km radius with minimum spacing; at most {y_['N']} "
                "were placed and energy uses that layout's efficiency. Enlarge the radius or reduce the turbine count.",
            },
        )
    if s3 and s3["yerlesim"]:
        y_ = s3["yerlesim"]
        nedenler.insert(
            1,
            {
                "tr": f"Türbin yerleşimi ({y_['yontem']}): {y_['N']} türbin, iç iz kaybı %{100 * y_['ic_iz']:.1f}, komşu santrallerden "
                f"%{100 * y_['dis_iz']:.1f}, konum kazancı (GWA) {y_['konum_kazanci']:.3f}",
                "en": f"Turbine layout ({y_['yontem_kodu']}): {y_['N']} turbines, internal wake loss {100 * y_['ic_iz']:.1f}%, from neighbouring "
                f"farms {100 * y_['dis_iz']:.1f}%, location gain (GWA) {y_['konum_kazanci']:.3f}",
            },
        )
    if s3 and s3["bakim"]:
        b_, i_ = s3["bakim"], s3["isletme"]
        mad = {"fsa": ("tam kapsamlı servis sözleşmesi (FSA)", "full-service agreement (FSA)"), "kendi": ("kendi bakımı", "self-perform")}
        m_ = mad.get(i_["model"], (i_["model"], i_["model"]))
        nedenler.insert(
            2,
            {
                "tr": f"İşletme ve bakım: {m_[0]}, O&M {i_['usd_mw_yil'] / 1e3:.1f} bin $/MW-yıl; enerji bazlı kullanılabilirlik %{100 * i_['kullanilabilirlik']:.1f} "
                f"(simülasyon %{100 * b_['A_enerji']:.1f}, strateji {b_['strateji']}); önleyici bakım çizelgesi yılda {b_['cizelge']['kazanc_bahar'] / 1e3:.1f} bin $ "
                "kayıp geliri azaltıyor",
                "en": f"Operations and maintenance: {m_[1]}, O&M {i_['usd_mw_yil'] / 1e3:.1f} k$/MW-yr; energy-based availability {100 * i_['kullanilabilirlik']:.1f}% "
                f"(simulation {100 * b_['A_enerji']:.1f}%, strategy {b_['strateji']}); the preventive schedule saves {b_['cizelge']['kazanc_bahar'] / 1e3:.1f} k$/yr "
                "of lost revenue",
            },
        )
    sure["toplam_analiz_s"] = time.perf_counter() - t0
    ek_tablo = {}
    if s3 and s3.get("turbinler") is not None:
        ek_tablo["turbinler"] = s3["turbinler"].reset_index(drop=True)
    if s3 and s3["bakim"]:
        ek_tablo["bakim_stratejileri"] = pd.DataFrame(s3["bakim"]["stratejiler"]).set_index("strateji")
    return {
        "ozet": {**ozet, "tetikleyiciler": tetik},
        "tablolar": {"gelir_yapilari": gelir_tablo, "yillik_uretim": yil, "yakinsama": pd.DataFrame(r["yakinsama"]), **ek_tablo},
        "grafikler": graf,
        "nedenler": nedenler,
        "sure": sure,
    }
