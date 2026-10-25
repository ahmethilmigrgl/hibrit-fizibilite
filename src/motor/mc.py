"""
Tam analiz Monte Carlo'su — v1 07 hattının (src/07_gelir_yapilari.py, 07_baz_vaka.py) sahaya genellenmiş, azaltılmış hali.

Belirsizlikler (v1 ile aynı): fiyat (log-AR(1), kriz/tavan), hava yılı (blok), kanibalizasyon, SFK doyum senaryoları ve ortak
batarya sürücüsü, sistem kaynaklı kesinti, CAPEX/OPEX, batarya bozunması, YEKDEM fiyatı.
v2 farkları:
  • RES model belirsizliği sahanın güven seviyesinden: m ~ LogNormal(−σ²/2, σ), σ = 1,4826 × medyan mutlak KF hatası /
    atlas ortalama KF (yüksek ~%9, orta ~%23, düşük ~%27); kalibre (v1) modda v1 üçgen dağılımı korunur.
  • COD simülasyon başına proje aşamasının takvim dağılımından (v1 CPM + Monte Carlo örnekleri) çekilir; NPV, erteleme
    yılları 0–3 arasında simülasyon bazında ara değerlenir. COD 31.12.2030'dan sonraysa YEKDEM hakkı yoktur (tüccar).
  • Simülasyon sayısı: başlangıçtan itibaren ikiye katlanır; en iyi yapının E[NPV] standart hatası hedefin altına inince durur.
"""

from __future__ import annotations

import os
from dataclasses import replace

import numpy as np
import pandas as pd

from src.ayarlar import KOK, deger
from src.risk.degerleme import irr_vektor, nakit_akislari
from src.risk.doyum import ornekle_doyum
from src.risk.monte_carlo import ornekle, ucgen_ters, yekdem_katilim
from src.risk.tasarim import Tasarim

KMAX = 3
COD_ORIJIN_AY = 15  # takvim örnekleri: 2026-10'dan ay; model COD 2028-01 = 15. ay
YEKDEM_SON_AY = 50  # 31.12.2030 ≈ 2026-10 + 50 ay
ATLAS_ORT_KF = 0.328


def res_sigma(guven: dict) -> float | None:
    if str(guven.get("seviye", "")).startswith("kalibre"):
        return None
    return float(1.4826 * guven["medyan_puan"] / 100 / ATLAS_ORT_KF)


def _kesinti(cfg, n, yillar, senaryo, rng, batarya: bool, kurtarma: float, deger_faktoru: float, yekdem: bool, carp_ozel):
    k = deger(cfg["kesinti"])
    k0 = ucgen_ters(rng.random(n), *k["oran_ucgen"])
    carp = carp_ozel if carp_ozel is not None else np.array([k["senaryo_carpani"][s] for s in senaryo])[:, None]
    gurultu = np.exp(k["yil_sd"] * rng.standard_normal((n, len(yillar))) - 0.5 * k["yil_sd"] ** 2)
    kappa = np.clip(k0[:, None] * carp * (1 + k["gunes_buyume"]) ** (yillar - 2026)[None] * gurultu, 0, 0.3)
    tazmin = rng.uniform(*k["tazmin_orani"], n)
    if yekdem:
        kur = 0.35 if batarya else 0.0
        return kappa * (1 - tazmin * deger_faktoru)[:, None] * (1 - kur), kappa * (1 - kur)
    kur = kurtarma if batarya else 0.0
    return kappa * deger_faktoru * (1 - tazmin)[:, None] * (1 - kur), kappa * (1 - (0.35 if batarya else 0.0))


def _kes(g: dict, kd: int, N: int) -> dict:
    return {k: (v[:, kd : kd + N] if np.ndim(v) == 2 else v) for k, v in g.items()}


