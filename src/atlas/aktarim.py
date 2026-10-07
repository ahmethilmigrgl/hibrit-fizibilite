"""
Kalibrasyon aktarım kuralı (v2 A4): yeni bir sahada RES hız katsayısı matrisi nasıl seçilir?

Ayrıştırma: bir santralin k matrisi K_s = c_s · R_s
    c_s = GWA_s / ERA5_s        (GWA ortalama düzeltmesi: mikro ölçek arazi etkisi)
    R_s = K_s / c_s             (GWA'dan arta kalan sapma ve ay × saat şekli: meltem, kararlılık, vekil türbin farkı)
Yeni saha x için yöntemler:
    "dogrudan"   K_x = Σ w_i K_i                 (komşu santral matrislerinin ağırlıklı ortalaması)
    "gwa_olcekli" K_x = c_x · Σ w_i R_i          (komşuların şekli/artığı + sahanın kendi GWA düzeltmesi)  ← kural
    "gwa"        K_x = c_x (sabit)
    (komşu yoksa "gwa_olcekli": K_x = c_x · medyan R — ulusal medyan artık matrisi; GWA'nın sistematik düşük sapmasını ve
     ortalama gün içi şekli taşır)
    "yok"        K_x = 1
Ağırlık: ters mesafe karesi, en fazla 3 benzer santral (rakım, karmaşıklık, kıyı sınıfı; config v2.aktarim).
Güven seviyesi (Ö4): yüksek (en yakın benzer santral ≤ 15 km), orta (15–30 km), düşük (30 km içinde benzer santral yok →
GWA × ulusal medyan artık). 30–80 km'deki komşular çapraz doğrulamada bilgi katmadı.
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
    from src import veri_katmani

    df = pd.read_csv(veri_katmani.yol("atlas/kalibrasyon_atlasi.csv"))
    df = df[df["sinif"].isin(KULLANILIR)].reset_index(drop=True)
    z = np.load(veri_katmani.yol("atlas/kalibrasyon_matrisleri.npz"))
    mat = {int(k[2:]): z[k].astype(float) for k in z.files if k.startswith("k_")}
    return df, mat


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def gwa_hizi(enlem: float, boylam: float, mod: str, adet: int = 12, yaricap_km: float = 2.0, asgari_aralik_m: float = 500.0) -> float:
    """GWA 100 m hız: 'nokta1km' (Faz A), 'nokta250' (250 m hücre) ya da 'yerlesim' (yarıçapta en rüzgârlı hücreler)."""
    from src.kaynaklar import gwa250

    if mod == "nokta1km":
        return gwa.nokta(enlem, boylam)["ws_ort"]
    if mod == "nokta250":
        return gwa250.nokta(enlem, boylam)
    return gwa250.turbin_yerlesimi(enlem, boylam, yaricap_km, adet, asgari_aralik_m)["ortalama"]


@lru_cache(maxsize=1)
def santral_c() -> dict[int, float]:
    """
    Atlas santrallerinin GWA düzeltmesi c_i = GWA_i / ERA5_i. GWA_i santralin GERÇEK türbin konumlarındaki 250 m hücrelerin
    ortalamasıdır (OSM; konum yoksa 3 km yerleşim kuralı) ve sahanın GWA modundan bağımsızdır: santralin gözlenen
    performansı türbinlerinin durduğu yerin rüzgârını yansıtır. (Önceki sürümde santral c'si sahanın moduyla birlikte
    değişiyordu; bu, türbin yerleşimi seçeneğinin etkisini oranda yok ediyordu.)
    """
    df, _ = atlas()
    return {int(r.epias_id): float(np.clip(r.c_turbin, 0.5, 3.2)) for r in df.itertuples()}


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
    kb = a["kiyi_benzerlik"]
    if kb is True or kb == "sinif":  # ikili sınıf: kıyı < 20 km / iç
        benzer &= (d["kiyi_km"] < 20) == (tan["kiyi_km"] < 20)
    elif kb == "oran":  # sürekli: |ln((d1 + 10) / (d2 + 10))| ≤ eşik (20 km eşiğindeki kırılmayı önler)
        benzer &= np.abs(np.log((d["kiyi_km"] + 10) / (tan["kiyi_km"] + 10))) <= a.get("kiyi_oran_esik", 0.7)
    return d[benzer & (d["mesafe_km"] <= a["orta_km"])].sort_values("mesafe_km").head(a["azami_komsu"])


def tahmin(
    enlem: float,
    boylam: float,
    era5_v100: float,
    yontem: str = "gwa_olcekli",
    cfg: dict | None = None,
    haric: int | None = None,
    tan: dict | None = None,
    gwa_hiz: float | None = None,
    gmod: str | None = None,
) -> tuple[np.ndarray, dict]:
    """
    12 × 24 k matrisi ve açıklama (güven seviyesi, kullanılan santraller).
    gwa_hiz: sahanın GWA 100 m hızı (yerleşim ya da nokta); verilmezse gmod'a göre hesaplanır.
    gmod: yalnız sahanın GWA modu — 'nokta1km' / 'nokta250' / 'yerlesim' (santral c'leri her zaman türbin konumlarından).
    """
    cfg = cfg or config_oku()
    a = deger(cfg["v2"]["aktarim"])
    gmod = gmod or a["gwa_modu"]
    tan = tan or tanimlayicilar(enlem, boylam)
    if gwa_hiz is None:
        gwa_hiz = gwa_hizi(enlem, boylam, gmod, 16, 2.0, a["asgari_aralik_m"])
    c = float(np.clip(gwa_hiz / era5_v100, 0.5, 3.2))
    ci = santral_c()
    if yontem == "yok":
        return np.ones((12, 24)), {"yontem": yontem, "guven": "—"}
    if yontem == "gwa":
        return np.full((12, 24), c), {"yontem": yontem, "c": c, "guven": "düşük"}
    k = komsular(enlem, boylam, tan, cfg, haric)
    _, mat = atlas()
    if k.empty:
        guven = "düşük"
        if yontem == "gwa_olcekli":  # komşu yok: sahanın GWA düzeltmesi × ulusal medyan artık matrisi (sistematik sapma + ortalama şekil)
            return c * ulusal_artik(haric), {"yontem": "gwa × ulusal artık (komşu yok)", "c": c, "guven": guven, "komsu": []}
        return np.full((12, 24), c), {"yontem": "gwa (komşu yok)", "c": c, "guven": guven, "komsu": []}
    w = 1.0 / np.maximum(k["mesafe_km"].to_numpy(), 1.0) ** a["idw_us"]
    w = w / w.sum()
    if yontem == "dogrudan":
        K = sum(wi * mat[int(i)] for wi, i in zip(w, k["epias_id"]))
    else:  # gwa_olcekli
        R = sum(wi * mat[int(i)] / ci[int(i)] for wi, i in zip(w, k["epias_id"]))
        R = r_duzelt(R, len(k), a, haric)
        K = c * R
    gv = deger(cfg["v2"]["guven"])
    guven = "yüksek" if k["mesafe_km"].iloc[0] <= gv["yuksek_km"] else "orta"
    return K, {"yontem": yontem, "c": c, "guven": guven, "komsu": k["ad"].tolist(), "mesafe_km": k["mesafe_km"].round(1).tolist()}


def r_duzelt(R: np.ndarray, n: int, a: dict, haric: int | None = None) -> np.ndarray:
    """
    Komşu artığının büzülmesi ve sınırı (Revizyon R2):
      büzülme: R ← (n·R + n0·R_ulusal) / (n + n0)  (n = komşu sayısı; tek komşulu tahminler ulusal medyana çekilir)
      sınır:   R matrisinin ortalaması [alt, üst] dışına çıkarsa matris orantılı ölçeklenir
    """
    n0 = float(a.get("r_buzulme_n0", 0) or 0)
    if n0 > 0:
        R = (n * R + n0 * ulusal_artik(haric)) / (n + n0)
    sinir = a.get("r_sinir")
    if sinir:
        m = float(R.mean())
        R = R * float(np.clip(m, sinir[0], sinir[1])) / m
    return R


@lru_cache(maxsize=256)
def ulusal_artik(haric: int | None = None) -> np.ndarray:
    """Atlastaki tüm kullanılabilir santrallerin GWA sonrası artık matrislerinin (R = K / c) hücre bazında medyanı."""
    df, mat = atlas()
    ci = santral_c()
    d = df if haric is None else df[df["epias_id"] != haric]
    return np.median([mat[int(i)] / ci[int(i)] for i in d["epias_id"]], axis=0)


def aktarim_matrisi(saha, era5_v100: float, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """genel.profil_uret için: atlas kuralıyla 12 × 24 matris (DataFrame) ve açıklama (sahanın türbin yerleşimi seçeneğiyle)."""
    from src.saha import gwa_hizi as saha_gwa

    g = saha_gwa(saha, cfg)
    gmod = "yerlesim" if g["yerlesim"] else "nokta250"
    K, bilgi = tahmin(saha.enlem, saha.boylam, era5_v100, "gwa_olcekli", cfg, gwa_hiz=g["hiz"], gmod=gmod)
    bilgi.update({"mod": "atlas", "gwa_hiz": g["hiz"], "turbin_yerlesimi": g["yerlesim"]})
    return pd.DataFrame(K, index=range(1, 13), columns=range(24)), bilgi
