"""
Güneş (GES) üretim modeli: PVGIS saatlik ışınım + pvlib PVWatts yaklaşımı.

Akış:
    1) pvgis_isinim_indir  → PVGIS'ten optimum eğimli, güneye bakan düzlemde saatlik
                              ışınım bileşenleri + hava sıcaklığı + rüzgâr (önbellekli)
    2) gunes_kapasite_faktoru → PVWatts: IAM → hücre sıcaklığı → DC güç → sistem kayıpları
                              → inverter (verim + kırpma) → MW AC başına kapasite faktörü
    3) pvgis_pv_indir       → doğrulama için PVGIS'in kendi PV hesabı (pvcalculation)

Zaman: Tüm seriler UTC. PVGIS zaman damgaları HH:10 gibi ışınım ölçüm anını gösterir;
güneş konumu bu gerçek anlarda hesaplanır, sonra indeks saat başına (HH:00 UTC) yuvarlanır.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from src.ayarlar import HAM_VERI, deger

PVGIS_KLASOR = HAM_VERI / "pvgis"


def _dosya_adi(kod: str, y1: int, y2: int, tur: str) -> Path:
    return PVGIS_KLASOR / f"{kod}_{y1}_{y2}_{tur}"


def pvgis_isinim_indir(kod: str, enlem: float, boylam: float, y1: int, y2: int,
                       cfg_gunes: dict) -> tuple[pd.DataFrame, dict]:
    """
    PVGIS seriescalc ile saatlik düzlem ışınımı (POA) bileşenlerini indirir.
    Daha önce indirildiyse data/raw/pvgis altındaki önbellekten okur.

    Döndürür: (veri, meta) — meta içinde PVGIS'in seçtiği optimum eğim vardır.
    """
    PVGIS_KLASOR.mkdir(parents=True, exist_ok=True)
    yol = _dosya_adi(kod, y1, y2, "isinim")
    veri_yolu, meta_yolu = yol.with_suffix(".parquet"), yol.with_suffix(".json")

    if veri_yolu.exists() and meta_yolu.exists():
        return pd.read_parquet(veri_yolu), json.loads(meta_yolu.read_text())

    veri, meta = pvlib.iotools.get_pvgis_hourly(
        enlem, boylam, start=y1, end=y2,
        surface_azimuth=deger(cfg_gunes["azimut"]),
        optimal_surface_tilt=True,          # PVGIS optimum eğimi kendisi bulur
        components=True,                    # direkt / yaygın / yansıyan ayrı ayrı
        url=deger(cfg_gunes["pvgis_url"]),
        timeout=120,
    )
    veri.to_parquet(veri_yolu)
    meta_yolu.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return veri, meta


def pvgis_pv_indir(kod: str, enlem: float, boylam: float, y1: int, y2: int,
                   cfg_gunes: dict) -> tuple[pd.DataFrame, dict]:
    """Doğrulama için PVGIS'in kendi PV hesabı: 1 kWp, crystSi, toplam kayıp %14 (önbellekli)."""
    PVGIS_KLASOR.mkdir(parents=True, exist_ok=True)
    yol = _dosya_adi(kod, y1, y2, "pvcalc")
    veri_yolu, meta_yolu = yol.with_suffix(".parquet"), yol.with_suffix(".json")

    if veri_yolu.exists() and meta_yolu.exists():
        return pd.read_parquet(veri_yolu), json.loads(meta_yolu.read_text())

    veri, meta = pvlib.iotools.get_pvgis_hourly(
        enlem, boylam, start=y1, end=y2,
        surface_azimuth=deger(cfg_gunes["azimut"]),
        optimal_surface_tilt=True,
        pvcalculation=True, peakpower=1.0,  # 1 kWp → P sütunu W cinsinden
        pvtechchoice="crystSi", mountingplace="free",
        loss=deger(cfg_gunes["dogrulama_kaybi_pvgis"]) * 100,
        url=deger(cfg_gunes["pvgis_url"]),
        timeout=120,
    )
    veri.to_parquet(veri_yolu)
    meta_yolu.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return veri, meta


def optimum_egim(meta: dict) -> float:
    """PVGIS meta verisinden kullanılan (optimum) panel eğimini okur."""
    return float(meta["inputs"]["mounting_system"]["fixed"]["slope"]["value"])


