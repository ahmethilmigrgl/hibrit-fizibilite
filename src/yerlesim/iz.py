"""
İz (wake) modeli.

Referans: DTU PyWake (MIT lisansı) — PropagateDownwind + BastankhahGaussianDeficit (Bastankhah & Porté-Agel 2014; genişleme
katsayısı k = 0,38·TI + 0,004, Niayifar & Porté-Agel 2016) + karelerin toplamı süperpozisyonu; duyarlılık için Jensen/Park
(NOJ, Katić vd. 1986; kara için k = 0,075). Türbin başına yerel hız GWA çarpanıyla (XRSite 'Speedup').

Hızlı vekil (optimizasyon için): PyWake'in Bastankhah formülünün aynısı, iki basitleştirmeyle:
    (1) kaynak türbinin CT'si kendi yerel serbest hızında (izli hızında değil) değerlendirilir;
    (2) açıklar aday çiftleri için bir kez hesaplanır: A[i, j, w, s] = (δ_ij(w, s) · m_j)².
    Bir yerleşimin (S) etkin hızı:  WS_eff_i = ws_s · (m_i − √(Σ_{j∈S} A[i, j, w, s]))
    δ_ij = min(1, 2·a(CT_j D_j² / (8σ²))) · exp(−r²/(2σ²)),  σ = k·x + ε·D_j,  ε = 0,2·√β,  β = ½(1+√(1−CT))/√(1−CT)
    (x: rüzgâr yönünde uzaklık > 0; r: dik uzaklık, göbek yüksekliği farkı dahil; a(·): Madsen 2020 CT→indüksiyon).
İkili enerji kaybı (MILP için): a_ij = E_i^serbest − E_i(yalnız j varken)  [MWh/yıl].
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from src.yerlesim.ruzgar_gulu import AkisTablosu
from src.yerlesim.turbin import TurbinEgrisi

SAAT_YIL = 8760.0


def ct2a(ct: np.ndarray) -> np.ndarray:
    """Madsen vd. (2020) CT → eksenel indüksiyon yaklaşımı (PyWake ct2a_madsen)."""
    return ct * (0.2460 + ct * (0.0586 + ct * 0.0883))


def k_ti(ti: float) -> float:
    """Gauss iz genişlemesi: k* = 0,38·TI + 0,004 (Niayifar & Porté-Agel 2016)."""
    return 0.38 * ti + 0.004


def akis_vektoru(wd_derece: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rüzgârın estiği yön θ için akış birim vektörü (doğu, kuzey): rüzgâr θ'dan θ+180'e akar."""
    t = np.radians(wd_derece)
    return -np.sin(t), -np.cos(t)


def bastankhah_delta(dw: np.ndarray, cw: np.ndarray, ct: np.ndarray, D: np.ndarray, k: float, ceps: float = 0.2, ctlim: float = 0.899):
    """Bağıl açık (kaynak yerel hızına göre); dw ≤ 0 için 0."""
    s1 = np.sqrt(1 - np.minimum(ctlim, ct))
    beta = 0.5 * (1 + s1) / s1
    eps = ceps * np.sqrt(beta)
    sig = k * np.maximum(dw, 0) + eps * D
    merkez = np.minimum(1.0, 2.0 * ct2a(ct * D**2 / (8 * sig**2)))
    return np.where(dw > 1e-6, merkez * np.exp(-(cw**2) / (2 * sig**2)), 0.0)


@dataclass
class CiftTablosu:
    """Aday çiftleri için önceden hesaplanmış açıklar ve enerji kayıpları (hızlı vekil)."""

    A: np.ndarray  # (n, n, n_wd, n_ws) float32: (δ_ij m_j)²
    m: np.ndarray  # (n,) GWA hız çarpanı
    akis: AkisTablosu
    turbin: TurbinEgrisi
    E_serbest: np.ndarray  # (n,) MWh/yıl
    a: np.ndarray  # (n, n) ikili enerji kaybı a_ij [MWh/yıl] (i'nin j yüzünden kaybı)

    def enerji(self, S: np.ndarray, turbin_basina: bool = False):
        """Seçim S için yıllık enerji [MWh] (karelerin toplamı süperpozisyonu)."""
        S = np.asarray(S, int)
        top = self.A[np.ix_(S, S)].sum(1)  # (|S|, w, s)
        ws = self.akis.ws[None, None, :]
        v = ws * np.maximum(self.m[S][:, None, None] - np.sqrt(top), 0.0)
        e = (self.turbin.guc_mw(v) * self.akis.P[None]).sum((1, 2)) * SAAT_YIL
        return e if turbin_basina else float(e.sum())


