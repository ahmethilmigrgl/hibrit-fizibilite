"""
Proje değerleme çekirdeği: proje_degerle(konfig, varsayimlar, fiyat_senaryosu, uretim_profili)

Zaman çizelgesi (yıl indeksi y = 0, 1, 2, ...; nakit akışları yıl sonunda, t = 0 = FID yılı başı):
    y = 0 … nb−1       : inşaat (CAPEX takvimi)
    y = nb … nb+N−1    : işletme yılları k = 1 … N  (takvim yılı = başlangıç_yılı + k − 1)
    İskonto çarpanı    : (1 + WACC)^−(y+1)

Üretim ve satış (her işletme yılı, her hava yılı w, her fiyat şekli yılı s, her saat t):
    G_t = ges_mw · ges_kf_t · (1−δ_ges)^(k−1)   ;   R_t = res_mw · res_kf_t · (1−δ_res)^(k−1)
    B_t = batarya net enjeksiyonu (Aşama 4 dispatch kancası; yoksa 0)
    Satılan_t = min(G_t + R_t + B_t, şebeke_mw)       Kesilen_t = G_t + R_t + B_t − Satılan_t
    Kesinti teknolojilere üretim payıyla dağıtılır (pro-rata).
    Beklenen değer: 10 hava yılı × 2 fiyat şekli yılının ortalaması.

Gelir = Σ_t Satılan_t · p_t  − eşzamanlılık düzeltmesi (RES) − dengesizlik maliyeti
Vergi = %25 × max(0, FAVÖK − amortisman − devreden zarar), zarar 5 yıl taşınır (kaldıraçsız)
Serbest nakit akışı = FAVÖK − vergi − augmentation − söküm − CAPEX
NPV  = Σ_y SNA_y / (1+WACC)^(y+1);  IRR: NPV = 0 yapan oran (vergi sonrası, kaldıraçsız, reel)
LCOE = Σ_y (CAPEX + OPEX + augmentation + söküm)_y·DF_y / Σ_y Enerji_y·DF_y  (vergi öncesi, reel)

Tüm tutarlar reel USD (2026).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import numpy_financial as npf
import pandas as pd

from src.ayarlar import deger
from src.finans.fiyat_senaryosu import FiyatSenaryosu
from src.finans.veri import UretimProfili


@dataclass
class Konfig:
    ges_mw: float = 0.0
    res_mw: float = 0.0
    bess_mw: float = 0.0
    bess_mwh: float = 0.0
    sebeke_mw: float = 50.0

    @classmethod
    def sozlukten(cls, d: dict) -> "Konfig":
        return cls(**{k: float(v) for k, v in d.items()})


@dataclass
class Varsayimlar:
    """config.yaml'dan okunan finansal ve teknik varsayımlar (duyarlılık için kopyalanıp değiştirilebilir)."""
    insaat_suresi: int
    capex_takvimi: list[float]
    omur: int
    wacc: float
    vergi: float
    zarar_mahsup: int
    amortisman: dict
    sokum: dict
    capex_ges: float
    capex_res: float
    capex_bess_enerji: float
    capex_bess_guc: float
    capex_sebeke: float
    opex_ges: float
    opex_res: float
    arazi_ges: float
    arazi_res: float
    opex_bess_oran: float
    sigorta_oran: float
    teias_kapasite: float
    teias_enerji: float
    dengesizlik: dict
    degr_ges: float
    degr_res: float
    omur_ges: int
    omur_res: int
    omur_bess: int
    augmentation: dict
    eszamanlilik_res: float
    bess_yenileme: dict
    bess_yipranma: float
    ekonomik_kesinti: bool = True
    capex_carpani: float = 1.0
    res_uretim_carpani: float = 1.0
    ges_uretim_carpani: float = 1.0

    @classmethod
    def configten(cls, cfg: dict) -> "Varsayimlar":
        p, f, t = cfg["proje"], cfg["finans"], cfg["teknoloji"]
        return cls(
            insaat_suresi=deger(p["insaat_suresi"]), capex_takvimi=deger(p["capex_takvimi"]), omur=deger(p["omur"]),
            wacc=deger(f["wacc_reel"]), vergi=deger(f["kurumlar_vergisi"]), zarar_mahsup=deger(f["zarar_mahsup_suresi"]),
            amortisman=deger(f["amortisman_suresi"]), sokum=deger(f["sokum_net"]),
            capex_ges=deger(t["ges"]["capex"]), capex_res=deger(t["res"]["capex"]),
            capex_bess_enerji=deger(t["bess"]["capex_enerji"]), capex_bess_guc=deger(t["bess"]["capex_guc"]),
            capex_sebeke=deger(t["sebeke"]["capex"]),
            opex_ges=deger(t["ges"]["opex_sabit"]), opex_res=deger(t["res"]["opex_sabit"]),
            arazi_ges=deger(t["ges"]["arazi"]), arazi_res=deger(t["res"]["arazi"]),
            opex_bess_oran=deger(t["bess"]["opex_oran"]), sigorta_oran=deger(t["ortak"]["sigorta"]),
            teias_kapasite=deger(t["sebeke"]["teias_kapasite_bedeli"]), teias_enerji=deger(t["sebeke"]["teias_enerji_bedeli"]),
            dengesizlik=deger(t["ortak"]["dengesizlik"]),
            degr_ges=deger(t["ges"]["degradasyon"]), degr_res=deger(t["res"]["degradasyon"]),
            omur_ges=deger(t["ges"]["omur"]), omur_res=deger(t["res"]["omur"]), omur_bess=deger(t["bess"]["omur"]),
            augmentation=deger(t["bess"]["augmentation"]),
            eszamanlilik_res=deger(cfg["fiyat_senaryolari"]["eszamanlilik_duzeltmesi"])["res"],
            bess_yenileme=deger(t["bess"]["yenileme"]), bess_yipranma=deger(t["bess"]["yipranma_maliyeti"]),
        )


