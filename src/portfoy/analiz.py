"""
Portföy analizleri (Faz F1 korelasyon, F3 etkin sınır, ayrıştırmalar, fiyat ve kapasite duyarlılığı, kaba kuvvet doğrulaması).

Çeşitlendirme ayrıştırması: seçilen tasarımların senaryo NPV'leri ortak sürücülere regresyonla ayrılır:
    V_js = f_j(F_s) + e_js,  F = [L10, L10², CAPEX çarpanı, SFK senaryosu kuklaları]   (fiyat, piyasa, düzenleyici: ortak)
    e_js: hava (sahalar arası korelasyonlu; aynı ERA5 yılı) + sahaya özgü (model hatası, bağlantı, COD; bağımsız tohum)
    Var(Π) = Var(Σ f_j) + Σ_j Var(e_j) + Σ_{j≠k} Cov(e_j, e_k)
             [ortak piyasa]   [sahaya özgü]   [hava korelasyonu]
Çeşitlendirme faydası (risk): Σ_j σ_j − σ_Π (tam korelasyona göre) ve Σ_j CVaR_j'ye göre CVaR_Π farkı. Çeşitlendirmenin
sınırı: n eşit saha için σ_Π/n → sqrt(ortalama kovaryans); ortak piyasa varyansı çeşitlendirilemez.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.portfoy import model as M


def cvar(x: np.ndarray, alfa: float = 0.05) -> float:
    return float(np.sort(x)[: max(1, int(round(alfa * len(x))))].mean())


def ortak_matris(o: dict) -> np.ndarray:
    L = o["L10"].astype(float)
    sc = o["senaryo"]
    kukla = [(sc == s).astype(float) for s in sorted(set(sc))[1:]]
    return np.c_[np.ones(len(L)), L - L.mean(), (L - L.mean()) ** 2, o["capex_res"].astype(float) - 1, *kukla]


def cesitlendirme(Vsec: np.ndarray, o: dict, psi: float = 0.0, alfa: float = 0.05) -> dict:
    """Vsec: (seçilen tasarım, senaryo). Varyans ayrıştırması ve risk ölçüleri."""
    F = ortak_matris(o)
    B = np.linalg.lstsq(F, Vsec.T, rcond=None)[0]
    fit = (F @ B).T
    e = Vsec - fit
    Pi = Vsec.sum(0) + psi
    v_ortak = float(np.var(fit.sum(0), ddof=1))
    C = np.cov(e) if len(Vsec) > 1 else np.array([[np.var(e, ddof=1)]])
    v_saha = float(np.trace(np.atleast_2d(C)))
    v_hava = float(np.atleast_2d(C).sum() - v_saha)
    cov_fe = float(np.var(Pi, ddof=1) - v_ortak - v_saha - v_hava)  # regresyon kalıntısı ortak sürücülerle ilişkisiz (≈ 0)
    sig = Vsec.std(1, ddof=1)
    r2 = 1 - e.var(1, ddof=1) / Vsec.var(1, ddof=1)
    return {
        "n": int(len(Vsec)),
        "e_npv": float(Pi.mean()),
        "sigma_portfoy": float(np.std(Pi, ddof=1)),
        "sigma_toplam_tek": float(sig.sum()),
        "cesitlendirme_sigma": float(sig.sum() - np.std(Pi, ddof=1)),
        "cvar_portfoy": cvar(Pi, alfa),
        "cvar_toplam_tek": float(sum(cvar(x, alfa) for x in Vsec)),
        "cesitlendirme_cvar": float(cvar(Pi, alfa) - sum(cvar(x, alfa) for x in Vsec)),
        "var_ortak_piyasa": v_ortak,
        "var_sahaya_ozgu": v_saha,
        "var_hava_korelasyonu": v_hava,
        "var_artik": cov_fe,
        "pay_ortak_piyasa": v_ortak / max(np.var(Pi, ddof=1), 1e-9),
        "r2_ortak_medyan": float(np.median(r2)),
    }


def egri_n(V: np.ndarray, o: dict, n_azami: int, tekrar: int = 200, tohum: int = 0) -> pd.DataFrame:
    """Rastgele n sahalı eşit portföylerde saha başına σ ve ortak piyasa payı (çeşitlendirmenin sınırı)."""
    rng = np.random.default_rng(tohum)
    F = ortak_matris(o)
    satir = []
    for n in range(1, n_azami + 1):
        s, p = [], []
        for _ in range(tekrar):
            sec = rng.choice(len(V), n, replace=False)
            Pi = V[sec].sum(0)
            fit = F @ np.linalg.lstsq(F, Pi, rcond=None)[0]
            s.append(np.std(Pi, ddof=1) / n)
            p.append(np.var(fit, ddof=1) / np.var(Pi, ddof=1))
        satir.append({"n": n, "sigma_saha_basina": float(np.mean(s)), "ortak_piyasa_payi": float(np.mean(p))})
    return pd.DataFrame(satir)


def fiyat_egimleri(V: np.ndarray, o: dict) -> np.ndarray:
    """∂NPV/∂L10 [M$ / ($/MWh)] — ortak regresyonun doğrusal fiyat katsayısı (tasarım başına)."""
    F = ortak_matris(o)
    return np.linalg.lstsq(F, V.T, rcond=None)[0][1]


def kaba_kuvvet(v: M.Veri, kodlar: list[str], ay: M.Ayar, sp: dict) -> dict:
    """Küçük örnekte tüm kombinasyonlar (her saha: yok ya da bir tasarım) × sinerji ikilileri; MILP ile karşılaştırma."""
    t = v.tas
    idx = {k: list(np.where(t["kod"].to_numpy() == k)[0]) for k in kodlar}
    en = (-np.inf, None)
    sayi = 0
    Sn = v.V.shape[1]
    bolge = sp["bolge"]
    for secim in itertools.product(*[[None, *idx[k]] for k in kodlar]):
        x = [i for i in secim if i is not None]
        if sum(t["capex_musd"].iloc[i] for i in x) > ay.butce_musd:
            continue
        if ay.bolge_kapasite_mw:
            bs = pd.Series([bolge[i] for i in x]).value_counts()
            if (bs * ay.baglanti_mw > ay.bolge_kapasite_mw).any():
                continue
        base = v.V[x].sum(0) if x else np.zeros(Sn)
        G = float(t["res_mw"].iloc[x].sum()) if x else 0.0
        en_psi = -np.inf
        for z in (0, 1):
            for h in (0, z):
                psi = 0.0
                if z and x:
                    psi += sum(sp["isl_tasarruf_jd"][i] for i in x) - sp["org"] - sp["ussu"] * len({bolge[i] for i in x})
                    if h:
                        psi += sum(sp["havuz_ayri_jd"][i] - sp["havuz_jd"][i] for i in x) - sp["havuz_a"]
                elif z and not x:
                    psi -= sp["org"]
                ind = 0.0
                for esik, oran in sp["indirim"]:
                    if G >= esik:
                        ind = oran
                psi += sum(ind * sp["indirim_jd"][i] for i in x)
                en_psi = max(en_psi, psi)
        Pi = base + en_psi
        amac = (1 - ay.lam) * Pi.mean() + ay.lam * cvar(Pi, ay.alfa)
        sayi += 1
        if amac > en[0] + 1e-9:
            en = (amac, x)
    return {"amac": en[0], "secim": [f"{t['kod'].iloc[i]}:{t['tasarim'].iloc[i]}" for i in en[1]], "kombinasyon": sayi}
