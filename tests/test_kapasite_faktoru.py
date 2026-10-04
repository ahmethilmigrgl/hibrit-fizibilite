"""Kapasite faktörleri 0-1 aralığında mı? Sentetik hava verisiyle model fonksiyonları + (varsa) işlenmiş profiller."""

import numpy as np
import pandas as pd
import pytest

from src.ayarlar import ISLENMIS_VERI, config_oku


@pytest.fixture(scope="module")
def cfg():
    return config_oku()


def test_ges_kf_sentetik(cfg):
    pytest.importorskip("pvlib")
    from src.uretim.gunes import gunes_kapasite_faktoru

    idx = pd.date_range("2020-06-21 00:10", periods=48, freq="h", tz="UTC")
    tepe = np.clip(np.sin(np.pi * ((idx.hour + 3 - 6) % 24) / 14), 0, None) * ((idx.hour + 3) % 24).isin(range(6, 20))
    veri = pd.DataFrame(
        {"poa_direct": 900 * tepe, "poa_sky_diffuse": 150 * tepe, "poa_ground_diffuse": 20 * tepe, "temp_air": 28.0, "wind_speed": 2.0},
        index=idx,
    )
    meta = {
        "inputs": {
            "location": {"latitude": 39.8, "longitude": 26.3, "elevation": 50.0},
            "mounting_system": {"fixed": {"slope": {"value": 32}}},
        }
    }
    kf = gunes_kapasite_faktoru(veri, meta, cfg["uretim"]["gunes"])
    assert kf.between(0, 1).all()
    assert kf.max() > 0.5 and kf.min() == 0.0


def test_res_kf_sentetik(cfg):
    pytest.importorskip("windpowerlib")
    from src.uretim.ruzgar import ruzgar_kapasite_faktoru

    hiz = np.linspace(0, 32, 200)
    idx = pd.date_range("2020-01-01", periods=len(hiz), freq="h", tz="UTC")
    df = pd.DataFrame({"u10": 0.8 * hiz, "v10": 0.0, "u100": hiz, "v100": 0.0, "t2m": 288.15, "sp": 101325.0}, index=idx)
    kf, _ = ruzgar_kapasite_faktoru(df, cfg["uretim"]["ruzgar"], katsayi=1.0, zaman_hizasi="anlik")
    assert kf.between(0, 1).all()
    assert kf.iloc[0] == 0.0 and kf.max() > 0.8


@pytest.mark.veri
@pytest.mark.skipif(
    not (ISLENMIS_VERI / "ezine_profiller_2014_2023.parquet").exists(),
    reason="İşlenmiş veri yok (repoya girmez; src/01_uretim_profilleri.py ile üretilir)",
)
def test_islenmis_profiller_0_1():
    df = pd.read_parquet(ISLENMIS_VERI / "ezine_profiller_2014_2023.parquet")
    for s in ["ges_kf", "res_kf"]:
        assert df[s].between(0, 1).all(), s
    assert 0.15 < df["ges_kf"].mean() < 0.30 and 0.25 < df["res_kf"].mean() < 0.50