@dataclass
class Sonuc:
    yillik: pd.DataFrame
    npv: float
    irr: float
    lcoe: dict
    ozet: dict = field(default_factory=dict)


# Batarya kancası: f(G, R, fiyat, konfig, varsayimlar) → (şebekeye verilen x, deşarj d, santralden şarj c),
# her biri (yıl, hava, şekil, saat) şeklinde [MW]
BessDispatch = Callable[[np.ndarray, np.ndarray, np.ndarray, Konfig, Varsayimlar], tuple]


def _vergi_hesapla(matrah_oncesi: np.ndarray, oran: float, mahsup: int) -> np.ndarray:
    """Yıllık vergi; zararlar 'mahsup' yıl ileri taşınır (FIFO)."""
    vergi = np.zeros_like(matrah_oncesi)
    zararlar: list[list[float]] = []   # [kalan_tutar, kalan_yil]
    for i, m in enumerate(matrah_oncesi):
        zararlar = [[z, y - 1] for z, y in zararlar if y - 1 >= 0 and z > 0]
        if m <= 0:
            zararlar.append([-m, mahsup])
            continue
        kalan = m
        for z in zararlar:
            kullan = min(z[0], kalan)
            z[0] -= kullan
            kalan -= kullan
        vergi[i] = oran * kalan
    return vergi


