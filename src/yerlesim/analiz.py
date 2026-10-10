"""
Yerleşim hattı (analiz motoru için): profil → rüzgâr gülü → aday konumlar → hızlı vekil → yöntem → PyWake referansı
(komşu santrallerle) → türbin başına üretim ve iz kaybı → saatlik çiftlik verimi (profil düzeltmesi).

Terimler (hepsi yıllık enerji oranı):
    konum kazancı  G  = E_serbest(S) / (N · E_ref)      E_ref: GWA çarpanı 1 olan, izsiz tek türbin (profilin türbini)
    iç iz kaybı    W_iç  = 1 − E_iç / E_serbest
    dış (komşu) iz kaybı W_dış = 1 − E_toplam / E_iç
    çiftlik verimi η = E_toplam / (N · E_ref) = G · (1 − W_iç) · (1 − W_dış)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import deger
from src.kaynaklar import era5_yon
from src.yerlesim import alan as A
from src.yerlesim import iz, yontemler
from src.yerlesim.ruzgar_gulu import AkisTablosu, akis_tablosu, esdeger_hiz, gul_tablosu
from src.yerlesim.turbin import TurbinEgrisi, genel_turbin, kutuphane_turbini

AZAMI_ADAY = 300


@lru_cache(maxsize=1)
def osm_turbinleri() -> pd.DataFrame:
    from src import veri_katmani

    return pd.read_csv(veri_katmani.yol("atlas/osm_turbinler.csv"))


def komsu_turbinler(enlem: float, boylam: float, yaricap_km: float, azami: int, haric_epias: int | None = None) -> pd.DataFrame:
    d = osm_turbinleri()
    if haric_epias is not None:
        d = d[d["epias_id"] != haric_epias]
    x, y = A.yerel_xy(d["enlem"], d["boylam"], enlem, boylam)
    r = np.hypot(x, y)
    s = r <= yaricap_km * 1000
    return d[s].assign(x=x[s], y=y[s], r=r[s]).sort_values("r").head(azami).reset_index(drop=True)


@dataclass
class Baglam:
    enlem: float
    boylam: float
    turbin: TurbinEgrisi
    akis: AkisTablosu  # 36 yön, 0,5 m/s
    akis_k: AkisTablosu  # 36 yön, kaba hız kutuları (optimizasyon vekili)
    adaylar: pd.DataFrame  # olurlu adaylar (x, y, gwa, m)
    dislanan: pd.DataFrame
    problem_sablon: dict
    cift: iz.CiftTablosu
    C: np.ndarray
    gwa_ref: float
    E_ref: float  # MWh/yıl, tek referans türbin
    komsu: pd.DataFrame
    ti: float
    ayar: dict
    gul: pd.DataFrame
    sure: dict = field(default_factory=dict)

    def problem(self, N: int) -> yontemler.Problem:
        return yontemler.Problem(
            self.adaylar["x"].to_numpy(), self.adaylar["y"].to_numpy(), self.C, self.cift, N, self.akis.eksen, self.turbin.D
        )


def saatlik_ruzgar(profil: pd.DataFrame, enlem: float, boylam: float) -> tuple[np.ndarray, np.ndarray | None, str]:
    """Profilin saatleri için yoğunluk eşdeğeri kalibre göbek hızı ve ERA5 100 m yönü."""
    if "v_kalibre" not in profil.columns:
        raise ValueError("Profilde 'v_kalibre' yok (v3 öncesi önbellek); profil yeniden üretilmeli.")
    v = esdeger_hiz(profil["v_kalibre"].to_numpy(), profil["hava_yogunlugu"].to_numpy())
    yon, kaynak = era5_yon.saatlik_yon(enlem, boylam)
    if yon is None:
        return v, None, kaynak
    s = pd.Series(yon, index=pd.date_range(era5_yon.BAS, periods=len(yon), freq="h", tz="UTC"))
    idx = profil.index if profil.index.name == "zaman_utc" else pd.DatetimeIndex(profil["zaman_utc"])
    y = s.reindex(idx).ffill().bfill().to_numpy()
    return v, y, kaynak


def hazirla(
    enlem: float,
    boylam: float,
    profil: pd.DataFrame,
    turbin_modeli: str,
    gobek: float,
    gwa_ref: float,
    yaricap_km: float,
    cfg: dict,
    dislama: list | None = None,
    haric_epias: int | None = None,
) -> Baglam:
    t0 = time.perf_counter()
    ay = deger(cfg["v3"]["yerlesim"])
    t = kutuphane_turbini(turbin_modeli, float(gobek))
    v, yon, kaynak = saatlik_ruzgar(profil, enlem, boylam)
    akis = akis_tablosu(v, yon, 36, 0.5, guc=t.guc_mw, kaynak=kaynak)
    akis_k = akis.kaba(36, np.r_[0.0, 3.0, np.arange(4.5, 16.0, 1.5), 18.0, 25.0, 35.0])
    gul = gul_tablosu(profil["v_kalibre"].to_numpy(), yon if yon is not None else np.zeros(len(v)))
    komsu = komsu_turbinler(enlem, boylam, ay["komsu_yaricap_km"], ay["komsu_azami"], haric_epias)
    katman = list(dislama or [])
    if len(komsu):
        katman.append(A.MevcutTurbinTamponu(komsu["enlem"].to_numpy(), komsu["boylam"].to_numpy(), ay["komsu_tampon_D"] * t.D))
    sa = A.SahaAlani(enlem, boylam, yaricap_km, katman)
    tum = sa.adaylar(ay.get("aday_alt_bolme", 1))
    ad = tum[tum["dislanan"] == ""].reset_index(drop=True)
    ad["m"] = ad["gwa"] / gwa_ref
    if len(ad) > AZAMI_ADAY:  # bellek: en rüzgârlı adaylar
        ad = ad.sort_values("gwa", ascending=False).head(AZAMI_ADAY).reset_index(drop=True)
    t1 = time.perf_counter()
    cift = iz.cift_tablosu(ad["x"], ad["y"], ad["m"], akis_k, t, ay["ti"])
    t2 = time.perf_counter()
    a = ay["asgari_aralik"]
    C = A.elips_catisma(ad["x"].to_numpy(), ad["y"].to_numpy(), t.D, a["hakim_D"], a["dik_D"], akis.eksen)
    E_ref = float((t.guc_mw(akis.ws)[None] * akis.P).sum() * iz.SAAT_YIL)
    return Baglam(
        enlem,
        boylam,
        t,
        akis,
        akis_k,
        ad,
        tum[tum["dislanan"] != ""],
        {},
        cift,
        C,
        gwa_ref,
        E_ref,
        komsu,
        ay["ti"],
        ay,
        gul,
        {"hazirlik_s": t1 - t0, "cift_tablosu_s": t2 - t1},
    )


def coz(b: Baglam, N: int, yontem: str | None = None, tohum: int = 0) -> yontemler.Sonuc:
    """yontem: 'milp' | 'ga' | 'sa' | 'izgara' | 'acgozlu' | 'gwa' (varsayılan config v3.yerlesim.yontem)."""
    p = b.problem(N)
    yontem = yontem or b.ayar["yontem"]
    if yontem == "milp":
        return yontemler.milp(p, b.ayar["milp_sure_s"], baslangic=yontemler.acgozlu(p).S)
    if yontem == "ga":
        g = b.ayar["ga"]
        return yontemler.genetik(
            p, tohum, g["nufus"], g["nesil"], g["mutasyon"], g["turnuva"], g["elit"], tohum_cozum=yontemler.acgozlu(p).S
        )
    if yontem == "sa":  # çok başlangıçlı: tohum·10 + k (k < başlangıç sayısı), en iyisi
        s = b.ayar["sa"]
        t0 = time.perf_counter()
        sonuc = [
            yontemler.tavlama(p, 10 * tohum + k, s["adim"], s["t0_oran"], s["sogutma"], s["yerel_arama"])
            for k in range(s.get("baslangic", 1))
        ]
        en_iyi = max(sonuc, key=lambda r: r.enerji)
        en_iyi.sure_s = time.perf_counter() - t0
        en_iyi.ayrinti["baslangic_enerjileri"] = [r.enerji for r in sonuc]
        if len(sonuc) > 1:
            en_iyi.yontem = f"Benzetimli tavlama + yerel arama ({len(sonuc)} başlangıç)"
        return en_iyi
    if yontem == "izgara":
        g = b.ayar["duzenli_izgara"]
        return yontemler.duzenli_izgara(p, g["hakim_D"], g["dik_D"])
    if yontem == "acgozlu":
        return yontemler.acgozlu(p)
    if yontem == "gwa":
        return yontemler.gwa_acgozlu(p, b.adaylar["gwa"].to_numpy())
    raise ValueError(yontem)


def azami_turbin(b: Baglam, Nmax: int) -> int:
    """Alana sığan en fazla türbin (açgözlü, elips kısıtıyla)."""
    s = yontemler.acgozlu(b.problem(Nmax))
    return len(s.S)


def iz_egrisi(b: Baglam, Nmax: int) -> pd.DataFrame:
    """
    N = 0..Nmax için vekil modelle açgözlü (iç içe) yerleşimin çiftlik verimi η_iç(N) = E_iç / (N·E_ref), iç iz kaybı ve
    konum kazancı. Alana sığmayan N'ler NaN. Kapasite MILP'ine parçalı doğrusal girdi.
    """
    p = b.problem(Nmax)
    s, oran = yontemler.acgozlu(p, Nmax, egri=True)
    S = s.S
    satir = [{"N": 0, "verim": 1.0, "ic_iz": 0.0, "konum": 1.0}]
    for n in range(1, Nmax + 1):
        if n <= len(S):
            Es = b.cift.E_serbest[S[:n]].sum()
            satir.append(
                {"N": n, "verim": float(Es * (1 - oran[n]) / (n * b.E_ref)), "ic_iz": float(oran[n]), "konum": float(Es / (n * b.E_ref))}
            )
        else:
            satir.append({"N": n, "verim": np.nan, "ic_iz": np.nan, "konum": np.nan})
    return pd.DataFrame(satir)


def komsu_sozlugu(b: Baglam) -> dict | None:
    if not len(b.komsu):
        return None
    from src.kaynaklar import gwa250

    tur = [genel_turbin(round(float(r.D_m)), round(float(r.H_m)), round(float(r.P_mw), 2)) for r in b.komsu.itertuples()]
    tipler: dict = {}
    idx = []
    for tt in tur:
        idx.append(tipler.setdefault(tt.ad, len(tipler)))
    tl = [None] * len(tipler)
    for tt in tur:
        tl[tipler[tt.ad]] = tt
    m = np.array([gwa250.nokta(float(r.enlem), float(r.boylam)) for r in b.komsu.itertuples()]) / b.gwa_ref
    return {"x": b.komsu["x"].to_numpy(), "y": b.komsu["y"].to_numpy(), "m": m, "turbinler": tl, "tip": np.array(idx)}


def degerlendir(b: Baglam, S: np.ndarray, model: str | None = None, komsu: bool = True) -> dict:
    """PyWake referans hesabı + türbin başına tablo + saatlik verim (profil düzeltmesi için)."""
    t0 = time.perf_counter()
    S = np.asarray(S, int)
    ad = b.adaylar.iloc[S].reset_index(drop=True)
    model = model or b.ayar["iz_modeli"]
    ref = iz.referans(ad["x"], ad["y"], ad["m"], b.turbin, b.akis, b.ti, model, komsu_sozlugu(b) if komsu else None)
    N = len(S)
    oran, kf_cift = iz.saatlik_verim(ref, b.akis, b.turbin, N)
    E_s, E_i, E_t = ref.E_serbest.sum(), ref.E_ic.sum(), ref.E_toplam.sum()
    tur = ad[["enlem", "boylam", "x", "y", "gwa", "m"]].assign(
        E_serbest_mwh=ref.E_serbest,
        E_ic_mwh=ref.E_ic,
        E_mwh=ref.E_toplam,
        ic_iz_=1 - ref.E_ic / ref.E_serbest,
        toplam_iz_=1 - ref.E_toplam / ref.E_serbest,
        kf=ref.E_toplam / (b.turbin.P_mw * iz.SAAT_YIL),
    )
    tur = tur.rename(columns={"ic_iz_": "ic_iz", "toplam_iz_": "toplam_iz"})
    return {
        "turbinler": tur,
        "ozet": {
            "N": N,
            "model": model,
            "E_serbest_mwh": float(E_s),
            "E_ic_mwh": float(E_i),
            "E_mwh": float(E_t),
            "konum_kazanci": float(E_s / (N * b.E_ref)),
            "ic_iz": float(1 - E_i / E_s),
            "dis_iz": float(1 - E_t / E_i),
            "toplam_iz": float(1 - E_t / E_s),
            "verim": float(E_t / (N * b.E_ref)),
            "komsu_turbin": int(len(b.komsu)) if komsu else 0,
            "hakim_yon": b.akis.hakim_yon,
            "eksen": b.akis.eksen,
            "yon_kaynagi": b.akis.yon_kaynagi,
        },
        "saatlik_oran": oran,
        "saatlik_kf_cift": kf_cift,
        "sure_s": time.perf_counter() - t0,
    }


def profil_duzelt(res_kf: np.ndarray, oran: np.ndarray, kf_cift: np.ndarray, elektrik_kaybi: float) -> np.ndarray:
    """
    İzsiz referans profil (res_kf: tek türbin, GWA_ref, yalnız elektrik kaybı) → çiftlik profili:
    referans gücün olduğu saatlerde res_kf · oran, olmadığı saatlerde (kesme altı, ama çarpanı > 1 olan konumlar üretiyor)
    doğrudan çiftlik KF'si · (1 − elektrik kaybı).
    """
    return np.clip(np.where(np.isfinite(oran), res_kf * np.nan_to_num(oran), kf_cift * (1 - elektrik_kaybi)), 0, 1)


def taban_kayip(cfg: dict) -> float:
    """
    v3 taban (iz ve kullanılabilirlik HARİÇ) kayıp oranı λ: atlas kalibrasyonuyla tutarlı göreli kural
    0,88 = (1 − λ) · (1 − W_ref) · A_k  ⇒  λ = 1 − 0,88 / ((1 − W_ref) · A_k)   (config v3.kayip; ≈ %6,3).
    """
    k = deger(cfg["v3"]["kayip"])
    return 1.0 - (1.0 - k["lumped_v2"]) / ((1.0 - k["iz_referansi"]) * k["kalibrasyon_kullanilabilirligi"])