def gunes_kapasite_faktoru(veri: pd.DataFrame, meta: dict, cfg_gunes: dict,
                           dc_ac_orani: float | None = None,
                           sistem_kaybi: float | None = None,
                           inverter_yok: bool = False,
                           dc_dondur: bool = False,
                           kirpma_kaybi_uygula: bool = True,
                           zaman_hizasi: str | None = None) -> pd.Series:
    """
    PVWatts yaklaşımıyla saatlik AC kapasite faktörü hesaplar (1 MW AC başına, 0-1).

    Opsiyonel argümanlar config değerlerini geçersiz kılar (doğrulama/duyarlılık için):
        inverter_yok=True → inverter verimi ve kırpma uygulanmaz (PVGIS ile aynı tanım için;
                            o durumda kayıp oranına inverter kaybı dahil edilmelidir)
        dc_dondur=True    → AC yerine kayıplar sonrası DC gücü döndürür (kırpma analizi için)
        kirpma_kaybi_uygula=False → config'teki ek kırpma kaybı (kirpma_kaybi) uygulanmaz
        zaman_hizasi      → "aralik": [t, t+1) aralık ortalamasına enterpolasyon; "anlik": PVGIS anı
    """
    dc_ac = dc_ac_orani if dc_ac_orani is not None else deger(cfg_gunes["dc_ac_orani"])
    kayip = sistem_kaybi if sistem_kaybi is not None else deger(cfg_gunes["sistem_kaybi"])
    eta_inv = deger(cfg_gunes["inverter_nominal_verim"])
    gamma = deger(cfg_gunes["sicaklik_katsayisi"])

    enlem = meta["inputs"]["location"]["latitude"]
    boylam = meta["inputs"]["location"]["longitude"]
    rakim = meta["inputs"]["location"]["elevation"]
    egim = optimum_egim(meta)
    azimut = deger(cfg_gunes["azimut"])

    # --- Geliş açısı (AOI) ve yansıma kaybı (IAM): sadece direkt ışınıma uygulanır
    konum = pvlib.solarposition.get_solarposition(veri.index, enlem, boylam, altitude=rakim)
    aoi = pvlib.irradiance.aoi(egim, azimut, konum["apparent_zenith"], konum["azimuth"])
    iam = pvlib.iam.ashrae(aoi, b=0.05)  # aoi ≥ 90° için 0 döner
    poa_etkin = (veri["poa_direct"] * iam + veri["poa_sky_diffuse"]
                 + veri["poa_ground_diffuse"]).clip(lower=0)
    poa_toplam = veri["poa_direct"] + veri["poa_sky_diffuse"] + veri["poa_ground_diffuse"]

    # --- Hücre sıcaklığı (SAPM, açık raf, cam-polimer)
    p = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"]
    t_hucre = pvlib.temperature.sapm_cell(poa_toplam, veri["temp_air"], veri["wind_speed"], **p)

    # --- DC güç: 1 MW AC başına dc_ac MWp panel
    pdc0 = dc_ac  # MWp
    p_dc = pvlib.pvsystem.pvwatts_dc(poa_etkin, t_hucre, pdc0, gamma)
    p_dc = p_dc * (1 - kayip)  # PVWatts sistem kayıpları (inverter hariç)
    if dc_dondur or inverter_yok:
        return pd.Series(np.asarray(p_dc, dtype=float), index=veri.index.floor("h"), name="ges_kf")

    # --- İnverter: nominal verim + AC nominal güçte kırpma (clipping)
    p_ac_nominal = 1.0  # MW AC
    p_ac = pvlib.inverter.pvwatts(p_dc, pdc0=p_ac_nominal / eta_inv, eta_inv_nom=eta_inv)
    p_ac = p_ac.clip(lower=0, upper=p_ac_nominal)

    # --- Ek kırpma kaybı: saatlik veri anlık tepeleri yumuşattığı için yukarıdaki kırpma
    #     gerçeği yansıtmaz; config'teki yıllık kırpma kaybı AC üretime tek tip uygulanır
    if kirpma_kaybi_uygula:
        p_ac = p_ac * (1 - deger(cfg_gunes["kirpma_kaybi"]))

    kf = pd.Series(np.asarray(p_ac, dtype=float), index=veri.index.floor("h"), name="ges_kf")

    # --- Zaman hizası: PVGIS değerleri ~HH:10 UTC anındaki ANLIK değerlerdir. [t, t+1) aralığının
    #     ortası HH:30 olduğu için HH:10 ve (HH+1):10 arasında doğrusal enterpolasyon: ⅔·P(t) + ⅓·P(t+1)
    hiza = zaman_hizasi or deger(cfg_gunes.get("zaman_hizasi", {"value": "anlik"}))
    if hiza == "aralik":
        kf = (2 / 3) * kf + (1 / 3) * kf.shift(-1).fillna(0.0)
    return kf


def kirpma_orani(veri: pd.DataFrame, meta: dict, cfg_gunes: dict) -> float:
    """
    Inverter kırpmasıyla kaybedilen enerjinin oranı (yaklaşık).

    Kırpmasız AC ≈ DC × nominal inverter verimi; kırpılan = max(bu − AC limiti, 0).
    """
    eta = deger(cfg_gunes["inverter_nominal_verim"])
    ac_kirpmasiz = gunes_kapasite_faktoru(veri, meta, cfg_gunes, dc_dondur=True) * eta
    kirpilan = (ac_kirpmasiz - 1.0).clip(lower=0)
    return float(kirpilan.sum() / ac_kirpmasiz.sum())
