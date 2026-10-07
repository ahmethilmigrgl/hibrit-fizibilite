"""
Arayüz ↔ motor/veri katmanı köprüsü. Streamlit önbellekli okuyucular ve seçilen nokta için anlık bilgiler.
Bütün dosya okumaları src/veri_katmani üzerinden (doğrudan yol yok).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import streamlit as st

from src import veri_katmani
from src.ayarlar import config_oku, deger


@st.cache_data(show_spinner=False)
def on_tarama() -> pd.DataFrame | None:
    p = veri_katmani.yol("atlas/on_tarama.parquet", zorunlu=False)
    if p is None:
        return None
    d = pd.read_parquet(p)
    return d[d["hata"] == ""].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def santraller() -> pd.DataFrame:
    from src.atlas import aktarim

    df, _ = aktarim.atlas()
    return df[["epias_id", "ad", "enlem", "boylam", "osm_mw", "turbin", "gobek", "gozlenen_kf", "sinif"]].copy()


@st.cache_data(show_spinner=False)
def il_ilce() -> pd.DataFrame:
    from src.kaynaklar import sinirlar

    return pd.DataFrame(sinirlar.ilceler(), columns=["il", "ilce"])


def _km(e1, b1, e2, b2):
    return 6371 * np.hypot(np.radians(e2 - e1), np.radians(b2 - b1) * np.cos(np.radians((e1 + e2) / 2)))


@st.cache_data(show_spinner=False)
def adaylar(il: str, ilce: str) -> pd.DataFrame:
    """İlçe içindeki en rüzgârlı GWA (1 km) noktaları; aralarında en az aday_aralik_km (açgözlü seçim)."""
    from src.kaynaklar import gwa, sinirlar

    a = deger(config_oku()["v2"]["uygulama"])
    p = sinirlar._yukle()
    maske = sinirlar.ilce_maskesi(il, ilce)
    g = gwa._yukle()
    # sınır ızgarası (0,01°) ile GWA 1 km ızgarası farklı; ilçe maskesini GWA ızgarasına en yakın komşuyla taşı
    n, m = g["ws_ort"].shape
    enl = g["ust"] - (np.arange(n) + 0.5) * g["adim"]
    boy = g["sol"] + (np.arange(m) + 0.5) * g["adim"]
    ii = np.clip(((p["ust"] - enl) / p["adim"]).astype(int), 0, maske.shape[0] - 1)
    jj = np.clip(((boy - p["sol"]) / p["adim"]).astype(int), 0, maske.shape[1] - 1)
    gm = maske[np.ix_(ii, jj)]
    havuz = gwa.aday_noktalar(gm, g["sol"], g["ust"], g["adim"], adet=400)
    secilen: list[tuple[float, float, float]] = []
    for e, b, v in havuz:
        if v <= 0:
            break
        if all(_km(e, b, x[0], x[1]) >= a["aday_aralik_km"] for x in secilen):
            secilen.append((e, b, v))
        if len(secilen) >= a["aday_sayisi"]:
            break
    return pd.DataFrame(secilen, columns=["enlem", "boylam", "gwa_1km"])


def nokta_bilgisi(enlem: float, boylam: float, yerlesim: bool = True, yaricap_km: float = 2.0, baglanti_mw: float = 50.0) -> dict:
    """Seçilen noktada anlık bilgiler (analiz çalıştırmadan): il/ilçe, GWA, güven seviyesi ve komşu santraller, ön tarama hücresi."""
    from src.atlas import aktarim
    from src.kaynaklar import sinirlar
    from src.motor.varsayimlar import MotorHatasi
    from src.saha import gwa_hizi, saha_olustur

    k = sinirlar.konum(enlem, boylam)
    if k is None:
        raise MotorHatasi(
            "kara_disi",
            "Seçilen nokta Türkiye karası dışında (deniz ya da komşu ülke). Lütfen kara üzerinde bir nokta seçin.",
            "The selected point is outside Türkiye's land area (sea or a neighbouring country). Please pick a point on land.",
        )
    cfg = config_oku()
    s = replace(saha_olustur("secim", enlem, boylam), turbin_yerlesimi=yerlesim, yerlesim_yaricap_km=yaricap_km, baglanti_mw=baglanti_mw)
    g = gwa_hizi(s, cfg)
    tan = aktarim.tanimlayicilar(enlem, boylam)
    kom = aktarim.komsular(enlem, boylam, tan, cfg)
    gv = deger(cfg["v2"]["guven"])
    seviye = "yüksek" if len(kom) and float(kom["mesafe_km"].iloc[0]) <= gv["yuksek_km"] else "düşük"
    gs = pd.read_csv(veri_katmani.yol("atlas/guven_seviyeleri.csv"), index_col=0)
    sat = gs.loc[seviye]
    hucre = None
    ot = on_tarama()
    if ot is not None:
        from src.kaynaklar.era5_grid import hucre as hc

        he, hb = hc(enlem, boylam)
        r = ot[(ot["hucre_enlem"] == he) & (ot["hucre_boylam"] == hb)]
        if len(r):
            hucre = r.iloc[0].to_dict()
            hucre["yuzdelik"] = yuzdelik(hucre["basabas_en_iyi"])  # adasız hücrelerin şu kadarından daha cazip
    from src.kaynaklar.adalar import ada_bilgisi

    return {
        "ada": ada_bilgisi(enlem, boylam),
        "il": k["il"],
        "ilce": k["ilce"],
        "gwa_nokta": float(g["nokta"]),
        "gwa_saha": float(g["hiz"]),
        "yerlesim": bool(g["yerlesim"]),
        "konumlar": g.get("konumlar", []),
        "rakim_m": tan["rakim_m"],
        "guven": seviye,
        "guven_medyan": float(sat["mutlak_medyan"]),
        "guven_p90": float(sat["mutlak_p90"]),
        "komsular": kom[["ad", "mesafe_km"]].head(3).to_dict("records") if len(kom) else [],
        "tek_komsu": len(kom) == 1,
        "hucre": hucre,
    }


def yuzdelik(basabas: float, adalar: bool = False) -> float | None:
    """Başabaş fiyatı Türkiye kara hücrelerinin yüzde kaçından düşük (yüksek = daha cazip); adalar varsayılan olarak hariç."""
    ot = on_tarama()
    if ot is None or basabas is None or not np.isfinite(basabas):
        return None
    if not adalar and "ada" in ot:
        ot = ot[~ot["ada"]]
    return float((ot["basabas_en_iyi"] > basabas).mean() * 100)


def ilk_n(n: int = 10, adalar: bool = False) -> pd.DataFrame | None:
    """Başabaş fiyatı en düşük n hücre (adalar varsayılan olarak hariç)."""
    ot = on_tarama()
    if ot is None:
        return None
    if not adalar and "ada" in ot:
        ot = ot[~ot["ada"]]
    return ot.nsmallest(n, "basabas_en_iyi")
