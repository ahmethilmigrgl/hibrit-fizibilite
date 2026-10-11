"""
Optimize edicinin laneti (optimizer's curse; Smith & Winkler 2006) ve Bayesçi büzülme düzeltmesi.

Sorun: 40 aday arasından en iyi görünenleri seçmek, rüzgâr tahmini olduğundan iyi çıkmış adayları seçmeye eğilimlidir; seçilen
portföyün tahmini değeri gerçek değerinden sistematik olarak yüksektir (beklenen hayal kırıklığı > 0), tahminler tek tek
yansız olsa bile.

Model (log KF, saha j, bölge r):
    gerçek       ln c_j ~ N(m_r, τ_r²)                     (bölgesel öncül; ön tarama hücrelerinden ampirik Bayes)
    tahmin       ln ĉ_j = ln c_j + e_j,  e_j ~ F_g          (F_g: güven seviyesinin birini dışarıda bırak hata dağılımı)
    sonsal       E[ln c_j | ĉ_j] = m_r + w_j (ln ĉ_j − m_r),  w_j = τ_r² / (τ_r² + σ_g²)     (büzülme)
NPV'nin KF'ye duyarlılığı: V_jds = f(ortak sürücüler) + κ_jd (μ_js − 1) + kalıntı; μ_js sahanın Monte Carlo model çarpanı (aynı
tohumla yeniden üretilir) → κ_jd [M$ / birim KF çarpanı]. KF çarpanı q olduğunda E[NPV] ≈ E[V] + κ (q − 1).
Simülasyon (tekrar başına): gerçek ln c_j sonsaldan çekilir; yeni tahmin = gerçek + e_j (ampirik hata); portföy (a) tahminlere
göre, (b) büzülmüş tahminlere göre seçilir; seçilenin tahmin edilen ve gerçek değeri karşılaştırılır. En iyi tek saha için aynısı.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku, deger
from src.portfoy import analiz as PA
from src.portfoy import model as M
from src.portfoy.adaylar import IL_BOLGE, tohum_saha


def guven_sigmalari() -> dict:
    """Güven seviyesi → (MC model çarpanının σ'sı, göreli RMSE). data/atlas/guven_seviyeleri.csv."""
    g = pd.read_csv(KOK / "data" / "atlas" / "guven_seviyeleri.csv").set_index("guven")
    from src.motor.mc import ATLAS_ORT_KF

    return {
        s: {"sigma_mc": float(1.4826 * r["mutlak_medyan"] / 100 / ATLAS_ORT_KF), "goreli_rmse": float(r["goreli_rmse_%"]) / 100}
        for s, r in g.iterrows()
    }


def ampirik_hatalar() -> dict:
    """
    Birini dışarıda bırak göreli hataları (Faz A çapraz doğrulama; türbin konumlu, GWA ölçekli kural), güven seviyesine göre
    (komşu ≤ 30 km yüksek). ln(tahmin / gözlenen); her grup güncel güven seviyesinin göreli RMSE'sine ölçeklenir.
    """
    d = pd.read_csv(KOK / "outputs" / "v2" / "A4_capraz_dogrulama.csv")
    d = d[(d["gmod"] == "turbin_konumu") & (d["yontem"] == "gwa_olcekli")]
    e = np.log(d["tahmin_kf"] / d["gozlenen_kf"])
    gs = guven_sigmalari()
    out = {}
    yakin = d["en_yakin_km"].fillna(np.inf) <= 30
    for s, maske in (("yüksek", yakin), ("düşük", ~yakin)):
        x = e[maske].to_numpy()
        x = x - x.mean()  # yansız tahmin varsayımı (lanet seçimden doğar, sistematik sapmadan değil)
        x = x * gs[s]["goreli_rmse"] / np.sqrt(np.mean(x**2))
        out[s] = x
    return out


def oncul(cfg: dict | None = None) -> pd.DataFrame:
    """Bölge başına ln KF öncülü: m_r = ortalama, τ_r² = Var(ln ĉ) − ortalama σ² (ampirik Bayes; alt sınır 0,05²)."""
    ot = pd.read_parquet(KOK / "data" / "atlas" / "on_tarama.parquet")
    ot = ot[(ot["hata"] == "") & ~ot["ada"].fillna(False) & (ot["res_kf"] > 0.05)]
    ot = ot.assign(bolge=ot["il"].map(IL_BOLGE), lc=np.log(ot["res_kf"]))
    gs = guven_sigmalari()
    ot["s2"] = ot["guven"].map({k: v["goreli_rmse"] ** 2 for k, v in gs.items()}).fillna(gs["düşük"]["goreli_rmse"] ** 2)
    g = ot.groupby("bolge").agg(m=("lc", "mean"), v=("lc", "var"), s2=("s2", "mean"), n=("lc", "size"))
    g["tau2"] = np.maximum(g["v"] - g["s2"], 0.05**2)
    return g


def kappa(v: M.Veri, o: dict) -> np.ndarray:
    """κ_jd: NPV'nin sahanın KF çarpanına duyarlılığı (ortak sürücüler + model çarpanı regresyonu)."""
    gs = guven_sigmalari()
    F = PA.ortak_matris(o)
    g = v.ad.set_index("kod")["guven"]
    n = v.V.shape[1]
    k = np.zeros(len(v.tas))
    for i, r in enumerate(v.tas.itertuples()):
        s = gs.get(g[r.kod], gs["düşük"])["sigma_mc"]
        m = np.exp(np.random.default_rng(tohum_saha(r.kod, deger(config_oku()["v3"]["portfoy"])["tohum"]) + 3).normal(-0.5 * s * s, s, n))
        X = np.c_[F, m - 1]
        k[i] = np.linalg.lstsq(X, v.V[i], rcond=None)[0][-1]
    return np.clip(k, 0, None)


def buzulme(v: M.Veri, onc: pd.DataFrame) -> pd.DataFrame:
    """Aday başına büzülme: w, sonsal ortalama ve KF düzeltme çarpanı q = exp(sonsal − ln ĉ)."""
    gs = guven_sigmalari()
    a = v.ad.copy()
    a["s2"] = a["guven"].map({k: x["goreli_rmse"] ** 2 for k, x in gs.items()}).fillna(gs["düşük"]["goreli_rmse"] ** 2)
    a = a.join(onc[["m", "tau2"]], on="bolge")
    a["lc"] = np.log(a["res_kf"])
    a["w"] = a["tau2"] / (a["tau2"] + a["s2"])
    a["sonsal"] = a["m"] + a["w"] * (a["lc"] - a["m"])
    a["q"] = np.exp(a["sonsal"] - a["lc"])
    a["kf_duzeltilmis"] = a["res_kf"] * a["q"]
    return a


def uygula(v: M.Veri, q_kod: dict, k: np.ndarray) -> M.Veri:
    """Tasarım NPV'lerine KF çarpanı q (kod başına) uygular: V + κ (q − 1)."""
    q = v.tas["kod"].map(q_kod).to_numpy()
    d = k * (q - 1)
    return M.Veri(tas=v.tas.assign(e_npv=v.tas["e_npv"] + d), ad=v.ad, V=v.V + d[:, None], lojistik=v.lojistik)


def simulasyon(v: M.Veri, o: dict, R: int, ay: M.Ayar, tohum: int = 0, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or config_oku()
    onc = oncul(cfg)
    bz = buzulme(v, onc)
    k = kappa(v, o)
    hat = ampirik_hatalar()
    rng = np.random.default_rng(tohum)
    kod = bz["kod"].to_numpy()
    sp = M._sinerji_parametreleri(v, cfg)
    post_sd = np.sqrt(bz["w"] * bz["s2"]).to_numpy()  # sonsal varyans = w σ² (normal–normal)
    satir = []
    tas_kod = v.tas["kod"].to_numpy()
    for t in range(R):
        ln_gercek = bz["sonsal"].to_numpy() + post_sd * rng.standard_normal(len(kod))
        e = np.array([rng.choice(hat.get(g, hat["düşük"])) for g in bz["guven"]])
        ln_tahmin = ln_gercek + e
        ln_buz = bz["m"].to_numpy() + bz["w"].to_numpy() * (ln_tahmin - bz["m"].to_numpy())
        q_gercek = dict(zip(kod, np.exp(ln_gercek - bz["lc"].to_numpy())))
        q_tahmin = dict(zip(kod, np.exp(ln_tahmin - bz["lc"].to_numpy())))
        q_buz = dict(zip(kod, np.exp(ln_buz - bz["lc"].to_numpy())))
        vg = uygula(v, q_gercek, k)
        out = {"tekrar": t}
        for ad_, qd in (("saf", q_tahmin), ("buzulmus", q_buz)):
            vt = uygula(v, qd, k)
            r = M.coz(vt, ay, cfg, sp)
            x = r["x"]
            e_tahmin = r["e_npv"]
            e_gercek = float(vg.V[x].sum(0).mean() + r["psi_musd"]) if x.any() else 0.0
            i1 = int(np.argmax(vt.V.mean(1)))
            out.update(
                {
                    f"{ad_}_portfoy_tahmin": e_tahmin,
                    f"{ad_}_portfoy_gercek": e_gercek,
                    f"{ad_}_n": int(x.sum()),
                    f"{ad_}_tek_tahmin": float(vt.V[i1].mean()),
                    f"{ad_}_tek_gercek": float(vg.V[i1].mean()),
                    f"{ad_}_tek_kod": tas_kod[i1],
                }
            )
        satir.append(out)
    return pd.DataFrame(satir)
