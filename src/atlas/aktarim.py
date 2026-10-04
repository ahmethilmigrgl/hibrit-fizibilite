"""
Kalibrasyon aktarım kuralı (v2 A4): yeni bir sahada RES hız katsayısı matrisi nasıl seçilir?

Ayrıştırma: bir santralin k matrisi K_s = c_s · R_s
    c_s = GWA_s / ERA5_s        (GWA ortalama düzeltmesi: mikro ölçek arazi etkisi)
    R_s = K_s / c_s             (GWA'dan arta kalan sapma ve ay × saat şekli: meltem, kararlılık, vekil türbin farkı)
Yeni saha x için yöntemler:
    "dogrudan"   K_x = Σ w_i K_i                 (komşu santral matrislerinin ağırlıklı ortalaması)
    "gwa_olcekli" K_x = c_x · Σ w_i R_i          (komşuların şekli/artığı + sahanın kendi GWA düzeltmesi)  ← kural
    "gwa"        K_x = c_x (sabit)
    "yok"        K_x = 1
Ağırlık: ters mesafe karesi, en fazla 3 benzer santral (rakım, karmaşıklık, kıyı sınıfı; config v2.aktarim).
Güven seviyesi: yüksek (benzer santral ≤ 30 km), orta (≤ 80 km), düşük (benzer santral yok → yalnız GWA).
Tipik hatalar (KF puanı) A4 çapraz doğrulamasından: data/atlas/guven_seviyeleri.csv.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku, deger
from src.kaynaklar import arazi, gwa

ATLAS = KOK / "data" / "atlas"
KULLANILIR = ("temiz", "kullanilabilir")


@lru_cache(maxsize=1)
def atlas() -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(ATLAS / "kalibrasyon_atlasi.csv")
    df = df[df["sinif"].isin(KULLANILIR)].reset_index(drop=True)
    z = np.load(ATLAS / "kalibrasyon_matrisleri.npz")
    mat = {int(k[2:]): z[k].astype(float) for k in z.files if k.startswith("k_")}
    return df, mat


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def tanimlayicilar(enlem: float, boylam: float) -> dict:
    return {
        "rakim_m": arazi.rakim([(enlem, boylam)])[0],
        "karmasiklik": arazi.karmasiklik(enlem, boylam),
        "kiyi_km": arazi.kiyi_km(enlem, boylam),
    }


def komsular(enlem: float, boylam: float, tan: dict, cfg: dict, haric: int | None = None) -> pd.DataFrame:
    """Benzer santraller (mesafeye göre sıralı), 'haric' epias_id dışarıda bırakılır (çapraz doğrulama)."""
    a = deger(cfg["v2"]["aktarim"])
    df, _ = atlas()
    d = df if haric is None else df[df["epias_id"] != haric]
    d = d.assign(mesafe_km=_km(enlem, boylam, d["enlem"].to_numpy(), d["boylam"].to_numpy()))
    benzer = ((d["rakim_m"] - tan["rakim_m"]).abs() <= a["rakim_farki_m"]) & (
        (d["karmasiklik"] - tan["karmasiklik"]).abs() <= a["karmasiklik_farki"]
    )
    if a["kiyi_benzerlik"]:
        benzer &= (d["kiyi_km"] < 20) == (tan["kiyi_km"] < 20)
    return d[benzer & (d["mesafe_km"] <= a["orta_km"])].sort_values("mesafe_km").head(a["azami_komsu"])


def tahmin(
    enlem: float,
    boylam: float,
    era5_v100: float,
    yontem: str = "gwa_olcekli",
    cfg: dict | None = None,
    haric: int | None = None,
    tan: dict | None = None,
) -> tuple[np.ndarray, dict]:
    """12 × 24 k matrisi ve açıklama (güven seviyesi, kullanılan santraller)."""
    cfg = cfg or config_oku()
    a = deger(cfg["v2"]["aktarim"])
    tan = tan or tanimlayicilar(enlem, boylam)
    c = gwa.duzeltme_katsayisi(enlem, boylam, era5_v100)
    if yontem == "yok":
        return np.ones((12, 24)), {"yontem": yontem, "guven": "—"}
    if yontem == "gwa":
        return np.full((12, 24), c), {"yontem": yontem, "c": c, "guven": "düşük"}
    k = komsular(enlem, boylam, tan, cfg, haric)
    if k.empty:
        return np.full((12, 24), c), {"yontem": "gwa (komşu yok)", "c": c, "guven": "düşük", "komsu": []}
    _, mat = atlas()
    w = 1.0 / np.maximum(k["mesafe_km"].to_numpy(), 1.0) ** a["idw_us"]
    w = w / w.sum()
    if yontem == "dogrudan":
        K = sum(wi * mat[int(i)] for wi, i in zip(w, k["epias_id"]))
    else:  # gwa_olcekli
        R = sum(wi * mat[int(i)] / float(np.clip(r.gwa_era5_orani, 0.6, 1.8)) for wi, i, r in zip(w, k["epias_id"], k.itertuples()))
        K = c * R
    guven = "yüksek" if k["mesafe_km"].iloc[0] <= a["yakin_km"] else "orta"
    return K, {"yontem": yontem, "c": c, "guven": guven, "komsu": k["ad"].tolist(), "mesafe_km": k["mesafe_km"].round(1).tolist()}


def aktarim_matrisi(saha, era5_v100: float, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """genel.profil_uret için: atlas kuralıyla 12 × 24 matris (DataFrame) ve açıklama."""
    K, bilgi = tahmin(saha.enlem, saha.boylam, era5_v100, "gwa_olcekli", cfg)
    bilgi["mod"] = "atlas"
    return pd.DataFrame(K, index=range(1, 13), columns=range(24)), bilgi
