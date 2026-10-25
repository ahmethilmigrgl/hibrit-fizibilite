"""
Merit order fiyat modeli (v4 Faz K): saatlik termik artık yük → arz eğrisi → fiyat.

Sevk sırası (her saat t):
    1. Net yük N_t = talep − rüzgâr − güneş − akarsu − jeotermal − biyokütle − nükleer
    2. Barajlı hidro, aylık su bütçesiyle tepe saatlere: H_t = clip(N_t − λ_m, H_min, H_max), Σ_m H_t = bütçe_m (su doldurma)
    3. Depolama, günlük arbitraj: en düşük artık yük saatlerinde şarj, en yükseklerde deşarj (güç, enerji, verim sınırlı)
    4. Termik artık yük RL_t = N_t − H_t − deşarj_t + şarj_t;  RL_t < 0 → yenilenebilir fazlası kesilir, fiyat 0

Arz eğrisi f(x), x = termik artık yük [MW]:
    [0, M)            f_bant(M) · (x/M)^α          zorunlu çalışma altında fiyat sıfıra iner (M = must_oran · (K_L + K_C))
    [M, K_L)          MC_L + e_L · CO2              linyit
    [K_L, K_L + K_C)  C + e_C · CO2                 ithal kömür
    [K_L + K_C, K)    v + (G + e_G · CO2) · HR(q)   doğalgaz; q = (x − K_L − K_C)/K_G, HR(q) = HR_min (1 + (r − 1) q^κ)
    [K, ∞)            tavan
Gözlenen fiyat basamaklı değildir (kullanılabilir kapasite, ithalat, teklif davranışı): fiyat = E[f(RL + ε)], ε ~ N(0, σ_RL²)
(Gauss–Hermite, 9 düğüm). C ve G'de doğrusaldır → p = A + C·B + G·Γ; kalibrasyonda G (aylık) ve C (yıllık) en küçük kareler.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

GH_X, GH_W = np.polynomial.hermite.hermgauss(9)
GH_W = GH_W / np.sqrt(np.pi)


@dataclass
class Teta:
    MC_L: float
    r: float  # HR_max / HR_min
    kappa: float
    v: float
    sigma_RL: float
    must_oran: float
    alpha: float
    beta: float = 0.0  # döngü indirimi: gün içi tepeden uzaklık d_t ile fiyat × (1 − β d_t)

    @classmethod
    def vektorden(cls, x: np.ndarray) -> Teta:
        return cls(*[float(a) for a in x])

    def vektor(self) -> np.ndarray:
        return np.array([self.MC_L, self.r, self.kappa, self.v, self.sigma_RL, self.must_oran, self.alpha, self.beta])


def gun_derinligi(RL: np.ndarray, K: np.ndarray, gun: np.ndarray) -> np.ndarray:
    """d_t = (günün azami artık yükü − RL_t) / K: saatin, akşam tepesine göre ne kadar 'çukurda' olduğu (0–1)."""
    s = pd.Series(np.asarray(RL, float))
    tepe = s.groupby(np.asarray(gun)).transform("max").to_numpy()
    return np.clip((tepe - s.to_numpy()) / np.maximum(np.asarray(K, float), 1.0), 0, 1)


def bilesenler(
    RL: np.ndarray, K_L: np.ndarray, K_C: np.ndarray, K_G: np.ndarray, t: Teta, HR_min: float, tavan: float,
    co2: np.ndarray | float = 0.0, e_L: float = 1.10, e_C: float = 0.95, e_G: float = 0.202, derinlik: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # fmt: skip
    """
    Düzgünleştirilmiş eğrinin doğrusal bileşenleri: fiyat = A + C·B + G·Γ (tümü RL şeklinde). derinlik verilirse döngü indirimi
    (1 − β d_t): termik santraller akşam tepesi için devrede kalmak üzere gün içi çukurda marjinal maliyetin altında satar
    (kalkış maliyeti, asgari çalışma süresi); doğrusallık korunur.
    """
    RL = np.asarray(RL, float)
    K_L, K_C, K_G = (np.broadcast_to(np.asarray(k, float), RL.shape) for k in (K_L, K_C, K_G))
    co2 = np.broadcast_to(np.asarray(co2, float), RL.shape)
    M = t.must_oran * (K_L + K_C)
    A = np.zeros_like(RL)
    B = np.zeros_like(RL)
    Gm = np.zeros_like(RL)
    for xi, wi in zip(GH_X, GH_W, strict=True):
        x = RL + np.sqrt(2) * t.sigma_RL * xi
        a, b, g = _f(x, K_L, K_C, K_G, M, t, HR_min, tavan, co2, e_L, e_C, e_G)
        A += wi * a
        B += wi * b
        Gm += wi * g
    if derinlik is not None and t.beta:
        k = 1 - t.beta * np.asarray(derinlik, float)
        A, B, Gm = A * k, B * k, Gm * k
    return A, B, Gm


def _hr(q: np.ndarray, t: Teta, HR_min: float) -> np.ndarray:
    return HR_min * (1 + (t.r - 1) * np.clip(q, 0, 1) ** t.kappa)


def _bant(x, K_L, K_C, K_G, t, HR_min, tavan, co2, e_L, e_C, e_G):
    """Basamaklı eğrinin x'teki (a, b, g) katsayıları (x ≥ M bölgesi)."""
    lig = x < K_L
    kom = (~lig) & (x < K_L + K_C)
    gaz = (~lig) & (~kom) & (x < K_L + K_C + K_G)
    ust = ~(lig | kom | gaz)
    q = (x - K_L - K_C) / np.maximum(K_G, 1.0)
    hr = _hr(q, t, HR_min)
    a = (
        np.where(lig, t.MC_L + e_L * co2, 0.0)
        + np.where(kom, e_C * co2, 0.0)
        + np.where(gaz, t.v + e_G * co2 * hr, 0.0)
        + np.where(ust, tavan, 0.0)
    )
    b = np.where(kom, 1.0, 0.0)
    g = np.where(gaz, hr, 0.0)
    return a, b, g


