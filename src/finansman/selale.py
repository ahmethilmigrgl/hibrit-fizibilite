"""
Nakit şelalesi (cash waterfall) — Monte Carlo senaryoları üzerinde vektörize, yıllık, nominal USD.

Borç FID'de kredi veren senaryosuyla boyutlanır (deterministik servis planı); senaryoların gerçekleşen CFADS'si şelaleden geçer:
    1) kullanılabilir nakit = CFADS + faiz vergi kalkanı
    2) borç servisi (önceki yıldan ödenmemiş servis varsa faiziyle birlikte)
    3) eksik kalırsa borç servisi rezerv hesabından (DSRA) çekilir; DSRA da yetmezse → ödeme temerrüdü (gecikmiş servis birikir)
    4) DSRA hedefine (sonraki yılın servisinin dsra_ay/12'si) tamamlanır
    5) kâr dağıtım testi: DSCR < kilit_dscr ya da gecikmiş servis varsa nakit kilit hesabında kalır; test geçilince serbest kalır
    6) kalan nakit öz kaynağa dağıtılır. Vade sonunda DSRA ve kilit hesabı serbest kalır.
DSRA'nın ilk dolumu COD'da öz kaynakla yapılır. COD gecikmesi şelalede yoktur (borç metrikleri COD'a koşullu).
"""

from __future__ import annotations

import warnings
from dataclasses import replace

import numpy as np

from src.finansman.borc_lp import BorcLP
from src.risk.degerleme import irr_vektor


def selale(
    cfads: np.ndarray,
    vergi: np.ndarray,
    capex_top: np.ndarray,
    capex_takvimi: list[float],
    borc: BorcLP,
    enf: np.ndarray,
    faiz: float,
    vergi_orani: float,
    dsra_ay: float,
    kilit_dscr: float,
    ozkaynak_maliyeti: float,
) -> dict:
    """
    cfads, vergi: (n, N) reel USD (proje, kaldıraçsız); capex_top: (n,) reel; enf: (N,) reel → nominal çarpanı (işletme yılları).
    Döndürür: olasılıklar, DSCR dağılımı, öz kaynak IRR'ı ve NPV'si (reel) ve yıllık özetler.
    """
    n, N = cfads.shape
    nb = len(capex_takvimi)
    s = borc.servis
    hedef = np.r_[s[1:], 0.0] * dsra_ay / 12  # yıl k sonunda tutulacak DSRA
    cf_nom = cfads * enf[None, :]
    kalkan = np.minimum(borc.faiz[None, :] * vergi_orani, np.clip(vergi, 0, None) * enf[None, :])
    dsra = np.full(n, s[0] * dsra_ay / 12)
    dsra0 = dsra.copy()
    gecikmis = np.zeros(n)
    kilitli = np.zeros(n)
    dagitim = np.zeros((n, N))
    dscr = np.full((n, N), np.inf)
    temerrut = np.zeros(n, bool)
    dsra_kullanim = np.zeros(n, bool)
    kilit_yil = np.zeros(n, int)
    for k in range(N):
        nakit = cf_nom[:, k] + kalkan[:, k]
        borclu = s[k] + gecikmis * (1 + faiz)
        if s[k] > 0:
            dscr[:, k] = nakit / s[k]
        ode = np.clip(np.minimum(nakit, borclu), 0, None)
        nakit = nakit - ode
        eksik = borclu - ode
        cek = np.minimum(dsra, eksik)
        dsra = dsra - cek
        dsra_kullanim |= cek > 1e-6
        eksik = eksik - cek
        gecikmis = eksik
        temerrut |= eksik > 1e-6 * max(s.max(), 1.0)
        # Negatif nakit (ör. batarya yenileme yılı, borç sonrası): öz kaynak karşılar → dağıtım negatif olabilir
        tamamla = np.clip(np.minimum(np.clip(nakit, 0, None), hedef[k] - dsra), 0, None)
        dsra = dsra + tamamla
        nakit = nakit - tamamla
        serbest = np.clip(dsra - hedef[k], 0, None) * (gecikmis <= 0)
        dsra = dsra - serbest
        nakit = nakit + serbest
        kilit = (s[k] > 0) & ((dscr[:, k] < kilit_dscr) | (gecikmis > 0))
        kilit_yil += kilit
        pozitif = np.clip(nakit, 0, None)
        kilitli = kilitli + np.where(kilit, pozitif, 0.0)
        nakit = np.where(kilit, nakit - pozitif, nakit + kilitli)
        kilitli = np.where(kilit, kilitli, 0.0)
        dagitim[:, k] = nakit
    dagitim[:, -1] += kilitli + dsra  # ömür sonu: kalan hesaplar serbest
    # Reel öz kaynak akışı: inşaat yıllarında CAPEX − borç çekişi (CAPEX takvimiyle orantılı), COD'da DSRA dolumu
    pi1 = enf[0] ** (1 / (nb + 1))  # enf_k = (1 + π)^(nb + k) → 1 + π
    borc_reel = borc.borc_nom / pi1**nb
    takvim = np.asarray(capex_takvimi, float)
    akis = np.zeros((n, nb + N))
    akis[:, :nb] = (-capex_top[:, None] + borc_reel) * takvim[None, :]
    akis[:, nb - 1] -= dsra0 / pi1**nb
    akis[:, nb:] = dagitim / enf[None, :]
    irr = irr_vektor(akis)
    df = (1 + ozkaynak_maliyeti) ** -(np.arange(nb + N) + 1)
    V = borc.vade
    dmin = dscr[:, :V].min(1) if V > 0 else np.full(n, np.inf)
    with warnings.catch_warnings():  # servisi 0 olan yıllar (ör. CFADS ≤ 0) tüm senaryolarda NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        d_ = np.where(np.isfinite(dscr[:, :V]), dscr[:, :V], np.nan)
        dy10 = np.nanpercentile(d_, 10, axis=0).tolist() if V else []
        dy50 = np.nanpercentile(d_, 50, axis=0).tolist() if V else []
    return {
        "p_temerrut": float(temerrut.mean()),
        "p_dsra_kullanim": float(dsra_kullanim.mean()),
        "p_kilit": float((kilit_yil > 0).mean()),
        "e_kilit_yil": float(kilit_yil.mean()),
        "dscr_min_p5": float(np.percentile(dmin, 5)),
        "dscr_min_p50": float(np.percentile(dmin, 50)),
        "irr_p10": float(np.nanpercentile(irr, 10)),
        "irr_p50": float(np.nanpercentile(irr, 50)),
        "irr_p90": float(np.nanpercentile(irr, 90)),
        "ozkaynak_npv_e": float((akis @ df).mean()),
        "ozkaynak_tutari_e": float(-np.clip(akis[:, :nb], None, 0).sum(1).mean()),
        "dscr_yillik_p10": dy10,
        "dscr_yillik_p50": dy50,
        "n": n,
        "_irr": irr,
        "_dmin": dmin,
    }


