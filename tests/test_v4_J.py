"""v4 Faz J: YEKA katkı payı açık artırması — sıra istatistiği MLE, strateji, fiyat aşaması, lot değerlemesi ve arayüz."""

import numpy as np
import pytest

from src.yeka import muzayede as M


def _sentetik(L=120, tohum=0, delta=500_000.0, gamma=-100_000.0, s=150_000.0):
    rng = np.random.default_rng(tohum)
    v = rng.normal(-700_000, 100_000, L)
    mw = rng.uniform(80, 500, L)
    n = rng.integers(4, 25, L)
    y = np.array([np.sort(rng.normal(v[i] + delta + gamma * np.log(mw[i] / M.MW_REF), s, n[i]))[-2] for i in range(L)])
    g = y >= M.ALT  # seçilim: yalnız tabana inen (ikinci en yüksek ≥ başlangıç) yarışmalarda katkı payı gözlenir
    return y[g], v[g], mw[g], n[g]


def test_mle_parametreleri_geri_bulur():
    """Sentetik veriden (gerçek δ, γ, s bilinen) en çok olabilirlik parametreleri makul doğrulukla geri bulur."""
    y, v, mw, n = _sentetik()
    t = M.tahmin(y, v, mw, n, True)
    assert t["delta"] == pytest.approx(500_000, abs=60_000)
    assert t["gamma"] == pytest.approx(-100_000, abs=60_000)
    assert t["s"] == pytest.approx(150_000, rel=0.25)


def test_aic_buyukluk_terimini_secer():
    y, v, mw, n = _sentetik(tohum=1)
    assert M.tahmin(y, v, mw, n, True)["aic"] < M.tahmin(y, v, mw, n, False)["aic"]


def test_ikinci_en_yuksek_istekli_sayisiyla_artar():
    a = np.median(M.ikinci_en_yuksek(0.0, 1.0, 4, 50_000))
    b = np.median(M.ikinci_en_yuksek(0.0, 1.0, 12, 50_000))
    assert b > a > 0  # 4 istekli: ikinci en yüksek ~0,3σ; 12: ~1,1σ


def test_strateji_baskin_strateji_degerde_cekilmek():
    """Değerimiz kesin (sd ~ 0) iken beklenen fazlayı büyüten çekilme eşiği değerimize eşit (İngiliz artırması)."""
    V = np.full(1000, 300_000.0)
    s = M.strateji(V, mu_rakip=200_000, s=100_000, n_istekli=4, cekilme=np.linspace(10_000, 600_000, 60), R=40_000)
    assert s["en_iyi"]["cekilme"] == pytest.approx(300_000, abs=15_000)
    p = [e["p_kazanma"] for e in s["egri"]]
    assert all(np.diff(p) >= -1e-12)  # kazanma olasılığı eşikle artar


def test_fiyat_asamasi():
    """İkinci en yüksek değer < 0 → fiyat tabanın üstünde kapanır (eğimle); ≥ 0 → tabanda, katkı payı ≥ başlangıç."""
    ik = np.array([-100_000.0, 50_000.0, 5_000.0])
    r = M.fiyat_asamasi(ik, egim_eur_mw_sent=200_000.0, taban=3.5, tavan=5.5, baslangic=10_000.0)
    assert r["p_taban"] == pytest.approx(2 / 3)
    assert r["katki_p10"] >= 10_000.0


@pytest.mark.veri
def test_lot_degerleme_ve_sozlesme_yapisi(monkeypatch):
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    from src.yeka.deger import katki_carpani, lot_degerle

    r = lot_degerle("R25-Balıkesir-3", onbellek_kullan=False)
    assert r["sozlesme_yillari"] == [2033, 2052]
    assert 0.2 < r["res_kf"] < 0.5 and r["baglanti_kaynak"] == "teias_gorusu"
    b = r["basabas_eur_mw"]
    assert b["p10"] < b["p50"] < b["p90"]
    # Fiyat 1 sent artınca değer artar
    r2 = lot_degerle("R25-Balıkesir-3", onbellek_kullan=False, fiyat_sent=4.5)
    assert r2["basabas_eur_mw"]["ortalama"] > b["ortalama"]
    from src.ayarlar import config_oku

    assert 0.7 < katki_carpani(config_oku()) < 1.0


@pytest.mark.veri
def test_yeka_sayfasi_acilir():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "uygulama" / "sayfa_yeka.py"), default_timeout=60).run()
    assert not at.exception
