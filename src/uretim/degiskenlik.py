"""
Yıldan yıla üretim değişkenliği ve P50/P90 istatistikleri.

P50: yılların yarısında aşılması beklenen yıllık üretim.
P90: yılların %90'ında aşılması beklenen (yani 10 yılda ~1 yıl altına düşülen) yıllık üretim.

İki P90 yöntemi:
    • Ampirik: yıllık üretimlerin 10. yüzdebirliği (np.percentile, doğrusal enterpolasyon).
      Varsayım gerektirmez ama 10 gözlemle en kötü iki yıl arasına düşer, örneklem küçüktür.
    • Normal dağılım: P90 = P50 − 1.282 · σ   (1.282 = standart normalin %10 kantili, z_0.90)
      Burada P50 = ortalama, σ = örneklem standart sapması (ddof=1).

Not: Bunlar yalnızca HAVA kaynaklı yıllar arası değişkenliği (1 yıllık P90) yansıtır;
model/ölçüm belirsizliği ve çok yıllık ortalama P90'ı (σ/√N) Aşama 5'te ele alınacak.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_P90 = 1.2816  # standart normal dağılımın 0.90 kantili


def yillik_uretim(df: pd.DataFrame, sutunlar: list[str]) -> pd.DataFrame:
    """
    Saatlik kapasite faktörlerinden yıllık üretim [MWh/MW] = yıllık ortalama KF × 8760 h.
    8760 ile normalize etmek, artık yılların (2016, 2020) fazladan 24 saatinin
    değişkenlik istatistiklerine sahte gürültü eklemesini önler.
    """
    return (df[sutunlar].groupby(df.index.year).mean() * 8760).rename_axis("yil")


def p50_p90(seri: pd.Series) -> dict:
    """Yıllık üretim serisi için özet istatistikler."""
    ort = seri.mean()
    std = seri.std(ddof=1)
    return {
        "Ortalama": ort,
        "Std. sapma": std,
        "Değişkenlik katsayısı [%]": 100 * std / ort,
        "En düşük yıl": seri.min(),
        "En yüksek yıl": seri.max(),
        "P50 (ampirik medyan)": seri.median(),
        "P90 (ampirik, 10. yüzdebirlik)": np.percentile(seri, 10),
        "P90 (normal: ort − 1.282σ)": ort - Z_P90 * std,
        "P90 / P50 (normal) [%]": 100 * (ort - Z_P90 * std) / ort,
    }
