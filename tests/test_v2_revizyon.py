"""v2 Revizyon R (ilk 10 makullüğü, modern türbin, adalar, tam analiz hızı): aktarım büzülmesi ve kıyı benzerliği,
ada tespiti, highspy işletme LP'sinin Pyomo sürümüyle eşdeğerliği, MILP N aralığı, arayüzde ada uyarısı."""

import numpy as np
import pytest

from src.kaynaklar import gwa, sinirlar

paket_var = pytest.mark.skipif(not (gwa.PAKET.exists() and sinirlar.PAKET.exists()), reason="data/atlas paketleri yok")


@paket_var
def test_r_buzulme_tek_komsuyu_ulusala_ceker():
    from src.atlas import aktarim

    R = np.full((12, 24), 1.30)
    ulusal = aktarim.ulusal_artik()
    yari = aktarim.r_duzelt(R, 1, {"r_buzulme_n0": 1})
    assert np.allclose(yari, (R + ulusal) / 2)
    uc = aktarim.r_duzelt(R, 1, {"r_buzulme_n0": 2})
    assert np.allclose(uc, (R + 2 * ulusal) / 3)
    assert np.allclose(aktarim.r_duzelt(R, 3, {"r_buzulme_n0": 0}), R)  # kapalı
    sinirli = aktarim.r_duzelt(R, 1, {"r_buzulme_n0": 0, "r_sinir": [0.85, 1.15]})
    assert abs(sinirli.mean() - 1.15) < 1e-9


@paket_var
def test_kiyi_orani_20km_kirilmasini_kaldirir():
    from src.atlas import aktarim
    from src.ayarlar import config_oku

    cfg = config_oku()
    tan = aktarim.tanimlayicilar(41.246, 27.996)  # Çerkezköy hücresi, kıyıya ~21,7 km
    adlar = set(aktarim.komsular(41.246, 27.996, tan, cfg)["ad"])
    assert "YAMAÇTEPE RES" in adlar
    assert adlar & {"SİLİVRİ RES", "TAYAKADIN RES", "ÇANTA RES"}  # ikili sınıfta (< 20 km) dışlanıyordu


@paket_var
def test_ada_tespiti():
    from src.kaynaklar.adalar import ada_bilgisi

    assert ada_bilgisi(40.17, 25.85)["ilce"] == "Gökçeada"
    assert ada_bilgisi(39.83, 26.05)["ilce"] == "Bozcaada"
    assert ada_bilgisi(40.62, 27.60)["ilce"] == "Marmara"
    assert ada_bilgisi(42.02, 35.15) is None  # Sinop yarımadası (kıstak)
    assert ada_bilgisi(39.33, 26.65) is None  # Cunda (köprü)
    assert ada_bilgisi(39.79, 26.33) is None  # anakara


def _amac(r: dict, p: np.ndarray, phi: float, ah: np.ndarray, ds: bool) -> float:
    pd_ = ((1 - phi) * p + phi * 55) if ds else p
    return float((((1 - phi) * p + phi * 55 + 1 - 3.8) * r["y"]).sum() + (pd_ + 1 - 3.8 - 5) @ r["d"] + ah @ r["r"])


def test_hizli_isletme_lp_pyomo_ile_ayni():
    from src.risk.isletme import IsletmeLP, IsletmeLPHizli
    from src.risk.tasarim import Tasarim

    t = Tasarim("t", 54.6, 0.0, 31.0, 60.0, sebeke_mw=50.0, yan_hizmet=True, dengesizlik_azaltim=True, yekg=True)
    sab = dict(eta=0.92, yipranma=5.0, teias_e=3.8, yekg=1.0, rezerv_tavan=30.0, enerji_saat=1.0, ppa_fiyat=55.0, n=168)
    rng = np.random.default_rng(3)
    for ds in (False, True):
        a, b = IsletmeLP(t, **sab, desarj_sozlesmeli=ds), IsletmeLPHizli(t, **sab, desarj_sozlesmeli=ds)
        for phi in (0.0, 0.7):
            A = np.clip(rng.gamma(1.2, 20, 168), 0, 54.6)
            p = np.clip(58 + 25 * np.sin(np.arange(168) / 24 * 2 * np.pi) + rng.normal(0, 8, 168), 0, None)
            ah = np.full(168, 6.0)
            ra, rb = a.coz(A, p, ah, phi), b.coz(A, p, ah, phi)
            assert abs(_amac(ra, p, phi, ah, ds) - _amac(rb, p, phi, ah, ds)) <= 1e-6 * abs(_amac(ra, p, phi, ah, ds))


def test_milp_n_araligi_parametresi():
    import inspect

    from src.optimizasyon import kapasite as K

    assert "n_aralik" in inspect.signature(K.kapasite_coz).parameters


@paket_var
def test_arayuz_ada_uyarisi(monkeypatch):
    import streamlit_folium
    from streamlit.testing.v1 import AppTest

    from tests.test_v2_uygulama import APP

    monkeypatch.setattr(streamlit_folium, "st_folium", lambda *a, **k: {"last_clicked": {"lat": 40.17, "lng": 25.85}})
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("denizaltı kablosu" in w.value for w in at.warning)
