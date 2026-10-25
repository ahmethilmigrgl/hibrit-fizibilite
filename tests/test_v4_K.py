"""v4 Faz K: merit order — sevk (su doldurma, depolama), arz eğrisi doğrusallığı, kalibrasyon, motor bağlantısı, derin kanibalizasyon."""

import numpy as np
import pandas as pd
import pytest

from src.merit import model as Mo
from src.merit.model import Teta

T0 = Teta(MC_L=20.0, r=1.5, kappa=1.0, v=5.0, sigma_RL=800.0, must_oran=0.4, alpha=2.0, beta=0.0)


def test_su_doldur_butce_ve_tepe_tiras():
    N = 20000 + 6000 * np.sin(np.linspace(0, 4 * np.pi, 720))
    H = Mo.su_doldur(N, butce=720 * 4000.0, h_min=1000.0, h_max=9000.0)
    assert H.sum() == pytest.approx(720 * 4000.0, rel=1e-6)
    assert H.min() >= 1000.0 - 1e-6 and H.max() <= 9000.0 + 1e-6
    assert (N - H).max() < N.max() and (N - H).std() < N.std()  # tepe tıraşlama


def test_depolama_enerji_dengesi():
    R = 20000 + 5000 * np.sin(np.linspace(0, 2 * np.pi * 30, 30 * 24)).reshape(30, 24)
    D, S = Mo.depolama_gunluk(R, P=3000.0, E=6000.0, eta=0.87)
    assert np.allclose(D.sum(1), 0.87 * S.sum(1), rtol=1e-4)
    assert (D.sum(1) <= 6000.0 + 1e-3).all() and (D <= 3000 + 1e-6).all()
    assert ((R - D + S).std(1) < R.std(1)).all()


def test_arz_egrisi_dogrusal_ve_artan():
    RL = np.linspace(-2000, 40000, 500)
    K = dict(K_L=6000.0, K_C=10000.0, K_G=17000.0)
    A, B, G = Mo.bilesenler(RL, t=T0, HR_min=1.75, tavan=150.0, **K)
    p = Mo.fiyat(RL, C=40.0, G=25.0, t=T0, HR_min=1.75, tavan=150.0, **K)
    beklenen = np.clip(np.where(RL < 0, 0, A + 40.0 * B + 25.0 * G), 0, 150.0)
    assert np.allclose(p, beklenen)
    assert np.all(np.diff(p) >= -1e-6)  # β = 0 iken fiyat artık yükte artan (arz eğrisi)


def test_dongu_indirimi_cukurda_dusurur():
    RL = np.r_[np.full(12, 15000.0), np.full(12, 28000.0)]
    gun = np.zeros(24, int)
    d = Mo.gun_derinligi(RL, np.full(24, 33000.0), gun)
    t = Teta(**{**T0.__dict__, "beta": 1.0})
    p0 = Mo.fiyat(RL, 6000, 10000, 17000, 40.0, 25.0, T0, 1.75, 150.0)
    p1 = Mo.fiyat(RL, 6000, 10000, 17000, 40.0, 25.0, t, 1.75, 150.0, derinlik=d)
    assert (p1[:12] < p0[:12]).all() and np.allclose(p1[12:], p0[12:])  # tepe saatleri (d = 0) değişmez


