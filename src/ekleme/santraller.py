"""
Mevcut RES listesi (v4 Faz I): atlasın kullanılabilir santralleri, performans izlemeyle aynı anonim kodlarla (S021 …).

Ad gösterilmez (config v3.performans.santral_adlari_goster ile aynı gerekçe): sonuçlar modelden türetilmiştir ve belirli bir şirketin
santrali hakkında doğrulanmamış finansal iddia üretir. Kod, il, kurulu güç, türbin vekili ve gözlenen KF gösterilir.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src import veri_katmani
from src.atlas.aktarim import KULLANILIR


@lru_cache(maxsize=1)
def liste() -> pd.DataFrame:
    """kod → il, enlem, boylam, kurulu_mw, turbin, gobek, gozlenen_kf, epias_id (yalnız kalibrasyon matrisi olan santraller)."""
    d = pd.read_csv(veri_katmani.yol("atlas/izleme/durum.csv"))[["epias_id", "kod", "il", "enlem", "boylam", "kapasite_mw"]]
    a = pd.read_csv(veri_katmani.yol("atlas/kalibrasyon_atlasi.csv"))
    a = a[a["sinif"].isin(KULLANILIR)][["epias_id", "gozlenen_kf", "kapasite_azami_mw"]]
    t = pd.read_csv(veri_katmani.yol("atlas/santral_turbinleri.csv"))[["epias_id", "turbin", "gobek"]]
    x = d.merge(a, on="epias_id").merge(t, on="epias_id")
    x["kurulu_mw"] = x["kapasite_mw"].fillna(x["kapasite_azami_mw"]).round(1)
    return x.drop(columns=["kapasite_mw", "kapasite_azami_mw"]).sort_values(["il", "kod"]).set_index("kod")


def bul(kod: str) -> pd.Series:
    x = liste()
    if kod not in x.index:
        raise KeyError(f"Santral kodu bulunamadı: {kod}")
    return x.loc[kod]
