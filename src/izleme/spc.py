"""
İstatistiksel süreç kontrolü (SPC): alt yönlü Shewhart, EWMA ve CUSUM kartları, parametrelerin hedef ortalama çalışma
uzunluğuna (ARL0) göre kalibrasyonu ve yapay arıza testi.

Girdi: santral başına dönemlik (aylık) standart sapma birimli z_t = (x_t − μ_t) / σ0 (x = akranla birleştirilmiş ln oran,
μ_t taban, σ0 sağlam tahminci; src/izleme/analiz.py).
Kartlar (yalnız düşüşler; performans artışı alarm değildir):
    Shewhart    alarm ⇔ z_t < −L_s                                  (ani, büyük düşüşler)
    EWMA        e_t = λ z_t + (1 − λ) e_{t−1}, e_0 = 0; alarm ⇔ e_t < −L_e · sqrt(λ / (2 − λ))   (küçük, kalıcı kaymalar)
    CUSUM       C_t = max(0, C_{t−1} − z_t − k), C_0 = 0;  alarm ⇔ C_t > h                     (kalıcı kayma, en hızlı)
ARL0: kontrol altındaki süreçte ilk (yanlış) alarma kadar beklenen dönem sayısı. Parametreler, z'lerden
durağan blok bootstrap ile üretilen kontrol altı serilerde ARL0 = hedef olacak şekilde kök bularak seçilir (otokorelasyon
korunur; normal varsayımı yok).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def shewhart(z: np.ndarray, L: float) -> np.ndarray:
    return np.asarray(z) < -L


def ewma(z: np.ndarray, lam: float, L: float) -> tuple[np.ndarray, np.ndarray]:
    e = np.zeros(len(z))
    s = 0.0
    for i, x in enumerate(z):
        if not np.isnan(x):  # eksik dönem: kart değişmez
            s = lam * x + (1 - lam) * s
        e[i] = s
    return e, e < -L * np.sqrt(lam / (2 - lam))


def cusum(z: np.ndarray, k: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    c = np.zeros(len(z))
    s = 0.0
    for i, x in enumerate(z):
        if not np.isnan(x):
            s = max(0.0, s - x - k)
        c[i] = s
    return c, c > h


def _ilk_alarm_toplu(Z: np.ndarray, kart: str, p: float, lam: float, k: float) -> np.ndarray:
    """Z: (R, T) seriler → ilk alarm indeksi (yoksa T). Vektörize (R boyunca)."""
    R, T = Z.shape
    ilk = np.full(R, T)
    aktif = np.ones(R, bool)
    s = np.zeros(R)
    esik = -p * np.sqrt(lam / (2 - lam))
    for t in range(T):
        x = Z[:, t]
        if kart == "shewhart":
            al = x < -p
        elif kart == "ewma":
            s = lam * x + (1 - lam) * s
            al = s < esik
        else:
            s = np.maximum(0.0, s - x - k)
            al = s > p
        yeni = al & aktif
        ilk[yeni] = t
        aktif &= ~yeni
        if not aktif.any():
            break
    return ilk


def bootstrap_seriler(havuz: list[np.ndarray], R: int, T: int, blok: int, tohum: int) -> np.ndarray:
    """Durağan blok bootstrap (Politis–Romano): santral taban serilerinden geometrik uzunluklu bloklar."""
    rng = np.random.default_rng(tohum)
    seriler = [s[~np.isnan(s)] for s in havuz if np.isfinite(s).sum() > 2 * blok]
    out = np.empty((R, T))
    for r in range(R):
        x = seriler[rng.integers(len(seriler))]
        i, t = rng.integers(len(x)), 0
        while t < T:
            out[r, t] = x[i]
            t += 1
            i = rng.integers(len(x)) if rng.random() < 1 / blok else (i + 1) % len(x)
            if rng.random() < 1 / blok:
                x = seriler[rng.integers(len(seriler))]
                i = rng.integers(len(x))
    return out


def arl(Z: np.ndarray, kart: str, p: float, lam: float = 0.2, k: float = 0.5) -> float:
    """Sansürlü ilk alarm zamanlarından ARL (T'ye ulaşanlar için üstel kuyruk düzeltmesiyle ortalama)."""
    ilk = _ilk_alarm_toplu(Z, kart, p, lam, k)
    T = Z.shape[1]
    olay = ilk < T
    # üstel (geometrik) yaklaşık: ARL ≈ toplam gözlenen süre / alarm sayısı (sansürlü veride ML tahmini)
    return float((np.minimum(ilk, T) + 1).sum() / max(olay.sum(), 1))


def kalibre(Z: np.ndarray, hedef_arl: float, lam: float, k: float) -> dict:
    """Her kart için ARL0 = hedef veren parametre (L_s, L_e, h)."""
    out = {}
    for kart, (a, b) in {"shewhart": (1.0, 6.0), "ewma": (0.5, 6.0), "cusum": (0.5, 15.0)}.items():
        f = lambda p, kart=kart: np.log(arl(Z, kart, p, lam, k)) - np.log(hedef_arl)
        out[kart] = float(brentq(f, a, b, xtol=1e-3))
    return out


def alarmlar(z: np.ndarray, par: dict, lam: float, k: float) -> dict:
    e, a_e = ewma(z, lam, par["ewma"])
    c, a_c = cusum(z, k, par["cusum"])
    return {"shewhart": shewhart(z, par["shewhart"]), "ewma": a_e, "cusum": a_c, "ewma_deger": e, "cusum_deger": c}


def yapay_ariza_testi(
    seriler: list[np.ndarray],
    sigma0: list[float],
    par: dict,
    lam: float,
    k: float,
    buyuklukler,
    sureler,
    n_tekrar: int,
    tohum: int,
    pencere_ek: int = 4,
) -> list[dict]:
    """
    Kontrol altı (normal durumlu) santrallerin izleme dönemi z serilerine yapay düşüş eklenir: oran × (1 − δ) ⇔
    z' = z + ln(1 − δ) / σ0, D dönem. Yakalama: arıza başlangıcından [0, D + pencere_ek) içinde alarm. Gecikme: ilk alarm −
    başlangıç (dönem). Yanlış alarm: arızasız dönemlerde yılda alarm sayısı (alarmdan sonra kart sıfırlanır).
    """
    rng = np.random.default_rng(tohum)
    sonuc = []
    for d in buyukluk_listesi(buyuklukler):
        for D in sureler:
            yak = {x: [] for x in ("shewhart", "ewma", "cusum")}
            gec = {x: [] for x in ("shewhart", "ewma", "cusum")}
            for _ in range(n_tekrar):
                j = rng.integers(len(seriler))
                z = seriler[j].copy()
                if len(z) < D + 30:
                    continue
                b = rng.integers(13, len(z) - D - pencere_ek)
                z[b : b + D] += np.log(1 - d) / sigma0[j]
                al = alarmlar(z[b - 13 :], par, lam, k)  # 13 dönemlik ısınma: kart arıza başladığında sıfır durumda değil
                for x in yak:
                    w = al[x][13 : 13 + D + pencere_ek]
                    ok = bool(w.any())
                    yak[x].append(ok)
                    if ok:
                        gec[x].append(int(np.argmax(w)))
            for x in yak:
                sonuc.append(
                    {
                        "kart": x,
                        "dusus": d,
                        "sure_donem": D,
                        "yakalama": float(np.mean(yak[x])) if yak[x] else np.nan,
                        "gecikme_medyan_donem": float(np.median(gec[x])) if gec[x] else np.nan,
                        "n": len(yak[x]),
                    }
                )
    return sonuc


def buyukluk_listesi(x) -> list[float]:
    return [float(v) for v in x]


def yanlis_alarm_orani(seriler: list[np.ndarray], par: dict, lam: float, k: float, donem_yil: float = 12.0) -> dict:
    """Kart sıfırlamalı yıllık alarm sayısı (gerçek izleme dönemi serilerinde; 'normal' santraller)."""
    out = {}
    for x in ("shewhart", "ewma", "cusum"):
        alarm, donem = 0, 0
        for z in seriler:
            zz = z[~np.isnan(z)]
            t = 0
            while t < len(zz):
                ilk = _ilk_alarm_toplu(zz[None, t:], x, par[x], lam, k)[0]
                if ilk >= len(zz) - t:
                    break
                alarm += 1
                t += ilk + 1
            donem += len(zz)
        out[x] = donem_yil * alarm / max(donem, 1)
    return out
