"""
v3 D1 — Atlas santrallerinin iz kaybı, "kümelenme iz kaybı atlas artığını açıklıyor mu?" hipotez testi ve izden arındırılmış
kalibrasyon (birini dışarıda bırak doğrulaması önce/sonra).

Adımlar
    1) Her kalibre santral (kendi OSM türbin konumları + kendi türbin vekili) için PyWake referans hesabı: iç iz W_iç, komşu
       santrallerden (OSM, 10 km) dış iz W_dış, toplam W; saatlik iz verimi η_p(t). Rüzgâr: santralin kendi kalibre hızı
       (v · K_p[ay, saat]) ve ERA5 hücresinin 100 m yönü (data/raw/era5_hucre). → data/atlas/santral_iz_kaybi.csv
    2) Hipotez: atlas artığı (R = K / c, GWA düzeltmesinden arta kalan hız sapması; ve enerji oranı q = gözlenen KF /
       GWA-düzeltmeli model KF) iz kaybıyla ilişkili mi? ln R ve ln q, ln(1 − W) üzerine regresyon (kontrollü/kontrolsüz),
       bootstrap GA; Balıkesir–Biga (Balıkesir + Çanakkale) bölge farkının ne kadarını iz farkı açıklıyor?
    3) İzden arındırılmış katsayılar: K'_p = s_p · K_p,  ort[brüt(s K v) · η_p] = ort[brüt(K v)] · (1 − W_ref)
       (W_ref: v2 toplu %12 kaybına gömülü tipik iz kaybı, config v3.kayip). → data/atlas/kalibrasyon_matrisleri_izsiz.npz
    4) Birini dışarıda bırak (90 santral): önce = v2 kuralı (K, toplu %12); sonra = K' atlası + tahmin edilen santralin kendi
       iz verimi: KF = brüt(K'_x v) · (1 − λ_e) · A_k · η_x(t). → outputs/v3D/D1_loo_once_sonra.csv
Çalıştırma: .venv/bin/python src/v3_D1_atlas_iz.py   (≈ 10 dk; santral iz tablosu önbellekli: --yeniden)
"""

import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from src.atlas import aktarim
from src.ayarlar import CIKTILAR, HAM_VERI, KOK, config_oku, deger
from src.kaynaklar import era5_yon, gwa250, sinirlar
from src.yerlesim import alan as A
from src.yerlesim import iz
from src.yerlesim.analiz import Baglam, komsu_sozlugu, komsu_turbinler
from src.yerlesim.ruzgar_gulu import akis_tablosu, esdeger_hiz
from src.yerlesim.turbin import kutuphane_turbini

CIKTI = CIKTILAR / "v3D"
IZ_CSV = KOK / "data" / "atlas" / "santral_iz_kaybi.csv"
IZSIZ_NPZ = KOK / "data" / "atlas" / "kalibrasyon_matrisleri_izsiz.npz"
ETA_NPZ = KOK / "data" / "onbellek" / "santral_iz_verimi.npz"


