"""
v2 regresyon: genelleştirilmiş hat Ezine sahasıyla (kalibre mod: CDS ERA5 + v1 ay × saat matrisi) v1.0.0'ı yeniden üretir.
"""

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ayarlar import ISLENMIS_VERI, config_oku
from src.saha import ezine, saha_cfg

V1_PROFIL = ISLENMIS_VERI / "ezine_profiller_2014_2023.parquet"
veri_var = pytest.mark.skipif(not V1_PROFIL.exists(), reason="İşlenmiş veri yok (repoya girmez)")


def _v1_anahtarlari(cfg: dict) -> dict:
    c = copy.deepcopy(cfg)
    c.pop("_saha", None)
    c.pop("v2", None)
    return c


def test_ezine_saha_cfg_v1_ile_ayni():
    """Sahaya özgü config, Ezine için v1 config'inin tüm anahtarlarını aynen korur (bağlantı açıkça 50 MW)."""
    v1 = config_oku()
    v2 = saha_cfg(ezine(), v1)
    a, b = _v1_anahtarlari(v1), _v1_anahtarlari(v2)
    b["saha"]["sebeke_baglanti_kapasitesi"]["value"] = a["saha"]["sebeke_baglanti_kapasitesi"]["value"]
    assert a == b


@pytest.mark.veri
@veri_var
def test_ezine_profil_v1_ile_birebir():
    from src.uretim import genel

    s = ezine()
    df, _ = genel.profil_uret(s, saha_cfg(s), ruzgar_kaynagi="cds", kalibrasyon="v1")
    v1 = pd.read_parquet(V1_PROFIL).set_index("zaman_utc")
    o = df.index.intersection(v1.index)
    assert len(o) == len(v1) == 87648
    for k in ("ges_kf", "res_kf"):
        assert np.abs(df.loc[o, k] - v1.loc[o, k]).max() < 1e-12


@pytest.mark.veri
@veri_var
def test_ezine_ortam_npv_v1_ile_ayni():
    """Genelleştirilmiş Ortam (saha config + v2 profil) ile v1 Ortam aynı tasarımın NPV'sini verir (yalnız RES 58,8)."""
    from src.finans.veri import uretim_profili
    from src.risk.degerleme import nakit_akislari
    from src.risk.tasarim import Tasarim
    from src.uretim import genel

    spec = importlib.util.spec_from_file_location("gy", Path(__file__).parents[1] / "src" / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gy)
    s = ezine()
    c = saha_cfg(s)
    df, _ = genel.profil_uret(s, c, ruzgar_kaynagi="cds", kalibrasyon="v1")
    yol = genel.profil_kaydet(df, s, "regresyon", 2014, 2023)
    o1, o2 = gy.Ortam(), gy.Ortam(cfg=c, uretim=uretim_profili(yol))
    t = Tasarim("A", 58.8, 0.0)
    n1 = nakit_akislari(t, o1.tablo(t), o1.c, o1.beklenen_girdi(58.0))["npv"][0]
    n2 = nakit_akislari(t, o2.tablo(t), o2.c, o2.beklenen_girdi(58.0))["npv"][0]
    assert o2.baglanti == 50.0
    assert abs(n1 - n2) < 1.0  # USD


@pytest.mark.veri
@veri_var
def test_ezine_kapasite_milp_v1_ile_ayni():
    """Kapasite MILP'i (24 temsilî gün, yan hizmet + dengesizlik + YEK-G) iki Ortam'da aynı tasarım ve amaç değerini verir."""
    from src.finans.veri import uretim_profili
    from src.uretim import genel

    spec = importlib.util.spec_from_file_location("gy", Path(__file__).parents[1] / "src" / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gy)
    s = ezine()
    c = saha_cfg(s)
    df, _ = genel.profil_uret(s, c, ruzgar_kaynagi="cds", kalibrasyon="v1")
    o1, o2 = gy.Ortam(), gy.Ortam(cfg=c, uretim=uretim_profili(genel.profil_kaydet(df, s, "regresyon", 2014, 2023)))
    r1, r2 = (o.milp({"yh", "dz", "yekg"}, "baz", K=24) for o in (o1, o2))
    for k in ("RES [MW]", "GES [MWac]", "BESS [MW]", "BESS [MWh]"):
        assert abs(r1[k] - r2[k]) < 1e-6, k
    assert abs(r1["NPV tahmini [M USD]"] - r2["NPV tahmini [M USD]"]) < 1e-6