def _f(x, K_L, K_C, K_G, M, t, HR_min, tavan, co2, e_L, e_C, e_G):
    a, b, g = _bant(np.maximum(x, M), K_L, K_C, K_G, t, HR_min, tavan, co2, e_L, e_C, e_G)
    am, bm, gm = _bant(M, K_L, K_C, K_G, t, HR_min, tavan, co2, e_L, e_C, e_G)
    ram = np.clip(x / np.maximum(M, 1.0), 0, 1) ** t.alpha
    alt = x < M
    return np.where(alt, am * ram, a), np.where(alt, bm * ram, b), np.where(alt, gm * ram, g)


def fiyat(RL, K_L, K_C, K_G, C, G, t: Teta, HR_min: float, tavan: float, co2=0.0, **kw) -> np.ndarray:  # kw: e_*, derinlik
    """Saatlik fiyat (USD/MWh). C: kömür bandı fiyatı (RL şeklinde yayınlanabilir), G: gaz yakıt maliyeti ($/MWh_th)."""
    A, B, Gm = bilesenler(RL, K_L, K_C, K_G, t, HR_min, tavan, co2, **kw)
    p = A + np.asarray(C) * B + np.asarray(G) * Gm
    return np.clip(np.where(np.asarray(RL) < 0, 0.0, p), 0.0, tavan)


def su_doldur(N: np.ndarray, butce: float, h_min: float, h_max: float, iter_: int = 60) -> np.ndarray:
    """
    Barajlı hidro: Σ clip(N − λ, h_min, h_max) = bütçe olacak λ (ikiye bölme). Su en yüksek net yük saatlerine gider
    (tepe tıraşlama) — fiyat net yükte artan olduğundan bu, sabit su değeriyle gelir enbüyüklemenin yaklaşığıdır.
    """
    n = len(N)
    butce = float(np.clip(butce, n * h_min, n * h_max))
    lo, hi = float(N.min() - h_max), float(N.max())
    for _ in range(iter_):
        lam = (lo + hi) / 2
        if np.clip(N - lam, h_min, h_max).sum() > butce:
            lo = lam
        else:
            hi = lam
    return np.clip(N - (lo + hi) / 2, h_min, h_max)


def depolama_gunluk(R: np.ndarray, P: float, E: float, eta: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Günlük arbitraj, tüm günler birlikte (R: gün × 24): deşarj D = clip(R − λ_ü, 0, P) en yüksek, şarj S = clip(λ_a − R, 0, P)
    en düşük saatlerde; Σ D = η Σ S = x ≤ E. Gün başına x, λ_ü > λ_a (artık yük farkı kayıpları karşılıyor) kaldıkça büyütülür
    (iç içe ikiye bölme, günler boyunca vektörize). Fiyat artık yükte artan olduğundan bu, fiyat farkı arbitrajının vekilidir.
    """
    R = np.atleast_2d(np.asarray(R, float))
    if P <= 0 or E <= 0:
        z = np.zeros_like(R)
        return z, z
    lo0, hi0 = R.min(1), R.max(1)

    def esik(x: np.ndarray, ust: bool) -> np.ndarray:
        lo, hi = lo0.copy(), hi0.copy()
        for _ in range(40):
            m = (lo + hi) / 2
            if ust:
                fazla = np.clip(R - m[:, None], 0, P).sum(1) > x
                lo, hi = np.where(fazla, m, lo), np.where(fazla, hi, m)
            else:
                fazla = np.clip(m[:, None] - R, 0, P).sum(1) > x
                lo, hi = np.where(fazla, lo, m), np.where(fazla, m, hi)
        return (lo + hi) / 2

    xlo, xhi = np.zeros(len(R)), np.full(len(R), min(E, P * 12.0))
    for _ in range(30):
        x = (xlo + xhi) / 2
        iyi = esik(x, True) > esik(x / eta, False)
        xlo, xhi = np.where(iyi, x, xlo), np.where(iyi, xhi, x)
    lu, la = esik(xlo, True), esik(xlo / eta, False)
    D = np.where(xlo[:, None] > 1e-6, np.clip(R - lu[:, None], 0, P), 0.0)
    S = np.where(xlo[:, None] > 1e-6, np.clip(la[:, None] - R, 0, P), 0.0)
    return D, S
