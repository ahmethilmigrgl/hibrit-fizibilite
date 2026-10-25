"""
Merit order kalibrasyon verisi: EPİAŞ saatlik kaynak bazında üretim + PTF (data/processed, çevrimdışı) → model girdileri.

Toplam güneş: EPİAŞ yalnız lisanslı güneşi görür. Lisanslı profil × (TEİAŞ toplam kurulu güneş / etkin lisanslı kurulu); etkin
lisanslı kurulu = yılın azami lisanslı saatlik üretimi / gunes_tepe_kf. Toplam talep D = EPİAŞ toplam üretimi + lisanssız güneş.
Böylece D − rüzgâr − güneş(toplam) = EPİAŞ toplamı − rüzgâr − lisanslı güneş (kalibrasyonda aynı termik artık yük).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ayarlar import ISLENMIS_VERI, config_oku, deger

KOLON = {
    "ruzgar": "W",
    "akarsu": "R",
    "jeotermal": "J",
    "biyokutle": "Bk",
    "barajli": "H",
    "linyit": "Lg",
    "ithal_komur": "Cg",
    "dogalgaz": "Gg",
}


def _kurulu_ortalama(cfg: dict, tek: str, yillar: np.ndarray) -> np.ndarray:
    """Yıl sonu kurulu güçlerin (MW) yıl içi ortalaması ((önceki yıl sonu + yıl sonu) / 2)."""
    k = {int(a): float(b) for a, b in cfg["kurulu_guc_turkiye"][tek].items()}
    son = max(k)
    f = lambda y: k.get(int(y), k[son])
    return np.array([(f(y - 1) + f(y)) / 2 for y in yillar])


def tarihsel(y1: int = 2018, y2: int = 2025) -> pd.DataFrame:
    cfg = config_oku()
    m = deger(cfg["v4"]["merit"])
    u = pd.read_parquet(ISLENMIS_VERI / "uretim_turkiye_2014_guncel.parquet")
    p = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")[["ptf_usd"]]
    d = u.join(p, how="inner").loc[f"{y1}" : f"{y2}"].copy()
    d = d.rename(columns=KOLON)
    yil = d.index.year.to_numpy()
    uy = np.unique(yil)
    lis_azami = d.groupby(yil)["gunes"].max()
    etkin = (lis_azami / m["gunes_tepe_kf"]).reindex(uy).to_numpy()
    toplam_kurulu = _kurulu_ortalama(cfg, "gunes", uy)
    olcek = pd.Series(np.maximum(toplam_kurulu / np.maximum(etkin, 1.0), 1.0), index=uy)
    d["S"] = d["gunes"] * olcek.reindex(yil).to_numpy()
    d["D"] = d["toplam"] + d["S"] - d["gunes"]
    d["P"] = d["ptf_usd"]
    d["RL"] = d["D"] - d["W"] - d["S"] - d["R"] - d["J"] - d["Bk"] - d["H"]
    q = m["kapasite_yuzdeligi"]
    kap = d.groupby(yil)[["Lg", "Cg", "Gg", "H"]].quantile(q)
    for c, a in (("Lg", "K_L"), ("Cg", "K_C"), ("Gg", "K_G"), ("H", "K_H")):
        d[a] = kap[c].reindex(yil).to_numpy()
    d["gunes_olcek"] = olcek.reindex(yil).to_numpy()
    d["K_S"] = pd.Series(toplam_kurulu, index=uy).reindex(yil).to_numpy()
    d["K_W"] = pd.Series(_kurulu_ortalama(cfg, "ruzgar", uy), index=uy).reindex(yil).to_numpy()
    d["ay"] = d.index.to_period("M").astype(str)
    d["yil"] = yil
    return d.drop(columns=["toplam", "gunes", "dolduruldu", "ptf_usd"], errors="ignore")


def yakalanma(p: np.ndarray, g: np.ndarray) -> float:
    """Üretim ağırlıklı fiyat / ortalama fiyat."""
    return float((p * g).sum() / max(g.sum(), 1e-9) / max(p.mean(), 1e-9))
