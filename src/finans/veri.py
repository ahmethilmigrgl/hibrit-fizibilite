"""
Finansal model için girdi dizileri: Ezine üretim profilleri (10 hava yılı) ve PTF şekil yılları.

Her şey 8760 saatlik "standart yıl" dizilerine çevrilir (UTC saat sırası, 29 Şubat atılır),
böylece hava yılları ile fiyat yılları vektörel olarak eşleştirilebilir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.ayarlar import ISLENMIS_VERI, KOK

SAAT = 8760


def _standart_yil(seri: pd.Series) -> np.ndarray:
    """UTC indeksli bir yıllık seriyi 8760 saatlik diziye çevirir (29 Şubat atılır, eksikler doldurulur)."""
    s = seri[~((seri.index.month == 2) & (seri.index.day == 29))]
    yil = s.index[0].year
    tam = pd.date_range(f"{yil}-01-01", f"{yil}-12-31 23:00", freq="h", tz="UTC")
    tam = tam[~((tam.month == 2) & (tam.day == 29))]
    return s.reindex(tam).ffill().bfill().to_numpy()[:SAAT]


@dataclass
class UretimProfili:
    """1 MW başına saatlik kapasite faktörleri: (hava_yili, 8760)."""

    ges: np.ndarray
    res: np.ndarray
    hava_yillari: list[int]


def piyasa_serisi(kolon: str) -> pd.Series:
    """
    Saatlik ulusal piyasa serisi (UTC). Önce çevrimdışı işlenmiş veri (data/processed), yoksa uygulamaya gömülü piyasa paketi
    (data/atlas/piyasa/saatlik.parquet; v2 web uygulaması kişisel EPİAŞ anahtarı olmadan bununla çalışır).
    """
    kaynak = {
        "ptf_usd": "ptf_2014_guncel.parquet",
        "ptf_tl": "ptf_2014_guncel.parquet",
        "sfk_fiyat_usd": "yan_hizmet_2023_guncel.parquet",
        "pfk_fiyat_usd": "yan_hizmet_2023_guncel.parquet",
    }
    yol = ISLENMIS_VERI / kaynak.get(kolon, "")
    if kolon in kaynak and yol.exists():
        return pd.read_parquet(yol)[kolon]
    return pd.read_parquet(KOK / "data" / "atlas" / "piyasa" / "saatlik.parquet")[kolon].astype(float)


def profil_df_den(df: pd.DataFrame) -> UretimProfili:
    """profil_uret çıktısından (zaman_utc indeksli, ges_kf/res_kf) doğrudan UretimProfili (dosyaya yazmadan)."""
    d = df.reset_index().set_index("zaman_utc") if "zaman_utc" in df.columns or df.index.name != "zaman_utc" else df
    yillar = sorted(set(d.index.year))
    ges = np.vstack([_standart_yil(d.loc[str(y), "ges_kf"]) for y in yillar])
    res = np.vstack([_standart_yil(d.loc[str(y), "res_kf"]) for y in yillar])
    return UretimProfili(ges=ges, res=res, hava_yillari=yillar)


def uretim_profili(dosya: str = "ezine_profiller_2014_2023.parquet") -> UretimProfili:
    """İşlenmiş saatlik üretim profillerini (UTC, MW başına KF) yükler."""
    df = pd.read_parquet(ISLENMIS_VERI / dosya).set_index("zaman_utc")
    yillar = sorted(set(df.index.year))
    ges = np.vstack([_standart_yil(df.loc[str(y), "ges_kf"]) for y in yillar])
    res = np.vstack([_standart_yil(df.loc[str(y), "res_kf"]) for y in yillar])
    return UretimProfili(ges=ges, res=res, hava_yillari=yillar)


def fiyat_sekil_yillari(bas: str = "2025-01", son: str = "2026-09") -> tuple[np.ndarray, list[str]]:
    """
    Saatlik PTF (USD) şeklini (yıllık ortalamaya bölünmüş) iki takvim yılı olarak döndürür:
        A = 2025 (Oca–Ara)
        B = 2026 Oca–Eyl + 2025 Eki–Ara (son 12 ay, takvim sırasına dizilmiş)
    Döndürür: (2, 8760) dizi, her satırın ortalaması 1; ve etiketler.
    """
    p = piyasa_serisi("ptf_usd")
    a = _standart_yil(p.loc["2025-01-01":"2025-12-31 23:00"])
    son_12 = pd.concat([p.loc["2026-01-01":"2026-09-30 23:00"], p.loc["2025-10-01":"2025-12-31 23:00"]])
    # 2025 Eki–Ara kısmını 2026 takvimine taşı (yalnızca şekil kullanıldığı için)
    son_12.index = son_12.index.map(lambda z: z.replace(year=2026))
    b = _standart_yil(son_12.sort_index())
    sekil = np.vstack([a / a.mean(), b / b.mean()])
    return sekil, ["2025", "Eki 2025 – Eyl 2026"]


def yan_hizmet_sekil_yillari(urun: str = "sfk") -> np.ndarray:
    """
    Yan hizmet kapasite fiyatı [USD/MW-saat], PTF şekil yıllarıyla aynı iki takvim yılı:
        A = 2025, B = 2026 Oca–Eyl + 2025 Eki–Ara.  Döndürür (2, 8760). Seviye korunur (normalize edilmez).
    """
    df = piyasa_serisi(f"{urun}_fiyat_usd")
    a = _standart_yil(df.loc["2025-01-01":"2025-12-31 23:00"])
    son_12 = pd.concat([df.loc["2026-01-01":"2026-09-30 23:00"], df.loc["2025-10-01":"2025-12-31 23:00"]])
    son_12.index = son_12.index.map(lambda z: z.replace(year=2026))
    b = _standart_yil(son_12.sort_index())
    return np.vstack([a, b])
