"""
ERA5 rüzgâr modelinin gözlenen santral üretimiyle kalibrasyonu: sabit k ve ay × saat k matrisi.

Kalibrasyon katsayısı rüzgâr HIZINI ölçekler (kapasite faktörünü değil): güç eğrisi doğrusal
olmadığı için yalnızca hız katsayısı başka bir türbine/göbek yüksekliğine taşınabilir.

    Sabit k     : tek katsayı; modellenen ortalama KF = gözlenen ortalama KF
    Ay × saat k : 12 × 24 matris; her (ay, TSİ saati) hücresinde modellenen ortalama KF = gözlenen.
                  Komşu ay ve saatler arasında dairesel 3 × 3 çekirdekle yumuşatılır, sonra
                  toplam ortalama yeniden eşlenir (tek bir ölçek çarpanıyla).

Gözlenen ve model aynı zaman tanımında olmalıdır: [t, t+1) UTC saat aralığı ortalaması.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from windpowerlib.power_output import power_curve_density_correction

from src.ayarlar import deger
from src.uretim import ruzgar

K_ALT, K_UST = 0.5, 2.0
YUMUSATMA_CEKIRDEGI = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=float) / 16


@dataclass
class ReferansModel:
    """Referans santralin hız/yoğunluk serileri ve güç eğrisi; k verildiğinde KF üretir."""
    v: np.ndarray          # göbek yüksekliği hızı (kalibrasyonsuz, aralık ortalaması) [m/s]
    rho: np.ndarray        # hava yoğunluğu [kg/m³]
    ay: np.ndarray         # TSİ ayı (1-12)
    saat: np.ndarray       # TSİ saati (0-23)
    indeks: pd.DatetimeIndex
    egri_hiz: np.ndarray
    egri_guc: np.ndarray
    nominal: float
    kayip: float

    def kf(self, k: float | np.ndarray, secim: np.ndarray | None = None) -> np.ndarray:
        """k skaler ya da her saat için dizi olabilir. secim: boolean maske (alt küme)."""
        v, rho = (self.v, self.rho) if secim is None else (self.v[secim], self.rho[secim])
        kk = k if np.isscalar(k) else (k if secim is None else k[secim])
        guc = power_curve_density_correction(v * kk, self.egri_hiz, self.egri_guc, rho)
        return np.clip(np.asarray(guc) / self.nominal * (1 - self.kayip), 0, 1)

    def kf_matris(self, matris: np.ndarray) -> np.ndarray:
        return self.kf(matris[self.ay - 1, self.saat])


def referans_model(era5: pd.DataFrame, cfg_ruzgar: dict, turbin_modeli: str, gobek: float) -> ReferansModel:
    """Referans santrali vekil türbin ve göbek yüksekliğiyle, aralık ortalaması zaman tanımında hazırlar."""
    _, ara = ruzgar.ruzgar_kapasite_faktoru(era5, cfg_ruzgar, turbin_modeli=turbin_modeli, gobek=gobek,
                                            katsayi=1.0, zaman_hizasi="aralik")
    t = ruzgar.turbin(turbin_modeli, cfg_ruzgar, gobek)
    ay, saat = ruzgar.tsi_ay_saat(ara.index)
    return ReferansModel(v=ara["v_gobek"].to_numpy(), rho=ara["yogunluk"].to_numpy(), ay=ay, saat=saat,
                         indeks=ara.index, egri_hiz=t.power_curve["wind_speed"].to_numpy(),
                         egri_guc=t.power_curve["value"].to_numpy(), nominal=t.nominal_power,
                         kayip=deger(cfg_ruzgar["toplam_kayip"]))


def sabit_k(model: ReferansModel, gozlenen: np.ndarray, maske: np.ndarray) -> float:
    """Maske içindeki saatlerde ortalama KF'yi eşleyen tek katsayı."""
    hedef = np.nanmean(gozlenen[maske])
    return brentq(lambda k: model.kf(k, maske).mean() - hedef, K_ALT, K_UST, xtol=1e-4)


def _hucre_k(model: ReferansModel, hedef: float, secim: np.ndarray) -> float:
    f = lambda k: model.kf(k, secim).mean() - hedef
    alt, ust = f(K_ALT), f(K_UST)
    if alt > 0:
        return K_ALT
    if ust < 0:
        return K_UST
    return brentq(f, K_ALT, K_UST, xtol=1e-4)


def yumusat(matris: np.ndarray) -> np.ndarray:
    """Dairesel (Aralık↔Ocak, 23↔00) 3 × 3 ağırlıklı ortalama."""
    sonuc = np.zeros_like(matris)
    for i, di in enumerate((-1, 0, 1)):
        for j, dj in enumerate((-1, 0, 1)):
            sonuc += YUMUSATMA_CEKIRDEGI[i, j] * np.roll(np.roll(matris, di, axis=0), dj, axis=1)
    return sonuc


def k_matrisi(model: ReferansModel, gozlenen: np.ndarray, maske: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ay × saat (TSİ) hız katsayısı matrisi.
    Döndürür: (ham matris, yumuşatılmış ve toplam ortalaması yeniden eşlenmiş matris)
    """
    ham = np.full((12, 24), np.nan)
    for a in range(1, 13):
        for h in range(24):
            secim = maske & (model.ay == a) & (model.saat == h)
            if secim.sum() < 30:
                continue
            ham[a - 1, h] = _hucre_k(model, np.nanmean(gozlenen[secim]), secim)
    # Eksik hücreler (çok az gözlem) → satır ortalaması
    ham = np.where(np.isnan(ham), np.nanmean(ham, axis=1, keepdims=True), ham)
    yumusak = yumusat(ham)
    # Yumuşatma toplam ortalamayı biraz kaydırır → tek ölçek çarpanıyla yeniden eşle
    hedef = np.nanmean(gozlenen[maske])
    olcek = brentq(lambda c: model.kf(c * yumusak[model.ay - 1, model.saat], maske).mean() - hedef,
                   0.8, 1.25, xtol=1e-5)
    yumusak = yumusak * olcek
    kolonlar = pd.Index(range(24), name="tsi_saat")
    satirlar = pd.Index(range(1, 13), name="ay")
    return pd.DataFrame(ham, satirlar, kolonlar), pd.DataFrame(yumusak, satirlar, kolonlar)


def metrikler(model: ReferansModel, gozlenen: np.ndarray, model_kf: np.ndarray, maske: np.ndarray) -> dict:
    """Saatlik korelasyon, ay × saat RMSE, gün içi profil RMSE, yıllık KF hatası (KF puanı)."""
    g, m = gozlenen[maske], model_kf[maske]
    ay, saat = model.ay[maske], model.saat[maske]
    yil = (model.indeks[maske] + pd.Timedelta(hours=3)).year
    df = pd.DataFrame({"g": g, "m": m, "ay": ay, "saat": saat, "yil": yil})
    ays = df.groupby(["ay", "saat"])[["g", "m"]].mean()
    gun = df.groupby("saat")[["g", "m"]].mean()
    yillik = df.groupby("yil")[["g", "m"]].mean()
    return {
        "Saatlik korelasyon": float(np.corrcoef(g, m)[0, 1]),
        "Ay×saat RMSE [KF puanı]": float(100 * np.sqrt(((ays.g - ays.m) ** 2).mean())),
        "Gün içi profil RMSE [KF puanı]": float(100 * np.sqrt(((gun.g - gun.m) ** 2).mean())),
        "Yıllık KF ort. mutlak hata [puan]": float(100 * (yillik.g - yillik.m).abs().mean()),
        "Ortalama KF hatası [puan]": float(100 * (m.mean() - g.mean())),
    }