def olcekle(b: BorcLP, a: float) -> BorcLP:
    """Servis profilini a ile orantılı ölçekler (borç, faiz, anapara ve bakiye doğrusal; DSCR'ler 1/a ile)."""
    return replace(
        b,
        borc_nom=b.borc_nom * a,
        servis=b.servis * a,
        faiz=b.faiz * a,
        anapara=b.anapara * a,
        bakiye=b.bakiye * a,
        dscr={k: v / a for k, v in b.dscr.items()} if a > 0 else b.dscr,
    )


def pd_hedefli(b: BorcLP, pd_hedef: float, ust: float = 2.0, iter_: int = 30, **kw) -> tuple[float, dict]:
    """
    Olasılık tabanlı boyutlandırma: LP servis profilinin şekli korunarak en büyük ölçek a ∈ [0, ust] öyle ki Monte Carlo
    ödeme temerrüdü olasılığı ≤ pd_hedef. P(temerrüt) a'da monoton artar (her senaryoda servis büyüdükçe açık büyür) →
    ikiye bölme. kw: selale() argümanları (borc hariç). Döndürür: (a, o ölçekteki şelale sonucu).
    """
    alt, ust_ = 0.0, ust
    if selale(borc=olcekle(b, ust_), **kw)["p_temerrut"] <= pd_hedef:
        return ust_, selale(borc=olcekle(b, ust_), **kw)
    for _ in range(iter_):
        orta = (alt + ust_) / 2
        if selale(borc=olcekle(b, orta), **kw)["p_temerrut"] <= pd_hedef:
            alt = orta
        else:
            ust_ = orta
    return alt, selale(borc=olcekle(b, alt), **kw)