def test_seviyeler_bilinen_yakit_fiyatlarini_geri_bulur():
    """θ biliniyorken aylık G ve yıllık C en küçük karelerle tam geri bulunur (gürültüsüz sentetik veri)."""
    from src.merit.kalibrasyon import seviyeler

    ix = pd.date_range("2022-01-01", "2023-12-31 23:00", freq="h", tz="UTC")
    r = np.random.default_rng(0)
    RL = 18000 + 7000 * np.sin(2 * np.pi * ix.hour / 24) + 2000 * r.standard_normal(len(ix))
    d = pd.DataFrame(
        {"RL": RL, "K_L": 6000.0, "K_C": 10000.0, "K_G": 17000.0, "ay": ix.to_period("M").astype(str), "yil": ix.year}, index=ix
    )
    Gg = {a: 20 + i for i, a in enumerate(sorted(d["ay"].unique()))}
    Cc = {2022: 60.0, 2023: 45.0}
    t = Teta(**{**T0.__dict__})
    A, B, G = Mo.bilesenler(d["RL"].to_numpy(), 6000.0, 10000.0, 17000.0, t, 1.75, 500.0)
    d["P"] = A + d["yil"].map(Cc).to_numpy() * B + d["ay"].map(Gg).to_numpy() * G
    s = seviyeler(d, t, 1.75)
    assert s["C"].loc[2022] == pytest.approx(60.0, abs=0.5) and s["C"].loc[2023] == pytest.approx(45.0, abs=0.5)
    assert np.allclose([s["G"][a] for a in Gg], list(Gg.values()), atol=0.3)


def test_derin_kanibalizasyon_fiyat_sekli():
    """d > 1 (kırpmalı) şekil d < 1 ile ulaşılamayan yakalanma hedeflerine ulaşır; d ≤ 1 aralığındaki kök değişmez."""
    from src.finans.fiyat_senaryosu import _derinlik, _gunes_orani

    h = np.arange(8760) % 24
    g = np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)
    s = 1 + 0.2 * np.cos(2 * np.pi * (h - 19) / 24)
    for hedef in (0.8, 0.15):
        d = _derinlik(s, g, hedef)
        assert _gunes_orani(s, g, d) == pytest.approx(hedef, abs=1e-4)
    assert _derinlik(s, g, 0.8) < 1 < _derinlik(s, g, 0.15)


def test_motor_parametreleri_bilinen_yolu_bulur():
    from src.ayarlar import config_oku
    from src.merit.projeksiyon import motor_parametreleri

    y = np.arange(2026, 2051)
    h = np.clip(0.8 + (0.4 - 0.8) * (y - 2026) / (2036 - 2026), 0.4, 0.8)
    df = pd.DataFrame({"ort_fiyat": 60.0, "gunes_yakalanma": h}, index=y)
    mp = motor_parametreleri(df, config_oku())
    assert mp["seviye"] == pytest.approx(60.0) and mp["kanibalizasyon_taban_oran"] == pytest.approx(0.40, abs=0.011)
    assert mp["kanibalizasyon_taban_yili"] == 2036


@pytest.mark.veri
def test_merit_paketi_ve_motor_baglantisi():
    from src.ayarlar import config_oku, deger
    from src.merit.motor import senaryolar, uygula
    from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi, dogrula

    assert set(senaryolar()) == {"baz", "hizli_donusum", "yavas"}
    cfg = config_oku()
    mp = uygula(cfg, "baz")
    assert deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"])["seviye"] == pytest.approx(mp["seviye"], abs=0.01)
    assert deger(cfg["fiyat_senaryolari"]["kanibalizasyon"])["taban_oran"] == mp["kanibalizasyon_taban_oran"]
    dogrula(KullaniciVarsayimlari(fiyat_kaynagi="merit:yavas"))
    with pytest.raises(MotorHatasi):
        dogrula(KullaniciVarsayimlari(fiyat_kaynagi="merit:yok"))


@pytest.mark.veri
def test_tarihsel_veri_ve_dogrulama():
    from src.ayarlar import ISLENMIS_VERI

    if not (ISLENMIS_VERI / "uretim_turkiye_2014_guncel.parquet").exists():
        pytest.skip("EPİAŞ işlenmiş verisi yok")
    from src.merit.veri import tarihsel

    d = tarihsel(2024, 2025)
    termik = d["Lg"] + d["Cg"] + d["Gg"]
    assert abs((d["RL"] - termik).median()) < 2000  # RL ≈ termik üretim (+ ithalat/diğer)
    assert 0.17 < (d["S"].sum() / d["K_S"].mean() / 8760 / 2) < 0.25  # ulusal güneş KF


@pytest.mark.veri
def test_fiyat_sayfasi_acilir():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "uygulama" / "sayfa_fiyat.py"), default_timeout=60).run()
    assert not at.exception
