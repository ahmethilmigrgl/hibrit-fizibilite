"""Batarya LP'leri: şarj durumu (SOC) dengesi ve sınırları çözümde sağlanıyor mu?"""
import numpy as np
import pytest

pyo = pytest.importorskip("pyomo.environ")

from src.optimizasyon.batarya import arbitraj_coz
from src.risk.isletme import IsletmeLP
from src.risk.tasarim import Tasarim

TOL = 1e-5


def test_arbitraj_soc_dengesi_ve_sinirlar():
    saat = np.arange(72)
    fiyat = 50 + 30 * np.sin(2 * np.pi * saat / 24)
    P, E, verim = 10.0, 20.0, 0.88
    df, _ = arbitraj_coz(fiyat, P, E, verim, yipranma=2.0)
    eta = np.sqrt(verim)
    s0 = 0.5 * E
    onceki = np.r_[s0, df.soc.to_numpy()[:-1]]
    assert np.allclose(df.soc, onceki + eta * df.sarj - df.desarj / eta, atol=TOL)
    assert df.soc.between(-TOL, E + TOL).all()
    assert df.sarj.between(-TOL, P + TOL).all() and df.desarj.between(-TOL, P + TOL).all()
    assert df.soc.iloc[-1] == pytest.approx(s0, abs=TOL)
    assert (df.fiyat * (df.desarj - df.sarj)).sum() > 0     # salınımlı fiyatta arbitraj kârlı


def test_isletme_lp_kisitlari():
    n, rng = 96, np.random.default_rng(0)
    t = Tasarim("test", res_mw=40.0, ges_mw=0.0, bess_mw=10.0, bess_mwh=20.0, sebeke_mw=25.0, yan_hizmet=True)
    eta, h = np.sqrt(0.88), 1.0
    lp = IsletmeLP(t, eta=eta, yipranma=2.0, teias_e=3.8, yekg=0.0, rezerv_tavan=30.0, enerji_saat=h, ppa_fiyat=50.0, n=n)
    A = 40.0 * rng.uniform(0, 1, n)
    p = 50 + 30 * np.sin(2 * np.pi * np.arange(n) / 24)
    a = rng.uniform(0, 15, n)
    r = lp.coz(A, p, a, 0.0)
    s = np.array([lp.m.s[i].value for i in range(n)])
    y, k, c, d, rr = (r[x] for x in "ykcdr")
    assert np.allclose(s, np.roll(s, 1) + eta * c - d / eta, atol=TOL)        # döngüsel SOC dengesi
    assert np.allclose(y + k + c, A, atol=TOL)                                # üretim dengesi
    assert (y + d <= t.sebeke_mw + TOL).all()                                 # şebeke bağlantısı
    assert (c + rr <= t.bess_mw + TOL).all() and (d + rr <= t.bess_mw + TOL).all()
    assert (s >= h * rr - TOL).all() and (s + h * rr <= t.bess_mwh + TOL).all()  # rezerv için enerji payı
    assert (s >= -TOL).all() and (s <= t.bess_mwh + TOL).all()


def test_yekdem_modunda_arbitraj_yok():
    """YEKDEM (φ = 1, deşarj da sözleşmeli fiyattan): kesinti yoksa batarya döngü yapmamalı; kesinti varsa saklamalı."""
    n = 96
    t = Tasarim("test", res_mw=40.0, ges_mw=0.0, bess_mw=10.0, bess_mwh=20.0, sebeke_mw=50.0)
    lp = IsletmeLP(t, eta=np.sqrt(0.88), yipranma=2.0, teias_e=3.8, yekg=0.0, rezerv_tavan=0.0, enerji_saat=1.0,
                   ppa_fiyat=55.0, n=n, desarj_sozlesmeli=True)
    p = 50 + 40 * np.sin(2 * np.pi * np.arange(n) / 24)          # güçlü spot salınımı
    r = lp.coz(np.full(n, 30.0), p, np.zeros(n), 1.0)               # üretim < bağlantı: kesinti yok
    assert r["d"].sum() < 1e-6                                      # arbitraj teşviki yok
    A = np.where(np.arange(n) % 24 < 6, 60.0, 30.0)                  # günde 6 saat bağlantı aşımı
    r2 = lp.coz(A, p, np.zeros(n), 1.0)
    assert r2["d"].sum() > 1.0                                      # kesilecek enerji saklanıp sonra veriliyor
