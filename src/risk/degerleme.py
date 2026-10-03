"""
Vektörize proje değerlemesi: işletme tablolarından (src/risk/isletme.py) yıllık nakit akışı, vergi,
NPV, IRR, borç ve DSCR — aynı anda binlerce simülasyon için.

Her simülasyon i ve işletme yılı k için girdiler (n × N diziler):
    w, s   hava yılı ve fiyat şekli yılı indeksleri
    h      güneş yakalanma hedefi (kanibalizasyon derinliği)
    m      RES üretim çarpanı (model belirsizliği × kullanılabilirlik)
    a      yan hizmet fiyat çarpanı (2026 seviyesine göre)
    L      yıllık baz yük fiyat seviyesi [USD/MWh, reel]
    tavan  düzenleyici azami fiyat olayı (bool)
Simülasyon başına çarpanlar (n): capex_res, capex_ges, capex_bess, opex, bozunma (batarya yıpranması).

Gelir (yıl k):
    spot_doğrudan = (1 − φ_k) · L · Σ y·q      (tavan yılında q yerine min(q, 0,70))
    PPA           = φ_k · PPA_fiyatı · Σ y
    batarya       = L · Σ d·q ;  yan hizmet = a · Σ r·a_şekil ;  YEK-G = yekg · (Σ y + Σ d)
Giderler: dengesizlik (GES %2, RES %4 × (1 − batarya azaltımı)), eşzamanlılık düzeltmesi (RES, PPA dışı),
TEİAŞ (kapasite + enerji), sabit O&M + arazi + sigorta, batarya O&M, yıpranma, augmentation, yenileme, söküm.
Vergi: %25, amortisman 10 yıl doğrusal, zarar 5 yıl taşınır. Nakit akışı yıl sonu, t = 0 FID.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.ayarlar import deger
from src.finans.model import Varsayimlar
from src.risk.isletme import ALANLAR, Tasarim

AI = {a: i for i, a in enumerate(ALANLAR)}


def _izgara_agirlik(deg: np.ndarray, izgara: np.ndarray):
    """Doğrusal ara değerleme indeksleri ve ağırlıkları (uçlarda sabit dışdeğerleme)."""
    if len(izgara) == 1:
        z = np.zeros(deg.shape, int)
        return z, z, np.zeros(deg.shape)
    x = np.clip(deg, izgara[0], izgara[-1])
    j = np.clip(np.searchsorted(izgara, x) - 1, 0, len(izgara) - 2)
    t = (x - izgara[j]) / (izgara[j + 1] - izgara[j])
    return j, j + 1, t


def tablo_ara(tablo: dict, w, s, h, m, a, ip) -> np.ndarray:
    """Tablodan (h, m, a) üzerinde üç doğrusal ara değerleme. Girdiler aynı şekilli diziler; çıktı (..., alan)."""
    T = tablo["T"]
    h0, h1, th = _izgara_agirlik(h, tablo["h"])
    m0, m1, tm = _izgara_agirlik(m, tablo["m"])
    a0, a1, ta = _izgara_agirlik(a, tablo["a"])
    sonuc = 0.0
    for hj, wh in ((h0, 1 - th), (h1, th)):
        for mj, wm in ((m0, 1 - tm), (m1, tm)):
            for aj, wa in ((a0, 1 - ta), (a1, ta)):
                sonuc = sonuc + (wh * wm * wa)[..., None] * T[w, s, hj, mj, aj, ip]
    return sonuc


@dataclass
class Sabitler:
    v: Varsayimlar
    yekg: float
    ppa_fiyat: float
    ppa_pay: float          # saatlik üretim payı (φ)
    ppa_vade: int
    dz_azami: float
    dz_doyum: float
    tavan_carpan: float
    pi: float               # ABD enflasyonu (borç)

    @classmethod
    def configten(cls, cfg: dict, v: Varsayimlar, L_baz: float = None):
        gy = cfg["gelir_yigini"]
        L0 = L_baz if L_baz is not None else deger(cfg["fiyat_senaryolari"]["seviye"])["baz"]
        return cls(v=v, yekg=deger(gy["yekg"]), ppa_fiyat=L0 * (1 - deger(gy["ppa"]["iskonto"])),
                   ppa_pay=deger(gy["ppa"]["pay"]) * 0.94, ppa_vade=deger(gy["ppa"]["vade"]),
                   dz_azami=deger(gy["dengesizlik_azaltim"]["azami_oran"]),
                   dz_doyum=deger(gy["dengesizlik_azaltim"]["doyum_orani"]),
                   tavan_carpan=deger(cfg["fiyat_senaryolari"]["duzenleyici_tavan"])["tavan_carpani"],
                   pi=deger(cfg["finans"]["abd_enflasyonu"]))


def capex_kalemleri(t: Tasarim, v: Varsayimlar) -> dict:
    return {"res": t.res_mw * v.capex_res, "ges": t.ges_mw * v.capex_ges,
            "bess": t.bess_mw * v.capex_bess_guc + t.bess_mwh * v.capex_bess_enerji,
            "sebeke": t.sebeke_mw * v.capex_sebeke}


def nakit_akislari(t: Tasarim, tablo: dict, c: Sabitler, girdi: dict) -> dict:
    """
    girdi: w, s, h, m, a, L, tavan (n × N) ve capex_res, capex_ges, capex_bess, opex, bozunma (n).
    Döndürür: yıllık kalemler (n × N), SNA (n × T), NPV (n), CFADS (n × N), satılan enerji (n × N) ...
    """
    v = c.v
    n, N = girdi["L"].shape
    nb = v.insaat_suresi
    k = np.arange(1, N + 1)
    phi = np.where(k <= c.ppa_vade, c.ppa_pay, 0.0) if t.ppa else np.zeros(N)
    ip = (k <= c.ppa_vade).astype(int) if (t.ppa and len(tablo["ppa"]) > 1) else np.zeros(N, int)
    deg_g = (1 - v.degr_ges) ** (k - 1)
    deg_r = (1 - v.degr_res) ** (k - 1)
    # RES degradasyonu tablonun RES çarpanı boyutundan geçer → kesinti degrade üretimle doğru hesaplanır
    m_eff = girdi["m"] * deg_r[None, :]
    if "X" in girdi:
        X = girdi["X"]          # dışarıdan verilmiş yıllık işletme büyüklükleri (doğrulama: tam LP çözümü)
    elif girdi.get("ws_ortalama"):
        # Beklenen değer modu: her yılın işletme büyüklükleri 10 hava × 2 şekil yılının ortalaması (Aşama 3 tanımı)
        W, S = tablo["T"].shape[:2]
        X = np.mean([tablo_ara(tablo, np.full((n, N), w_), np.full((n, N), s_), girdi["h"], m_eff, girdi["a"],
                               ip[None, :].repeat(n, 0)) for w_ in range(W) for s_ in range(S)], axis=0)
    else:
        X = tablo_ara(tablo, girdi["w"], girdi["s"], girdi["h"], m_eff, girdi["a"], ip[None, :].repeat(n, 0))
    g = lambda ad: X[..., AI[ad]]
    L, tav = girdi["L"], girdi["tavan"]
    q_ges = np.where(tav, g("gelir_ges_qt"), g("gelir_ges_q")) * deg_g
    q_res = np.where(tav, g("gelir_res_qt"), g("gelir_res_q"))
    q_d = np.where(tav, g("gelir_d_qt"), g("gelir_d_q"))
    E_ges, E_res, E_d = g("E_ges") * deg_g, g("E_res"), g("E_d")
    ppa_fiyat_t = c.ppa_fiyat          # PPA fiyatı sabit; düzenleyici tavandan etkilenmez
    gelir_ges = (1 - phi) * L * q_ges + phi * ppa_fiyat_t * E_ges
    gelir_res = (1 - phi) * L * q_res + phi * ppa_fiyat_t * E_res
    gelir_bess = L * q_d
    gelir_yh = girdi["a"] * g("yh_a") if t.yan_hizmet else 0.0 * L
    gelir_yekg = c.yekg * (E_ges + E_res + E_d) if t.yekg else 0.0 * L
    # Dengesizlik: RES maliyeti batarya gücüyle doygunlaşarak azalır (yan hizmete ayrılmayan güç)
    azaltim = 0.0
    if t.dengesizlik_azaltim and t.res_mw > 0:
        serbest_guc = np.clip(t.bess_mw - g("rezerv") / 8760, 0, None)
        azaltim = c.dz_azami * np.minimum(serbest_guc / (c.dz_doyum * t.res_mw), 1.0)
    esz = v.eszamanlilik_res * L * E_res * (1 - phi)
    dengesizlik = v.dengesizlik["ges"] * gelir_ges + v.dengesizlik["res"] * (gelir_res - esz) * (1 - azaltim)
    satilan = E_ges + E_res + E_d
    capex = capex_kalemleri(t, v)
    cm = {"res": girdi["capex_res"], "ges": girdi["capex_ges"], "bess": girdi["capex_bess"], "sebeke": np.ones(n)}
    capex_top = sum(capex[kk] * cm[kk] for kk in capex)                                          # (n,)
    sabit_opex = ((v.opex_ges + v.arazi_ges) * t.ges_mw + (v.opex_res + v.arazi_res) * t.res_mw) * girdi["opex"]
    bess_opex = v.opex_bess_oran * capex["bess"] * girdi["capex_bess"]
    sigorta = v.sigorta_oran * capex_top
    teias = v.teias_kapasite * t.sebeke_mw + v.teias_enerji * satilan
    yipranma = v.bess_yipranma * E_d * girdi["bozunma"][:, None]
    opex = (sabit_opex + bess_opex + sigorta)[:, None] + teias + yipranma
    favok = gelir_ges + gelir_res + gelir_bess + gelir_yh + gelir_yekg - dengesizlik - esz - opex
    # Augmentation, yenileme, söküm
    aug = np.zeros((n, N))
    if t.bess_mwh > 0:
        a_ = v.augmentation
        for y in list(a_["yillar"]) + [y + v.omur_bess for y in a_["yillar"]]:
            if y <= N and y != v.omur_bess:
                aug[:, y - 1] += a_["oran"] * t.bess_mwh * v.capex_bess_enerji * girdi["capex_bess"] \
                    * girdi["bozunma"] * (1 - a_["maliyet_dususu_yillik"]) ** y
        if v.bess_yenileme["aktif"] and v.omur_bess < N:
            aug[:, v.omur_bess - 1] += capex["bess"] * girdi["capex_bess"] * (1 - v.bess_yenileme["maliyet_dususu_yillik"]) ** v.omur_bess
    sokum = np.zeros(N)
    sokum[-1] = v.sokum["ges"] * t.ges_mw + v.sokum["res"] * t.res_mw + v.sokum["bess"] * t.bess_mwh
    # Vergi: amortisman 10 yıl, zarar 5 yıl ileri (kova kaydırmalı)
    amort = np.zeros((n, N))
    for kk, tutar in capex.items():
        sure = v.amortisman["sebeke" if kk == "sebeke" else kk]
        amort[:, :sure] += (tutar * cm[kk] / sure)[:, None]
    matrah = favok - amort - aug - sokum
    vergi = np.zeros((n, N))
    kova = np.zeros((n, v.zarar_mahsup))          # kova[j]: (j+1) yıl daha kullanılabilir zarar
    for y in range(N):
        mt = matrah[:, y]
        zarar = np.clip(-mt, 0, None)
        kalan = np.clip(mt, 0, None)
        for j in range(v.zarar_mahsup):           # en eski zarar önce
            kullan = np.minimum(kova[:, j], kalan)
            kova[:, j] -= kullan
            kalan -= kullan
        vergi[:, y] = v.vergi * kalan
        kova = np.concatenate([kova[:, 1:], zarar[:, None]], axis=1)
    cfads = favok - vergi - aug - sokum
    T = nb + N
    sna = np.zeros((n, T))
    takvim = np.array(v.capex_takvimi)
    sna[:, :nb] = -capex_top[:, None] * takvim[None]
    sna[:, nb:] = cfads
    df = (1 + v.wacc) ** -(np.arange(T) + 1)
    return {"sna": sna, "npv": sna @ df, "cfads": cfads, "favok": favok, "vergi": vergi, "satilan": satilan,
            "capex_top": capex_top, "gelir_bess": gelir_bess, "gelir_yh": gelir_yh, "gelir_spot": gelir_ges + gelir_res,
            "E_res": E_res, "E_ges": E_ges, "dengesizlik": dengesizlik, "azaltim": azaltim,
            "kesilen": g("E_k"), "uretilebilir": g("E_A")}


def irr_vektor(sna: np.ndarray, alt: float = -0.5, ust: float = 0.6, iter_: int = 80) -> np.ndarray:
    """Her satır için NPV(r) = 0 kökü (ikiye bölme). Kök yoksa NaN."""
    T = sna.shape[1]
    t = np.arange(1, T + 1)
    f = lambda r: (sna * (1 + r[:, None]) ** -t).sum(1)
    a, b = np.full(len(sna), alt), np.full(len(sna), ust)
    fa, fb = f(a), f(b)
    gecerli = np.sign(fa) != np.sign(fb)
    for _ in range(iter_):
        orta = (a + b) / 2
        fm = f(orta)
        sol = np.sign(fm) == np.sign(fa)
        a, fa = np.where(sol, orta, a), np.where(sol, fm, fa)
        b = np.where(sol, b, orta)
    return np.where(gecerli, (a + b) / 2, np.nan)


def borc_boyutla(cfads_p90: np.ndarray, capex_top: float, t: Tasarim, cfg: dict, c: Sabitler,
                 cfads_ppa_payi: np.ndarray | None = None) -> dict:
    """
    Heykelsi borç (deterministik, FID'de): servis_k = CFADS_nom,k(P90) / DSCR_k, vadenin ilk yıllarında.
    PPA'lı tasarımda DSCR, CFADS'nin sözleşmeli payına 1,20, kalanına hedef DSCR uygulanarak harmanlanır;
    vade PPA'lı borç vadesi (18 yıl) olur.
    """
    b = cfg["borc"]
    gy = cfg["gelir_yigini"]["ppa"]
    dscr_m, i = deger(b["hedef_dscr"]), deger(b["faiz_nominal"])
    vade = deger(gy["borc_vadesi"]) if t.ppa else deger(b["vade"])
    nb = c.v.insaat_suresi
    N = len(cfads_p90)
    k = np.arange(1, N + 1)
    enf = (1 + c.pi) ** (nb + k)
    pay = cfads_ppa_payi if (t.ppa and cfads_ppa_payi is not None) else np.zeros(N)
    dscr = 1.0 / (pay / deger(gy["dscr"]) + (1 - pay) / dscr_m)
    servis = np.where(k <= vade, np.clip(cfads_p90, 0, None) * enf / dscr, 0.0)
    borc_nom = float((servis * (1 + i) ** -k).sum())
    capex_nom = capex_top * float((np.array(c.v.capex_takvimi) * (1 + c.pi) ** (np.arange(nb) + 1)).sum())
    tavan = deger(b["azami_borc_orani"])
    if borc_nom > tavan * capex_nom:
        servis *= tavan * capex_nom / borc_nom
        borc_nom = tavan * capex_nom
    bakiye, faiz = borc_nom, np.zeros(N)
    for y in range(N):
        faiz[y] = bakiye * i
        bakiye = bakiye + faiz[y] - servis[y]
    return {"servis_nom": servis, "faiz_nom": faiz, "borc_reel": borc_nom / (1 + c.pi) ** nb, "enf": enf,
            "vade": vade, "borc_orani": borc_nom / (1 + c.pi) ** nb / capex_top}


def ozkaynak(sonuc: dict, borc: dict, c: Sabitler) -> dict:
    """Simülasyon başına öz kaynak akışı, IRR ve DSCR (borç deterministik, nakit akışı stokastik)."""
    v = c.v
    nb = v.insaat_suresi
    n, N = sonuc["cfads"].shape
    enf = borc["enf"]
    kalkan = np.minimum(borc["faiz_nom"] * v.vergi, np.clip(sonuc["vergi"], 0, None) * enf)
    akis = np.zeros((n, nb + N))
    takvim = np.array(v.capex_takvimi)
    akis[:, :nb] = (-sonuc["capex_top"][:, None] + borc["borc_reel"]) * takvim[None]
    akis[:, nb:] = sonuc["cfads"] - (borc["servis_nom"] - kalkan) / enf
    aktif = borc["servis_nom"] > 0
    dscr = np.where(aktif, sonuc["cfads"] * enf / np.where(aktif, borc["servis_nom"], 1), np.inf)
    return {"akis": akis, "irr": irr_vektor(akis), "dscr_min": dscr.min(1), "dscr": dscr}
