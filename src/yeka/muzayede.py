"""
YEKA katkı payı açık artırması: rakip değer modeli, en çok olabilirlik tahmini ve teklif stratejisi.

Mekanizma (2024–2026): fiyat 5,50'den taban 3,50 sent/kWh'ye iner; tabanda iki ya da daha fazla istekli kalırsa MW başına katkı
payı 10.000 €'dan açık artırmayla yükselir (İngiliz artırması). 2024–25'teki 11 yarışmanın hepsi tabana indi; kazananı katkı
payı belirledi.

İngiliz artırmasında baskın strateji: katkı payı kendi değerinize (başabaş katkı payı) ulaşınca çekilmek. Kazanan en yüksek
değerli isteklidir ve yaklaşık ikinci en yüksek değeri öder. Bu yüzden gözlenen katkı payı = n istekli arasında İKİNCİ EN
YÜKSEK değer (sıra istatistiği).

Rakip değer modeli (lot i, istekli j):
    V_ij = v̂_i + δ + γ · ln(MW_i / 150) + s · ε_ij,   ε_ij ~ N(0, 1) bağımsız
    v̂_i : bizim modelimizin başabaş katkı payı (€/MW)      δ : piyasa primi (piyasa bizden ne kadar iyimser)
    γ   : lot büyüklüğü etkisi (büyük lotta sermaye kısıtı)  s : istekliler arası dağınıklık
Gözlem y_i ~ ikinci en yüksek değerin yoğunluğu (n_i istekli), tabana inme koşuluyla kesilmiş:
    f(y | Y₍ₙ₋₁₎ ≥ 10.000) = n(n−1) Φ(z)^{n−2} (1 − Φ(z)) φ(z) / s / P(Y₍ₙ₋₁₎ ≥ 10.000),   z = (y − μ_i) / s
    (gözlenen 11 yarışmanın hepsi tabana indi; tabana inmeyen yarışma olsaydı katkı payı gözlenmeyecekti → seçilim yanlılığı)
Parametreler en çok olabilirlikle (scipy), güven aralıkları lot bazında bootstrap ile.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

MW_REF = 150.0


OLCEK = 1e5  # optimizasyon €/MW yerine 100 bin €/MW biriminde (Nelder–Mead adımları dengeli olsun)


def _mu(p: np.ndarray, v: np.ndarray, mw: np.ndarray) -> np.ndarray:
    return v + (p[0] + p[1] * np.log(mw / MW_REF)) * OLCEK


ALT = 10_000.0  # katkı payı artırmasının başlangıcı: gözlenen yarışmalar ikinci en yüksek değerin ≥ ALT olduğu (tabana inen) yarışmalardır


def log_ikinci_ust_olasilik(c: float, mu: np.ndarray, s: float, n: np.ndarray) -> np.ndarray:
    """
    log P(Y₍ₙ₋₁₎ ≥ c): en az iki istekli c'nin üstünde. S = 1 − F(c) ile P = 1 − (1 − S)ⁿ⁻¹ (1 + (n − 1) S); kuyrukta (S küçük)
    sayısal iptal olmasın diye P ≈ C(n, 2) S² (log-uzayda, logsf ile).
    """
    z = (c - mu) / s
    logS = norm.logsf(z)
    S = np.exp(logS)
    a = (n - 1) * np.log1p(-np.minimum(S, 1 - 1e-12)) + np.log1p((n - 1) * S)
    tam = np.log(np.maximum(-np.expm1(a), 1e-300))
    yaklasik = np.log(n * (n - 1) / 2) + 2 * logS
    return np.where(S < 1e-5, yaklasik, tam)


def negatif_log_olabilirlik(p: np.ndarray, y: np.ndarray, v: np.ndarray, mw: np.ndarray, n: np.ndarray) -> float:
    """p = [δ/1e5, γ/1e5, ln(s/1e5)]. Kesilmiş olabilirlik: gözlem yalnız Y₍ₙ₋₁₎ ≥ ALT ise var (fiyat tabana indi)."""
    s = np.exp(p[2]) * OLCEK
    mu = _mu(p, v, mw)
    z = (y - mu) / s
    lf = np.log(n * (n - 1)) + (n - 2) * norm.logcdf(z) + norm.logsf(z) + norm.logpdf(z) - np.log(s)
    lf = lf - log_ikinci_ust_olasilik(ALT, mu, s, n)
    return float(-lf.sum())


def tahmin(y: np.ndarray, v: np.ndarray, mw: np.ndarray, n: np.ndarray, buyukluk: bool = True) -> dict:
    """En çok olabilirlik (çok başlangıçlı Nelder–Mead): δ, γ (buyukluk=False → 0), s. Birimler €/MW."""
    y, v, mw, n = (np.asarray(a, float) for a in (y, v, mw, n))
    f = (
        (lambda q: negatif_log_olabilirlik(q, y, v, mw, n))
        if buyukluk
        else (lambda q: negatif_log_olabilirlik(np.r_[q[0], 0.0, q[1]], y, v, mw, n))
    )
    d0 = float(np.mean(y - v)) / OLCEK
    en = None
    for ds in (-3.0, 0.0, 3.0):
        for ls in (np.log(0.5), np.log(2.0), np.log(5.0)):
            q0 = np.array([d0 + ds, 0.0, ls]) if buyukluk else np.array([d0 + ds, ls])
            r = minimize(f, q0, method="Nelder-Mead", options={"maxiter": 6000, "xatol": 1e-6, "fatol": 1e-9})
            if en is None or r.fun < en.fun:
                en = r
    q = en.x if buyukluk else np.r_[en.x[0], 0.0, en.x[1]]
    return {
        "delta": float(q[0] * OLCEK),
        "gamma": float(q[1] * OLCEK),
        "s": float(np.exp(q[2]) * OLCEK),
        "nll": float(en.fun),
        "basarili": bool(en.success),
        "k": 3 if buyukluk else 2,
        "aic": float(2 * en.fun + 2 * (3 if buyukluk else 2)),
    }


def bootstrap(y, v, mw, n, B: int = 300, tohum: int = 0, buyukluk: bool = True) -> dict:
    """Lotları yeniden örnekleyerek parametre güven aralıkları (%5–95)."""
    rng = np.random.default_rng(tohum)
    y, v, mw, n = (np.asarray(a, float) for a in (y, v, mw, n))
    ps = []
    for _ in range(B):
        i = rng.integers(0, len(y), len(y))
        if len(np.unique(i)) < 4:
            continue
        t = tahmin(y[i], v[i], mw[i], n[i], buyukluk)
        ps.append([t["delta"], t["gamma"], t["s"]])
    ps = np.array(ps)
    return {k: [float(np.percentile(ps[:, j], 5)), float(np.percentile(ps[:, j], 95))] for j, k in enumerate(["delta", "gamma", "s"])}


def ikinci_en_yuksek(mu: float, s: float, n: int, R: int = 200_000, tohum: int = 1) -> np.ndarray:
    """n istekli arasında ikinci en yüksek değer örnekleri (beklenen katkı payı dağılımı)."""
    x = np.random.default_rng(tohum).normal(mu, s, (R, n))
    return np.sort(x, axis=1)[:, -2]


def kosullu_ikinci(mu: float, s: float, n: int, R: int = 50_000, tohum: int = 1, asgari: int = 2_000) -> np.ndarray:
    """Tabana inme koşullu (Y₍ₙ₋₁₎ ≥ ALT) ikinci en yüksek değer örnekleri; nadir olayda örneklem büyütülür (en çok 4 M)."""
    toplanan, k = [], 0
    while sum(len(a) for a in toplanan) < asgari and k < 8:
        x = ikinci_en_yuksek(mu, s, n, R, tohum=tohum + 1000 * k)
        toplanan.append(x[x >= ALT])
        k += 1
        R = min(R * 2, 500_000)
    x = np.concatenate(toplanan)
    return x if len(x) else np.array([ALT])


def strateji(
    deger_biz: np.ndarray, mu_rakip: float, s: float, n_istekli: int, cekilme: np.ndarray, R: int = 100_000, tohum: int = 2
) -> dict:
    """
    Bizim değer dağılımımız (senaryo örnekleri, €/MW) ve n_istekli − 1 rakip (N(mu_rakip, s)) karşısında, çekilme eşiği b'ye
    göre kazanma olasılığı, beklenen ödeme ve beklenen fazla (V − ödenen katkı payı; kazanılmazsa 0).
    Kazanırsak ödeme = max(rakip değerleri, başlangıç 10.000 €) (İngiliz artırması, artış adımı ihmal).
    """
    rng = np.random.default_rng(tohum)
    H = np.max(rng.normal(mu_rakip, s, (R, max(n_istekli - 1, 1))), axis=1)
    H = np.maximum(H, 10_000.0)
    V = rng.choice(np.asarray(deger_biz, float), R, replace=True)
    sonuc = []
    for b in np.asarray(cekilme, float):
        kaz = H < b
        fazla = np.where(kaz, V - H, 0.0)
        sonuc.append(
            {
                "cekilme": float(b),
                "p_kazanma": float(kaz.mean()),
                "beklenen_odeme": float(H[kaz].mean()) if kaz.any() else None,
                "beklenen_fazla": float(fazla.mean()),
                "kazaninca_zarar_olasiligi": float((V[kaz] < H[kaz]).mean()) if kaz.any() else None,
            }
        )
    return {"egri": sonuc, "en_iyi": max(sonuc, key=lambda x: x["beklenen_fazla"])}


def birini_disarida_birak(y, v, mw, n, buyukluk: bool = True, R: int = 50_000) -> list[dict]:
    """Her geçmiş yarışma için: kalan yarışmalarla tahmin → bu yarışmanın katkı payı dağılımı; gözlemin yüzdeliği ve %80 aralığı."""
    y, v, mw, n = (np.asarray(a, float) for a in (y, v, mw, n))
    sonuc = []
    for i in range(len(y)):
        m = np.arange(len(y)) != i
        t = tahmin(y[m], v[m], mw[m], n[m], buyukluk)
        mu = v[i] + t["delta"] + t["gamma"] * np.log(mw[i] / MW_REF)
        x = kosullu_ikinci(mu, t["s"], int(n[i]), R, tohum=i)  # gözlemle karşılaştırılabilir: tabana inen yarışma koşullu
        sonuc.append(
            {
                "i": i,
                "gozlenen": float(y[i]),
                "p10": float(np.percentile(x, 10)),
                "p50": float(np.percentile(x, 50)),
                "p90": float(np.percentile(x, 90)),
                "yuzdelik": float((x < y[i]).mean()),
            }
        )
    return sonuc


def fiyat_asamasi(ikinci: np.ndarray, egim_eur_mw_sent: float, taban: float, tavan: float, baslangic: float) -> dict:
    """
    İkinci en yüksek değer (tabanda, €/MW) < 0 ise fiyat tabana inmeden durur: ikinci istekli fiyat p'de çekilir, burada değeri
    sıfırdır → p = taban − ikinci / eğim (tavanla sınırlı). ≥ 0 ise fiyat tabana iner ve katkı payı max(ikinci, başlangıç) olur.
    egim: alım fiyatındaki 1 sentlik artışın değeri (€/MW / sent).
    """
    taban_iner = ikinci >= 0
    p = np.where(taban_iner, taban, np.minimum(taban - ikinci / max(egim_eur_mw_sent, 1e-9), tavan))
    katki = np.where(taban_iner, np.maximum(ikinci, baslangic), 0.0)
    return {
        "p_taban": float(taban_iner.mean()),
        "fiyat_p50": float(np.percentile(p, 50)),
        "katki_p10": float(np.percentile(katki[taban_iner], 10)) if taban_iner.any() else 0.0,
        "katki_p50": float(np.percentile(katki[taban_iner], 50)) if taban_iner.any() else 0.0,
        "katki_p90": float(np.percentile(katki[taban_iner], 90)) if taban_iner.any() else 0.0,
        "katki_ortalama": float(katki.mean()),
    }
