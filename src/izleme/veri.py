"""
Performans izleme verisi (çevrimdışı): kalibre santraller için günlük gözlenen üretim ve model beklentisi.

Gözlenen: EPİAŞ gerçek zamanlı üretim (santral bazında, saatlik MWh) — yalnız yerel önbellekten okunur (kimlik bilgisi
gerektirmez; önbellek Faz A'da oluşturuldu). Model: santral hücresinin ERA5 serisi → santralin türbin vekili ve göbek
yüksekliğiyle güç eğrisi → atlas ay × saat k matrisi (src/atlas/kalibrasyon.py ile aynı model) → saatlik KF (MW başına).
Kapasite: aylık %99,5 yüzdelik çıkışın geçmişe dönük en büyüğü (artırımda yükselir, arızada düşmez); %8'den büyük artış
"kapasite artırımı/yenileme" olayıdır.
Çıktı (ham saatlik veri değil, günlük toplam; data/processed altında, uygulamaya girmez): izleme_gunluk.parquet
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ayarlar import HAM_VERI, KOK

ATLAS = KOK / "data" / "atlas"


def gozlenen_onbellek(epias_id: int) -> pd.Series:
    """Önbellekteki çeyreklik JSON dosyalarından saatlik üretim (UTC)."""
    kayit = []
    for f in sorted((HAM_VERI / "epias" / f"uretim_santral_{epias_id}").glob("*.json")):
        kayit += json.loads(f.read_text(encoding="utf-8")).get("items", [])
    if not kayit:
        return pd.Series(dtype=float)
    d = pd.DataFrame(kayit)
    t = pd.to_datetime(d["date"], utc=True)
    s = pd.Series(pd.to_numeric(d["total"], errors="coerce").to_numpy(), index=t).sort_index()
    return s[~s.index.duplicated()]


def model_kf(r: pd.Series, km: np.ndarray, cr: dict) -> pd.Series:
    from src.kaynaklar import era5_cds
    from src.uretim import kalibrasyon as kal

    he, hb = era5_cds.hucre(r["enlem"], r["boylam"])
    yol = era5_cds.KLASOR / f"era5_{he:.2f}_{hb:.2f}_2014-01-01_2025-12-31.parquet"
    era5 = pd.read_parquet(yol)
    m = kal.referans_model(era5, cr, r["turbin"], float(r["gobek"]))
    return pd.Series(m.kf_matris(km), index=m.indeks)


def santral_gunluk(r: pd.Series, km: np.ndarray, cr: dict) -> pd.DataFrame | None:
    g = gozlenen_onbellek(int(r["epias_id"]))
    if g.empty:
        return None
    m = model_kf(r, km, cr)
    g = g.reindex(m.index)
    ay = g.groupby(g.index.tz_convert("Europe/Istanbul").to_period("M")).quantile(0.995)
    kap = ay.where(ay > 0.2 * ay.max()).cummax().ffill()
    kap_s = pd.Series(kap.reindex(g.index.tz_convert("Europe/Istanbul").to_period("M")).to_numpy(), index=g.index)
    gecerli = g.notna() & np.isfinite(m) & (kap_s > 0)
    gun = g.index.tz_convert("Europe/Istanbul").normalize().tz_localize(None)
    d = pd.DataFrame(
        {
            "gozlenen_mwh": g.where(gecerli),
            "beklenen_mwh": (m * kap_s).where(gecerli),
            "saat": gecerli.astype(int),
            "kapasite_mw": kap_s,
            "gun": gun,
        }
    )
    o = d.groupby("gun").agg(
        gozlenen_mwh=("gozlenen_mwh", "sum"), beklenen_mwh=("beklenen_mwh", "sum"), saat=("saat", "sum"), kapasite_mw=("kapasite_mw", "max")
    )
    o["epias_id"] = int(r["epias_id"])
    return o.reset_index()


def hazirla(cikti: Path) -> pd.DataFrame:
    from src.ayarlar import config_oku

    cr = config_oku()["uretim"]["ruzgar"]
    a = pd.read_csv(ATLAS / "kalibrasyon_atlasi.csv")
    a = a[a["sinif"].isin(["temiz", "kullanilabilir"])]
    z = np.load(ATLAS / "kalibrasyon_matrisleri.npz")
    parca = []
    for _, r in a.iterrows():
        anahtar = f"k_{int(r['epias_id'])}"
        if anahtar not in z.files:
            continue
        try:
            d = santral_gunluk(r, z[anahtar].astype(float), cr)
        except FileNotFoundError:
            continue
        if d is not None and len(d):
            parca.append(d)
    out = pd.concat(parca, ignore_index=True)
    out.to_parquet(cikti, index=False)
    return out
