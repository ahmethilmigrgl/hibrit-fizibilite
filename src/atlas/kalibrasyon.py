"""
Tek santral kalibrasyonu (v1 Ezine yöntemi, ortak vekil türbinle):
    gözlenen KF: EPİAŞ gerçek zamanlı üretim / yıllık kapasite (yıllık %99,9 yüzdelik; kapasite artırımı geçiş yılları ve
                 ≥48 saatlik duruşlar hariç) — v1 degisken_kapasiteli_kf
    model: ERA5 (santral hücresi) → göbek hızı (vekil E-92/2350, 80 m; v1 ile aynı) → güç eğrisi (yoğunluk düzeltmeli)
    k: sabit hız katsayısı; ay × saat (TSİ) matrisi (yumuşatılmış, ortalamaya yeniden eşlenmiş)
Ortak vekil türbin, k değerlerini santraller arasında karşılaştırılabilir kılar: k, ERA5'in o noktadaki hız sapmasını
ve gerçek türbin/göbek ile vekil arasındaki farkı birlikte taşır (sınırlama; docs/v2_A_veri_altyapisi.md).

Kalite bayrakları:
    veri_yili         — geçerli saat / 8760
    korelasyon        — saatlik (k matrisiyle)
    kapasite_orani    — EPİAŞ en yüksek yıllık kapasite / OSM kurulu güç (eşleşme ve kapasite tutarlılığı)
    kapasite_dusus_yili — kapasitenin en yüksek değerin yarısının altına düştüğü yıl sayısı (veri kopukluğu, kimlik değişimi)
    kapasite_degisimi — %8'den büyük yıllık kapasite değişimi sayısı (artırım)
    talimat_suphesi   — model KF > 0,5 iken gözlenen < 0,1 × model olan saatlerin payı (YAT/kesinti ya da arıza)
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.ayarlar import KOK
from src.uretim import kalibrasyon as kal

VEKIL_TURBIN, VEKIL_GOBEK = "E-92/2350", 80


def _v1_kalibrasyon_modulu():
    spec = importlib.util.spec_from_file_location("v1kal", KOK / "src" / "02_ruzgar_kalibrasyonu.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V1 = _v1_kalibrasyon_modulu()
ARALIK = (
    0.4,
    3.5,
)  # Türkiye geneli: iç/dağlık kesimde ERA5 hücre ortalaması santral noktasındaki hızın üçte birine kadar düşebilir (GWA/ERA5 ≤ 3)


@contextmanager
def _aralik(alt: float, ust: float):
    """v1 arama aralığını yalnız atlas kalibrasyonu süresince değiştirir (v1 kodu etkilenmez)."""
    eski = (kal.K_ALT, kal.K_UST)
    kal.K_ALT, kal.K_UST = alt, ust
    try:
        yield
    finally:
        kal.K_ALT, kal.K_UST = eski


class KSinirDisi(ValueError):
    """Gözlenen KF'yi eşleyen k, kalibrasyon arama aralığının (v1 K_ALT–K_UST) dışında."""


@dataclass
class SantralKalibrasyonu:
    ozet: dict
    matris: np.ndarray  # 12 × 24 yumuşatılmış hız katsayısı
    gozlenen_ay_saat: np.ndarray  # 12 × 24 gözlenen ortalama KF (çapraz doğrulama için; türetilmiş)
    yillik: pd.DataFrame


def supheli_saatler(m, g: np.ndarray, gecerli: np.ndarray, k: float) -> np.ndarray:
    """Talimat (YAT/kesinti) ya da arıza şüphesi: model KF > 0,5 iken gözlenen < 0,1 × model."""
    model_k = m.kf(k)
    return gecerli & (model_k > 0.5) & (g < 0.1 * model_k)


