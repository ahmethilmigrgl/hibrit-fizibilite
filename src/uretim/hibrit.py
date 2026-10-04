"""
Basit hibrit göstergeleri: GES ve RES aynı şebeke bağlantısını paylaşırsa ne olur?

Burada optimizasyon yok; sabit kapasitelerle (ör. 1 MW GES + 1 MW RES, 1 MW bağlantı)
saatlik "satılan = min(üretim, bağlantı)" ve "kesilen = üretim − satılan" hesaplanır.
"""

from __future__ import annotations

import pandas as pd


def ortak_baglanti(ges_kf: pd.Series, res_kf: pd.Series, ges_mw: float = 1.0, res_mw: float = 1.0, baglanti_mw: float = 1.0) -> dict:
    """
    Saatlik kapasite faktörlerinden ortak bağlantı göstergeleri (yıllık ortalama).

    Döndürür:
        uretim_mwh_yil   — kesinti öncesi toplam üretim
        satilan_mwh_yil  — şebekeye verilebilen enerji
        kesinti_orani    — kesilen / toplam üretim
        baglanti_kf      — satılan / (bağlantı × saat): bağlantının ne kadar dolu kullanıldığı
    """
    df = pd.concat([ges_kf.rename("ges"), res_kf.rename("res")], axis=1, join="inner").dropna()
    uretim = ges_mw * df["ges"] + res_mw * df["res"]  # MW (saatlik ortalama → MWh)
    satilan = uretim.clip(upper=baglanti_mw)
    yil_sayisi = len(df) / 8766  # ortalama yıl uzunluğu (saat)
    return {
        "uretim_mwh_yil": uretim.sum() / yil_sayisi,
        "satilan_mwh_yil": satilan.sum() / yil_sayisi,
        "kesinti_orani": 1 - satilan.sum() / uretim.sum(),
        "baglanti_kf": satilan.mean() / baglanti_mw,
    }
