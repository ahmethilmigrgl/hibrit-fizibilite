"""
v2 genelleştirilmiş üretim profili: herhangi bir Saha için saatlik GES ve RES kapasite faktörleri.

ruzgar_kaynagi:
    "open_meteo" — çalışma zamanı (anahtarsız; A1: CDS ile 100 m hız korelasyonu 0,9999, KF farkı −0,07 puan)
    "cds"        — çevrimdışı (kişisel anahtar; yalnız ön hesaplama ve v1 regresyonu)
kalibrasyon (RES hız katsayısı, 12 × 24 ay × TSİ saati matrisi olarak uygulanır):
    "v1"    — v1 Ezine ay × saat matrisi (yalnız Ezine regresyonu)
    "atlas" — Türkiye kalibrasyon atlasından aktarım kuralı (A4): yakın/benzer santral(ler)in matrisi, yoksa GWA
    "gwa"   — yalnız GWA ortalama düzeltmesi: sabit c = GWA 100 m / ERA5 100 m ortalaması (gün içi şekil düzeltilmez)
    "yok"   — ham ERA5
GES: PVGIS-SARAH3 saatlik ışınım (anahtarsız API) + pvlib (v1 ile aynı model).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.ayarlar import ISLENMIS_VERI, KOK, deger
from src.kaynaklar import open_meteo
from src.saha import Saha
from src.uretim import gunes, ruzgar

V2_KLASOR = ISLENMIS_VERI / "v2"


def hava_verisi(saha: Saha, y1: int, y2: int, kaynak: str, cfg: dict) -> pd.DataFrame:
    """
    kaynak: "grid" (Türkiye ERA5 nokta gridi; yerel ya da Hugging Face), "open_meteo", "cds" (çevrimdışı) ya da
    "otomatik" (grid → yoksa Open-Meteo). Grid yalnız 2014–2023'ü kapsar.
    """
    if kaynak in ("grid", "otomatik"):
        from src import veri_katmani
        from src.kaynaklar import era5_grid

        mantiksal = f"grid/era5_tr/{era5_grid.GRID_SURUMU}/{era5_grid.dosya_adi(saha.enlem, saha.boylam)}"
        p = veri_katmani.yol(mantiksal, zorunlu=False)
        if p is not None:
            d = era5_grid.ac(p).loc[f"{y1}-01-01" : f"{y2}-12-31 23:00"]
            if len(d) >= 8760 * (y2 - y1 + 1) - 48:
                d.attrs["kaynak"] = "era5_grid"
                return d
        if kaynak == "grid" or veri_katmani.yerel_mi():  # yerel modda ağ çağrısı yok
            raise veri_katmani.VeriYok(mantiksal)
        kaynak = "open_meteo"
    if kaynak == "open_meteo":
        d = open_meteo.indir(saha.enlem, saha.boylam, f"{y1}-01-01", f"{y2}-12-31").drop(columns=["om_enlem", "om_boylam"])
        d.attrs["kaynak"] = "open_meteo"
        return d
    if kaynak == "cds":
        d = ruzgar.era5_coklu_yil(saha.kod, saha.enlem, saha.boylam, y1, y2, cfg["uretim"]["ruzgar"])
        d = d[~d.index.duplicated()][["u100", "v100", "u10", "v10", "t2m", "sp"]]
        d.attrs["kaynak"] = "cds"
        return d
    raise ValueError(f"Bilinmeyen rüzgâr kaynağı: {kaynak}")


def gunes_profili(saha: Saha, y1: int, y2: int, cg: dict, grid: bool = True) -> tuple[pd.Series, str]:
    """
    Saatlik GES KF. grid=True: sahanın 0,25° hücresinin PVGIS KF gridi (veri katmanı; uygulama ağ çağrısı yapmaz).
    grid=False ya da grid yoksa (uzak/çevrimdışı mod): PVGIS API ile sahanın kendi noktası.
    """
    from src import veri_katmani
    from src.kaynaklar import pvgis_grid

    if grid:
        mantiksal = f"grid/pvgis_tr/{pvgis_grid.GRID_SURUMU}/{pvgis_grid.dosya_adi(saha.enlem, saha.boylam)}"
        p = veri_katmani.yol(mantiksal, zorunlu=veri_katmani.yerel_mi())
        if p is not None:
            return pvgis_grid.ac(p).loc[f"{y1}-01-01" : f"{y2}-12-31 23:00"], "pvgis_grid"
    isinim, meta = gunes.pvgis_isinim_indir(saha.kod, saha.enlem, saha.boylam, y1, y2, cg)
    return gunes.gunes_kapasite_faktoru(isinim, meta, cg), "pvgis_api"


def sabit_matris(k: float) -> pd.DataFrame:
    return pd.DataFrame(np.full((12, 24), float(k)), index=range(1, 13), columns=range(24))


def k_matrisi(saha: Saha, hava: pd.DataFrame, kalibrasyon: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Seçilen kalibrasyon moduna göre 12 × 24 hız katsayısı matrisi ve açıklama."""
    cr = cfg["uretim"]["ruzgar"]
    if kalibrasyon == "v1":
        return pd.read_parquet(KOK / deger(cr["k_matris_dosyasi"])), {"mod": "v1", "aciklama": "v1 Ezine ay × saat matrisi"}
    if kalibrasyon == "yok":
        return sabit_matris(1.0), {"mod": "yok", "aciklama": "ham ERA5"}
    v100 = float(np.hypot(hava["u100"], hava["v100"]).mean())
    if kalibrasyon == "gwa":
        from src.saha import gwa_hizi

        g = gwa_hizi(saha, cfg)
        c = float(np.clip(g["hiz"] / v100, 0.5, 3.2))
        bilgi = {"mod": "gwa", "c": c, "gwa_100m": g["hiz"], "turbin_yerlesimi": g["yerlesim"], "era5_100m": v100}
        return sabit_matris(c), {**bilgi, "aciklama": "GWA ortalama düzeltmesi (sabit katsayı)"}
    if kalibrasyon == "atlas":
        from src.atlas.aktarim import aktarim_matrisi

        return aktarim_matrisi(saha, v100, cfg)
    raise ValueError(f"Bilinmeyen kalibrasyon: {kalibrasyon}")