def kalibre_et(
    uretim_mw: pd.Series,
    era5: pd.DataFrame,
    cfg_ruzgar: dict,
    osm_mw: float | None,
    turbin: str = VEKIL_TURBIN,
    gobek: float = VEKIL_GOBEK,
    supheli_haric: bool = True,
) -> SantralKalibrasyonu | None:
    """
    turbin/gobek: santralin kendi türbin vekili (src/atlas/turbinler.py). supheli_haric: talimat/arıza şüpheli saatler k
    uydurmasından çıkarılır (iki geçiş: önce tüm saatlerle k, şüpheliler işaretlenir, sonra onlarsız yeniden). Böylece
    sistem kaynaklı kesinti ve uzun arızalar k'ya "düşük rüzgâr" olarak girip yeni sahaya taşınmaz (kesinti finans
    modelinde ayrıca uygulanır).
    """
    mw = uretim_mw.loc[:"2025-12-31 23:00"].astype(float)
    if mw.max() <= 0:
        return None
    kf_g = V1.degisken_kapasiteli_kf(mw)
    m = kal.referans_model(era5, cfg_ruzgar, turbin, gobek)
    g = kf_g.reindex(m.indeks).clip(upper=1.05).to_numpy()
    gecerli = ~np.isnan(g)
    if gecerli.sum() < 2 * 8760 or np.nanmean(g) < 0.05:
        return None
    try:
        with _aralik(*ARALIK):
            k = kal.sabit_k(m, g, gecerli)
            if supheli_haric:
                gecerli = gecerli & ~supheli_saatler(m, g, gecerli, k)
                k = kal.sabit_k(m, g, gecerli)
        # Ay × saat hücreleri santralin kendi k'sine göre görece aralıkta (v1 Ezine: 0,5–2,0 ≈ 0,47k–1,87k): zayıf rüzgârlı
        # hücrelerde güç eğrisi düz olduğundan mutlak geniş aralık hücre katsayısını sınıra kaçırır
        with _aralik(0.5 * k, 1.8 * k):
            _, yum = kal.k_matrisi(m, g, gecerli)
    except ValueError as ex:  # k arama aralığı dışında: çoğunlukla yanlış eşleşme, kapasite ya da veri sorunu
        raise KSinirDisi(f"gözlenen KF {np.nanmean(g):.3f}") from ex
    km = yum.to_numpy()
    kf_m = m.kf_matris(km)
    met = kal.metrikler(m, g, kf_m, gecerli)
    met_sabit = kal.metrikler(m, g, m.kf(k), gecerli)
    yil = (m.indeks + pd.Timedelta(hours=3)).year
    kap_yil = mw.groupby(mw.index.tz_convert("Europe/Istanbul").year).quantile(0.999)
    kap_yil = kap_yil[kap_yil > 1]
    supheli = supheli_saatler(m, g, ~np.isnan(g), k)
    gay = pd.DataFrame({"g": g, "ay": m.ay, "saat": m.saat})[gecerli].groupby(["ay", "saat"])["g"].mean()
    gozlenen = gay.reindex(pd.MultiIndex.from_product([range(1, 13), range(24)])).to_numpy().reshape(12, 24)
    ozet = {
        "k_sabit": k,
        "k_matris_ort": float(km.mean()),
        "k_gunici_genlik": float(km.mean(0).max() - km.mean(0).min()),
        "gozlenen_kf": float(np.nanmean(g[gecerli])),  # şüpheli (talimat/arıza) saatler hariç
        "gozlenen_kf_tum": float(np.nanmean(g)),
        "veri_yili": float(gecerli.sum() / 8760),
        "ilk_yil": int(yil[gecerli].min()),
        "son_yil": int(yil[gecerli].max()),
        "korelasyon": met["Saatlik korelasyon"],
        "korelasyon_sabit_k": met_sabit["Saatlik korelasyon"],
        "gunici_rmse_puan": met["Gün içi profil RMSE [KF puanı]"],
        "gunici_rmse_sabit_k_puan": met_sabit["Gün içi profil RMSE [KF puanı]"],
        "kapasite_azami_mw": float(kap_yil.max()) if len(kap_yil) else np.nan,
        "kapasite_orani": float(kap_yil.max() / osm_mw) if (osm_mw and len(kap_yil)) else np.nan,
        "kapasite_degisimi": int((kap_yil.pct_change().abs() > 0.08).sum()),
        "kapasite_dusus_yili": int((kap_yil < 0.5 * kap_yil.max()).sum()),
        "talimat_suphesi": float(supheli.sum() / (~np.isnan(g)).sum()),
        "turbin": turbin,
        "gobek": gobek,
    }
    yillik = pd.DataFrame({"g": g, "m": kf_m, "yil": yil})[gecerli].groupby("yil").mean()
    return SantralKalibrasyonu(ozet, km, gozlenen, yillik)


def kalite_sinifi(o: dict, gwa_era5_orani: float | None = None) -> str:
    """
    temiz / kullanilabilir / disarida — eşikler docs/v2_A_veri_altyapisi.md'de.
    k'nin makullüğü ham değerle değil, GWA düzeltmesinden arta kalan R = k / (GWA/ERA5) ile sınanır: iç ve karmaşık arazide
    k > 1,5 fiziksel olarak beklenir (ERA5 hücre ortalaması sırt hızını düşük gösterir), ama R ~1'den çok sapmamalıdır.
    """
    oran_iyi = np.isnan(o["kapasite_orani"]) or 0.7 <= o["kapasite_orani"] <= 1.3
    R = o["k_sabit"] / gwa_era5_orani if gwa_era5_orani and np.isfinite(gwa_era5_orani) else o["k_sabit"]
    if o["korelasyon"] >= 0.70 and o["veri_yili"] >= 3 and o["talimat_suphesi"] <= 0.02 and oran_iyi and 0.75 <= R <= 1.35:
        return "temiz"
    if o["korelasyon"] >= 0.60 and o["veri_yili"] >= 2 and o["talimat_suphesi"] <= 0.05 and 0.6 <= R <= 1.6:
        return "kullanilabilir"
    return "disarida"
