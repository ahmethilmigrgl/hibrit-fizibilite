"""Finansal hesaplar: IRR, vergi zararı mahsubu, LCOE ve vektörize nakit akışı — elle hesaplanmış küçük örneklerle."""

from dataclasses import replace

import numpy as np
import pytest

from src.ayarlar import config_oku
from src.finans.model import Varsayimlar, _vergi_hesapla, lcoe_hesapla
from src.risk.degerleme import Sabitler, irr_vektor, nakit_akislari
from src.risk.tasarim import ALANLAR, Tasarim


def test_irr_el_hesabi():
    # −100 + 60/(1+r) + 60/(1+r)² = 0  →  r = 0,130662
    irr = irr_vektor(np.array([[-100.0, 60.0, 60.0]]))
    assert irr[0] == pytest.approx(0.130662, abs=1e-5)


def test_irr_kok_yoksa_nan():
    assert np.isnan(irr_vektor(np.array([[10.0, 10.0, 10.0]]))[0])


def test_vergi_zarar_mahsubu():
    # 100 zarar sonraki yılların matrahından düşülür: 50 tamamen, 80'in 30'u vergilenir
    assert _vergi_hesapla(np.array([-100.0, 50.0, 80.0]), 0.25, 5) == pytest.approx([0.0, 0.0, 7.5])


def test_vergi_zarar_suresi_dolar():
    # Mahsup süresi 1 yıl: 0. yılın zararı 3. yıla taşınamaz
    assert _vergi_hesapla(np.array([-100.0, 0.0, 0.0, 50.0]), 0.25, 1) == pytest.approx([0.0, 0.0, 0.0, 12.5])


def test_lcoe_el_hesabi():
    # İnşaat 1 yıl (CAPEX 100), 2 işletme yılı (maliyet 10, enerji 1), WACC %10
    pay = 100 / 1.1 + 10 / 1.1**2 + 10 / 1.1**3
    payda = 1 / 1.1**2 + 1 / 1.1**3
    assert lcoe_hesapla(np.array([100.0]), np.array([10.0, 10.0]), np.array([1.0, 1.0]), 0.10) == pytest.approx(pay / payda)


@pytest.fixture
def sade_varsayimlar():
    """Vergi, işletme gideri, bozunma ve dengesizlik sıfır → NPV elle hesaplanabilir."""
    v = Varsayimlar.configten(config_oku())
    return replace(
        v,
        vergi=0.0,
        capex_sebeke=0.0,
        opex_res=0.0,
        arazi_res=0.0,
        sigorta_oran=0.0,
        teias_kapasite=0.0,
        teias_enerji=0.0,
        dengesizlik={"ges": 0.0, "res": 0.0},
        degr_res=0.0,
        eszamanlilik_res=0.0,
        sokum={"ges": 0.0, "res": 0.0, "bess": 0.0},
    )


def test_nakit_akisi_npv_el_hesabi(sade_varsayimlar):
    v = sade_varsayimlar
    c = Sabitler(v=v, yekg=0.0, ppa_fiyat=0.0, ppa_pay=0.0, ppa_vade=0, dz_azami=0.0, dz_doyum=1.0, tavan_carpan=0.7, pi=0.025)
    t = Tasarim("test", res_mw=10.0, ges_mw=0.0)
    T = np.zeros((1, 1, 1, 1, 1, 1, len(ALANLAR)))
    T[..., ALANLAR.index("gelir_res_q")] = 1000.0  # Σ y·q (birim fiyat şekliyle) → gelir = L × 1000
    T[..., ALANLAR.index("E_res")] = 1000.0
    tablo = {"T": T, "h": np.array([0.6]), "m": np.array([1.0]), "a": np.array([1.0]), "ppa": np.array([0.0])}
    N, nb = v.omur, v.insaat_suresi
    girdi = {
        "w": np.zeros((1, N), int),
        "s": np.zeros((1, N), int),
        "h": np.full((1, N), 0.6),
        "m": np.ones((1, N)),
        "a": np.ones((1, N)),
        "L": np.full((1, N), 50.0),
        "tavan": np.zeros((1, N), bool),
        **{k: np.ones(1) for k in ["capex_res", "capex_ges", "capex_bess", "opex", "bozunma"]},
    }
    r = nakit_akislari(t, tablo, c, girdi)
    capex = 10.0 * v.capex_res
    beklenen = -capex * sum(p / (1 + v.wacc) ** (j + 1) for j, p in enumerate(v.capex_takvimi)) + 50.0 * 1000.0 * sum(
        (1 + v.wacc) ** -(nb + k) for k in range(1, N + 1)
    )
    assert r["npv"][0] == pytest.approx(beklenen, rel=1e-9)
    assert r["cfads"][0] == pytest.approx(np.full(N, 50_000.0))