def mc_calistir(
    o,
    t: Tasarim,
    tb_T: dict,
    tb_Y: dict | None,
    yapilar: list[str],
    cod_ay: np.ndarray,
    n: int,
    tohum: int,
    sigma: float | None,
    sfk: bool,
    tohum_saha: int | None = None,
    finans: bool = False,
    sozlesme: dict | None = None,
) -> dict:
    """tohum: ortak sürücüler (fiyat yolu, hava yılı, SFK/doyum, CAPEX/OPEX, kesinti, YEKDEM koridoru). tohum_saha (Faz F
    portföyü): sahaya özgü belirsizlikler (RES model hatası, bağlantı mesafesi) için ayrı tohum; verilmezse tohum.
    finans (v4 Faz H): GES model belirsizliği (m_ges) eklenir; gecikmesiz (kd = 0) yıllık CFADS/vergi/enerji ve kredi veren
    senaryosu için ortalama girdi yolları döndürülür.
    sozlesme (v4 Faz J): {"phi": (N + KMAX,) sözleşmeli pay yolu, "fiyat": (N + KMAX,) reel USD/MWh} → "sozlesme" yapısı
    (ör. YEKA: tüccar dönem + sabit fiyatlı alım dönemi; sözleşmeli yıllarda YEKDEM kesinti tazmini)."""
    ts = tohum if tohum_saha is None else tohum_saha
    cfg, v = o.cfg, o.v
    N = v.omur
    yil_ext = np.arange(o.yillar[0], o.yillar[0] + N + KMAX)
    mot = deger(cfg["v2"]["motor"])
    gx = ornekle(cfg, n, yil_ext, o.oran0, tohum)
    sur, gx = gx["suruculer"], gx["girdi"]
    if sigma is not None:  # sahanın güven seviyesinden RES model belirsizliği (v1 üçgeninin yerine)
        m_site = np.exp(np.random.default_rng(ts + 3).normal(-0.5 * sigma**2, sigma, n))
        gx["m"] = gx["m"] / sur["RES model çarpanı"][:, None] * m_site[:, None]
    # v3 Ö2: bağlantı mesafesi belirsizliği (TEİAŞ atanan / en yakın trafo oranı) → senaryo başına şebeke CAPEX çarpanı
    from src.cbs.baglanti import carpan_ornekle

    bg = (cfg.get("_saha", {}).get("altyapi") or {}).get("baglanti") or {}
    gx["capex_sebeke"] = carpan_ornekle(bg.get("belirsizlik"), n, ts + 13)
    if finans:  # v4 Faz H: GES üretim çarpanı — kalıcı (ışınım veri seti + PV modeli) × yıllık kullanılabilirlik
        vv = deger(cfg["v4"]["verim"])
        sg = float(np.hypot(vv["gunes_veri_seti"], vv["gunes_model"]))
        rg = np.random.default_rng(ts + 17)
        kalici = np.exp(rg.normal(-0.5 * sg**2, sg, n))
        gx["m_ges"] = kalici[:, None] * (1 + vv["gunes_kullanilabilirlik_yillik"] * rg.standard_normal((n, len(yil_ext))))
        gx["m_disdeger"] = True
    W = tb_T["T"].shape[0]
    if W < o.u.res.shape[0]:
        gx["w"] = np.random.default_rng(tohum + 4).integers(0, W, gx["w"].shape)
    fo = float(pd.read_csv(KOK / "results" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
    dy = ornekle_doyum(cfg, n, yil_ext, fo, tohum)
    gx["a"] = dy["a"] if sfk else np.zeros_like(dy["a"])
    os_ = deger(cfg["ortak_surucu"])
    emme = lambda mw, yil: np.clip(
        mw * os_["sure_saat"] * os_["fazla_gun"] * os_["verim"] / (os_["fazla_2026_twh"] * 1e6 * (1 + os_["fazla_buyume"]) ** (yil - 2026)),
        0,
        1,
    )
    a_abs = emme(dy["kurulu_mw"], yil_ext[None, :])
    carp_ozel = (1 - a_abs) / (1 - float(emme(1000.0, 2026)))
    gx["h"] = gx["h"] + (o.oran0 - gx["h"]) * a_abs * os_["kanibalizasyon_geri_alma"]
    pil = t.bess_mw > 0.5
    kw = dict(kurtarma=mot["kesinti_kurtarma"], deger_faktoru=mot["kesinti_deger_faktoru"], carp_ozel=carp_ozel)
    kes_m = _kesinti(cfg, n, yil_ext, dy["senaryo"], np.random.default_rng(tohum + 11), pil, yekdem=False, **kw)
    kes_y = _kesinti(cfg, n, yil_ext, dy["senaryo"], np.random.default_rng(tohum + 11), pil, yekdem=True, **kw)
    yk = deger(cfg["yekdem"])
    pi = deger(cfg["finans"]["abd_enflasyonu"])
    yk_nom = 10 * ucgen_ters(np.random.default_rng(tohum + 7).random(n), yk["taban_usd_sent"], yk["tepe_usd_sent"], yk["tavan_usd_sent"])
    yk_reel = yk_nom[:, None] / (1 + pi) ** (yil_ext - 2026)[None]
    c_y = replace(o.c, ppa_pay=1.0, ppa_vade=yk["sure_yil"], ppa_fiyat=float(yk_reel[:, : yk["sure_yil"]].mean()))
    esik = deger(cfg["yekdem_opsiyon"])["esik_carpani"]
    npv_kd: dict[str, np.ndarray] = {}
    ek: dict[str, dict] = {}
    fin: dict[str, dict] = {}
    for y in yapilar:
        dizi = np.zeros((n, KMAX + 1))
        for kd in range(KMAX + 1):
            gk = _kes(gx, kd, N)
            gk["capex_bess"] = gx["capex_bess"] * (1 - deger(cfg["stres_testi"]["bess_capex_dususu"])) ** kd
            sl = slice(kd, kd + N)
            if y == "yekdem_opsiyon":
                katil = yekdem_katilim(cfg, gx["L"], yk_reel, kd, N, esik, yk["sure_yil"])
                gk.update(
                    {
                        "phi": katil.astype(float),
                        "ip": katil.astype(int),
                        "ppa_fiyat": yk_reel[:, sl],
                        "desarj_sozlesmeli": True,
                        "kesinti_gelir": np.where(katil, kes_y[0][:, sl], kes_m[0][:, sl]),
                        "kesinti_enerji": np.where(katil, kes_y[1][:, sl], kes_m[1][:, sl]),
                    }
                )
                r = nakit_akislari(replace(t, ppa=True), tb_Y, c_y, gk)
                if kd == 0:
                    ek[y] = {"katilim_yil": katil[:, : yk["sure_yil"]].mean(0).round(3).tolist()}
            elif y == "sozlesme":
                ph = np.broadcast_to(np.asarray(sozlesme["phi"], float)[sl], (n, N))
                gk.update(
                    {
                        "phi": ph,
                        "ppa_fiyat": np.broadcast_to(np.asarray(sozlesme["fiyat"], float)[sl], (n, N)),
                        "kesinti_gelir": np.where(ph > 0.5, kes_y[0][:, sl], kes_m[0][:, sl]),
                        "kesinti_enerji": np.where(ph > 0.5, kes_y[1][:, sl], kes_m[1][:, sl]),
                    }
                )
                r = nakit_akislari(t, tb_T, o.c, gk)
            else:
                gk.update({"kesinti_gelir": kes_m[0][:, sl], "kesinti_enerji": kes_m[1][:, sl]})
                tt = t
                if y == "ppa":
                    gk["tuccar_dispatch"] = True
                    tt = replace(t, ppa=True)
                r = nakit_akislari(tt, tb_T, o.c, gk)
            dizi[:, kd] = r["npv"] * (1 + v.wacc) ** -kd / 1e6
            if kd == 0 and finans:
                fin.setdefault(y, {}).update({a: r[a] for a in ("cfads", "vergi", "capex_top", "satilan")})
            if kd == 0:
                ek.setdefault(y, {})["irr_p50"] = float(np.nanpercentile(irr_vektor(r["sna"]), 50))
                ek[y]["capex_musd"] = float(np.mean(r["capex_top"]) / 1e6)
        npv_kd[y] = dizi
    kk = np.clip((cod_ay - COD_ORIJIN_AY) / 12, 0, KMAX)
    k0 = np.floor(kk).astype(int)
    w = kk - k0
    k1 = np.minimum(k0 + 1, KMAX)
    idx = np.arange(n)
    sonuc = {}
    for y, d in npv_kd.items():
        x = (1 - w) * d[idx, k0] + w * d[idx, k1]
        if y == "yekdem_opsiyon" and "tuccar" in npv_kd:  # COD 2030 sonrası: YEKDEM hakkı yok → tüccar
            xt = (1 - w) * npv_kd["tuccar"][idx, k0] + w * npv_kd["tuccar"][idx, k1]
            x = np.where(cod_ay > YEKDEM_SON_AY, xt, x)
        sonuc[y] = x
    return {
        "npv": sonuc,
        "ek": ek,
        "senaryo": dy["senaryo"],
        "m": gx["m"][:, 0],
        # ortak sürücülerin senaryo özetleri (Faz F çeşitlendirme ayrıştırması)
        "ortak": {"L10": gx["L"][:, :10].mean(1), "capex_res": np.asarray(gx["capex_res"]), "w10": gx["w"][:, :10]},
        "saha": {"capex_sebeke": gx["capex_sebeke"]},
        **(
            {
                "finans": {
                    "yapilar": fin,
                    # kredi veren senaryosu için gecikmesiz ortalama yollar (N,)
                    "ortalama": {
                        "L": gx["L"][:, :N].mean(0),
                        # kredi veren fiyat yolu: tavanlı kriz yılları hariç ortalama (tavanlı kriz geliri artırmaz)
                        "L_tavansiz": np.nanmean(np.where(gx["tavan"][:, :N], np.nan, gx["L"][:, :N]), axis=0),
                        "h": gx["h"][:, :N].mean(0),
                        "a": gx["a"][:, :N].mean(0),
                        "kes_m": (kes_m[0][:, :N].mean(0), kes_m[1][:, :N].mean(0)),
                        "kes_y": (kes_y[0][:, :N].mean(0), kes_y[1][:, :N].mean(0)),
                        "yk_reel": yk_reel[:, :N].mean(0),
                    },
                }
            }
            if finans
            else {}
        ),
    }


def metrik(x: np.ndarray) -> dict:
    kotu = np.sort(x)[: max(1, int(0.05 * len(x)))]
    return {
        "e_npv": float(x.mean()),
        "se": float(x.std(ddof=1) / np.sqrt(len(x))),
        "p_pozitif": float((x > 0).mean()),
        "cvar5": float(kotu.mean()),
        "p10": float(np.percentile(x, 10)),
        "p50": float(np.percentile(x, 50)),
        "p90": float(np.percentile(x, 90)),
        "n": len(x),
    }


def yakinsayan_mc(
    o, t, tb_T, tb_Y, yapilar, cod_kaynak: np.ndarray, sigma, sfk, tohum: int = 42, ilerleme=None, finans: bool = False
) -> dict:
    mot = deger(o.cfg["v2"]["motor"])
    n = mot["mc_baslangic"]
    if os.environ.get("MOTOR_KUCUK") == "1":  # yalnız testler
        n, mot = 500, {**mot, "mc_azami": 500}
    gecmis = []
    while True:
        cod = np.random.default_rng(tohum + 99).choice(cod_kaynak, n, replace=True)
        r = mc_calistir(o, t, tb_T, tb_Y, yapilar, cod, n, tohum, sigma, sfk, finans=finans)
        met = {y: metrik(x) for y, x in r["npv"].items()}
        en_iyi = max(met, key=lambda y: met[y]["e_npv"])
        gecmis.append({"n": n, **{f"E[{y}]": met[y]["e_npv"] for y in met}, "SE_en_iyi": met[en_iyi]["se"]})
        if ilerleme:
            ilerleme(0.85, f"Monte Carlo n = {n}, standart hata {met[en_iyi]['se']:.2f} M$")
        if met[en_iyi]["se"] <= mot["mc_hedef_se_musd"] or n >= mot["mc_azami"]:
            return {**r, "metrik": met, "en_iyi": en_iyi, "yakinsama": gecmis, "cod": cod}
        n *= 2
