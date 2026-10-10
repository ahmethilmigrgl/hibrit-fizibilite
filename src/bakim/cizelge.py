"""
Yıllık önleyici bakım çizelgesi — zaman indeksli MILP (highspy).

Kümeler      I türbinler, D = {0..364} yılın günleri
Parametreler W   bakım iş saati (tırmanma koşulunda, vardiya içinde)
             p_d  d gününde (08:00 TSİ) başlayan bakımın beklenen takvim süresi [gün] (hava ve vardiya; 10 hava yılı)
             c_d  aynı bakımın beklenen kayıp geliri [$] (ortalama paylı türbin; yalnız çalışılan saatlerde duruş,
                  saatlik üretim × saatlik fiyat; 10 hava yılı ortalaması);  π_i türbin üretim payı (iz ve GWA)
             K    aynı anda çalışabilen bakım ekibi sayısı
Değişkenler  x_{i,d} ∈ {0,1}  türbin i'nin bakımı d gününde başlar  (d + p_d ≤ 365)
Amaç         min Σ_i Σ_d π_i c_d x_{i,d}
Kısıtlar     Σ_d x_{i,d} = 1                                    ∀ i      (her türbin yılda bir kez)
             Σ_i Σ_{d : d ≤ t < d + p_d} x_{i,d} ≤ K            ∀ t ∈ D  (ekip kapasitesi)
Kazanç, iki saf kurala göre raporlanır: "bahar kampanyası" (1 Nisan'dan ardışık) ve "yıla eşit dağıtım".
"""

from __future__ import annotations

import time

import numpy as np

from src.bakim.hava import SAAT_YIL, HavaZaman


def gunluk_parametreler(v_yillar, E_yillar, fiyat, W: float, tirmanma: float, vardiya) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(c_d [$], p_d [gün, tamsayı], kayıp enerji [MWh]) — ortalama paylı türbin için, 10 hava yılı ortalaması."""
    Y = v_yillar.shape[0]
    c = np.zeros((Y, 365))
    e = np.zeros((Y, 365))
    gun = np.zeros((Y, 365))
    for y in range(Y):
        v = np.r_[v_yillar[y], v_yillar[(y + 1) % Y]]
        E = np.r_[E_yillar[y], E_yillar[(y + 1) % Y]]
        R = E * np.r_[fiyat, fiyat]
        hz = HavaZaman(v, tirmanma, vardiya, 1, [99.0])
        ok = np.flatnonzero(np.diff(hz.cum) > 0)
        for d in range(365):
            bas = d * 24 + 5
            k0 = int(hz.cum[bas])
            idx = ok[k0 : k0 + int(np.ceil(W))]
            c[y, d] = R[idx].sum()
            e[y, d] = E[idx].sum()
            gun[y, d] = (idx[-1] + 1 - bas) / 24 if len(idx) else 365
    p = np.ceil(gun.mean(0)).astype(int)
    return c.mean(0), np.maximum(p, 1), e.mean(0)


def coz(pay: np.ndarray, c: np.ndarray, p: np.ndarray, K: int, zaman_s: float = 30.0) -> dict:
    import highspy
    from scipy import sparse

    t0 = time.perf_counter()
    N = len(pay)
    gunler = [d for d in range(365) if d + p[d] <= 365]
    G = len(gunler)
    col = lambda i, k: i * G + k
    satir, sutun, deg = [], [], []
    for i in range(N):
        satir.append(np.full(G, i))
        sutun.append(i * G + np.arange(G))
        deg.append(np.ones(G))
    r0 = N
    for k, d in enumerate(gunler):
        for i in range(N):
            for t in range(d, d + p[d]):
                satir.append(np.array([r0 + t]))
                sutun.append(np.array([col(i, k)]))
                deg.append(np.array([1.0]))
    A = sparse.csc_matrix((np.concatenate(deg), (np.concatenate(satir), np.concatenate(sutun))), shape=(N + 365, N * G))
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = N * G, N + 365
    lp.col_cost_ = np.concatenate([pay[i] * c[gunler] for i in range(N)])
    lp.col_lower_ = np.zeros(N * G)
    lp.col_upper_ = np.ones(N * G)
    lp.row_lower_ = np.r_[np.ones(N), np.full(365, -highspy.kHighsInf)]
    lp.row_upper_ = np.r_[np.ones(N), np.full(365, float(K))]
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
    lp.sense_ = highspy.ObjSense.kMinimize
    lp.integrality_ = [highspy.HighsVarType.kInteger] * (N * G)
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(zaman_s))
    h.passModel(lp)
    h.run()
    durum = h.modelStatusToString(h.getModelStatus())
    if not h.getSolution().value_valid:
        raise RuntimeError(f"Bakım çizelgesi MILP'i çözülemedi: {durum}")
    x = np.asarray(h.getSolution().col_value).reshape(N, G)
    bas = np.array([gunler[int(np.argmax(x[i]))] for i in range(N)])
    info = h.getInfo()
    return {
        "gun": bas,
        "maliyet": float(sum(pay[i] * c[bas[i]] for i in range(N))),
        "durum": durum,
        "bosluk": float(info.mip_gap),
        "sure_s": time.perf_counter() - t0,
        "degisken": N * G,
    }


def kapasite_ihlali(bas: np.ndarray, p: np.ndarray, K: int) -> int:
    yuk = np.zeros(400, int)
    for d in bas:
        yuk[d : d + p[d]] += 1
    return int((yuk > K).sum())


def bahar_kampanyasi(pay, c, p, K: int, baslangic: int = 90) -> dict:
    """K ekip 1 Nisan'dan itibaren türbinleri sırayla bakar (biten ekip sıradakine geçer)."""
    serbest = np.full(K, baslangic)
    bas = np.zeros(len(pay), int)
    for i in range(len(pay)):
        k = int(np.argmin(serbest))
        d = int(serbest[k])
        bas[i] = d
        serbest[k] = d + p[d]
    return {"gun": bas, "maliyet": float(sum(pay[i] * c[bas[i]] for i in range(len(pay))))}


def esit_dagitim(pay, c, p, K: int) -> dict:
    bas = np.linspace(0, 365 - p.max() - 1, len(pay)).astype(int)
    return {"gun": bas, "maliyet": float(sum(pay[i] * c[bas[i]] for i in range(len(pay))))}


def aylik_takvim(bas: np.ndarray) -> list[int]:
    ay = np.repeat(np.arange(12), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    return np.bincount(ay[np.asarray(bas) % 365], minlength=12).tolist()


__all__ = ["SAAT_YIL", "aylik_takvim", "bahar_kampanyasi", "coz", "esit_dagitim", "gunluk_parametreler", "kapasite_ihlali"]
