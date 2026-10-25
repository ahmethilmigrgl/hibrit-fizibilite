"""
Merit order kalibrasyonu.

İç problem (θ verilince, doğrusal): p_t ≈ A_t + C_{y(t)} B_t + G_{m(t)} Γ_t → aylık gaz yakıt maliyeti G_m ve yıllık kömür bandı
fiyatı C_y sınırlı doğrusal en küçük kareler (scipy lsq_linear, seyrek tasarım matrisi). G_m ve C_y "yakıt fiyatı gözlemi"dir:
fiyatın seviyesini taşır.
Dış problem (θ, doğrusal değil): MC_L, r = HR_max/HR_min, κ, v, σ_RL, must_oran, α → aylık ortalamaya göre bağıl saatlik
RMSE'yi Nelder–Mead ile küçült (mutlak RMSE'de 2022 krizinin yüksek fiyatları şekli bastırıyordu)
(HR_min sabit: G·HR ölçek belirsizliğini kaldırır). θ ŞEKLİ taşır: saat içi, gün içi ve yenilenebilir bolluğuna tepki.
Doğrulama: θ kalibrasyon yıllarında, test yıllarında yalnız G_m ve C_y yeniden tahmin edilir (seviye bilgisi) — şekil dışarıdan sınanır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear, minimize
from scipy.sparse import csr_matrix, hstack

from src.merit.model import Teta, bilesenler, gun_derinligi
from src.merit.veri import yakalanma

SINIR = {
    "MC_L": (0, 120), "r": (1.05, 3.0), "kappa": (0.3, 6), "v": (-20, 40), "sigma_RL": (200, 6000), "must_oran": (0.05, 0.95),
    "alpha": (0.2, 15), "beta": (0.0, 3.0),
}  # fmt: skip


def _donustur(x: np.ndarray) -> Teta:
    """Kısıtsız vektör → sınırlı θ (lojistik)."""
    s = list(SINIR.values())
    return Teta.vektorden(np.array([lo + (hi - lo) / (1 + np.exp(-xi)) for xi, (lo, hi) in zip(x, s, strict=True)]))


def _ters(t: Teta) -> np.ndarray:
    s = list(SINIR.values())
    return np.array([np.log((v - lo) / (hi - v)) for v, (lo, hi) in zip(t.vektor(), s, strict=True)])


def seviyeler(d: pd.DataFrame, t: Teta, HR_min: float) -> dict:
    """İç problem: aylık G ve yıllık C (en küçük kareler) + uydurulmuş fiyat."""
    tavan = d.groupby("ay")["P"].transform("max").to_numpy()
    K = (d["K_L"] + d["K_C"] + d["K_G"]).to_numpy()
    der = gun_derinligi(d["RL"].to_numpy(), K, d.index.tz_convert("Europe/Istanbul").date if d.index.tz is not None else d.index.date)
    A, B, Gm = bilesenler(d["RL"].to_numpy(), d["K_L"].to_numpy(), d["K_C"].to_numpy(), d["K_G"].to_numpy(), t, HR_min, tavan, derinlik=der)
    ay_kod, ay_ad = pd.factorize(d["ay"])
    yil_kod, yil_ad = pd.factorize(d["yil"])
    n = len(d)
    satir = np.arange(n)
    Xg = csr_matrix((Gm, (satir, ay_kod)), shape=(n, len(ay_ad)))
    Xc = csr_matrix((B, (satir, yil_kod)), shape=(n, len(yil_ad)))
    X = hstack([Xg, Xc]).tocsr()
    y = d["P"].to_numpy() - A
    r = lsq_linear(
        X, y, bounds=(np.r_[np.full(len(ay_ad), 1.0), np.zeros(len(yil_ad))], np.full(len(ay_ad) + len(yil_ad), 500.0)), lsmr_tol="auto"
    )
    G = r.x[: len(ay_ad)]
    C = r.x[len(ay_ad) :]
    p = np.clip(A + C[yil_kod] * B + G[ay_kod] * Gm, 0, tavan)
    p = np.where(d["RL"].to_numpy() < 0, 0.0, p)
    ort = d.groupby("ay")["P"].transform("mean").to_numpy()
    return {
        "G": pd.Series(G, index=ay_ad),
        "C": pd.Series(C, index=yil_ad),
        "p": p,
        "rmse": float(np.sqrt(np.mean((p - d["P"].to_numpy()) ** 2))),
        # bağıl hata (aylık ortalamaya göre): seviye yerine şekli ölçer; 2022 krizinin yüksek fiyatları amacı domine etmez
        "rmse_goreli": float(np.sqrt(np.mean(((p - d["P"].to_numpy()) / np.maximum(ort, 5.0)) ** 2))),
    }


def kalibre(d: pd.DataFrame, baslangic: Teta, HR_min: float, maxiter: int = 600, olcut: str = "rmse_goreli") -> tuple[Teta, dict]:
    hedef = lambda x: seviyeler(d, _donustur(x), HR_min)[olcut]
    r = minimize(
        hedef, _ters(baslangic), method="Nelder-Mead", options={"maxiter": maxiter, "xatol": 1e-3, "fatol": 1e-4, "adaptive": True}
    )
    t = _donustur(r.x)
    return t, {olcut: float(r.fun), "iter": int(r.nit), "basarili": bool(r.success)}


def metrikler(d: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    """Yıl başına saatlik uyum ve yakalanma oranları (gözlenen ↔ model)."""
    sat = []
    for y, x in d.assign(_p=p).groupby("yil"):
        o, m = x["P"].to_numpy(), x["_p"].to_numpy()
        go = x.groupby(x.index.hour)
        sat.append(
            {
                "yil": int(y),
                "ort_gozlenen": float(o.mean()),
                "ort_model": float(m.mean()),
                "rmse": float(np.sqrt(np.mean((m - o) ** 2))),
                "r2": float(1 - np.sum((m - o) ** 2) / np.sum((o - o.mean()) ** 2)),
                "korelasyon": float(np.corrcoef(o, m)[0, 1]),
                "gunici_korelasyon": float(np.corrcoef(go["P"].mean(), go["_p"].mean())[0, 1]),
                "gunes_yakalanma_gozlenen": yakalanma(o, x["S"].to_numpy()),
                "gunes_yakalanma_model": yakalanma(m, x["S"].to_numpy()),
                "ruzgar_yakalanma_gozlenen": yakalanma(o, x["W"].to_numpy()),
                "ruzgar_yakalanma_model": yakalanma(m, x["W"].to_numpy()),
                "sifir_saat_gozlenen": float((o < 1).mean()),
                "sifir_saat_model": float((m < 1).mean()),
            }
        )
    return pd.DataFrame(sat).set_index("yil")
