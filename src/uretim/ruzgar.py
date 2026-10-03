"""
Rüzgâr (RES) üretim modeli: ERA5 nokta zaman serisi + windpowerlib türbin güç eğrisi.

Akış:
    1) era5_indir            → CDS 'reanalysis-era5-single-levels-timeseries' veri setinden
                               yıl yıl CSV (data/raw/era5, önbellekli)
    2) gobek_hizi            → 10 m ve 100 m hızlarından saatlik kayma üssü (shear exponent),
                               hızı göbek yüksekliğine taşıma
    3) hava_yogunlugu        → 2 m sıcaklık + yüzey basıncından göbek yüksekliğinde yoğunluk
    4) ruzgar_kapasite_faktoru → hız kalibrasyon katsayısı → yoğunluk düzeltmeli güç eğrisi (IEC 61400-12) → kayıplar
                               → MW başına kapasite faktörü

Zaman: ERA5 zaman damgaları UTC'dir ve rüzgâr değişkenleri o andaki (anlık) değerlerdir.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from windpowerlib import WindTurbine
from windpowerlib.power_output import power_curve_density_correction

from src.ayarlar import HAM_VERI, cds_istemcisi, deger

ERA5_KLASOR = HAM_VERI / "era5"
VERI_SETI = "reanalysis-era5-single-levels-timeseries"
R_KURU_HAVA = 287.05      # J/(kg·K), kuru hava gaz sabiti
G = 9.80665               # m/s², yerçekimi ivmesi
SICAKLIK_GRADYANI = 0.0065  # K/m, standart atmosfer sıcaklık düşüş oranı


def era5_indir(kod: str, enlem: float, boylam: float, yil: int, cfg_ruzgar: dict) -> pd.DataFrame:
    """
    Bir saha ve yıl için ERA5 nokta zaman serisini indirir (önbellekli).
    Dosya: data/raw/era5/{kod}_{yil}.csv
    """
    ERA5_KLASOR.mkdir(parents=True, exist_ok=True)
    yol = ERA5_KLASOR / f"{kod}_{yil}.csv"

    if not yol.exists():
        istek = {
            "variable": deger(cfg_ruzgar["degiskenler"]),
            "location": {"longitude": boylam, "latitude": enlem},
            "date": [f"{yil}-01-01/{yil}-12-31"],
            "data_format": "csv",
        }
        gecici = yol.with_suffix(".zip")
        cds_istemcisi().retrieve(VERI_SETI, istek, str(gecici))
        # Veri seti CSV'yi zip içinde döndürür; içindeki tek CSV'yi çıkar
        with zipfile.ZipFile(gecici) as z:
            csv_adi = [n for n in z.namelist() if n.endswith(".csv")][0]
            yol.write_bytes(z.read(csv_adi))
        gecici.unlink()

    df = pd.read_csv(yol, parse_dates=["valid_time"])
    df = df.set_index("valid_time")
    df.index = df.index.tz_localize("UTC")
    df.index.name = "zaman_utc"
    return df


def era5_coklu_yil(kod: str, enlem: float, boylam: float, y1: int, y2: int,
                   cfg_ruzgar: dict) -> pd.DataFrame:
    """y1..y2 (dahil) yıllarını indirip birleştirir (önbellekte olmayan yıllar paralel indirilir)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as havuz:
        parcalar = havuz.map(lambda y: era5_indir(kod, enlem, boylam, y, cfg_ruzgar), range(y1, y2 + 1))
        return pd.concat(list(parcalar))


def gobek_hizi(df: pd.DataFrame, cfg_ruzgar: dict, gobek: float | None = None) -> pd.DataFrame:
    """
    Saatlik kayma üssü (α) ve göbek yüksekliğindeki rüzgâr hızını hesaplar.

    Kuvvet yasası:  v(h) = v_ref · (h / h_ref)^α
    α, iki yükseklikten:  α = ln(v100 / v10) / ln(100 / 10)
    """
    h = gobek or deger(cfg_ruzgar["gobek_yuksekligi"])
    a_min, a_max = deger(cfg_ruzgar["kayma_ussu_sinirlari"])
    v10_min = deger(cfg_ruzgar["kayma_min_hiz_10m"])

    v10 = np.hypot(df["u10"], df["v10"])
    v100 = np.hypot(df["u100"], df["v100"])

    with np.errstate(divide="ignore", invalid="ignore"):
        alfa = np.log(v100 / v10) / np.log(100 / 10)
    gecerli = (v10 >= v10_min) & np.isfinite(alfa)
    medyan = float(np.median(alfa[gecerli]))
    alfa = alfa.where(gecerli, medyan).clip(a_min, a_max)

    v_gobek = v100 * (h / 100.0) ** alfa
    return pd.DataFrame({"v10": v10, "v100": v100, "alfa": alfa, "v_gobek": v_gobek})