def proje_degerle(konfig: Konfig | dict, v: Varsayimlar, fiyat: FiyatSenaryosu, uretim: UretimProfili,
                  bess_dispatch: BessDispatch | None = None, gelir_carpani: float = 1.0) -> Sonuc:
    k = konfig if isinstance(konfig, Konfig) else Konfig.sozlukten(konfig)
    nb, N = v.insaat_suresi, v.omur
    yil_isl = np.arange(1, N + 1)                                          # işletme yılı k
    takvim = np.array(fiyat.yillar[:N])

    # ------------------------------------------------------------- üretim (yıl, hava, saat)
    deg_g = (1 - v.degr_ges) ** (yil_isl - 1) * (yil_isl <= v.omur_ges)
    deg_r = (1 - v.degr_res) ** (yil_isl - 1) * (yil_isl <= v.omur_res)
    G = k.ges_mw * v.ges_uretim_carpani * deg_g[:, None, None] * uretim.ges[None]          # (N, W, 8760)
    R = k.res_mw * v.res_uretim_carpani * deg_r[:, None, None] * uretim.res[None]
    P = fiyat.fiyatlar[:N]                                                                 # (N, S, 8760)

    # Satış ve kesinti. Ekonomik kesinti: fiyat < TEİAŞ enerji bedeli olan saatlerde satılmaz
    # (santral bu saatlerde değişken maliyetinin altında satmak yerine üretimini keser).
    if bess_dispatch is not None and k.bess_mw > 0:
        Gx, Rx = G[:, :, None, :], R[:, :, None, :]
        # Kanca: (şebekeye verilen x, deşarj d, santralden şarj c), şekil (N, W, S, 8760)
        x, d, c = bess_dispatch(Gx, Rx, P[:, None, :, :], k, v)
        dogrudan = np.clip(x - d, 0, None)                            # santralden doğrudan satılan
        pay_g = np.divide(Gx, Gx + Rx, out=np.zeros_like(x), where=(Gx + Rx) > 0)
        Pb = P[:, None]
        sat_ges = (dogrudan * pay_g).sum(-1).mean(axis=(1, 2))
        sat_res = (dogrudan * (1 - pay_g)).sum(-1).mean(axis=(1, 2))
        gelir_ges = (dogrudan * pay_g * Pb).sum(-1).mean(axis=(1, 2))
        gelir_res = (dogrudan * (1 - pay_g) * Pb).sum(-1).mean(axis=(1, 2))
        gelir_bess = (d * Pb).sum(-1).mean(axis=(1, 2))
        desarj = d.sum(-1).mean(axis=(1, 2))
        enerji_sat = x.sum(-1).mean(axis=(1, 2))
        kesilen = np.clip(Gx + Rx - dogrudan - c, 0, None).sum(-1).mean(axis=(1, 2))
        bess_sat = desarj
    else:
        top = G + R
        tavan = np.minimum(top, k.sebeke_mw)                                               # (N, W, 8760)
        pay_g = np.divide(G, top, out=np.zeros_like(top), where=top > 0)
        S = P.shape[1]
        gelir_ges = gelir_res = sat_ges = sat_res = enerji_sat = kesilen = 0.0
        for s_ in range(S):
            satis_var = (P[:, s_] > v.teias_enerji)[:, None, :] if v.ekonomik_kesinti else True
            satilan = tavan * satis_var
            sg, sr = satilan * pay_g, satilan * (1 - pay_g)
            gelir_ges = gelir_ges + (sg * P[:, s_][:, None]).sum(-1).mean(1) / S
            gelir_res = gelir_res + (sr * P[:, s_][:, None]).sum(-1).mean(1) / S
            sat_ges = sat_ges + sg.sum(-1).mean(1) / S
            sat_res = sat_res + sr.sum(-1).mean(1) / S
            enerji_sat = enerji_sat + satilan.sum(-1).mean(1) / S
            kesilen = kesilen + (top - satilan).sum(-1).mean(1) / S
        gelir_bess = desarj = bess_sat = np.zeros(N)
    uretim_ges = G.sum(-1).mean(1)
    uretim_res = R.sum(-1).mean(1)
    ort_fiyat = P.mean(axis=(1, 2))

    # Eşzamanlılık düzeltmesi: hava ve fiyat yılları farklı kaynaklı → RES'in gerçek (rüzgârlı saatte düşen fiyat)
    # ilişkisi kayboluyor; Aşama 2'de ölçülen fark RES satılan enerjisinden düşülür
    esz = v.eszamanlilik_res * ort_fiyat * sat_res
    gelir_ges = gelir_ges * gelir_carpani
    gelir_res = (gelir_res - esz) * gelir_carpani
    gelir_bess = gelir_bess * gelir_carpani
    sat_ges, sat_res, enerji_sat = sat_ges * gelir_carpani, sat_res * gelir_carpani, enerji_sat * gelir_carpani
    gelir = gelir_ges + gelir_res + gelir_bess
    dengesizlik = v.dengesizlik["ges"] * gelir_ges + v.dengesizlik["res"] * gelir_res

    # ------------------------------------------------------------- maliyetler
    cc = v.capex_carpani
    capex = {
        "ges": k.ges_mw * v.capex_ges * cc,
        "res": k.res_mw * v.capex_res * cc,
        "bess": (k.bess_mw * v.capex_bess_guc + k.bess_mwh * v.capex_bess_enerji) * cc,
        "sebeke": (k.sebeke_mw * v.capex_sebeke * cc) if (k.ges_mw + k.res_mw + k.bess_mw) > 0 else 0.0,
    }
    capex_top = sum(capex.values())
    aktif_g = yil_isl <= v.omur_ges
    aktif_r = yil_isl <= v.omur_res
    yenile = v.bess_yenileme["aktif"] and k.bess_mwh > 0 and v.omur_bess < N
    aktif_b = np.ones(N, bool) if yenile else (yil_isl <= v.omur_bess)
    opex_ges = (v.opex_ges + v.arazi_ges) * k.ges_mw * aktif_g
    opex_res = (v.opex_res + v.arazi_res) * k.res_mw * aktif_r
    opex_bess = v.opex_bess_oran * capex["bess"] * aktif_b
    sigorta = v.sigorta_oran * capex_top * np.ones(N)
    teias = v.teias_kapasite * k.sebeke_mw * np.ones(N) + v.teias_enerji * enerji_sat
    yipranma = v.bess_yipranma * desarj                                   # kullanıma bağlı batarya yıpranması
    opex = opex_ges + opex_res + opex_bess + sigorta + teias + yipranma

    aug = np.zeros(N)
    if k.bess_mwh > 0:
        a = v.augmentation
        yillar = list(a["yillar"]) + ([y + v.omur_bess for y in a["yillar"]] if yenile else [])
        for y in yillar:
            if y <= N and (yenile or y <= v.omur_bess) and y != v.omur_bess:
                aug[y - 1] += a["oran"] * k.bess_mwh * v.capex_bess_enerji * cc * (1 - a["maliyet_dususu_yillik"]) ** y
        if yenile:   # ömür sonunda tam yenileme (maliyet düşüşüyle)
            aug[v.omur_bess - 1] += capex["bess"] * (1 - v.bess_yenileme["maliyet_dususu_yillik"]) ** v.omur_bess
    sokum = np.zeros(N)
    sokum[min(N, v.omur_ges) - 1] += v.sokum["ges"] * k.ges_mw
    sokum[min(N, v.omur_res) - 1] += v.sokum["res"] * k.res_mw
    sokum[(N if yenile else min(N, v.omur_bess)) - 1] += v.sokum["bess"] * k.bess_mwh

    favok = gelir - dengesizlik - opex

    # ------------------------------------------------------------- vergi (kaldıraçsız)
    amort = np.zeros(N)
    for kalem, tutar in capex.items():
        sure = v.amortisman["sebeke" if kalem == "sebeke" else kalem]
        amort[:sure] += tutar / sure
    # Augmentation ve söküm vergi açısından gider yazılır (basitleştirme)
    matrah = favok - amort - aug - sokum
    vergi = _vergi_hesapla(matrah, v.vergi, v.zarar_mahsup)

    # ------------------------------------------------------------- zaman çizelgesi ve göstergeler
    T = nb + N
    capex_akisi = np.zeros(T)
    capex_akisi[:nb] = capex_top * np.array(v.capex_takvimi)
    isl = slice(nb, T)
    sna = -capex_akisi.copy()
    sna[isl] += favok - vergi - aug - sokum
    df = (1 + v.wacc) ** -(np.arange(T) + 1)
    npv = float((sna * df).sum())
    irr = float(npf.irr(sna)) if np.any(sna > 0) else float("nan")

    # LCOE (vergi öncesi): maliyetlerin bugünkü değeri / enerjinin bugünkü değeri
    df_isl = df[isl]
    pay = {"ges": k.ges_mw, "res": k.res_mw}
    top_mw = max(k.ges_mw + k.res_mw, 1e-9)
    lcoe = {}
    for tek, ur, opx in [("ges", uretim_ges, opex_ges), ("res", uretim_res, opex_res)]:
        if pay[tek] == 0:
            lcoe[tek] = float("nan")
            continue
        sebeke_payi = pay[tek] / top_mw
        maliyet = (capex[tek] + capex["sebeke"] * sebeke_payi) * (capex_akisi[:nb] / max(capex_top, 1e-9) * df[:nb]).sum()
        isl_maliyet = opx + sebeke_payi * v.teias_kapasite * k.sebeke_mw + v.sigorta_oran * (capex[tek] + capex["sebeke"] * sebeke_payi)
        isl_maliyet = isl_maliyet + v.teias_enerji * ur + (v.sokum[tek] * pay[tek]) * (np.arange(1, N + 1) == min(N, getattr(v, f"omur_{tek}")))
        lcoe[tek] = float((maliyet + (isl_maliyet * df_isl).sum()) / (ur * df_isl).sum())
    toplam_maliyet = (capex_akisi * df).sum() + ((opex + aug + sokum) * df_isl).sum()
    lcoe["hibrit_satilan"] = float(toplam_maliyet / (enerji_sat * df_isl).sum()) if enerji_sat.sum() > 0 else float("nan")

    yillik = pd.DataFrame({
        "İşletme yılı": yil_isl, "Takvim yılı": takvim,
        "GES üretim [MWh]": uretim_ges, "RES üretim [MWh]": uretim_res,
        "Kesilen [MWh]": kesilen, "Satılan [MWh]": enerji_sat,
        "Ort. PTF [USD/MWh]": ort_fiyat,
        "GES geliri [USD]": gelir_ges, "RES geliri [USD]": gelir_res, "BESS geliri [USD]": gelir_bess,
        "BESS deşarj [MWh]": desarj, "BESS'ten satılan [MWh]": bess_sat,
        "Eşzamanlılık düzeltmesi [USD]": -esz * gelir_carpani, "Toplam gelir [USD]": gelir,
        "Dengesizlik [USD]": -dengesizlik, "İşletme-bakım + arazi [USD]": -(opex_ges + opex_res + opex_bess),
        "BESS yıpranma [USD]": -yipranma,
        "Sigorta [USD]": -sigorta, "TEİAŞ bedelleri [USD]": -teias, "FAVÖK [USD]": favok,
        "Amortisman [USD]": -amort, "BESS augmentation + yenileme [USD]": -aug, "Söküm [USD]": -sokum,
        "Vergi [USD]": -vergi, "Serbest nakit akışı [USD]": favok - vergi - aug - sokum,
    })
    sat_top = enerji_sat.sum()
    ozet = {
        "CAPEX [M USD]": capex_top / 1e6,
        "CAPEX kalemleri [M USD]": {kk: vv / 1e6 for kk, vv in capex.items()},
        "Satılan enerji, yıl 1 [GWh]": enerji_sat[0] / 1e3,
        "Kesinti oranı [%]": 100 * kesilen.sum() / max((uretim_ges + uretim_res).sum(), 1e-9),
        "Yakalanan fiyat [USD/MWh]": gelir.sum() / sat_top if sat_top > 0 else float("nan"),
        "Ort. PTF [USD/MWh]": float(ort_fiyat.mean()),
        "GES yakalanan [USD/MWh]": gelir_ges.sum() / sat_ges.sum() if sat_ges.sum() > 0 else float("nan"),
        "RES yakalanan [USD/MWh]": gelir_res.sum() / sat_res.sum() if sat_res.sum() > 0 else float("nan"),
        "nakit_akisi": sna, "capex_akisi": capex_akisi, "favok": favok, "vergi": vergi,
        "amortisman": amort, "aug": aug, "sokum": sokum, "capex_top": capex_top,
    }
    return Sonuc(yillik=yillik, npv=npv, irr=irr, lcoe=lcoe, ozet=ozet)


def p90_carpani(konfig: Konfig | dict, uretim: UretimProfili, v: Varsayimlar | None = None) -> float:
    """
    Konfigürasyonun satılan enerjisi için 1 yıllık P90 / ortalama oranı (normal dağılım varsayımı):
    1 − 1,282 × (σ / ortalama), σ: 10 hava yılının yıllık satılan enerjisinin örneklem standart sapması.
    Kesinti iyi yılları kırptığı için oran konfigürasyona bağlıdır.
    """
    k = konfig if isinstance(konfig, Konfig) else Konfig.sozlukten(konfig)
    gc = v.ges_uretim_carpani if v else 1.0
    rc = v.res_uretim_carpani if v else 1.0
    satilan = np.minimum(k.ges_mw * gc * uretim.ges + k.res_mw * rc * uretim.res, k.sebeke_mw).sum(axis=1)
    return float(1 - 1.2816 * satilan.std(ddof=1) / satilan.mean())
