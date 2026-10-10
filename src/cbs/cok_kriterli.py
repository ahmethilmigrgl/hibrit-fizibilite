"""
Çok kriterli saha seçimi (v3 E3): AHP ağırlıkları, TOPSIS sıralaması, ağırlık belirsizliğine dayanıklılık, ROC/AUC doğrulaması.

AHP (Saaty 1980):
    A_ij: i kriterinin j'ye göre önemi (1–9 ölçeği), A_ji = 1/A_ij
    ağırlık w = A'nın en büyük özdeğerine (λ_max) ait özvektör, Σw = 1
    tutarlılık indeksi CI = (λ_max − n)/(n − 1);  tutarlılık oranı CR = CI / RI(n)  (RI: Saaty rastgele indeksi)
    CR > 0,10 → karşılaştırmalar tutarsız, gözden geçirilmeli
TOPSIS (Hwang & Yoon 1981):
    r_ij = x_ij / ‖x_·j‖ (vektör normalizasyonu), v_ij = w_j r_ij
    ideal A⁺_j = maks v_ij (fayda) | min v_ij (maliyet); ideal olmayan A⁻ tersi
    d⁺_i = ‖v_i − A⁺‖, d⁻_i = ‖v_i − A⁻‖;  yakınlık C_i = d⁻_i / (d⁺_i + d⁻_i) ∈ [0, 1]
Dayanıklılık: ağırlıklar Dirichlet(α · w) ile örneklenir (α büyüdükçe w etrafında dar); her örnekte TOPSIS ilk K → olasılık.
Doğrulama: mevcut RES hücreleri (1) ile diğerleri (0) arasında uygunluk puanının ROC eğrisi ve AUC (Mann–Whitney).
"""

from __future__ import annotations

import numpy as np

RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


def ahp(A: np.ndarray) -> dict:
    A = np.asarray(A, float)
    n = A.shape[0]
    if not np.allclose(A * A.T, 1.0, atol=1e-6):
        raise ValueError("AHP matrisi karşılıklı değil (A_ji = 1/A_ij olmalı)")
    deg, vek = np.linalg.eig(A)
    k = int(np.argmax(deg.real))
    lam = float(deg[k].real)
    w = np.abs(vek[:, k].real)
    w = w / w.sum()
    ci = (lam - n) / (n - 1) if n > 2 else 0.0
    cr = ci / RI[n] if RI.get(n, 0) > 0 else 0.0
    return {"agirlik": w, "lambda_maks": lam, "CI": ci, "CR": cr, "tutarli": cr <= 0.10}


def ikili_matris(degerler: dict[tuple[int, int], float], n: int) -> np.ndarray:
    """Üst üçgen karşılaştırmalardan (i < j: i'nin j'ye göre önemi) karşılıklı matris."""
    A = np.ones((n, n))
    for (i, j), v in degerler.items():
        A[i, j] = v
        A[j, i] = 1.0 / v
    return A


def topsis(X: np.ndarray, w: np.ndarray, fayda: np.ndarray, vektor: bool = True) -> np.ndarray:
    """X: (m alternatif, n kriter); fayda: True = büyük iyi, False = küçük iyi. Döndürür: yakınlık katsayısı C (m).
    vektor=False: X önceden ortak [0, 1] ölçeğe standardize edilmiş (değer fonksiyonu), normalizasyon atlanır."""
    X = np.asarray(X, float)
    w = np.asarray(w, float) / np.sum(w)
    if vektor:
        nrm = np.sqrt((X**2).sum(0))
        R = X / np.where(nrm > 0, nrm, 1.0)
    else:
        R = X
    V = R * w
    fayda = np.asarray(fayda, bool)
    a_pos = np.where(fayda, V.max(0), V.min(0))
    a_neg = np.where(fayda, V.min(0), V.max(0))
    dp = np.sqrt(((V - a_pos) ** 2).sum(1))
    dn = np.sqrt(((V - a_neg) ** 2).sum(1))
    return dn / np.maximum(dp + dn, 1e-12)


def dayaniklilik(
    X: np.ndarray, w: np.ndarray, fayda: np.ndarray, K: int = 10, n: int = 1000, alfa: float = 50.0, tohum: int = 0, vektor: bool = True
) -> np.ndarray:
    """Her alternatifin, ağırlıklar Dirichlet(alfa·w) ile örneklendiğinde ilk K'ya girme olasılığı."""
    rng = np.random.default_rng(tohum)
    W = rng.dirichlet(np.maximum(alfa * np.asarray(w, float), 1e-3), n)
    say = np.zeros(X.shape[0])
    for wi in W:
        c = topsis(X, wi, fayda, vektor)
        say[np.argsort(-c)[:K]] += 1
    return say / n


def auc(puan: np.ndarray, etiket: np.ndarray) -> float:
    """ROC eğrisi altındaki alan (Mann–Whitney U / (n1·n0)); eşit puanlar yarım sayılır."""
    puan = np.asarray(puan, float)
    etiket = np.asarray(etiket, bool)
    from scipy.stats import rankdata

    r = rankdata(puan)
    n1, n0 = etiket.sum(), (~etiket).sum()
    return float((r[etiket].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def roc(puan: np.ndarray, etiket: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(yanlış pozitif oranı, doğru pozitif oranı) dizileri, eşik azalan."""
    o = np.argsort(-np.asarray(puan, float))
    e = np.asarray(etiket, bool)[o]
    tp = np.r_[0, np.cumsum(e)] / max(e.sum(), 1)
    fp = np.r_[0, np.cumsum(~e)] / max((~e).sum(), 1)
    return fp, tp


def en_iyi_agirlik(X: np.ndarray, fayda: np.ndarray, etiket: np.ndarray, n: int = 3000, tohum: int = 0, vektor: bool = True) -> dict:
    """Ağırlık simpleksinde rastgele arama: mevcut santralleri en iyi ayıran (AUC en büyük) TOPSIS ağırlıkları ("açığa çıkan tercih")."""
    rng = np.random.default_rng(tohum)
    k = X.shape[1]
    en = (-1.0, None)
    for w in np.r_[np.eye(k), rng.dirichlet(np.ones(k), n)]:
        a = auc(topsis(X, w, fayda, vektor), etiket)
        if a > en[0]:
            en = (a, w)
    return {"auc": en[0], "agirlik": en[1]}
