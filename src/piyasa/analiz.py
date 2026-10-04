"""
Yakalanan fiyat (capture price), yakalanma oranı (capture rate) ve batarya ön göstergeleri.

Tanımlar (her dönem için, ör. yıl ya da ay):
    Yakalanan fiyat  = Σ(üretim_t × fiyat_t) / Σ(üretim_t)       — üretim ağırlıklı ortalama fiyat
    Ortalama fiyat   = Σ(fiyat_t) / N                            — zaman ağırlıklı (baz yük) ortalama
    Yakalanma oranı  = yakalanan fiyat / ortalama fiyat          — birimsiz; 1'in altı = ortalamanın altında satış

Yakalanma oranı aynı dönemin fiyatlarının oranı olduğu için para birimi ve enflasyondan
neredeyse bağımsızdır; yıllar arası kıyas için ana gösterge budur.

Tüm seriler UTC saat indekslidir; dönemler Türkiye yerel saatine (Europe/Istanbul) göre belirlenir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def yerel_donem(indeks: pd.DatetimeIndex, frekans: str = "Y") -> pd.Index:
    """UTC indeksi Türkiye yerel saatine göre dönem etiketine çevirir (yıl: int, ay: 'YYYY-MM')."""
    yerel = indeks.tz_convert("Europe/Istanbul")
    if frekans == "Y":
        return pd.Index(yerel.year, name="yil")
    return pd.Index(yerel.strftime("%Y-%m"), name="ay")


def yakalanan_fiyat(fiyat: pd.Series, uretimler: pd.DataFrame, frekans: str = "Y") -> pd.DataFrame:
    """
    fiyat     : saatlik fiyat serisi (UTC)
    uretimler : saatlik üretim/ağırlık sütunları (UTC), ör. ges, res, hibrit_satilan
    Döndürür  : her dönem için ortalama fiyat ve her sütun için yakalanan fiyat ve yakalanma oranı.
    Yalnızca fiyat ve üretimin ikisinin de bulunduğu saatler kullanılır.
    """
    df = pd.concat([fiyat.rename("_fiyat"), uretimler], axis=1, join="inner").dropna()
    donem = yerel_donem(df.index, frekans)
    sonuc = pd.DataFrame({"ortalama_fiyat": df["_fiyat"].groupby(donem).mean()})
    for s in uretimler.columns:
        gelir = (df[s] * df["_fiyat"]).groupby(donem).sum()
        miktar = df[s].groupby(donem).sum()
        sonuc[f"{s}_yakalanan"] = gelir / miktar.replace(0, np.nan)
        sonuc[f"{s}_oran"] = sonuc[f"{s}_yakalanan"] / sonuc["ortalama_fiyat"]
    sonuc["saat"] = df["_fiyat"].groupby(donem).size()
    return sonuc


def gun_ici_profil(fiyat: pd.Series) -> pd.DataFrame:
    """Yıl × yerel saat ortalama fiyat tablosu (satır: yıl, sütun: 0–23 TSİ)."""
    yerel = fiyat.index.tz_convert("Europe/Istanbul")
    return fiyat.groupby([yerel.year.rename("yil"), yerel.hour.rename("saat")]).mean().unstack()


def gunluk_spread(fiyat: pd.Series) -> pd.DataFrame:
    """
    Her yerel gün için en yüksek − en düşük saatlik fiyat (batarya arbitraj potansiyelinin kaba göstergesi)
    ve en yüksek 4 saat ortalaması − en düşük 4 saat ortalaması (4 saatlik bataryanın kabaca yakalayabileceği fark).
    """
    yerel = fiyat.index.tz_convert("Europe/Istanbul")
    gun = pd.Index(yerel.normalize().tz_localize(None), name="gun")
    gruplar = fiyat.groupby(gun)

    def ust_alt_4(s: pd.Series) -> float:
        d = np.sort(s.values)
        return d[-4:].mean() - d[:4].mean() if len(d) >= 8 else np.nan

    return pd.DataFrame(
        {
            "spread": gruplar.max() - gruplar.min(),
            "spread_4s": gruplar.apply(ust_alt_4),
            "saat": gruplar.size(),
        }
    )


def dusuk_fiyat_saatleri(fiyat_usd: pd.Series, esikler: list[float]) -> pd.DataFrame:
    """Her yıl için fiyatı eşik değerinin altında ya da eşit olan saat sayısı."""
    yil = yerel_donem(fiyat_usd.index, "Y")
    return pd.DataFrame({f"<= {e:g} $/MWh": (fiyat_usd <= e).groupby(yil).sum() for e in esikler})


def hava_yillari_ile_yakalanan(fiyat: pd.Series, profil: pd.DataFrame, fiyat_yillari: list[int]) -> pd.DataFrame:
    """
    Profil yıllarıyla örtüşmeyen fiyat yılları için yakalanan fiyat: her fiyat yılına profildeki
    her hava yılını (yerel ay-gün-saat eşleşmesiyle, 29 Şubat hariç) uygular ve sonuçların
    ortalamasını, en düşüğünü ve en yükseğini döndürür. 'Aynı yılın fiyatı' yaklaşımından farklıdır:
    hava ile fiyat arasındaki gerçek eşzamanlılık (ör. rüzgârlı saatte fiyat düşmesi) kaybolur.
    """

    def anahtar(indeks: pd.DatetimeIndex) -> pd.MultiIndex:
        """UTC zaman damgasını Türkiye saatinde (ay, gün, saat) anahtarına çevirir."""
        y = indeks.tz_convert("Europe/Istanbul")
        return pd.MultiIndex.from_arrays([y.month, y.day, y.hour], names=["ay", "gun", "saat"])

    f = fiyat.copy()
    f.index = pd.MultiIndex.from_arrays(
        [
            fiyat.index.tz_convert("Europe/Istanbul").year,
            anahtar(fiyat.index).get_level_values(0),
            anahtar(fiyat.index).get_level_values(1),
            anahtar(fiyat.index).get_level_values(2),
        ],
        names=["yil", "ay", "gun", "saat"],
    )
    f = f[~f.index.duplicated()]
    p_yil = profil.index.tz_convert("Europe/Istanbul").year
    sonuclar = []
    for py in fiyat_yillari:
        fy = f.xs(py, level="yil")
        fy = fy[~((fy.index.get_level_values("ay") == 2) & (fy.index.get_level_values("gun") == 29))]
        for hy in sorted(set(p_yil)):
            pr = profil[p_yil == hy].copy()
            pr.index = anahtar(pr.index)
            pr = pr[~pr.index.duplicated()]
            ortak = fy.index.intersection(pr.index)
            if len(ortak) < 1000:
                continue
            ff, pp = fy.loc[ortak], pr.loc[ortak]
            satir = {"fiyat_yili": py, "hava_yili": hy, "ortalama_fiyat": ff.mean()}
            for s in pp.columns:
                satir[f"{s}_yakalanan"] = (pp[s] * ff).sum() / pp[s].sum()
                satir[f"{s}_oran"] = satir[f"{s}_yakalanan"] / ff.mean()
            sonuclar.append(satir)
    return pd.DataFrame(sonuclar)
