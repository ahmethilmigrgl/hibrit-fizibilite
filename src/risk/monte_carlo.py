"""
Monte Carlo örnekleme: belirsizlik kaynakları, Gauss kopula, fiyat yolları, kriz/tavan olayları.

Bir simülasyon i için (N işletme yılı):
    Hava          w_ik ∈ {0..9}, s_ik ∈ {0,1}  (blok bootstrap: yıllar bütün olarak çekilir)
    RES modeli    m_i ~ Üçgen(0,88; 1; 1,08) — simülasyon başına SABİT (sistematik model hatası)
                  × (1 + N(0; 0,01)) simülasyon × (1 + N(0; 0,015)) yıl  (kullanılabilirlik)
    Fiyat         μ_i ~ LogNormal(m; 0,15), m = log_merkez(cfg) (bkz. tanım: medyan/ortalama);  x_k = ln μ + φ(x_{k−1} − ln μ) + σ ε_k,  L_k = e^{x_k}
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


def log_merkez(cfg: dict) -> float:
    """
    Log-fiyat sürecinin merkezi m (μ_i ~ LogNormal(m; s_μ)).
    config → monte_carlo.fiyat_uzun_ortalama.tanim:
      "medyan"   : m = ln(seviye) — seviye fiyatın medyanıdır; beklenen fiyat lognormal çarpıklık yüzünden daha yüksektir.
      "ortalama" : m = ln(seviye) − s_μ²/2 − σ²/(2(1−φ²)) — durağan dağılımda E[L] = seviye (kriz olayları hariç).
    Gerekçe: x_k | μ ~ N(ln μ, σ²/(1−φ²)) (AR(1) durağan varyansı), ln μ ~ N(m, s_μ²) → E[L] = exp(m + s_μ²/2 + σ²/(2(1−φ²))).
    """
    fo, fs = deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"]), deger(cfg["monte_carlo"]["fiyat_sureci"])
    m = float(np.log(fo["seviye"]))
    if fo.get("tanim", "medyan") == "ortalama":
        m -= fo["log_sd"] ** 2 / 2 + fs["sigma"] ** 2 / (2 * (1 - fs["phi"] ** 2))
    return m


def fiyat_tahmini(cfg: dict, log_onceki: np.ndarray, adim: int = 1) -> np.ndarray:
    """
    YEKDEM kararı için bilinen son fiyattan 'adim' yıl sonrasının fiyat tahmini (karar verenin bildiği m, φ, σ ile).
    "medyan" tanımında (eski) koşullu medyan; "ortalama" tanımında koşullu beklenen değer (lognormal düzeltmeli).
    """
    fo, fs = deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"]), deger(cfg["monte_carlo"]["fiyat_sureci"])
    m, phi, sig = log_merkez(cfg), fs["phi"], fs["sigma"]
    x = m + phi**adim * (log_onceki - m)
    if fo.get("tanim", "medyan") == "ortalama":
        x = x + sig**2 * (1 - phi ** (2 * adim)) / (1 - phi**2) / 2 + (1 - phi**adim) ** 2 * fo["log_sd"] ** 2 / 2
    return np.exp(x)


def yekdem_katilim(cfg: dict, L_ext: np.ndarray, yol: np.ndarray, kd: int, N: int, esik: float, sure: int) -> np.ndarray:
    """
    YEKDEM yıllık opsiyonu (YEK Yön. md. 4/2, 5/1, 8/1): t−1 yılının 30 Kasım'ında, bilinen son yıl fiyatından tahminle
    katıl ⇔ YEKDEM reel fiyatı > eşik × tahmini PTF; yalnız ilk 'sure' işletme yılı. Döndürür (n × N) bool.
    L_ext: uzatılmış fiyat yolları (ilk sütun model COD yılı), kd: erteleme yılı.
    """
    kol = np.arange(kd, kd + N)
    log_onceki = np.where(kol[None, :] >= 1, np.log(L_ext[:, np.clip(kol - 1, 0, None)]), np.log(49.0))
    adim = np.where(kol >= 1, 1, 3)  # ilk yıl: 2026 seviyesinden (49 USD/MWh) üç adımlık tahmin
    tahmin = np.where(adim[None, :] == 1, fiyat_tahmini(cfg, log_onceki, 1), fiyat_tahmini(cfg, log_onceki, 3))
    k = np.arange(1, N + 1)
    return (yol[:, kol] > tahmin * esik) & (k[None, :] <= sure)


def ornekle(cfg: dict, n: int, yillar: np.ndarray, oran0: float, tohum: int, W: int = 10) -> dict:
    """Monte Carlo girdilerini örnekler: fiyat yolları, kriz/tavan, hava, kanibalizasyon, SFK, CAPEX, OPEX (bkz. modül notu)."""
    mc = cfg["monte_carlo"]
    rng = np.random.default_rng(tohum)
    N = len(yillar)
    rho = deger(mc["korelasyon"])["fiyat_capex"]
    # --- Gauss kopula: fiyat uzun dönem ortalaması ↔ CAPEX ortak faktörü
    z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], size=n)
    u_mu, u_capex = norm.cdf(z[:, 0]), norm.cdf(z[:, 1])
    fo = deger(mc["fiyat_uzun_ortalama"])
    mu = np.exp(log_merkez(cfg) + fo["log_sd"] * norm.ppf(u_mu))
    cx = deger(mc["capex"])
    capex = {k: ucgen_ters(u_capex, *cx[k]) for k in ("res", "ges", "bess")}
    # --- Fiyat yolu (2026'dan başlar; ilk değer son 12 ayın seviyesi ~49 USD/MWh)
    fs = deger(mc["fiyat_sureci"])
    phi, sig = fs["phi"], fs["sigma"]
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
    kriz = np.zeros((n, N), bool)
    tavan = np.zeros((n, N), bool)
    kalan = np.zeros(n, int)
    tav_aktif = np.zeros(n, bool)
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
    rm = deger(mc["res_model_carpani"])
    ku = deger(mc["kullanilabilirlik"])
    m_model = ucgen_ters(rng.random(n), rm["alt"], rm["tepe"], rm["ust"])
    m = (m_model * (1 + ku["sim_sd"] * rng.standard_normal(n)))[:, None] * (1 + ku["yil_sd"] * rng.standard_normal((n, N)))
    # --- Hava (blok bootstrap) ve fiyat şekli yılı
    w = rng.integers(0, W, (n, N))
    s = rng.integers(0, 2, (n, N))
    opex = 1 + deger(mc["opex"])["sd"] * rng.standard_normal(n)
    bozunma = ucgen_ters(rng.random(n), *deger(mc["batarya_bozunma"]))
    DF = (1.07) ** -(np.arange(N) + 3)
    return {
        "girdi": {
            "w": w,
            "s": s,
            "h": h,
            "m": m,
            "a": a,
            "L": L,
            "tavan": tavan,
            "capex_res": capex["res"],
            "capex_ges": capex["ges"],
            "capex_bess": capex["bess"],
            "opex": opex,
            "bozunma": bozunma,
        },
        "suruculer": {
            "Fiyat uzun dönem ortalaması": mu,
            "Fiyat yolu (iskontolu ort.)": (L * DF).sum(1) / DF.sum(),
            "Kriz / tavan yılı sayısı": tavan.sum(1) + kriz.sum(1) * 0,
            "Kanibalizasyon tabanı": f,
            "RES model çarpanı": m_model,
            "Hava (ort. RES yılı)": w.mean(1) * 0 + 0,  # yer tutucu; aşağıda hava KF'siyle doldurulur
            "CAPEX ortak faktörü": u_capex,
            "OPEX çarpanı": opex,
            "Batarya bozunma": bozunma,
            "Yan hizmet azalma hızı": azalma,
            "Yan hizmet tabanı": yh_taban,
        },
    }