def cv_veri():
    sys.path.insert(0, str(KOK / "src"))
    import importlib.util

    sp = importlib.util.spec_from_file_location("r2", KOK / "src" / "v2_R2_kural_varyantlari.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m, m.veri(config_oku())


def santral_yon(enlem: float, boylam: float, indeks: pd.DatetimeIndex) -> np.ndarray | None:
    e, b = era5_yon.hucre(enlem, boylam)
    p = HAM_VERI / "era5_hucre" / f"era5_{e:.2f}_{b:.2f}_2014-01-01_2025-12-31.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["u100", "v100"])
    return (
        pd.Series(era5_yon.yon_derece(d["u100"].to_numpy(), d["v100"].to_numpy()), index=d.index).reindex(indeks).ffill().bfill().to_numpy()
    )


def santral_iz(cfg, d) -> tuple[pd.DataFrame, dict]:
    ay = deger(cfg["v3"]["yerlesim"])
    df, mat = aktarim.atlas()
    konum = pd.read_csv(KOK / "data" / "atlas" / "santral_turbin_konumlari.csv")
    satir, eta = [], {}
    for r in df.itertuples():
        i = int(r.epias_id)
        k = konum[konum["epias_id"] == i]
        m, _, _ = d[i]
        if len(k) == 0:
            satir.append({"epias_id": i, "ad": r.ad, "n_turbin": 0})
            continue
        t0 = time.perf_counter()
        t = kutuphane_turbini(r.turbin, float(r.gobek))
        K = mat[i]
        v = esdeger_hiz(m.v * K[m.ay - 1, m.saat], m.rho)
        yon = santral_yon(r.enlem, r.boylam, m.indeks)
        akis = akis_tablosu(v, yon, 36, 0.5, guc=t.guc_mw, kaynak="era5_hucre")
        e0, b0 = float(k["enlem"].mean()), float(k["boylam"].mean())
        x, y = A.yerel_xy(k["enlem"], k["boylam"], e0, b0)
        g_t = np.array([gwa250.nokta(float(a), float(b)) for a, b in zip(k["enlem"], k["boylam"])])
        gref = float(g_t.mean())
        kom = komsu_turbinler(e0, b0, ay["komsu_yaricap_km"], ay["komsu_azami"], haric_epias=i)
        # OSM'de santrale bağlanmamış ama santralin içinde duran düğümler (aynı türbinin ikinci kaydı) komşu sayılmaz
        if len(kom):
            dmin = np.hypot(kom["x"].to_numpy()[:, None] - x[None], kom["y"].to_numpy()[:, None] - y[None]).min(1)
            kom = kom[dmin > 0.5 * t.D].reset_index(drop=True)
        b = Baglam(e0, b0, t, akis, akis, pd.DataFrame(), pd.DataFrame(), {}, None, None, gref, 0.0, kom, ay["ti"], ay, pd.DataFrame())
        ref = iz.referans(x, y, g_t / gref, t, akis, ay["ti"], ay["iz_modeli"], komsu_sozlugu(b))
        eta[i] = iz.iz_verimi_saatlik(ref, akis).astype(np.float32)
        il = sinirlar.konum(r.enlem, r.boylam) or {}
        satir.append(
            {
                "epias_id": i,
                "ad": r.ad,
                "il": il.get("il"),
                "ilce": il.get("ilce"),
                "n_turbin": len(k),
                "turbin": r.turbin,
                "D_m": t.D,
                "komsu_turbin": len(kom),
                "W_ic": float(1 - ref.E_ic.sum() / ref.E_serbest.sum()),
                "W_dis": float(1 - ref.E_toplam.sum() / ref.E_ic.sum()),
                "W_toplam": float(1 - ref.E_toplam.sum() / ref.E_serbest.sum()),
                "ort_aralik_D": float(
                    np.sort(np.hypot(x[:, None] - x[None], y[:, None] - y[None]) + np.eye(len(x)) * 1e9, 1)[:, 0].mean() / t.D
                ),
                "yon_kaynagi": "era5_hucre" if yon is not None else "yok",
                "sure_s": time.perf_counter() - t0,
            }
        )
        print(
            f"{r.ad:28s} n={len(k):3d} komşu={len(kom):3d}  W_iç %{100 * satir[-1]['W_ic']:.1f}  W_dış %{100 * satir[-1]['W_dis']:.1f}",
            flush=True,
        )
    return pd.DataFrame(satir), eta


def ols(y, X):
    X = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    s2 = e @ e / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))
    return b, se, r2


def bootstrap_egim(y, X, n=4000, tohum=42):
    rng = np.random.default_rng(tohum)
    out = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        out.append(ols(y[i], X[i])[0][1])
    return np.percentile(out, [5, 50, 95])