def profil_uret(
    saha: Saha, cfg: dict, y1: int = 2014, y2: int = 2023, ruzgar_kaynagi: str = "open_meteo", kalibrasyon: str = "atlas"
) -> tuple[pd.DataFrame, dict]:
    """
    Döndürür (v1 saha_profilleri ile aynı biçim): df (zaman_utc; ges_kf, res_kf, v100_ham, v_gobek_ham, hava_yogunlugu)
    ve bilgi (kaynak, kalibrasyon, türbin, ortalama KF'ler).
    cfg: saha_cfg(saha) ile üretilmiş sahaya özgü config.
    """
    cg, cr = cfg["uretim"]["gunes"], cfg["uretim"]["ruzgar"]
    hava = hava_verisi(saha, y1, y2, ruzgar_kaynagi, cfg)
    km, kal = k_matrisi(saha, hava, kalibrasyon, cfg)
    ges_kf, ges_kaynagi = gunes_profili(saha, y1, y2, cg, grid=ruzgar_kaynagi in ("grid", "otomatik"))
    res_kf, ara = ruzgar.ruzgar_kapasite_faktoru(hava, cr, k_matris=km)
    df = pd.concat(
        [
            ges_kf.rename("ges_kf"),
            res_kf.rename("res_kf"),
            ara["v100"].rename("v100_ham"),
            ara["v_gobek"].rename("v_gobek_ham"),
            ara["yogunluk"].rename("hava_yogunlugu"),
        ],
        axis=1,
        join="inner",
    )
    df.index.name = "zaman_utc"
    bilgi = {
        "saha": saha.ad,
        "kod": saha.kod,
        "ruzgar_kaynagi": hava.attrs.get("kaynak", ruzgar_kaynagi),  # fiilen kullanılan kaynak
        "gunes_kaynagi": ges_kaynagi,
        "kalibrasyon": kal,
        "turbin": deger(cr["turbin_modeli"]),
        "gobek": deger(cr["gobek_yuksekligi"]),
        "ges_kf": float(df["ges_kf"].mean()),
        "res_kf": float(df["res_kf"].mean()),
        "saat": len(df),
    }
    return df, bilgi


def profil_kaydet(df: pd.DataFrame, saha: Saha, etiket: str, y1: int, y2: int) -> str:
    """data/processed/v2/ altına kaydeder; finans.veri.uretim_profili(dosya=...) için göreli yol döndürür."""
    V2_KLASOR.mkdir(parents=True, exist_ok=True)
    yol = V2_KLASOR / f"{saha.kod}_{etiket}_profiller_{y1}_{y2}.parquet"
    df.reset_index().to_parquet(yol, index=False)
    return str(Path("v2") / yol.name)
