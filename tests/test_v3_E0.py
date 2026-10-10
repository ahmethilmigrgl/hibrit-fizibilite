"""v3 Ö1–Ö2: işletme modeli (FSA / kendi bakımı), başabaş filo, kayıp tablosunun tutarlılığı."""

import numpy as np
import pytest

from src.ayarlar import config_oku
from src.bakim import isletme
from src.uretim import kayip


@pytest.fixture(scope="module")
def cfg():
    return config_oku()


def test_fsa_opex_kalemleri(cfg):
    o = isletme.opex(cfg, "fsa", 42.0)
    assert o["usd_mw_yil"] == pytest.approx(1000 * (isletme.fsa_usd_kw(cfg) + isletme.sahip_usd_kw(cfg)))
    assert "fsa" in o["kalemler_usd_kw_yil"] and "bop_bakimi" in o["kalemler_usd_kw_yil"]


def test_kendi_opex_organizasyon_olcekle_azalir(cfg):
    g = {
        "sabit_ekip": 180000.0,
        "duzeltici_malzeme": 50000.0,
        "vinc": 25000.0,
        "onleyici_malzeme": 42000.0,
        "cms": 8400.0,
        "stok_tutma": 0.0,
    }
    kucuk = isletme.opex(cfg, "kendi", 29.4, g)["kalemler_usd_kw_yil"]["organizasyon_sabit"]
    buyuk = isletme.opex(cfg, "kendi", 294.0, g)["kalemler_usd_kw_yil"]["organizasyon_sabit"]
    assert kucuk == pytest.approx(10 * buyuk)


def test_fsa_garantisi_tabandir(cfg):
    A = np.array([0.95, 0.96, 0.98, 0.99])
    g = isletme.ayar(cfg)["fsa"]["kullanilabilirlik_garantisi"]
    assert isletme.kullanilabilirlik(cfg, "fsa", A) == pytest.approx(np.maximum(A, g).mean())
    assert isletme.kullanilabilirlik(cfg, "kendi", A) == pytest.approx(A.mean())
    assert isletme.kullanilabilirlik(cfg, "fsa", A) >= isletme.kullanilabilirlik(cfg, "kendi", A)


def test_basabas_filo(cfg):
    P = 4.2
    c = 0.5 * isletme.fsa_usd_kw(cfg) * P * 1000  # kendi türbin maliyeti FSA'nın yarısı
    b = isletme.basabas_filo(cfg, P, {7: c, 140: c})
    org = isletme.ayar(cfg)["kendi"]["organizasyon_sabit_usd_yil"]
    assert b["N_basabas"] == int(np.ceil(org / (isletme.fsa_usd_kw(cfg) * P * 1000 - c)))
    assert b["N_basabas_fsa_yuksek"] <= b["N_basabas"] <= (b["N_basabas_fsa_dusuk"] or 10**9)


@pytest.mark.parametrize("W,A", [(None, None), (0.031, 0.974), (0.08, 0.95)])
def test_kayip_tablosu_tutarli(cfg, W, A):
    t = kayip.tablo(cfg, W, A)
    assert t["tutarli"]
    if W is None:  # atlas referansı v2'nin toplu kaybını birebir verir
        assert t["toplam_saha"] == pytest.approx(t["lumped_v2"])
    assert {s["kategori"] for s in t["satirlar"]} >= {"iz", "kullanilabilirlik", "elektrik", "turbin_performansi", "kalibrasyon_farki"}