def cift_tablosu(x, y, m, akis: AkisTablosu, t: TurbinEgrisi, ti: float) -> CiftTablosu:
    x, y, m = np.asarray(x, float), np.asarray(y, float), np.asarray(m, float)
    n = len(x)
    k = k_ti(ti)
    fx, fy = akis_vektoru(akis.wd)  # (w,)
    dx = x[:, None] - x[None]  # i − j (hedef − kaynak)
    dy = y[:, None] - y[None]
    dw = dx[..., None] * fx + dy[..., None] * fy  # (n, n, w)
    cw = np.abs(-dx[..., None] * fy + dy[..., None] * fx)
    ct = t.ct_v(m[:, None] * akis.ws[None])  # (j, s) kaynak CT'si yerel serbest hızında
    A = np.empty((n, n, len(akis.wd), len(akis.ws)), np.float32)
    for s in range(len(akis.ws)):
        d = bastankhah_delta(dw, cw, ct[None, :, None, s], t.D, k)  # (n, n, w)
        A[..., s] = (d * m[None, :, None]) ** 2
    idx = np.arange(n)
    A[idx, idx] = 0.0
    ws = akis.ws[None, None, :]
    E_s = (t.guc_mw(m[:, None, None] * ws) * akis.P[None]).sum((1, 2)) * SAAT_YIL
    a = np.zeros((n, n))
    for i in range(n):
        v = ws * np.maximum(m[i] - np.sqrt(A[i]), 0.0)  # (j, w, s)
        a[i] = E_s[i] - (t.guc_mw(v) * akis.P[None]).sum((1, 2)) * SAAT_YIL
    a[idx, idx] = 0.0
    return CiftTablosu(A, m, akis, t, E_s, np.maximum(a, 0.0))


# ---------------------------------------------------------------------------------------------------------------- PyWake
def _pywake_site(P: np.ndarray, wd: np.ndarray, ws: np.ndarray, speedup: np.ndarray, ti: float):
    import xarray as xr
    from py_wake.site import XRSite

    ds = xr.Dataset(
        {"P": (("wd", "ws"), P), "Speedup": ("i", speedup), "TI": ti},
        coords={"wd": wd, "ws": ws, "i": np.arange(len(speedup))},
    )
    return XRSite(ds)


def pywake_modeli(site, wts, model: str, ti: float, k_jensen: float = 0.075):
    from py_wake.deficit_models.gaussian import BastankhahGaussianDeficit
    from py_wake.deficit_models.noj import NOJDeficit
    from py_wake.superposition_models import SquaredSum
    from py_wake.wind_farm_models import PropagateDownwind

    if model == "jensen":
        defi = NOJDeficit(k=k_jensen)
    else:
        defi = BastankhahGaussianDeficit(k=k_ti(ti))
    return PropagateDownwind(site, wts, wake_deficitModel=defi, superpositionModel=SquaredSum())


@dataclass
class ReferansSonuc:
    E_serbest: np.ndarray  # (N,) MWh/yıl — çiftlik türbinleri, iz yok
    E_ic: np.ndarray  # yalnız çiftlik içi iz
    E_toplam: np.ndarray  # çiftlik içi + komşu izleri
    guc_tablosu: np.ndarray  # (n_wd, n_ws) çiftliğin toplam gücü [MW] (komşular dahil izle)
    guc_tablosu_ic: np.ndarray  # yalnız iç iz
    guc_tablosu_serbest: np.ndarray  # izsiz (GWA çarpanlarıyla)
    wd: np.ndarray
    ws: np.ndarray


