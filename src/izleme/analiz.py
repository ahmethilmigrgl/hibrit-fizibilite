"""
Santral performans izleme analizi (Faz F4).

1. Günlük oran: PR_{i,d} = Σ gözlenen / Σ model beklentisi (geçerli saatler; model = ERA5 + atlas k matrisi × kapasite).
2. Analiz dışı günler:
   - bölgesel eşzamanlı düşüş: santralin akranları (≤ akran_km, kendisi dahil, ≥ 3 santral) arasında o gün PR'si kendi
     90 günlük medyanının bolgesel_dusus_orani katının altına düşenlerin payı ≥ bolgesel_santral_payi (sistem talimatı,
     şebeke arızası, buzlanma gibi ortak olaylar),
   - ulusal YAT günü: EPİAŞ yük atma talimatı günlük toplamı ≥ yat_gun_yuzdelik (2023+; talimat özeti),
   - kapasite olayı günleri: kapasite (geçmişe dönük en büyük aylık %99,5 çıkış) > kapasite_olay_esigi artış → artırım
     ya da yenileme; olaydan sonra yeni taban dönem başlar.
3. Aylık oran (≥ asgari_gecerli_gun geçerli gün; haftalık oranın doğal gürültüsü ~%17–19 olduğundan izleme birimi ay) ve akran
   oranı: ln PR_akran = medyan_{j ∈ akran(i), j≠i} ln PR_j (yoksa Türkiye medyanı).
4. Taban dönem (her kapasite bölütünün ilk taban_donem geçerli ayı): akran ağırlığı b = Cov/Var ∈ [0, 1] (en küçük varyanslı
   birleşim), x = ln PR − b·ln PR_akran, μ0 = medyan x, σ0 = 1,4826 · MAD, z = (x − μ0) / σ0.
5. Kontrol kartları (src/izleme/spc.py), parametreler ARL0 hedefine göre (taban z'lerinden blok bootstrap).
6. Durum (son ay): kalıcı sapma ⇔ son kalici_pencere ayın ≥ kalici_alarm'ında EWMA alarmı ve ortalama açık ≥ kalici_dusus;
   izleniyor ⇔ son 3 ayda herhangi bir alarm; normal; veri yetersiz.
7. Tahmini kayıp: EWMA alarmlı aylarda (taban göreli performansla beklenen − gözlenen) MWh × aylık ortalama PTF (USD).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku, deger
from src.izleme import spc

ATLAS = KOK / "data" / "atlas"
CIKTI = ATLAS / "izleme"


def ayar() -> dict:
    return deger(config_oku()["v3"]["performans"])


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def akranlar(s: pd.DataFrame, km: float, asgari: int) -> dict[int, list[int]]:
    """Her santral için kendisi hariç akranlar: ≤ km; az ise en yakın (asgari − 1) santral."""
    e, b, ids = s["enlem"].to_numpy(), s["boylam"].to_numpy(), s["epias_id"].to_numpy()
    out = {}
    for i, sid in enumerate(ids):
        d = _km(e[i], b[i], e, b)
        d[i] = np.inf
        sec = np.where(d <= km)[0]
        if len(sec) < asgari - 1:
            sec = np.argsort(d)[: asgari - 1]
        out[int(sid)] = [int(ids[j]) for j in sec]
    return out


def yat_gunleri(q: float) -> pd.DatetimeIndex:
    p = KOK / "data" / "processed" / "talimat_ozeti_2023_guncel.parquet"
    if not p.exists():
        return pd.DatetimeIndex([])
    t = pd.read_parquet(p)
    yat = t[[c for c in t.columns if c.startswith("yat_")]].sum(1)
    g = yat.groupby(yat.index.tz_convert("Europe/Istanbul").normalize().tz_localize(None)).sum()
    return g.index[g >= g.quantile(q)]


def gunluk_isaretle(gd: pd.DataFrame, s: pd.DataFrame, a: dict) -> pd.DataFrame:
    gd = gd.copy()
    gd["pr"] = gd["gozlenen_mwh"] / gd["beklenen_mwh"].where(gd["beklenen_mwh"] > 0)
    gd.loc[gd["saat"] < 20, "pr"] = np.nan
    P = gd.pivot(index="gun", columns="epias_id", values="pr").sort_index()
    med = P.rolling(90, min_periods=30).median()
    dusuk = (P < a["bolgesel_dusus_orani"] * med).astype(float).where(P.notna())
    ak = akranlar(s, a["akran_km"], a["akran_asgari"])
    bolgesel = pd.DataFrame(False, index=P.index, columns=P.columns)
    for sid in P.columns:
        grup = [sid, *[j for j in ak.get(int(sid), []) if j in P.columns]]
        n = dusuk[grup].notna().sum(1)
        pay = dusuk[grup].mean(1)
        bolgesel[sid] = (n >= a["akran_asgari"]) & (pay >= a["bolgesel_santral_payi"])
    yat = yat_gunleri(a["yat_gun_yuzdelik"])
    b = bolgesel.stack().rename("bolgesel").reset_index()
    gd = gd.merge(b, on=["gun", "epias_id"], how="left")
    gd["bolgesel"] = gd["bolgesel"].fillna(False).astype(bool)
    gd["yat"] = gd["gun"].isin(yat)
    # kapasite olayları: günlük kapasite serisinde eşik üstü artış
    gd = gd.sort_values(["epias_id", "gun"])
    onceki = gd.groupby("epias_id")["kapasite_mw"].shift()
    gd["kapasite_olayi"] = (gd["kapasite_mw"] > (1 + a["kapasite_olay_esigi"]) * onceki) & onceki.notna()
    gd["gecerli"] = gd["pr"].notna() & ~gd["bolgesel"] & ~gd["yat"]
    return gd


def donemlik(gd: pd.DataFrame, s: pd.DataFrame, a: dict) -> pd.DataFrame:
    """Dönem (ay) toplamları, kendi oranı ve akran oranı (log)."""
    gd = gd.copy()
    gd["donem"] = gd["gun"].dt.to_period(a["donem"]).dt.start_time
    gd["bolut"] = gd.groupby("epias_id")["kapasite_olayi"].cumsum()
    v = gd[gd["gecerli"]]
    w = v.groupby(["epias_id", "donem"]).agg(
        gozlenen_mwh=("gozlenen_mwh", "sum"), beklenen_mwh=("beklenen_mwh", "sum"), gun=("gun", "count")
    )
    hepsi = gd.groupby(["epias_id", "donem"]).agg(
        bolut=("bolut", "max"), dislanan_bolgesel=("bolgesel", "sum"), dislanan_yat=("yat", "sum"), kapasite_mw=("kapasite_mw", "max")
    )
    w = hepsi.join(w, how="left").reset_index()
    # çok düşük beklentili aylar (az geçerli gün, sakin ay) oranı patlatır: santralin medyan aylık beklentisinin %25'i altı dışarıda
    esik = w.groupby("epias_id")["beklenen_mwh"].transform("median") * 0.25
    w["pr"] = (w["gozlenen_mwh"] / w["beklenen_mwh"]).where((w["gun"].fillna(0) >= a["asgari_gecerli_gun"]) & (w["beklenen_mwh"] >= esik))
    w["ln_pr"] = np.log(w["pr"].clip(lower=0.05))
    # akran medyanına veri boşluğu / tam duruş ayları (PR < 0,2) girmez; santralin kendi düşük ayları sinyal olarak kalır
    P = w.assign(ln_ak=w["ln_pr"].where(w["pr"] >= 0.2)).pivot(index="donem", columns="epias_id", values="ln_ak")
    ak = akranlar(s, a["akran_km"], a["akran_asgari"])
    ulusal = P.median(1)
    M = pd.DataFrame(index=P.index, columns=P.columns, dtype=float)
    for sid in P.columns:
        grup = [j for j in ak.get(int(sid), []) if j in P.columns]
        m = P[grup].median(1) if grup else ulusal
        n = P[grup].notna().sum(1) if grup else pd.Series(0, index=P.index)
        M[sid] = m.where(n >= max(1, a["akran_asgari"] - 1), ulusal)
    r = M.stack().rename("ln_akran").reset_index()
    return w.merge(r, on=["donem", "epias_id"], how="left")


def taban_ve_z(w: pd.DataFrame, a: dict) -> tuple[pd.DataFrame, dict]:
    """
    Kapasite bölütü başına taban dönem (ilk taban_donem geçerli dönem): akran ağırlığı b = Cov(ln PR, ln PR_akran) /
    Var(ln PR_akran), [0, 1]'e kırpılır (en küçük varyanslı birleşim: hava/model hatasının akranlarla ortak kısmı kadar düşülür);
    x = ln PR − b · ln PR_akran;  μ0 = medyan x, σ0 = 1,4826 · MAD;  z = (x − μ0) / σ0.
    """
    w = w.sort_values(["epias_id", "donem"]).copy()
    w["taban"] = False
    for c in ("z", "x", "mu0", "sigma0", "b_akran"):
        w[c] = np.nan
    par = {}
    T = a["taban_donem"]
    kayan = a.get("taban_turu") == "kayan"
    if kayan:  # kapasite olayı ayı ve sonraki 2 ay analiz dışı (bölüt bölünmez; kayan taban yeni düzeye uyum sağlar)
        olay = w.groupby("epias_id")["bolut"].diff().fillna(0) > 0
        dis = olay.copy()
        for k_ in (1, 2):
            dis |= olay.groupby(w["epias_id"]).shift(k_, fill_value=False)
        w.loc[dis, "ln_pr"] = np.nan
        w["kapasite_disi"] = dis
        anahtar = w["epias_id"].map(lambda v: (v, 0))
    else:
        anahtar = list(zip(w["epias_id"], w["bolut"]))
    for (sid, bol), g in w.groupby(pd.Series(anahtar, index=w.index)):
        gec = g[g["ln_pr"].notna() & g["ln_akran"].notna()]
        if len(gec) < T + 6:
            continue
        tb = gec.iloc[:T]
        va = float(np.var(tb["ln_akran"].to_numpy(), ddof=1))
        b = float(np.clip(np.cov(tb["ln_pr"].to_numpy(), tb["ln_akran"].to_numpy())[0, 1] / va, 0, 1)) if va > 0 else 0.0
        x = g["ln_pr"] - b * g["ln_akran"]
        xt = x.loc[tb.index]
        mu = float(xt.median())
        sd = max(float(1.4826 * (xt - mu).abs().median()), 0.01)
        w.loc[g.index, "x"] = x
        if a.get("taban_turu") == "kayan":
            # kayan taban: t ayı için [t − ust, t − alt] aylarının medyanı (en az 12 geçerli ay); yavaş kaymalar (yaşlanma,
            # ERA5'in yıllar arası sapması) elenir, 6 aya kadar süren basamak düşüşler tabanı kirletmez
            alt, ust = a["kayan_pencere"]
            xs = x.reset_index(drop=True)
            mu_t = pd.Series(
                [
                    xs.iloc[max(0, i - ust) : max(0, i - alt + 1)].median()
                    if xs.iloc[max(0, i - ust) : max(0, i - alt + 1)].notna().sum() >= 12
                    else np.nan
                    for i in range(len(xs))
                ],
                index=x.index,
            )
            d = x - mu_t
            sd = max(float(1.4826 * (d - d.median()).abs().median()), 0.01) if d.notna().sum() > 12 else sd
            w.loc[g.index, "z"] = d / sd
            w.loc[g.index, "mu_t"] = mu_t
            ilk = mu_t.notna()
            w.loc[g.index[~ilk.to_numpy()], "taban"] = True
            w.loc[g.index, "mu0"] = mu_t.fillna(mu)
            w.loc[g.index, "sigma0"] = sd
            w.loc[g.index, "b_akran"] = b
            par[(int(sid), int(bol))] = (mu, sd, b)
            continue
        w.loc[g.index, "z"] = (x - mu) / sd
        w.loc[tb.index, "taban"] = True
        w.loc[g.index, "mu0"] = mu
        w.loc[g.index, "sigma0"] = sd
        w.loc[g.index, "b_akran"] = b
        par[(int(sid), int(bol))] = (mu, sd, b)
    w["rel"] = np.exp(w["x"] - w["mu0"])  # taban dönemine göre akran düzeltmeli performans (1 = taban)
    return w, par


def analiz() -> dict:
    a = ayar()
    s = pd.read_csv(ATLAS / "kalibrasyon_atlasi.csv")
    s = s[s["sinif"].isin(["temiz", "kullanilabilir"])].reset_index(drop=True)
    gd = pd.read_parquet(KOK / "data" / "processed" / "izleme_gunluk.parquet")
    s = s[s["epias_id"].isin(gd["epias_id"].unique())].reset_index(drop=True)
    gd = gunluk_isaretle(gd, s, a)
    w = donemlik(gd, s, a)
    w, par = taban_ve_z(w, a)
    lam, k = a["ewma_lambda"], a["cusum_k"]
    # --- kalibrasyon: taban dönem z'lerinden ARL0
    # kalibrasyon havuzu: sabit tabanda taban dönem z'leri; kayan tabanda tüm izleme z'leri (gerçek verinin uzun bellekli
    # değişkenliğini içerir; arada gerçek düşüşler de bulunduğundan ARL0 muhafazakâr kalibre edilir)
    sec = w["taban"] if a.get("taban_turu") != "kayan" else w["z"].notna()
    havuz = [g["z"].to_numpy() for _, g in w[sec].groupby("epias_id")]
    Z = spc.bootstrap_seriler(havuz, 4000, 240, a["bootstrap_blok"], 7)
    kp = spc.kalibre(Z, a["hedef_arl0_donem"], lam, k)
    Z1 = spc.bootstrap_seriler(havuz, 3000, 240, a["bootstrap_blok"], 8)
    arl1 = {
        f"{d:.0%}": {x: spc.arl(Z1 + np.log(1 - d) / np.median([p[1] for p in par.values()]), x, kp[x], lam, k) for x in kp}
        for d in (0.03, 0.05, 0.10)
    }
    # --- alarmlar (izleme dönemi: taban sonrası)
    w["izleme"] = w["z"].notna() & ~w["taban"]
    for x in ("shewhart", "ewma", "cusum"):
        w[f"alarm_{x}"] = False
    w["ewma"] = np.nan
    w["cusum"] = np.nan
    for (_sid, _bol), g in w[w["z"].notna()].groupby(["epias_id", "bolut"]):
        z = g["z"].to_numpy()
        al = spc.alarmlar(z, kp, lam, k)
        izl = g["izleme"].to_numpy()
        for x in ("shewhart", "ewma", "cusum"):
            w.loc[g.index, f"alarm_{x}"] = al[x] & izl
        w.loc[g.index, "ewma"] = al["ewma_deger"]
        w.loc[g.index, "cusum"] = al["cusum_deger"]
    # --- kayıp enerji ve gelir (EWMA alarmlı aylar)
    ptf = pd.read_parquet(KOK / "data" / "processed" / "ptf_2014_guncel.parquet")["ptf_usd"]
    pw = ptf.groupby(ptf.index.tz_convert("Europe/Istanbul").tz_localize(None).to_period(a["donem"]).start_time).mean()
    w["ptf_usd"] = w["donem"].map(pw)
    beklenen_taban = w["gozlenen_mwh"] / w["rel"]
    w["kayip_mwh"] = np.where(w["alarm_ewma"], np.clip(beklenen_taban - w["gozlenen_mwh"], 0, None), 0.0)
    w["kayip_usd"] = w["kayip_mwh"] * w["ptf_usd"].fillna(pw.mean())
    # --- durum
    son = w.loc[w["pr"].notna(), "donem"].max()  # ERA5 2025 sonunda bittiği için beklenen üretimi olan son ay
    sira = {int(x): f"S{i + 1:03d}" for i, x in enumerate(sorted(s["epias_id"]))}
    from src.kaynaklar import sinirlar

    dur = []
    for _, r in s.iterrows():
        sid = int(r["epias_id"])
        g = w[(w["epias_id"] == sid)].sort_values("donem")
        izl = g[g["izleme"]]
        konum = sinirlar.konum(r["enlem"], r["boylam"]) or {}
        kp_ = a["kalici_pencere"]
        son_p = izl[izl["donem"] > son - pd.DateOffset(months=kp_)]
        son_y = izl[izl["donem"] > son - pd.DateOffset(months=3)]
        acik = 1 - float(son_p["rel"].mean()) if len(son_p) else np.nan
        if len(izl) < 2 * kp_ or len(son_p) < kp_ // 2:
            d = "veri_yetersiz"
        elif son_p["alarm_ewma"].sum() >= a["kalici_alarm"] and acik >= a["kalici_dusus"]:
            d = "kalici_sapma"
        elif son_y[["alarm_shewhart", "alarm_ewma", "alarm_cusum"]].any().any():
            d = "izleniyor"
        else:
            d = "normal"
        dur.append(
            {
                "epias_id": sid,
                "kod": sira[sid],
                "ad": r["ad"],
                "il": konum.get("il", ""),
                "enlem": r["enlem"],
                "boylam": r["boylam"],
                "kapasite_mw": float(g["kapasite_mw"].max()),
                "durum": d,
                "son_acik": acik,
                "izleme_donem": int(len(izl)),
                "alarm_donem_ewma": int(izl["alarm_ewma"].sum()),
                "b_akran": float(g["b_akran"].dropna().iloc[-1]) if g["b_akran"].notna().any() else np.nan,
                "kayip_mwh": float(izl["kayip_mwh"].sum()),
                "kayip_usd": float(izl["kayip_usd"].sum()),
                "kapasite_olayi": int(gd.loc[gd["epias_id"] == sid, "kapasite_olayi"].sum()),
                "bolgesel_gun": int(gd.loc[gd["epias_id"] == sid, "bolgesel"].sum()),
                "yat_gun": int(gd.loc[gd["epias_id"] == sid, "yat"].sum()),
                "sigma0": float(g["sigma0"].dropna().iloc[-1]) if g["sigma0"].notna().any() else np.nan,
                "akran_sayisi": len(akranlar(s, a["akran_km"], a["akran_asgari"]).get(sid, [])),
            }
        )
    dur = pd.DataFrame(dur)
    # --- doğrulama: yapay arıza (normal santrallerin izleme dönemi)
    nrm = dur.loc[dur["durum"] == "normal", "epias_id"]
    ser, sg = [], []
    for sid in nrm:
        g = w[(w["epias_id"] == sid) & w["izleme"]]
        z = g["z"].to_numpy()
        z = z[~np.isnan(z)]
        if len(z) >= 24:
            ser.append(z)
            sg.append(float(g["sigma0"].iloc[0]))
    ya = a["yapay_ariza"]
    yap = spc.yapay_ariza_testi(ser, sg, kp, lam, k, ya["dusus"], ya["sure_donem"], ya["tekrar"], 11, pencere_ek=2)
    ya_gercek = spc.yanlis_alarm_orani(ser, kp, lam, k)
    dog = {
        "kart_parametreleri": kp,
        "donem": a["donem"],
        "hedef_arl0_donem": a["hedef_arl0_donem"],
        "arl1_donem": arl1,
        "sigma0_medyan": float(dur["sigma0"].median()),
        "yapay_ariza": yap,
        "yanlis_alarm_yil_gercek_normal": ya_gercek,
        "yanlis_alarm_yil_teorik": 12.0 / a["hedef_arl0_donem"],
        "n_santral": int(len(dur)),
        "durum_sayim": dur["durum"].value_counts().to_dict(),
        "son_donem": str(son.date()),
        "dislanan_gun_payi": {
            "bolgesel": float(gd["bolgesel"].mean()),
            "yat": float(gd["yat"].mean()),
        },
    }
    CIKTI.mkdir(parents=True, exist_ok=True)
    kol = ["epias_id", "donem", "pr", "rel", "z", "ewma", "cusum", "alarm_shewhart", "alarm_ewma", "alarm_cusum", "taban", "izleme",
           "bolut", "dislanan_bolgesel", "dislanan_yat", "kayip_mwh", "kayip_usd", "mu0", "sigma0", "b_akran", "gozlenen_mwh",
           "beklenen_mwh"]  # fmt: skip
    hw = w[kol].copy()
    for c in hw.select_dtypes("float64").columns:
        hw[c] = hw[c].astype("float32")
    hw.to_parquet(CIKTI / "aylik.parquet", index=False)
    gg = gd[["epias_id", "gun", "pr", "gecerli", "bolgesel", "yat", "kapasite_olayi"]].copy()
    gg["pr"] = gg["pr"].astype("float32")
    gg.to_parquet(CIKTI / "gunluk.parquet", index=False)
    dur.to_csv(CIKTI / "durum.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    (CIKTI / "dogrulama.json").write_text(json.dumps(dog, ensure_ascii=False, indent=1, default=float))
    return {"durum": dur, "dogrulama": dog, "aylik": w}