def hipotez(tb: pd.DataFrame, d) -> dict:
    df, _ = aktarim.atlas()
    ci = aktarim.santral_c()
    t = tb.merge(df[["epias_id", "R_artik", "karmasiklik", "kiyi_km", "rakim_m", "gozlenen_kf"]], on="epias_id")
    t = t[t["n_turbin"] > 1].copy()
    q = []
    for r in t.itertuples():
        m, g, ok = d[int(r.epias_id)]
        q.append(float(g[ok].mean() / m.kf(ci[int(r.epias_id)])[ok].mean()))
    t["q"] = q
    t["lnR"] = np.log(t["R_artik"])
    t["lnq"] = np.log(t["q"])
    t["ln1W"] = np.log(1 - t["W_toplam"])
    t["bolge"] = np.where(t["il"].isin(["Balıkesir", "Çanakkale"]), "Balıkesir–Biga", "diğer")
    sonuc = {"n": int(len(t))}
    for hedef in ("lnR", "lnq"):
        y = t[hedef].to_numpy()
        b, se, r2 = ols(y, t["ln1W"].to_numpy())
        Xk = t[["ln1W", "karmasiklik", "rakim_m"]].assign(lk=np.log(t["kiyi_km"] + 10)).to_numpy()
        bk, sek, r2k = ols(y, Xk)
        sonuc[hedef] = {
            "egim": float(b[1]),
            "se": float(se[1]),
            "t": float(b[1] / se[1]),
            "r2": float(r2),
            "egim_kontrollu": float(bk[1]),
            "se_kontrollu": float(sek[1]),
            "r2_kontrollu": float(r2k),
            "bootstrap_p5_p50_p95": bootstrap_egim(y, t["ln1W"].to_numpy()).round(3).tolist(),
            "spearman": float(pd.Series(y).corr(pd.Series(t["W_toplam"].to_numpy()), method="spearman")),
        }
    g = t.groupby("bolge").agg(
        n=("epias_id", "size"),
        W_toplam=("W_toplam", "mean"),
        W_ic=("W_ic", "mean"),
        W_dis=("W_dis", "mean"),
        lnR=("lnR", "mean"),
        lnq=("lnq", "mean"),
        R=("R_artik", "median"),
    )
    fark_R = float(g.loc["Balıkesir–Biga", "lnR"] - g.loc["diğer", "lnR"])
    fark_q = float(g.loc["Balıkesir–Biga", "lnq"] - g.loc["diğer", "lnq"])
    fark_iz = float(np.log(1 - g.loc["Balıkesir–Biga", "W_toplam"]) - np.log(1 - g.loc["diğer", "W_toplam"]))
    # Bölge farkı için permütasyon testi (iz kaybı farkı)
    rng = np.random.default_rng(7)
    bb = (t["bolge"] == "Balıkesir–Biga").to_numpy()
    w = t["W_toplam"].to_numpy()
    gozlenen = w[bb].mean() - w[~bb].mean()
    perm = [w[p[: bb.sum()]].mean() - w[p[bb.sum() :]].mean() for p in (rng.permutation(len(w)) for _ in range(5000))]
    sonuc["bolge"] = {
        "tablo": g.round(4).reset_index().to_dict(orient="records"),
        "lnq_farki": fark_q,
        "lnR_farki": fark_R,
        "ln1W_farki": fark_iz,
        "iz_acikladigi_pay_q": fark_iz / fark_q if fark_q != 0 else None,
        "W_farki_puan": 100 * float(gozlenen),
        "W_farki_permutasyon_p": float((np.abs(perm) >= abs(gozlenen)).mean()),
    }
    t.to_csv(CIKTI / "D1_hipotez_santraller.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    return sonuc


def izsiz_katsayilar(tb, eta, d, cfg) -> dict:
    df, mat = aktarim.atlas()
    k = deger(cfg["v3"]["kayip"])
    W_ref = 1 - (1 - k["lumped_v2"]) / ((1 - k["elektrik_diger"]) * k["kalibrasyon_kullanilabilirligi"])
    yeni, olcek = {}, {}
    for r in df.itertuples():
        i = int(r.epias_id)
        m, _, ok = d[i]
        K = mat[i]
        if i not in eta:
            yeni[i], olcek[i] = K, 1.0
            continue
        e = eta[i].astype(float)
        hedef = float(m.kf_matris(K)[ok].mean()) * (1 - W_ref)
        s = brentq(lambda s, m=m, K=K, e=e, ok=ok, h=hedef: float((m.kf_matris(s * K) * e)[ok].mean()) - h, 0.7, 1.5, xtol=1e-5)
        yeni[i], olcek[i] = s * K, s
    np.savez_compressed(IZSIZ_NPZ, **{f"k_{i}": v.astype(np.float32) for i, v in yeni.items()})
    return {"W_ref": W_ref, "olcek": olcek}


def loo(cfg, d, gw, eta, izsiz: bool, goreli_W: float | None = None) -> pd.DataFrame:
    k = deger(cfg["v3"]["kayip"])
    df, _ = aktarim.atlas()
    if izsiz:
        z = np.load(IZSIZ_NPZ)
        mat = {int(a[2:]): z[a].astype(float) for a in z.files}
        aktarim.atlas.cache_clear()
        aktarim._atlas_ozel = (df, mat)
    aktarim.ulusal_artik.cache_clear()
    satir = []
    try:
        for r in df.itertuples():
            i = int(r.epias_id)
            m, g, ok = d[i]
            tan = {"rakim_m": r.rakim_m, "karmasiklik": r.karmasiklik, "kiyi_km": r.kiyi_km}
            Km, b = aktarim.tahmin(r.enlem, r.boylam, r.era5_100m, "gwa_olcekli", cfg, haric=i, tan=tan, gwa_hiz=gw[i])
            kf = m.kf_matris(Km)
            if izsiz:
                e = eta[i].astype(float) if i in eta else 1 - 0.088
                kf = kf / (1 - k["lumped_v2"]) * (1 - k["elektrik_diger"]) * k["kalibrasyon_kullanilabilirligi"] * e
            elif goreli_W is not None:  # v2 atlası (K) + göreli iz düzeltmesi: η_x(t) / (1 − W̄)
                kf = kf * (eta[i].astype(float) if i in eta else 1 - goreli_W) / (1 - goreli_W)
            satir.append({"epias_id": i, "ad": r.ad, "komsu": len(b.get("komsu", [])), "hata": 100 * float(kf[ok].mean() - g[ok].mean())})
    finally:
        aktarim._atlas_ozel = None
        aktarim.atlas.cache_clear()
        aktarim.ulusal_artik.cache_clear()
    return pd.DataFrame(satir)


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    _, (d, gw) = cv_veri()
    if IZ_CSV.exists() and ETA_NPZ.exists() and "--yeniden" not in sys.argv:
        tb = pd.read_csv(IZ_CSV)
        z = np.load(ETA_NPZ)
        eta = {int(a[2:]): z[a] for a in z.files}
    else:
        tb, eta = santral_iz(cfg, d)
        tb.to_csv(IZ_CSV, index=False, encoding="utf-8-sig", float_format="%.5f")
        ETA_NPZ.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(ETA_NPZ, **{f"e_{i}": v for i, v in eta.items()})
    print(tb[["W_ic", "W_dis", "W_toplam"]].describe().round(4).to_string())
    h = hipotez(tb, d)
    print(json.dumps(h, ensure_ascii=False, indent=1, default=float))
    iz_s = izsiz_katsayilar(tb, eta, d, cfg)
    print("W_ref", round(iz_s["W_ref"], 4), "ölçek P10/50/90", np.percentile(list(iz_s["olcek"].values()), [10, 50, 90]).round(4))
    W_ort = float(tb.loc[tb["n_turbin"] > 1, "W_toplam"].mean())
    once = loo(cfg, d, gw, eta, izsiz=False)
    sonra = loo(cfg, d, gw, eta, izsiz=True)
    gor = loo(cfg, d, gw, eta, izsiz=False, goreli_W=W_ort)
    x = once.merge(sonra[["epias_id", "hata"]], on="epias_id", suffixes=("_once", "_sonra"))
    x["hata_goreli"] = gor["hata"].to_numpy()
    x.to_csv(CIKTI / "D1_loo_santraller.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    ozet = []
    for ad, e in (
        ("önce (v2: K, toplu %12)", x["hata_once"]),
        ("sonra-1 (izden arındırılmış K' + iz)", x["hata_sonra"]),
        (f"sonra-2 (K + göreli iz: η/(1−W̄), W̄ = %{100 * W_ort:.1f})", x["hata_goreli"]),
    ):
        ozet.append(
            {
                "durum": ad,
                "rmse": float(np.sqrt((e**2).mean())),
                "medyan_mutlak": float(e.abs().median()),
                "p90_mutlak": float(e.abs().quantile(0.9)),
                "ort_hata": float(e.mean()),
                "komsulu_rmse": float(np.sqrt((e[x["komsu"] > 0] ** 2).mean())),
            }
        )
    fark = (x["hata_sonra"] ** 2 - x["hata_once"] ** 2).to_numpy()
    rng = np.random.default_rng(42)
    bs, bs2 = [], []
    for _ in range(4000):
        j = rng.integers(0, len(x), len(x))
        r0 = np.sqrt((x["hata_once"].to_numpy()[j] ** 2).mean())
        bs.append(np.sqrt((x["hata_sonra"].to_numpy()[j] ** 2).mean()) - r0)
        bs2.append(np.sqrt((x["hata_goreli"].to_numpy()[j] ** 2).mean()) - r0)
    oz = pd.DataFrame(ozet)
    oz.to_csv(CIKTI / "D1_loo_once_sonra.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    print(oz.round(2).to_string())
    sonuc = {
        "hipotez": h,
        "W_ref": iz_s["W_ref"],
        "loo": ozet,
        "rmse_farki_bootstrap_p5_p50_p95": np.percentile(bs, [5, 50, 95]).round(3).tolist(),
        "rmse_farki_goreli_bootstrap": np.percentile(bs2, [5, 50, 95]).round(3).tolist(),
        "iyilesen": int((fark < 0).sum()),
        "W_atlas_ort": W_ort,
    }
    (CIKTI / "D1_hipotez_ozet.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=float))
    print("RMSE farkı bootstrap", sonuc["rmse_farki_bootstrap_p5_p50_p95"], "göreli", sonuc["rmse_farki_goreli_bootstrap"])


if __name__ == "__main__":
    main()
