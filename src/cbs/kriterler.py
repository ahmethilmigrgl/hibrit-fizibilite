"""
Çok kriterli saha seçimi için hücre kriter tablosu (v3 E3).

Dışlayıcı kısıtlar (hücre elenir):
    koruma alanı payı ≥ %50 · uygun alan (2 km yarıçapta dışlamalardan arınmış) < %10 · ada (kullanıcı dahil etmedikçe) · hesap hatası
Değerlendirme kriterleri (TOPSIS; fayda = büyük iyi):
    ekonomi   en iyi standart tasarımın başabaş fiyatı [$/MWh]           (maliyet)   — ya da "ruzgar": RES KF (fayda)
    sebeke    uygun gerilimli en yakın trafo merkezine uzaklık [km]      (maliyet)
    yol       ağır nakliyeye uygun en yakın yola uzaklık [km]            (maliyet)
    egim      2 km yarıçapta ortalama eğim [°]                           (maliyet)
    goc       göç koridoru riski (0/1/2; yaklaşık katman)                (maliyet)
    guven     rüzgâr tahmini güven seviyesi (yüksek 1, düşük 0)          (fayda)
    lojistik  bileşen teslim maliyeti [$/MW]                             (maliyet)
Hazır profiller AHP ikili karşılaştırma matrisi olarak (önem puanlarından A_ij = s_i/s_j; tam tutarlı, CR = 0).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

KRITERLER = {
    "ekonomi": ("Başabaş fiyat", "Break-even price", "basabas_en_iyi", False),
    "sebeke": ("Trafo merkezine uzaklık", "Distance to substation", "trafo_km", False),
    "yol": ("Ağır nakliye yoluna uzaklık", "Distance to heavy-haul road", "yol_km", False),
    "egim": ("Ortalama eğim", "Mean slope", "egim_ort", False),
    "goc": ("Göç koridoru riski", "Migration corridor risk", "goc_azami", False),
    "guven": ("Rüzgâr tahmini güveni", "Wind estimate confidence", "guven_puan", True),
    "lojistik": ("Lojistik maliyeti", "Logistics cost", "lojistik_usd_mw", False),
}
RUZGAR = ("RES kapasite faktörü", "Wind capacity factor", "res_kf", True)

PROFILLER = {
    "ekonomi": (
        "Ekonomi öncelikli",
        "Economy first",
        {"ekonomi": 9, "sebeke": 3, "yol": 2, "egim": 2, "goc": 1, "guven": 3, "lojistik": 3},
    ),
    "risk_cevre": (
        "Risk/çevre öncelikli",
        "Risk/environment first",
        {"ekonomi": 3, "sebeke": 2, "yol": 2, "egim": 5, "goc": 9, "guven": 6, "lojistik": 1},
    ),
    "dengeli": ("Dengeli", "Balanced", {"ekonomi": 6, "sebeke": 3, "yol": 2, "egim": 3, "goc": 4, "guven": 4, "lojistik": 2}),
}


def profil_matrisi(ad: str) -> np.ndarray:
    s = np.array([PROFILLER[ad][2][k] for k in KRITERLER], float)
    return s[:, None] / s[None, :]


@lru_cache(maxsize=1)
def tablo() -> pd.DataFrame:
    from src import veri_katmani

    ot = pd.read_parquet(veri_katmani.yol("atlas/on_tarama.parquet"))
    cb = pd.read_parquet(veri_katmani.yol("atlas/cbs_hucre.parquet"))
    d = ot.merge(cb, on=["hucre_enlem", "hucre_boylam"], how="left", suffixes=("", "_cbs"))
    d["guven_puan"] = (d["guven"] == "yüksek").astype(float)
    return d


def dislanan(d: pd.DataFrame, adalar_dahil: bool = False) -> pd.Series:
    """Dışlanma nedeni (boş = uygun)."""
    neden = pd.Series("", index=d.index)
    neden[d["hata"].fillna("") != ""] = "hesap hatası"
    neden[(neden == "") & (d["koruma_oran"].fillna(0) >= 0.5)] = "koruma alanı"
    neden[(neden == "") & (d["uygun_oran"].fillna(1) < 0.10)] = "uygun alan < %10"
    if not adalar_dahil:
        neden[(neden == "") & d["ada"].fillna(False)] = "ada"
    neden[(neden == "") & d["basabas_en_iyi"].isna()] = "başabaş hesaplanamadı"
    return neden


@lru_cache(maxsize=1)
def ayar() -> dict:
    from src.ayarlar import config_oku, deger

    return deger(config_oku()["v3"]["cok_kriterli"])


def vektor() -> bool:
    """TOPSIS'te klasik vektör normalizasyonu mu (True), değer fonksiyonu standardizasyonu mu (False)?"""
    return ayar()["normalizasyon"] == "vektor"


def matris(d: pd.DataFrame, kriterler: list[str], ruzgar: bool = False, standart: bool | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Karar matrisi. standart (varsayılan: config normalizasyon = deger_fonksiyonu): her kriter doğrusal değer
    fonksiyonuyla v = (x − kabul edilemez) / (en iyi − kabul edilemez), [0, 1]'e kırpılır; tüm sütunlar fayda olur."""
    standart = (not vektor()) if standart is None else standart
    kol, fay, uc = [], [], []
    for k in kriterler:
        rz = k == "ekonomi" and ruzgar
        a = RUZGAR if rz else KRITERLER[k]
        kol.append(a[2])
        fay.append(a[3])
        uc.append(ayar()["deger_fonksiyonu"]["ruzgar" if rz else k])
    X = d[kol].astype(float).to_numpy()
    X = np.where(np.isnan(X), np.nanmedian(X, axis=0), X)
    if standart:
        U = np.array(uc, float)
        V = np.clip((X - U[:, 1]) / (U[:, 0] - U[:, 1]), 0.0, 1.0)
        return V, np.ones(len(kriterler), bool)
    # TOPSIS vektör normalizasyonu sıfır içeren maliyet kriterlerinde (göç 0/1/2) çalışır; küçük kayma ile negatifsiz tutulur
    return X + 1e-9, np.array(fay, bool)