def referans(
    x,
    y,
    m,
    turbin: TurbinEgrisi,
    akis: AkisTablosu,
    ti: float,
    model: str = "bastankhah",
    komsu: dict | None = None,
    ws_adim: float = 1.0,
    parca: int = 6,
) -> ReferansSonuc:
    """
    PyWake referans hesabı (36 yön × ws_adim m/s). komsu: {"x","y","m","turbinler": [TurbinEgrisi], "tip": indeks dizisi}.
    Yönler 'parca'lık gruplar halinde çözülür (bellek). Döndürür: türbin başına enerjiler ve güç tabloları (saatlik verim için).
    """
    from py_wake.wind_turbines import WindTurbines

    x, y, m = np.asarray(x, float), np.asarray(y, float), np.asarray(m, float)
    N = len(x)
    ws = np.arange(ws_adim / 2, 30.0, ws_adim)
    # akış tablosunu bu hız ızgarasına topla
    j = np.clip(np.digitize(akis.ws, np.arange(0, 30.0 + ws_adim, ws_adim)) - 1, 0, len(ws) - 1)
    P = np.zeros((len(akis.wd), len(ws)))
    for jj in range(len(ws)):
        P[:, jj] = akis.P[:, j == jj].sum(1)
    turbinler = [turbin]
    tip = np.zeros(N, int)
    X, Y, M = x, y, m
    if komsu is not None and len(komsu["x"]):
        turbinler = turbinler + list(komsu["turbinler"])
        tip = np.r_[tip, np.asarray(komsu["tip"], int) + 1]
        X, Y, M = np.r_[x, komsu["x"]], np.r_[y, komsu["y"]], np.r_[m, komsu["m"]]
    wts = WindTurbines.from_WindTurbine_lst([t.pywake() for t in turbinler])

    def calistir(xx, yy, mm, tt, wake: bool):
        g = np.zeros((len(xx), len(akis.wd), len(ws)))
        site = _pywake_site(np.maximum(P, 1e-12), akis.wd, ws, mm, ti)
        wf = pywake_modeli(site, wts, model, ti)
        for b in range(0, len(akis.wd), parca):
            sl = slice(b, b + parca)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if wake:
                    sim = wf(xx, yy, type=tt, wd=akis.wd[sl], ws=ws)
                    g[:, sl] = sim.Power.values / 1e6
                else:
                    weff = mm[:, None, None] * ws[None, None, :] * np.ones((1, len(akis.wd[sl]), 1))
                    g[:, sl] = np.stack([turbinler[ti_].guc_mw(weff[i]) for i, ti_ in enumerate(tt)])
        return g

    g_s = calistir(x, y, m, tip[:N], False)
    g_i = calistir(x, y, m, tip[:N], True)
    g_t = calistir(X, Y, M, tip, True)[:N] if len(X) > N else g_i
    E = lambda g: (g * P[None]).sum((1, 2)) * SAAT_YIL
    return ReferansSonuc(E(g_s), E(g_i), E(g_t), g_t.sum(0), g_i.sum(0), g_s.sum(0), akis.wd, ws)


def tablo_saatlik(T: np.ndarray, ref: ReferansSonuc, akis: AkisTablosu) -> np.ndarray:
    """(yön, hız) güç tablosunu akış tablosunun saatlerine taşır (hız ekseninde doğrusal ara değer)."""
    v = akis.v
    w = akis.i_wd if len(akis.wd) == len(ref.wd) else np.zeros(len(v), int)
    out = np.empty(len(v))
    for k in range(len(ref.wd)):
        s = w == k
        if s.any():
            out[s] = np.interp(v[s], ref.ws, T[k], left=0.0, right=0.0)
    return out


def iz_verimi_saatlik(ref: ReferansSonuc, akis: AkisTablosu, ic: bool = False) -> np.ndarray:
    """Saatlik yalnız-iz verimi: izli çiftlik gücü / izsiz çiftlik gücü (izsiz güç ≈ 0 olan saatlerde 1)."""
    T = tablo_saatlik(ref.guc_tablosu_ic if ic else ref.guc_tablosu, ref, akis)
    S = tablo_saatlik(ref.guc_tablosu_serbest, ref, akis)
    return np.where(S > 1e-9, T / np.maximum(S, 1e-12), 1.0)


def saatlik_verim(ref: ReferansSonuc, akis: AkisTablosu, turbin: TurbinEgrisi, N: int, ic: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """
    Saatlik çiftlik gücü / (N × serbest referans türbin gücü) ve çiftlik gücü/(N·P_n) dizileri (akış tablosunun saatleri için).
    Referans türbin: GWA çarpanı 1, iz yok (üretim profilinin temsil ettiği türbin). Hız ekseninde doğrusal ara değer.
    """
    v = akis.v
    T_saat = tablo_saatlik(ref.guc_tablosu_ic if ic else ref.guc_tablosu, ref, akis)
    ref_guc = N * turbin.guc_mw(v)
    oran = np.where(ref_guc > 1e-3 * turbin.P_mw * N, T_saat / np.maximum(ref_guc, 1e-12), np.nan)
    return oran, T_saat / (N * turbin.P_mw)
