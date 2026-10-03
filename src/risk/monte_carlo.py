"""
Monte Carlo örnekleme: belirsizlik kaynakları, Gauss kopula, fiyat yolları, kriz/tavan olayları.

Bir simülasyon i için (N işletme yılı):
    Hava          w_ik ∈ {0..9}, s_ik ∈ {0,1}  (blok bootstrap: yıllar bütün olarak çekilir)
    RES modeli    m_i ~ Üçgen(0,88; 1; 1,08) — simülasyon başına SABİT (sistematik model hatası)
                  × (1 + N(0; 0,01)) simülasyon × (1 + N(0; 0,015)) yıl  (kullanılabilirlik)
    Fiyat         μ_i ~ LogNormal(ln 58; 0,15);  x_k = ln μ + φ(x_{k−1} − ln μ) + σ ε_k,  L_k = e^{x_k}
    Kriz          yıllık %3 başlama, 1-2 yıl sürer: L × 1,6; %80 olasılıkla spot gelire tavan (0,70 × L)
    Kanibalizasyon taban f_i ~ Üçgen(0,55; 0,62; 0,769) → h_ik yolu
    Yan hizmet    azalma ~ Üçgen(5%; 15%; 30%), taban ~ Düzgün(0,15; 0,40) → a_ik yolu
    CAPEX         Üçgen (teknoloji bazında), ortak faktör u_i; OPEX ~ N(1; 0,08); batarya bozunma ~ Üçgen(0,8; 1; 1,6)
    Korelasyon    Gauss kopula: (z_μ, z_capex) ~ N(0, [[1, ρ],[ρ, 1]]), ρ = 0,4 → marjinallere ters dönüşüm
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from src.ayarlar import deger
from src.risk.senaryo import a_yolu, h_yolu


def ucgen_ters(u: np.ndarray, a: float, c: float, b: float) -> np.ndarray:
    """Üçgen(a, tepe c, b) dağılımının ters birikimli dağılım fonksiyonu (kopula için)."""
    fc = (c - a) / (b - a)
    return np.where(u < fc, a + np.sqrt(u * (b - a) * (c - a)), b - np.sqrt((1 - u) * (b - a) * (b - c)))


def ornekle(cfg: dict, n: int, yillar: np.ndarray, oran0: float, tohum: int, W: int = 10) -> dict:
    mc = cfg["monte_carlo"]
    rng = np.random.default_rng(tohum)
    N = len(yillar)
    rho = deger(mc["korelasyon"])["fiyat_capex"]
    # --- Gauss kopula: fiyat uzun dönem ortalaması ↔ CAPEX ortak faktörü
    z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], size=n)
    u_mu, u_capex = norm.cdf(z[:, 0]), norm.cdf(z[:, 1])
    fo = deger(mc["fiyat_uzun_ortalama"])
    mu = np.exp(np.log(fo["medyan"]) + fo["log_sd"] * norm.ppf(u_mu))
    cx = deger(mc["capex"])
    capex = {k: ucgen_ters(u_capex, *cx[k]) for k in ("res", "ges", "bess")}
    # --- Fiyat yolu (2026'dan başlar; ilk değer son 12 ayın seviyesi ~49 USD/MWh)
    fs = deger(mc["fiyat_sureci"]); phi, sig = fs["phi"], fs["sigma"]
    adim = int(yillar[0] - 2026)
    x = np.full(n, np.log(49.0))
    for _ in range(adim):
        x = np.log(mu) + phi * (x - np.log(mu)) + sig * rng.standard_normal(n)
    L = np.empty((n, N))
    for k in range(N):
        x = np.log(mu) + phi * (x - np.log(mu)) + sig * rng.standard_normal(n)
        L[:, k] = np.exp(x)
    # --- Kriz + düzenleyici tavan olayları
    kr = deger(mc["kriz"])
    kriz = np.zeros((n, N), bool); tavan = np.zeros((n, N), bool)
    kalan = np.zeros(n, int); tav_aktif = np.zeros(n, bool)
    for k in range(N):
        basla = (kalan == 0) & (rng.random(n) < kr["yillik_olasilik"])
        sure = rng.integers(kr["sure_yil"][0], kr["sure_yil"][1] + 1, n)
        kalan = np.where(basla, sure, kalan)
        tav_aktif = np.where(basla, rng.random(n) < kr["tavan_olasiligi"], tav_aktif)
        kriz[:, k] = kalan > 0
        tavan[:, k] = (kalan > 0) & tav_aktif
        kalan = np.maximum(kalan - 1, 0)
    L = np.where(kriz, L * kr["fiyat_carpani"], L)
    # --- Kanibalizasyon tabanı ve h yolu
    kt = deger(mc["kanibalizasyon_tabani"])
    f = ucgen_ters(rng.random(n), kt["alt"], kt["tepe"], min(kt["ust"], oran0))
    h = np.array([h_yolu(cfg, yillar, fi, oran0) for fi in f])
    # --- Yan hizmet fiyat yolu
    ya = deger(mc["yan_hizmet_azalma"])
    azalma = ucgen_ters(rng.random(n), *ya["azalma"])
    yh_taban = rng.uniform(*ya["taban"], n)
    a = np.array([a_yolu(yillar, az, tb) for az, tb in zip(azalma, yh_taban)])
    # --- RES modeli + kullanılabilirlik
    rm = deger(mc["res_model_carpani"]); ku = deger(mc["kullanilabilirlik"])
    m_model = ucgen_ters(rng.random(n), rm["alt"], rm["tepe"], rm["ust"])
    m = (m_model * (1 + ku["sim_sd"] * rng.standard_normal(n)))[:, None] * (1 + ku["yil_sd"] * rng.standard_normal((n, N)))
    # --- Hava (blok bootstrap) ve fiyat şekli yılı
    w = rng.integers(0, W, (n, N)); s = rng.integers(0, 2, (n, N))
    opex = 1 + deger(mc["opex"])["sd"] * rng.standard_normal(n)
    bozunma = ucgen_ters(rng.random(n), *deger(mc["batarya_bozunma"]))
    DF = (1.07) ** -(np.arange(N) + 3)
    return {"girdi": {"w": w, "s": s, "h": h, "m": m, "a": a, "L": L, "tavan": tavan, "capex_res": capex["res"],
                      "capex_ges": capex["ges"], "capex_bess": capex["bess"], "opex": opex, "bozunma": bozunma},
            "suruculer": {"Fiyat uzun dönem ortalaması": mu,
                          "Fiyat yolu (iskontolu ort.)": (L * DF).sum(1) / DF.sum(),
                          "Kriz / tavan yılı sayısı": tavan.sum(1) + kriz.sum(1) * 0,
                          "Kanibalizasyon tabanı": f, "RES model çarpanı": m_model,
                          "Hava (ort. RES yılı)": w.mean(1) * 0 + 0,   # yer tutucu; aşağıda hava KF'siyle doldurulur
                          "CAPEX ortak faktörü": u_capex, "OPEX çarpanı": opex, "Batarya bozunma": bozunma,
                          "Yan hizmet azalma hızı": azalma, "Yan hizmet tabanı": yh_taban}}
