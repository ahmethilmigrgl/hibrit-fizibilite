"""
Portföy optimizasyonu (Faz F3): iki aşamalı stokastik MILP, ortalama–CVaR amaç (Rockafellar–Uryasev doğrusallaştırması).

Kümeler
    j ∈ J  aday sahalar;  d ∈ D_j  sahanın ayrık tasarım seçenekleri;  s ∈ S  ortak senaryolar (eşit olasılık 1/|S|)
    r ∈ R  bölgeler;  t ∈ T  bağlantı trafo merkezleri;  (c, k)  bileşen × tedarik kaynağı
Parametreler
    V_{jds}  tasarımın s senaryosundaki NPV'si [M$] (tek başına; FSA işletme modeliyle, kendi en ucuz lojistiğiyle)
    I_jd     CAPEX [M$];  n_jd türbin sayısı;  P_jd türbin gücü [kW];  G_jd RES gücü [MW];  B bütçe;  K_r, K_t bağlantı kapasitesi
    β  yıllık tutarın vergi sonrası bugünkü değer çarpanı;  α CVaR kuyruğu (%5);  λ ∈ [0, 1] risk ağırlığı
Karar değişkenleri (birinci aşama: yatırım)
    x_jd ∈ {0,1}  tasarım seçimi;  z ∈ {0,1} kendi bakımı;  q_jd = x_jd·z;  b_r ∈ {0,1} bölge üssü;  h ∈ {0,1} yedek parça havuzu
    g_jd = x_jd·h;  v_m ∈ {0,1} toplu indirim kademesi;  w_jdm = x_jd·v_m;  f_ckj ≥ 0 bileşen akışları (türbin seti)
İkinci aşama (senaryo başına): işletme kararları (dispatch, yıllık YEKDEM katılımı) V_{jds} içinde önceden çözüldü;
    η serbest (VaR adayı), u_s ≥ 0 kuyruk açığı.
Amaç
    max (1 − λ) · (1/|S|) Σ_s Π_s + λ · [η − (1/(α|S|)) Σ_s u_s]
    Π_s = Σ_jd V_jds x_jd + Ψ,  Ψ = sinerjiler (deterministik, M$):
      Ψ = β·[Σ q_jd n_jd P_jd (FSA − c_kendi) − O·z − U·Σ_r b_r − ΔA_jd q_jd]                (işletme modeli)
        + β·[Σ_jd (Y_jd q_jd − (b n_jd + c n_jd τ_j) g_jd) − a·h]                          (havuz: ayrı stok − havuz)
        + Σ_m Σ_jd δ_m θ I^tür_jd w_jdm · κ                                                (toplu indirim, κ: CAPEX→NPV)
        − (Σ_ckj u_ckj f_ckj − Σ_jd x_jd L^min_jd)/1e6 · κ                                 (çok sahalı ulaştırma)
Kısıtlar
    Σ_d x_jd ≤ 1;  Σ I_jd x_jd ≤ B;  Σ_{j∈r,d} 50·x_jd ≤ K_r;  Σ_{j∈t,d} 50·x_jd ≤ K_t
    q ≤ x, q ≤ z, q ≥ x + z − 1;  b_r ≥ q_jd (j ∈ r);  h ≤ z;  g ≤ x, g ≤ h, g ≥ x + h − 1
    Σ_jd G_jd x_jd ≥ M_m v_m;  v_2 ≤ v_1;  w ≤ x, w ≤ v_m
    Σ_k f_ckj = Σ_d n_jd x_jd;  Σ_j f_ckj ≤ C_ck
    u_s ≥ η − Π_s,  u_s ≥ 0
"Hiç yatırım yapma" (x = 0) her zaman uygundur: Π_s = 0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass
class Veri:
    tas: pd.DataFrame  # tasarımlar: kod, tasarim, res_mw, N, capex_musd, ..., satir
    ad: pd.DataFrame  # adaylar: kod, bolge, trafo_ad, enlem, boylam, turbin_mw
    V: np.ndarray  # (tasarım, senaryo) M$
    lojistik: pd.DataFrame | None = None


@dataclass
class Ayar:
    lam: float = 0.5
    alfa: float = 0.05
    butce_musd: float = 300.0
    bolge_kapasite_mw: float | None = 150.0
    trafo_kapasite_mw: float | None = 100.0
    baglanti_mw: float = 50.0
    sinerji: dict = field(default_factory=lambda: {"isletme": True, "havuz": True, "indirim": True, "ulastirma": True})
    zaman_s: float = 60.0
    cvar_alt: float | None = None  # ε-kısıt: CVaR ≥ cvar_alt (etkin sınır); amaç o zaman yalnız E (λ yok sayılır)
    mip_bosluk: float = 1e-4


def _sinerji_parametreleri(v: Veri, cfg: dict) -> dict:
    from src.ayarlar import deger
    from src.portfoy import sinerji as S

    a = deger(cfg["v3"]["portfoy"])
    ip = S.isletme_parametreleri()
    beta = S.bd_carpani(cfg)
    kappa = S.capex_bd_carpani(cfg)
    t = v.tas.merge(v.ad[["kod", "bolge", "trafo_ad", "enlem", "boylam", "turbin_mw", "res_kf"]], on="kod", how="left")
    P_kw = 1000 * t["turbin_mw"].to_numpy()
    n = t["N"].to_numpy(float)
    fiyat = float(deger(cfg["v3"]["portfoy"]).get("havuz_gelir_fiyat_usd_mwh", 58.0))
    gelir_gun = P_kw / 1000 * t["res_kf"].fillna(0.35).to_numpy() * 24 * fiyat  # türbin başına günlük gelir
    # depo: adayların (enlem, boylam) medoidi (çevrimdışı sabit; τ = yol ≈ 1,3 × kuş uçuşu / km_gun + elleçleme)
    e, b = v.ad["enlem"].to_numpy(), v.ad["boylam"].to_numpy()
    D = np.array([[_km(e[i], b[i], e[j], b[j]) for j in range(len(e))] for i in range(len(e))])
    dep = int(np.argmin(D.sum(1)))
    tau_aday = 1.3 * D[dep] / a["havuz_transfer_km_gun"] + a["havuz_elleclem_saat"] / 24
    tau = t["kod"].map(dict(zip(v.ad["kod"], tau_aday))).to_numpy()
    ayri = np.array([S.stok_maliyeti(int(ni), gg, cfg)["maliyet_yil"] if ni > 0 else 0.0 for ni, gg in zip(n, gelir_gun)])
    hd = S.havuz_dogrusal(float(np.median(gelir_gun)), cfg)
    dA = np.clip(t["kullanilabilirlik"].fillna(0) - t["kendi_kullanilabilirlik"].fillna(t["kullanilabilirlik"]), 0, None).to_numpy()
    E_mwh = t["res_mw"].to_numpy() * t["res_kf"].fillna(0.35).to_numpy() * 8760
    turbin_pay = float(a.get("turbin_capex_payi", 0.7))
    capex_res = t["res_mw"].to_numpy() * 1.15  # M$ (RES CAPEX 1,15 M$/MW; türbin payı bu tutarın üzerinden)
    return {
        "beta": beta,
        "kappa": kappa,
        "isl_tasarruf_jd": beta * n * P_kw * (ip["fsa_usd_kw"] - ip["kendi_degisken_usd_kw"]) / 1e6 - beta * dA * E_mwh * fiyat / 1e6,
        "org": beta * ip["organizasyon_usd_yil"] / 1e6,
        "ussu": beta * ip["bolge_ussu_usd_yil"] / 1e6,
        "havuz_ayri_jd": beta * ayri / 1e6,
        "havuz_jd": beta * (hd["havuz_b_turbin_yil"] * n + hd["havuz_c_turbin_gun_yil"] * n * tau) / 1e6,
        "havuz_a": beta * hd["havuz_a_yil"] / 1e6,
        "indirim": [(float(m), float(r)) for m, r in a["toplu_indirim"]],
        "indirim_jd": kappa * turbin_pay * capex_res,
        "depo": v.ad["kod"].iloc[dep],
        "tau_gun": dict(zip(v.ad["kod"], tau_aday.round(2))),
        "havuz_dogrusal": hd,
        "kapasite": _kapasiteler(v, cfg, a),
        "bolge": t["bolge"].to_numpy(),
        "trafo": t["trafo_ad"].fillna(t["kod"]).to_numpy(),
    }


def _kapasiteler(v: Veri, cfg: dict, a: dict) -> dict:
    """(kaynak, bileşen) → portföy inşaat penceresindeki azami türbin seti: yerli üretici (bilinen) ve liman elleçleme."""
    from src.ayarlar import deger

    L = deger(cfg["v3"]["lojistik"])
    pen = a["insaat_penceresi_yil"]
    out = {}
    if v.lojistik is None:
        return out
    for (kay, bil, tur), _g in v.lojistik.groupby(["kaynak", "bilesen", "tur"]):
        if kay in L.get("kapasite_turbin_yil", {}):
            out[(kay, bil)] = float(L["kapasite_turbin_yil"][kay]) * pen
        elif tur == "liman":
            out[(kay, bil)] = float(a["liman_kapasite_set_yil"]) * pen
    return out


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return float(12742 * np.arcsin(np.sqrt(min(1.0, a))))


def coz(v: Veri, ay: Ayar, cfg: dict | None = None, sp: dict | None = None, senaryo: np.ndarray | None = None) -> dict:
    """MILP'i kurar ve HiGHS (scipy.optimize.milp) ile çözer. senaryo: kullanılacak senaryo indeksleri (alt örnek)."""
    from src.ayarlar import config_oku

    cfg = cfg or config_oku()
    t0 = time.perf_counter()
    sp = sp or _sinerji_parametreleri(v, cfg)
    V = v.V if senaryo is None else v.V[:, senaryo]
    J, Sn = V.shape
    t = v.tas
    kodlar = t["kod"].to_numpy()
    siteler = list(dict.fromkeys(kodlar))
    bolgeler = sorted(set(sp["bolge"]))
    sn = ay.sinerji
    ind = sp["indirim"] if sn.get("indirim") else []
    # --- değişken indeksleri
    o = 0
    ix = {}

    def blok(ad, n):
        nonlocal o
        ix[ad] = np.arange(o, o + n)
        o += n

    blok("x", J)
    blok("q", J)
    blok("z", 1)
    blok("b", len(bolgeler))
    blok("g", J)
    blok("h", 1)
    blok("v", len(ind))
    blok("w", J * len(ind))
    # çok sahalı ulaştırma: f_ckj (türbin seti), yalnız aday kodu tasarımlar arasında olan satırlar
    loj = None
    if sn.get("ulastirma") and v.lojistik is not None and len(v.lojistik):
        loj = v.lojistik[v.lojistik["kod"].isin(siteler)].reset_index(drop=True)
        blok("f", len(loj))
    blok("eta", 1)
    blok("u", Sn)
    nv = o
    # --- Ψ (sinerji) katsayı vektörü (M$)
    kalem = {k: np.zeros(nv) for k in ("isletme", "havuz", "indirim", "ulastirma")}
    if sn.get("isletme"):
        kalem["isletme"][ix["q"]] += sp["isl_tasarruf_jd"]
        kalem["isletme"][ix["z"]] -= sp["org"]
        kalem["isletme"][ix["b"]] -= sp["ussu"]
        if sn.get("havuz"):  # kendi bakımında ayrı stoklar DES maliyetinin içinde; havuz farkı ek tasarruftur
            kalem["havuz"][ix["g"]] += sp["havuz_ayri_jd"] - sp["havuz_jd"]
            kalem["havuz"][ix["h"]] -= sp["havuz_a"]
    for m, (_esik, oran) in enumerate(ind):
        kalem["indirim"][ix["w"][m * J : (m + 1) * J]] += oran * sp["indirim_jd"] - (ind[m - 1][1] * sp["indirim_jd"] if m > 0 else 0)
    if loj is not None:
        # tek saha değerlemesi her bileşeni en ucuz kaynaktan aldı (NPV'de); portföyde maliyet farkı sinerjidir
        kalem["ulastirma"][ix["f"]] -= sp["kappa"] * loj["birim_usd"].to_numpy() / 1e6
        lmin = loj.groupby(["kod", "bilesen"])["birim_usd"].min().groupby("kod").sum()
        kalem["ulastirma"][ix["x"]] += sp["kappa"] * t["N"].to_numpy() * t["kod"].map(lmin).fillna(0).to_numpy() / 1e6
    psi = sum(kalem.values())
    Vbar = V.mean(1)
    # --- amaç (scipy minimize → eksi)
    c = np.zeros(nv)
    c[ix["x"]] = -(1 - ay.lam) * Vbar
    c -= (1 - ay.lam) * psi
    c[ix["eta"]] = -ay.lam
    c[ix["u"]] = ay.lam / (ay.alfa * Sn)
    if ay.cvar_alt is not None:  # amaç yalnız beklenen değer; CVaR kısıtı aşağıda
        c = np.zeros(nv)
        c[ix["x"]] = -Vbar
        c -= psi
    rows, lo, hi = [], [], []

    def ekle(r: dict, alt: float, ust: float):
        rows.append(r)
        lo.append(alt)
        hi.append(ust)

    for kod in siteler:
        ekle({int(i): 1.0 for i in ix["x"][kodlar == kod]}, -np.inf, 1.0)
    ekle({int(i): float(cc) for i, cc in zip(ix["x"], t["capex_musd"])}, -np.inf, ay.butce_musd)
    if ay.bolge_kapasite_mw:
        for bo in bolgeler:
            ekle({int(i): ay.baglanti_mw for i in ix["x"][sp["bolge"] == bo]}, -np.inf, ay.bolge_kapasite_mw)
    if ay.trafo_kapasite_mw:
        for tr in set(sp["trafo"]):
            sec = ix["x"][sp["trafo"] == tr]
            if len(sec) and len(set(kodlar[sp["trafo"] == tr])) > 1:
                ekle({int(i): ay.baglanti_mw for i in sec}, -np.inf, ay.trafo_kapasite_mw)
    z, h = int(ix["z"][0]), int(ix["h"][0])
    for jj in range(J):
        x, q, g = int(ix["x"][jj]), int(ix["q"][jj]), int(ix["g"][jj])
        ekle({q: 1, x: -1}, -np.inf, 0)
        ekle({q: 1, z: -1}, -np.inf, 0)
        ekle({q: 1, x: -1, z: -1}, -1, np.inf)
        ekle({int(ix["b"][bolgeler.index(sp["bolge"][jj])]): 1, q: -1}, 0, np.inf)
        ekle({g: 1, x: -1}, -np.inf, 0)
        ekle({g: 1, h: -1}, -np.inf, 0)
        for m in range(len(ind)):
            w = int(ix["w"][m * J + jj])
            ekle({w: 1, x: -1}, -np.inf, 0)
            ekle({w: 1, int(ix["v"][m]): -1}, -np.inf, 0)
    ekle({h: 1, z: -1}, -np.inf, 0)
    if not sn.get("isletme"):
        ekle({z: 1}, -np.inf, 0)
    if not sn.get("havuz"):
        ekle({h: 1}, -np.inf, 0)
    if ay.cvar_alt is not None:
        r_ = {int(i): -1.0 / (ay.alfa * Sn) for i in ix["u"]}
        r_[int(ix["eta"][0])] = 1.0
        ekle(r_, ay.cvar_alt, np.inf)
    for m, (esik, _o) in enumerate(ind):
        r = {int(i): float(gw) for i, gw in zip(ix["x"], t["res_mw"])}
        r[int(ix["v"][m])] = -esik
        ekle(r, 0, np.inf)
        if m > 0:
            ekle({int(ix["v"][m]): 1, int(ix["v"][m - 1]): -1}, -np.inf, 0)
    if loj is not None:
        for (kod, _bil), grp in loj.groupby(["kod", "bilesen"]):
            r = {int(ix["f"][i]): 1.0 for i in grp.index}
            for jj in np.where(kodlar == kod)[0]:
                r[int(ix["x"][jj])] = -float(t["N"].iloc[jj])
            ekle(r, 0.0, 0.0)
        for (kay, bil), grp in loj.groupby(["kaynak", "bilesen"]):
            cap = sp["kapasite"].get((kay, bil))
            if cap is not None:
                ekle({int(ix["f"][i]): 1.0 for i in grp.index}, -np.inf, cap)
    A_det = _sparse(rows, nv)
    # u_s ≥ η − Π_s  ⇔  u_s − η + Σ V_jds x_jd + Ψ ≥ 0
    psi_idx = np.nonzero(psi)[0]
    satir_idx = np.repeat(np.arange(Sn), J + 1 + len(psi_idx) + 1)
    sut = np.concatenate([np.r_[ix["x"], ix["eta"], psi_idx, ix["u"][s]] for s in range(Sn)])
    val = np.concatenate([np.r_[V[:, s], -1.0, psi[psi_idx], 1.0] for s in range(Sn)])
    A_cvar = sparse.csr_matrix((val, (satir_idx, sut)), shape=(Sn, nv))
    A = sparse.vstack([A_det, A_cvar]).tocsr()
    lo = np.r_[lo, np.zeros(Sn)]
    hi = np.r_[hi, np.full(Sn, np.inf)]
    tam = np.zeros(nv)
    for ad in ("x", "q", "z", "b", "g", "h", "v", "w"):
        tam[ix[ad]] = 1
    alt = np.zeros(nv)
    ust = np.ones(nv)
    alt[ix["eta"]], ust[ix["eta"]] = -1e4, 1e4
    ust[ix["u"]] = np.inf
    if "f" in ix:
        ust[ix["f"]] = np.inf
    r = milp(
        c,
        constraints=LinearConstraint(A, lo, hi),
        integrality=tam,
        bounds=Bounds(alt, ust),
        options={"time_limit": ay.zaman_s, "mip_rel_gap": ay.mip_bosluk, "disp": False},
    )
    if r.x is None:
        raise RuntimeError(f"Portföy MILP'i çözülemedi: {r.message}")
    xx = np.round(r.x[ix["x"]]).astype(bool)
    xr = np.where(tam > 0, np.round(r.x), r.x)
    psi_deger = float(psi @ xr)
    Pi = V[xx].sum(0) + psi_deger
    kotu = np.sort(Pi)[: max(1, int(round(ay.alfa * Sn)))]
    return {
        "secim": t[xx].copy(),
        "x": xx,
        "kendi_bakimi": bool(round(r.x[z])),
        "havuz": bool(round(r.x[h])),
        "indirim_kademesi": int(round(r.x[ix["v"]].sum())) if len(ind) else 0,
        "psi_musd": psi_deger,
        "psi_kalem": {k: float(kv @ xr) for k, kv in kalem.items()},
        "e_npv": float(Pi.mean()),
        "cvar": float(kotu.mean()),
        "cvar_dogrusal": float(r.x[ix["eta"]][0] - r.x[ix["u"]].sum() / (ay.alfa * Sn)),
        "amac": float(-r.fun),
        "p_pozitif": float((Pi > 0).mean()) if xx.any() else 0.0,
        "capex_musd": float(t.loc[xx, "capex_musd"].sum()),
        "Pi": Pi,
        "bosluk": float(getattr(r, "mip_gap", np.nan) or 0.0),
        "durum": r.message,
        "sure_s": time.perf_counter() - t0,
        "sp": sp,
    }


def _sparse(rows: list[dict], nv: int) -> sparse.csr_matrix:
    r, cc, v = [], [], []
    for i, d in enumerate(rows):
        for k, x in d.items():
            r.append(i)
            cc.append(k)
            v.append(x)
    return sparse.csr_matrix((v, (r, cc)), shape=(len(rows), nv))