def hava_yogunlugu(df: pd.DataFrame, cfg_ruzgar: dict, gobek: float | None = None) -> pd.Series:
    """
    Göbek yüksekliğinde hava yoğunluğu [kg/m³], ideal gaz yasası:  ρ = p / (R · T)

    2 m sıcaklık ve yüzey basıncı göbek yüksekliğine taşınır:
        T_h = T_2m − Γ · (h − 2)
        p_h = p_s · exp(−g · h / (R · T_ort))     (hipsometrik denklem)
    """
    h = gobek or deger(cfg_ruzgar["gobek_yuksekligi"])
    t_gobek = df["t2m"] - SICAKLIK_GRADYANI * (h - 2)
    t_ort = (df["t2m"] + t_gobek) / 2
    p_gobek = df["sp"] * np.exp(-G * h / (R_KURU_HAVA * t_ort))
    return p_gobek / (R_KURU_HAVA * t_gobek)


def turbin(model: str, cfg_ruzgar: dict, gobek: float | None = None) -> WindTurbine:
    """windpowerlib kütüphanesinden türbini güç eğrisiyle yükler."""
    return WindTurbine(turbine_type=model, hub_height=gobek or deger(cfg_ruzgar["gobek_yuksekligi"]))


def aralik_ortalamasi(seri: pd.Series) -> pd.Series:
    """
    Anlık (saat başı) değerleri [t, t+1) saat aralığının ortalamasına çevirir: (x_t + x_{t+1}) / 2.
    EPİAŞ verisi saat başlangıcı etiketli saatlik ortalama olduğu için ERA5 anlık değerleri bu
    tanıma getirilir. Serinin son saati için sonraki değer olmadığından kendi değeri kullanılır.
    """
    return (seri + seri.shift(-1).fillna(seri)) / 2


def tsi_ay_saat(indeks: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """UTC indeksinden Türkiye saati (UTC+3, sabit) ay ve saat dizileri."""
    tsi = indeks + pd.Timedelta(hours=3)
    return np.asarray(tsi.month), np.asarray(tsi.hour)


def ruzgar_kapasite_faktoru(df: pd.DataFrame, cfg_ruzgar: dict,
                            turbin_modeli: str | None = None, gobek: float | None = None,
                            katsayi: float | None = None, k_matris: pd.DataFrame | None = None,
                            zaman_hizasi: str | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """
    Saatlik RES kapasite faktörü (MW başına, 0-1, kayıplar düşülmüş).

    Opsiyonel argümanlar config'i geçersiz kılar (kalibrasyonda referans santrali kendi
    türbini ve göbek yüksekliğiyle modellemek, katsayıyı taramak için):
        katsayi      — sabit hız kalibrasyon katsayısı (verilmezse config)
        k_matris     — 12 × 24 hız katsayısı matrisi (satır: ay 1-12, sütun: TSİ saati 0-23).
                       Verilirse sabit katsayının yerine geçer. Yalnızca açıkça verildiğinde kullanılır.
        zaman_hizasi — "aralik": hız ve yoğunluk [t, t+1) aralık ortalamasına çevrilir (EPİAŞ ile aynı
                       tanım); "anlik": ERA5 saat başı anlık değerleri. Verilmezse config.

    Döndürür: (kf serisi, ara hesaplar tablosu: hızlar, α, yoğunluk, katsayı, brüt kf)
    """
    model = turbin_modeli or deger(cfg_ruzgar["turbin_modeli"])
    t = turbin(model, cfg_ruzgar, gobek)
    egri = t.power_curve  # sütunlar: wind_speed [m/s], value [W]

    ara = gobek_hizi(df, cfg_ruzgar, gobek)
    ara["yogunluk"] = hava_yogunlugu(df, cfg_ruzgar, gobek)

    hiza = zaman_hizasi or deger(cfg_ruzgar.get("zaman_hizasi", {"value": "anlik"}))
    if hiza == "aralik":
        for s in ["v10", "v100", "v_gobek", "yogunluk"]:
            ara[s] = aralik_ortalamasi(ara[s])

    # Kalibrasyon: ERA5'in hız sapmasını düzeltmek için hız güç eğrisinden önce ölçeklenir.
    # v_gobek ham (kalibrasyonsuz) hız olarak saklanır; v_kalibre güç eğrisine giren hızdır.
    if k_matris is not None:
        ay, saat = tsi_ay_saat(ara.index)
        ara["katsayi"] = k_matris.to_numpy()[ay - 1, saat]
    else:
        if katsayi is None:
            katsayi = deger(cfg_ruzgar["ruzgar_hiz_kalibrasyon_katsayisi"])
        ara["katsayi"] = katsayi
    ara["v_kalibre"] = ara["v_gobek"] * ara["katsayi"]

    # IEC 61400-12 yoğunluk düzeltmesi: güç eğrisinin hız ekseni her saat için
    # o saatin yoğunluğuna göre kaydırılır (windpowerlib uygulaması)
    guc = power_curve_density_correction(
        ara["v_kalibre"], egri["wind_speed"], egri["value"], ara["yogunluk"]
    )
    ara["brut_kf"] = np.asarray(guc, dtype=float) / t.nominal_power
    kayip = deger(cfg_ruzgar["toplam_kayip"])
    kf = (ara["brut_kf"] * (1 - kayip)).clip(0, 1).rename("res_kf")
    return kf, ara
