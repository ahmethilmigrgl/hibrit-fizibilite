"""Ortak hazırlık: saha + kullanıcı varsayımları → sahaya özgü config, profil (önbellekli), güven seviyesi, Ortam."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import KOK, deger
from src.finans.model import Varsayimlar
from src.finans.veri import UretimProfili, profil_df_den
from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi, Uyari
from src.saha import Saha, _ata, saha_cfg, saha_olustur
from src.uretim import genel

PROFIL_ONBELLEK = KOK / "data" / "onbellek" / "profil"


@lru_cache(maxsize=1)
def gelir_yigini_modulu():
    spec = importlib.util.spec_from_file_location("gelir_yigini_v1", KOK / "src" / "05_gelir_yigini.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@dataclass
class Hazirlik:
    saha: Saha
    cfg: dict
    profil: pd.DataFrame
    u: UretimProfili
    bilgi: dict
    guven: dict
    v: Varsayimlar
    uyarilar: list[Uyari]


def saha_hazirla(saha_girdi: Saha | dict, kv: KullaniciVarsayimlari) -> Saha:
    if isinstance(saha_girdi, dict):
        try:
            s = saha_olustur(saha_girdi.get("ad", "Saha"), float(saha_girdi["enlem"]), float(saha_girdi["boylam"]))
        except ValueError as ex:
            raise MotorHatasi(
                "kara_disi",
                "Seçilen nokta Türkiye karasında değil (deniz, ada dışı ya da komşu ülke).",
                "The selected point is not on Turkish land (sea or a neighbouring country).",
            ) from ex
    else:
        s = saha_girdi
    return replace(
        s,
        baglanti_mw=kv.baglanti_mw,
        azami_res_mw=kv.azami_res_mw,
        azami_ges_mw=kv.azami_ges_mw,
        turbin_yerlesimi=kv.turbin_yerlesimi,
        yerlesim_yaricap_km=kv.yerlesim_yaricap_km,
        turbin=kv.turbin or s.turbin,
        gobek=kv.gobek or s.gobek,
        varsayimlar={**s.varsayimlar, **kv.ekstra},
    )


def cfg_uygula(cfg: dict, kv: KullaniciVarsayimlari) -> dict:
    if kv.wacc is not None:
        _ata(cfg, "finans.wacc_reel", kv.wacc)
    for tek, carp in (("res", kv.capex_carpani_res), ("ges", kv.capex_carpani_ges)):
        if carp != 1.0:
            _ata(cfg, f"teknoloji.{tek}.capex", deger(cfg["teknoloji"][tek]["capex"]) * carp)
    if kv.capex_carpani_bess != 1.0:
        for k in ("capex_enerji", "capex_guc"):
            _ata(cfg, f"teknoloji.bess.{k}", deger(cfg["teknoloji"]["bess"][k]) * kv.capex_carpani_bess)
    _ata(cfg, "fiyat_senaryolari.kanibalizasyon", {**deger(cfg["fiyat_senaryolari"]["kanibalizasyon"]), "varyant": kv.kanibalizasyon})
    return cfg


def _profil_anahtari(saha: Saha, cfg: dict, kv: KullaniciVarsayimlari, y1: int, y2: int) -> str:
    cr = cfg["uretim"]["ruzgar"]
    a = [
        round(saha.enlem, 3),
        round(saha.boylam, 3),
        deger(cr["turbin_modeli"]),
        deger(cr["gobek_yuksekligi"]),
        kv.kalibrasyon,
        kv.ruzgar_kaynagi,
        bool(kv.turbin_yerlesimi),
        round(kv.yerlesim_yaricap_km, 2),
        saha.baglanti_mw,
        y1,
        y2,
        deger(cfg["v2"]["motor"])["veri_surumu"],
    ]
    return hashlib.sha1(json.dumps(a, default=str).encode()).hexdigest()[:16]


def guven_bilgisi(kal: dict) -> dict:
    """Profil kalibrasyon bilgisinden güven seviyesi ve tipik hata (data/atlas/guven_seviyeleri.csv)."""
    seviye = kal.get("guven") if kal.get("mod") == "atlas" else ("kalibre (v1)" if kal.get("mod") == "v1" else "düşük")
    t = pd.read_csv(KOK / "data" / "atlas" / "guven_seviyeleri.csv", index_col=0)
    satir = t.loc[seviye] if seviye in t.index else t.loc["düşük"]
    return {
        "seviye": seviye,
        "medyan_puan": float(satir["mutlak_medyan"]),
        "p90_puan": float(satir["mutlak_p90"]),
        "rmse_puan": float(satir["rmse"]),
        "goreli_rmse": float(satir["goreli_rmse_%"]) / 100,
        "komsu": kal.get("komsu", []),
        "mesafe_km": kal.get("mesafe_km", []),
    }


def hazirla(saha_girdi: Saha | dict, kv: KullaniciVarsayimlari, ilerleme=None) -> Hazirlik:
    ilerleme = ilerleme or (lambda *_: None)
    uyari: list[Uyari] = []
    saha = saha_hazirla(saha_girdi, kv)
    cfg = cfg_uygula(saha_cfg(saha), kv)
    y1, y2 = deger(cfg["v2"]["motor"])["profil_yillari"]
    anahtar = _profil_anahtari(saha, cfg, kv, y1, y2)
    yol = PROFIL_ONBELLEK / f"{anahtar}.parquet"
    ilerleme(0.05, "Üretim profilleri hazırlanıyor (PVGIS, ERA5)")
    if yol.exists():
        df = pd.read_parquet(yol)
        bilgi = json.loads((yol.with_suffix(".json")).read_text())
    else:
        try:
            df, bilgi = genel.profil_uret(saha, cfg, y1, y2, ruzgar_kaynagi=kv.ruzgar_kaynagi, kalibrasyon=kv.kalibrasyon)
        except Exception as ex:  # ağ/veri hatası
            raise MotorHatasi(
                "veri",
                f"Saha için hava verisi alınamadı ({type(ex).__name__}). Lütfen biraz sonra tekrar deneyin.",
                f"Weather data could not be retrieved for the site ({type(ex).__name__}). Please try again later.",
            ) from ex
        PROFIL_ONBELLEK.mkdir(parents=True, exist_ok=True)
        df.to_parquet(yol)
        yol.with_suffix(".json").write_text(json.dumps(bilgi, default=str, ensure_ascii=False))
    if df["res_kf"].isna().mean() > 0.01 or len(df) < 8760 * (y2 - y1 + 1) * 0.98:
        raise MotorHatasi(
            "eksik", "Saha için üretim profili eksik (veri boşluğu).", "Generation profile is incomplete for the site (data gap)."
        )
    if df["res_kf"].mean() < 0.15:
        uyari.append(
            Uyari(
                "dusuk_ruzgar",
                f"Rüzgâr çok zayıf: kapasite faktörü %{100 * df['res_kf'].mean():.0f}. RES ekonomik olmayabilir.",
                f"Very weak wind: capacity factor {100 * df['res_kf'].mean():.0f}%. Wind may not be economic.",
            )
        )
    if df["ges_kf"].mean() < 0.15:
        uyari.append(
            Uyari(
                "dusuk_gunes",
                f"Güneş zayıf: kapasite faktörü %{100 * df['ges_kf'].mean():.0f}.",
                f"Weak solar: capacity factor {100 * df['ges_kf'].mean():.0f}%.",
            )
        )
    guven = guven_bilgisi(bilgi["kalibrasyon"])
    if guven["seviye"] == "düşük":
        uyari.append(
            Uyari(
                "guven",
                "30 km içinde benzer kalibre santral yok: rüzgâr tahmini düşük güvenli (tipik hata ±{:.1f} puan).".format(
                    guven["medyan_puan"]
                ),
                "No similar calibrated wind farm within 30 km: low-confidence wind estimate (typical error ±{:.1f} pts).".format(
                    guven["medyan_puan"]
                ),
            )
        )
    return Hazirlik(saha, cfg, df, profil_df_den(df), bilgi, guven, Varsayimlar.configten(cfg), uyari)


def ortam(h: Hazirlik):
    return gelir_yigini_modulu().Ortam(cfg=h.cfg, uretim=h.u)


def sayisal(x: float) -> float:
    return float(np.round(x, 6))


_SFK_ONBELLEK: dict = {}


def sfk_milp_carpani(o) -> float:
    """
    Kapasite MILP'inin SFK geliri (Aşama 5 azalma yolu) ile Monte Carlo'nun beklediği SFK geliri (Aşama 6 doyum
    senaryolarının olasılık ağırlıklı yolu) arasındaki seviyelendirilmiş oran. MILP'e yh_carpan olarak verilir; böylece
    boyutlandırma, değerlemenin kullandığı doyum beklentisiyle tutarlı olur (v1'in stres testi dersi).
    """
    from src.risk.doyum import deterministik_yol

    yh = o.cfg["gelir_yigini"]["yan_hizmet"]
    y, d = np.asarray(o.yillar), np.asarray(o.DF)
    k = hashlib.sha1(json.dumps([y.tolist(), d.tolist(), o.cfg["stres_testi"], yh], sort_keys=True, default=str).encode()).hexdigest()
    if k not in _SFK_ONBELLEK:
        fo = float(pd.read_csv(KOK / "results" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
        sc = deger(o.cfg["stres_testi"]["senaryolar"])
        olas = np.array([sc[a]["olasilik"] for a in sc], float)
        beklenen = sum(p * deterministik_yol(o.cfg, a, y, fo) for a, p in zip(sc, olas / olas.sum(), strict=True))
        milp_yolu = np.maximum((1 - deger(yh["yillik_azalma"])) ** (y - 2026), deger(yh["taban_oran"]))
        _SFK_ONBELLEK[k] = float((beklenen * d).sum() / (milp_yolu * d).sum())
    return _SFK_ONBELLEK[k]
