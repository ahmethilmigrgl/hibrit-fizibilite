"""
Türbin yerleşimi yöntemleri — aday konumlardan N tanesini seçme (ikili seçim problemi, "wind farm layout optimisation").

Ortak girdi (Problem): n aday (x, y, GWA çarpanı m), çatışma matrisi C (elips biçimli asgari aralık), hızlı vekil iz
tablosu (CiftTablosu: türbin başına serbest enerji E_i, ikili kayıplar a_ij, karelerin toplamı süperpozisyonlu değerlendirme).

(a) MILP — ikinci dereceden ikili problemin doğrusallaştırılması (Glover 1975 kompakt doğrusallaştırması):
        maks  Σ_i E_i x_i − Σ_i Σ_j a_ij x_i x_j
        Σ_i x_i = N;   x_i + x_j ≤ 1  ((i, j) çatışıyorsa);   x ∈ {0,1}ⁿ
    x_i·(Σ_j a_ij x_j) çarpımı yerine w_i ≥ 0 ve  w_i ≥ Σ_j a_ij x_j − M_i (1 − x_i),  M_i = i'nin en büyük N−1 kaybı.
    x ikili olduğundan w_i = x_i Σ_j a_ij x_j (kesin). Amaç: maks Σ E_i x_i − Σ w_i. (Standart doğrusallaştırma
    y_ij ≥ x_i + x_j − 1 ile O(n²) değişken gerekirdi; Glover O(n) değişkenle aynı modeli kurar.)
    Not: MILP ikili kayıpların DOĞRUSAL toplamını en iyiler; gerçek model (karelerin toplamı) birden çok izin üst üste
    geldiği yerde daha az kayıp verir. Sonuç gerçek modelle yeniden değerlendirilir.
(b) Sezgiseller — gerçek vekil modeli (karelerin toplamı) doğrudan en iyiler:
    Genetik algoritma (GA): birey = N adaylık küme; turnuva seçimi, birleşim çaprazlaması (ebeveyn genleri havuzundan
    olurlu açgözlü yeniden kurma), yer değiştirme mutasyonu, elitizm; olursuz çocuk onarılır.
    Benzetimli tavlama (SA): bir türbini başka bir olurlu adaya taşı; Metropolis kabulü, geometrik soğutma; sonunda
    en iyi iyileştirme yerel araması (tüm tek taşımalar, iyileşme kalmayana dek).
(c) Referans — düzenli ızgara (hâkim eksene hizalı 7D × 4D) ve v2 açgözlü GWA kuralı (en rüzgârlı hücreler, 500 m aralık).
Açgözlü (yardımcı): her adımda (E_i − Σ_{j∈S}(a_ij + a_ji)) en büyük olurlu aday; iç içe yerleşimler → N'ye göre iz
kaybı eğrisi tek geçişte (kapasite MILP'ine parçalı doğrusal girdi).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from src.yerlesim.iz import CiftTablosu


@dataclass
class Problem:
    x: np.ndarray
    y: np.ndarray
    C: np.ndarray  # (n, n) çatışma
    cift: CiftTablosu
    N: int
    eksen: float = 0.0
    D: float = 100.0

    @property
    def n(self) -> int:
        return len(self.x)

    def olurlu_mu(self, S) -> bool:
        S = np.asarray(S, int)
        return len(set(S.tolist())) == len(S) == self.N and not self.C[np.ix_(S, S)].any()

    def amac(self, S) -> float:
        return self.cift.enerji(S)


@dataclass
class Sonuc:
    yontem: str
    S: np.ndarray
    enerji: float  # vekil model, MWh/yıl
    sure_s: float
    ayrinti: dict = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------------------ yardımcılar
def _olurlu_ekle(p: Problem, S: list[int], sira, rng=None) -> list[int]:
    """sira'daki adayları sırayla, çatışmıyorsa ekler (N'e ulaşınca durur)."""
    yasak = p.C[S].any(0) if S else np.zeros(p.n, bool)
    sec = set(S)
    for i in sira:
        if len(S) == p.N:
            break
        if i in sec or yasak[i]:
            continue
        S.append(int(i))
        sec.add(int(i))
        yasak |= p.C[i]
    return S


def acgozlu(p: Problem, N: int | None = None, egri: bool = False) -> Sonuc | tuple[Sonuc, np.ndarray]:
    """Açgözlü yerleştirme (ikili kayıplarla); egri=True → her N için vekil modelle iz kaybı oranı (iç içe yerleşimler)."""
    t0 = time.perf_counter()
    N = N or p.N
    E, a = p.cift.E_serbest, p.cift.a
    S: list[int] = []
    yasak = np.zeros(p.n, bool)
    kayip = np.zeros(p.n)
    oran = [0.0]
    for _ in range(N):
        skor = np.where(yasak, -np.inf, E - kayip)
        if not np.isfinite(skor).any():
            break
        i = int(np.argmax(skor))
        S.append(i)
        yasak |= p.C[i]
        yasak[i] = True
        kayip += a[:, i] + a[i, :]
        if egri:
            e_s = E[S].sum()
            oran.append(1 - p.cift.enerji(np.array(S)) / e_s)
    s = Sonuc("açgözlü", np.array(S), p.amac(S) if len(S) == N else np.nan, time.perf_counter() - t0)
    return (s, np.array(oran)) if egri else s


def milp(p: Problem, zaman_s: float = 60.0, bosluk: float = 1e-3, baslangic: np.ndarray | None = None) -> Sonuc:
    """Glover doğrusallaştırmalı MILP (highspy)."""
    import highspy
    from scipy import sparse

    t0 = time.perf_counter()
    n, N = p.n, p.N
    E, a = p.cift.E_serbest, p.cift.a
    M = np.sort(a, axis=1)[:, ::-1][:, : max(N - 1, 1)].sum(1)
    satir, sutun, deg = [], [], []
    alt, ust = [], []
    r = 0
    # Σ x = N
    satir += [np.full(n, r)]
    sutun += [np.arange(n)]
    deg += [np.ones(n)]
    alt.append(N)
    ust.append(N)
    r += 1
    # çatışmalar
    ii, jj = np.where(np.triu(p.C, 1))
    k = len(ii)
    satir += [r + np.arange(k), r + np.arange(k)]
    sutun += [ii, jj]
    deg += [np.ones(k), np.ones(k)]
    alt += [-np.inf] * k
    ust += [1.0] * k
    r += k
    # Glover: w_i − Σ_j a_ij x_j − M_i x_i ≥ −M_i
    for i in range(n):
        nz = np.where(a[i] > 1e-9)[0]
        satir += [np.full(len(nz) + 2, r)]
        sutun += [np.r_[nz, i, n + i]]
        deg += [np.r_[-a[i, nz], -M[i], 1.0]]
        alt.append(-M[i])
        ust.append(np.inf)
        r += 1
    A = sparse.csc_matrix((np.concatenate(deg), (np.concatenate(satir), np.concatenate(sutun))), shape=(r, 2 * n))
    inf = highspy.kHighsInf
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = 2 * n, r
    lp.col_cost_ = np.r_[E, -np.ones(n)]
    lp.col_lower_ = np.zeros(2 * n)
    lp.col_upper_ = np.r_[np.ones(n), np.full(n, inf)]
    lp.row_lower_ = np.where(np.isfinite(alt), alt, -inf)
    lp.row_upper_ = np.where(np.isfinite(ust), ust, inf)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
    lp.sense_ = highspy.ObjSense.kMaximize
    lp.integrality_ = [highspy.HighsVarType.kInteger] * n + [highspy.HighsVarType.kContinuous] * n
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(zaman_s))
    h.setOptionValue("mip_rel_gap", float(bosluk))
    h.setOptionValue("random_seed", 0)
    h.passModel(lp)
    if baslangic is not None:
        sol = highspy.HighsSolution()
        x0 = np.zeros(n)
        x0[np.asarray(baslangic, int)] = 1.0
        w0 = x0 * (a @ x0)
        sol.col_value = list(np.r_[x0, w0])
        h.setSolution(sol)
    h.run()
    if not h.getSolution().value_valid:
        raise RuntimeError(f"Yerleşim MILP'i çözülemedi: {h.modelStatusToString(h.getModelStatus())}")
    x = np.asarray(h.getSolution().col_value)[:n]
    S = np.where(x > 0.5)[0]
    info = h.getInfo()
    amac_milp = float(info.objective_function_value)
    sinir = float(info.mip_dual_bound)
    durum = h.modelStatusToString(h.getModelStatus())
    return Sonuc(
        "MILP (Glover)",
        S,
        p.amac(S) if len(S) == N else np.nan,
        time.perf_counter() - t0,
        {
            "amac_dogrusal": amac_milp,
            "ust_sinir": sinir,
            "bosluk": abs(sinir - amac_milp) / max(abs(amac_milp), 1e-9),
            "durum": durum,
            "dugum": int(info.mip_node_count),
            "catisma_cifti": int(k),
        },
    )


def genetik(
    p: Problem, tohum: int = 0, nufus: int = 40, nesil: int = 120, mutasyon: float = 0.3, turnuva: int = 3, elit: int = 2, tohum_cozum=None
) -> Sonuc:
    t0 = time.perf_counter()
    rng = np.random.default_rng(tohum)

    def rastgele() -> np.ndarray:
        # GWA'ya hafif ağırlıklı rastgele sıra (iyi bölgelerden başla)
        w = p.cift.E_serbest - p.cift.E_serbest.min() + 1e-6
        sira = rng.choice(p.n, p.n, replace=False, p=w / w.sum())
        return np.array(_olurlu_ekle(p, [], sira))

    def onar(S: list[int]) -> np.ndarray:
        return np.array(_olurlu_ekle(p, S, rng.permutation(p.n)))

    pop = [rastgele() for _ in range(nufus)]
    if tohum_cozum is not None:
        pop[0] = np.asarray(tohum_cozum, int)
    pop = [s for s in pop if len(s) == p.N] or [onar([])]
    fit = np.array([p.amac(s) for s in pop])
    gecmis = [float(fit.max())]
    for _ in range(nesil):
        sira = np.argsort(fit)[::-1]
        yeni = [pop[i] for i in sira[:elit]]
        while len(yeni) < nufus:
            ebeveyn = []
            for _ in range(2):
                adaylar = rng.choice(len(pop), turnuva, replace=False)
                ebeveyn.append(pop[adaylar[np.argmax(fit[adaylar])]])
            ortak = np.intersect1d(ebeveyn[0], ebeveyn[1])
            kalan = np.setdiff1d(np.union1d(ebeveyn[0], ebeveyn[1]), ortak)
            cocuk = _olurlu_ekle(p, [], np.r_[rng.permutation(ortak), rng.permutation(kalan)])
            if rng.random() < mutasyon and cocuk:  # yer değiştirme: 1–2 türbini yakın (≤ 4D) olurlu bir adaya taşı
                for _ in range(int(rng.integers(1, 3))):
                    k = int(rng.integers(len(cocuk)))
                    i0 = cocuk.pop(k)
                    yasak = p.C[cocuk].any(0) if cocuk else np.zeros(p.n, bool)
                    yasak[cocuk] = True
                    olur = np.where(~yasak)[0]
                    yakin = olur[np.hypot(p.x[olur] - p.x[i0], p.y[olur] - p.y[i0]) <= 4 * p.D]
                    secenek = yakin if len(yakin) else olur
                    if len(secenek):
                        cocuk.append(int(rng.choice(secenek)))
            c = onar(cocuk)
            if len(c) == p.N:
                yeni.append(c)
        pop = yeni
        fit = np.array([p.amac(s) for s in pop])
        gecmis.append(float(fit.max()))
    b = int(np.argmax(fit))
    return Sonuc("Genetik algoritma", np.sort(pop[b]), float(fit[b]), time.perf_counter() - t0, {"yakinsama": gecmis, "tohum": tohum})


def yerel_arama(p: Problem, S: np.ndarray, azami_tur: int = 10, yaricap_m: float | None = None) -> tuple[np.ndarray, float, int]:
    """En iyi iyileştirme: her türbin için (yarıçap içindeki) tüm olurlu taşımaları dene; iyileşme kalmayana dek."""
    S = np.array(S, int)
    f = p.amac(S)
    tur = 0
    for _ in range(azami_tur):
        tur += 1
        en_iyi = (0.0, None, None)
        for k in range(len(S)):
            digerleri = np.delete(S, k)
            yasak = p.C[digerleri].any(0)
            yasak[digerleri] = True
            aday = np.where(~yasak)[0]
            if yaricap_m is not None:
                aday = aday[np.hypot(p.x[aday] - p.x[S[k]], p.y[aday] - p.y[S[k]]) <= yaricap_m]
            for j in aday:
                if j == S[k]:
                    continue
                T = S.copy()
                T[k] = j
                d = p.amac(T) - f
                if d > en_iyi[0] + 1e-6:
                    en_iyi = (d, k, j)
        if en_iyi[1] is None:
            break
        S[en_iyi[1]] = en_iyi[2]
        f += en_iyi[0]
    return np.sort(S), float(p.amac(S)), tur


def tavlama(
    p: Problem, tohum: int = 0, adim: int = 3000, t0_oran: float = 0.02, sogutma: float = 0.997, yerel: bool = True, baslangic=None
) -> Sonuc:
    t0 = time.perf_counter()
    rng = np.random.default_rng(tohum)
    S = np.array(baslangic if baslangic is not None else acgozlu(p).S, int)
    f = p.amac(S)
    en_iyi_S, en_iyi_f = S.copy(), f
    T = t0_oran * f / p.N
    kabul = 0
    gecmis = []
    for it in range(adim):
        k = int(rng.integers(p.N))
        digerleri = np.delete(S, k)
        yasak = p.C[digerleri].any(0)
        yasak[S] = True
        olur = np.where(~yasak)[0]
        if len(olur) == 0:
            continue
        if rng.random() < 0.7:  # yakın taşıma
            yakin = olur[np.hypot(p.x[olur] - p.x[S[k]], p.y[olur] - p.y[S[k]]) <= 4 * p.D]
            olur = yakin if len(yakin) else olur
        j = int(rng.choice(olur))
        Y = S.copy()
        Y[k] = j
        fy = p.amac(Y)
        if fy >= f or rng.random() < np.exp((fy - f) / max(T, 1e-9)):
            S, f = Y, fy
            kabul += 1
            if f > en_iyi_f:
                en_iyi_S, en_iyi_f = S.copy(), f
        T *= sogutma
        if it % 100 == 0:
            gecmis.append(en_iyi_f)
    tur = 0
    if yerel:
        en_iyi_S, en_iyi_f, tur = yerel_arama(p, en_iyi_S, yaricap_m=6 * p.D)
    return Sonuc(
        "Benzetimli tavlama + yerel arama" if yerel else "Benzetimli tavlama",
        np.sort(en_iyi_S),
        en_iyi_f,
        time.perf_counter() - t0,
        {"kabul_orani": kabul / adim, "yakinsama": gecmis, "yerel_tur": tur, "tohum": tohum},
    )


def duzenli_izgara(p: Problem, hakim_D: float = 7.0, dik_D: float = 4.0, kaydirma_adimi: int = 4) -> Sonuc:
    """
    Hâkim eksene hizalı düzenli ızgara: satırlar hâkim rüzgâra dik, satır arası hakim_D·D, satır içi dik_D·D.
    Izgara düğümleri en yakın adaya (≤ 125 m) oturtulur; ızgara kaydırmaları denenir, en fazla düğüm sığdıran ve sonra
    serbest enerjisi en yüksek N düğüm seçilir (iz hesabı seçimde kullanılmaz — sektör pratiği referansı).
    """
    t0 = time.perf_counter()
    th = np.radians(p.eksen)
    ex, ey = np.sin(th), np.cos(th)
    u = p.x * ex + p.y * ey
    v = -p.x * ey + p.y * ex
    du, dv = hakim_D * p.D, dik_D * p.D
    en_iyi: tuple = (-1, -np.inf, None)
    for a in range(kaydirma_adimi):
        for b in range(kaydirma_adimi):
            ou, ov = a * du / kaydirma_adimi, b * dv / kaydirma_adimi
            iu = np.round((u - ou) / du)
            iv = np.round((v - ov) / dv)
            mesafe = np.hypot(u - (iu * du + ou), v - (iv * dv + ov))
            dugum: dict = {}
            for i in np.where(mesafe <= 125.0)[0]:
                key = (iu[i], iv[i])
                if key not in dugum or mesafe[i] < mesafe[dugum[key]]:
                    dugum[key] = i
            S = np.array(sorted(dugum.values(), key=lambda i: -p.cift.E_serbest[i]))
            S = np.array(_olurlu_ekle(p, [], S))[: p.N]
            if len(S) < p.N:
                skor = (len(S), -np.inf)
            else:
                skor = (len(S), float(p.cift.E_serbest[S].sum()))
            if skor > en_iyi[:2]:
                en_iyi = (*skor, S)
    S = en_iyi[2]
    if S is None or len(S) < p.N:  # ızgara N türbin sığdıramadı: kalanlar olurlu açgözlü GWA ile
        S = np.array(_olurlu_ekle(p, list(S) if S is not None else [], np.argsort(-p.cift.E_serbest)))
    return Sonuc(
        f"Düzenli ızgara {hakim_D:.0f}D×{dik_D:.0f}D", np.sort(S), p.amac(S) if len(S) == p.N else np.nan, time.perf_counter() - t0
    )


def gwa_acgozlu(p: Problem, gwa: np.ndarray, asgari_m: float = 500.0) -> Sonuc:
    """v2 kuralı: en rüzgârlı hücreler, birbirinden en az 500 m (iz ve elips kısıtı gözetilmez; elipsi ihlal ederse işaretlenir)."""
    t0 = time.perf_counter()
    S: list[int] = []
    for i in np.argsort(-np.asarray(gwa)):
        if all(np.hypot(p.x[i] - p.x[j], p.y[i] - p.y[j]) >= asgari_m for j in S):
            S.append(int(i))
        if len(S) == p.N:
            break
    S = np.array(S)
    return Sonuc("v2 GWA açgözlü (500 m)", np.sort(S), p.amac(S), time.perf_counter() - t0, {"elips_ihlali": bool(p.C[np.ix_(S, S)].any())})
