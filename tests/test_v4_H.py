"""v4 Faz H: verim bütçesi, borç LP'si, nakit şelalesi ve motor/arayüz bağlantısı."""

import numpy as np
import pandas as pd
import pytest

from src.ayarlar import config_oku
from src.finansman import borc_lp, selale, verim


def _yillik(n=10, res=2900.0, ges=1700.0, sr=0.07, sg=0.03, tohum=0):
    r = np.random.default_rng(tohum)
    return pd.DataFrame({"res_kf": res * (1 + sr * r.standard_normal(n)), "ges_kf": ges * (1 + sg * r.standard_normal(n))})


# ------------------------------------------------------------------------------------------------ verim bütçesi
def test_butce_ufuk_ve_p_siralamasi():
    cfg = config_oku()
    b = verim.butce(_yillik(), 50.0, 20.0, 0.10, cfg)
    p = b["p"]
    s1 = p[p.ufuk == 1]["sigma"].iloc[0]
    s10 = p[p.ufuk == 10]["sigma"].iloc[0]
    assert s10 < s1  # yıllık bileşenler 10 yılda söner
    o1 = p[p.ufuk == 1].set_index("ad")["oran"]
    assert o1["P50"] == 1.0 and o1["P75"] > o1["P90"] > o1["P95"] > o1["P99"]
    assert o1["P90"] == pytest.approx(1 - 1.2816 * s1, abs=1e-3)


def test_butce_hibrit_cesitlendirme():
    """ρ < 1 iken hibritin bağıl σ'sı teknolojilerin enerji ağırlıklı σ'sından küçük."""
    cfg = config_oku()
    y = _yillik(tohum=3)
    br = verim.butce(y, 50.0, 0.0, 0.10, cfg)
    bg = verim.butce(y, 0.0, 50.0, 0.10, cfg)
    bh = verim.butce(y, 50.0, 50.0, 0.10, cfg)
    s = lambda b: b["p"][b["p"].ufuk == 1]["sigma"].iloc[0]
    agirlikli = (s(br) * br["P50_mwh"] + s(bg) * bg["P50_mwh"]) / (br["P50_mwh"] + bg["P50_mwh"])
    assert s(bh) < agirlikli


def test_simulasyon_p_normal():
    x = np.random.default_rng(1).normal(100.0, 10.0, 200_000)
    p = verim.simulasyon_p(x, [0.5, 0.9, 0.99])
    assert p["P50"] == pytest.approx(100, abs=0.2)
    assert p["P90"] == pytest.approx(100 - 12.816, abs=0.3)


# ------------------------------------------------------------------------------------------------ borç LP'si
def test_lp_tek_senaryo_kapali_form():
    """Anapara kısıtı yok, tek senaryo: borç = Σ (CFADS/DSCR)·(1+i)^−k (klasik heykelsi borç)."""
    cf = np.r_[np.linspace(10e6, 8e6, 15), np.full(10, 7e6)]
    i, V = 0.08, 15
    lp = borc_lp.boyutla({"P90": cf}, {"P90": np.full(25, 1.3)}, V, i, 1e12, 0.75, anapara_kisiti=False)
    beklenen = (cf[:V] / 1.3 * (1 + i) ** -np.arange(1, V + 1)).sum()
    assert lp.borc_nom == pytest.approx(beklenen, rel=1e-6)
    assert abs(lp.bakiye[V - 1]) < 1e-3 * lp.borc_nom
    assert np.allclose(lp.dscr["P90"], 1.3)


def test_lp_baglayici_senaryo_ve_dual():
    """B senaryosu yalnız 3–5. yıllarda daha sıkı: o yıllarda B bağlar, dual (1+i)^−k."""
    N, i = 10, 0.07
    a = np.full(N, 10e6)
    b = a.copy()
    b[2:5] = 6e6
    lp = borc_lp.boyutla({"A": a, "B": b}, {"A": np.full(N, 1.3), "B": np.full(N, 1.0)}, N, i, 1e12, 0.9, anapara_kisiti=False)
    for x in lp.baglayici:
        assert x["senaryo"] == ("B" if 3 <= x["yil"] <= 5 else "A")
        assert x["dual"] == pytest.approx((1 + i) ** -x["yil"], rel=1e-6)
    assert lp.dscr["A"].min() == pytest.approx(1.3) and lp.dscr["B"].min() == pytest.approx(1.0)


def test_lp_kaldirac_tavani_orantili():
    N = 12
    cf = np.full(N, 10e6)
    serbest = borc_lp.boyutla({"P50": cf}, {"P50": np.full(N, 1.3)}, N, 0.08, 1e12, 0.75)
    capex = serbest.borc_nom / 0.75 * 0.5  # tavan serbest borcun yarısı
    lp = borc_lp.boyutla({"P50": cf}, {"P50": np.full(N, 1.3)}, N, 0.08, capex, 0.75)
    assert lp.kaldirac_bagliyor and lp.borc_nom == pytest.approx(0.75 * capex)
    assert np.allclose(lp.servis[:N], serbest.servis[:N] * lp.borc_nom / serbest.borc_nom)
    assert all(x["dual"] == 0 for x in lp.baglayici)


def test_lp_negatif_cfads_yili_vadeyi_kisaltmaz():
    """Vade içinde negatif CFADS yılı: o yıl servis 0 (faiz bakiyeye eklenir), anapara kısıtı diğer yıllarda korunur; borç
    vadenin sonuna kadar yayılır (kısıt o yılda da uygulansaydı LP borcu negatif yıldan önce kapatmak zorunda kalırdı)."""
    cf = np.full(10, 5e6)
    cf[4] = -1e6
    lp = borc_lp.boyutla({"P50": cf}, {"P50": np.full(10, 1.3)}, 10, 0.08, 1e12, 0.75, anapara_kisiti=True)
    assert lp.anapara_kisiti and lp.servis[4] == pytest.approx(0, abs=1) and lp.servis[9] > 0
    assert (lp.anapara[[0, 1, 2, 3, 5, 6, 7, 8, 9]] >= -1).all()


# ------------------------------------------------------------------------------------------------ nakit şelalesi
def _sel(cfads, servis_dscr=1.3, dsra_ay=6, n=1):
    N = cfads.shape[1]
    enf = np.ones(N)
    lp = borc_lp.boyutla({"P50": cfads[0]}, {"P50": np.full(N, servis_dscr)}, 10, 0.0, 1e12, 1.0, anapara_kisiti=False)
    kw = dict(vergi=np.zeros_like(cfads), capex_top=np.full(n, 100e6), capex_takvimi=[0.5, 0.5], enf=enf, faiz=0.0,
              vergi_orani=0.25, dsra_ay=dsra_ay, kilit_dscr=1.10, ozkaynak_maliyeti=0.1)  # fmt: skip
    return lp, kw


def test_selale_dsra_kilit_temerrut():
    N = 15
    taban = np.full((1, N), 10e6)
    lp, kw = _sel(taban)
    s = lp.servis[0]
    # Plan senaryosu: DSCR 1,3 her yıl → kilit yok, temerrüt yok
    r = selale.selale(cfads=taban, borc=lp, **kw)
    assert r["p_temerrut"] == 0 and r["p_kilit"] == 0 and r["p_dsra_kullanim"] == 0
    # Bir yıl servisin %80'i: DSRA (6 ay) açığı kapatır, kilit tetiklenir, temerrüt yok
    c = taban.copy()
    c[0, 3] = 0.8 * s
    r = selale.selale(cfads=c, borc=lp, **kw)
    assert r["p_dsra_kullanim"] == 1 and r["p_kilit"] == 1 and r["p_temerrut"] == 0
    # Üst üste iki yıl sıfır: DSRA yetmez → temerrüt
    c = taban.copy()
    c[0, 3:5] = 0.0
    r = selale.selale(cfads=c, borc=lp, **kw)
    assert r["p_temerrut"] == 1


def test_pd_hedefli_monoton():
    rng = np.random.default_rng(0)
    n, N = 4000, 15
    cfads = 10e6 * np.exp(0.25 * rng.standard_normal((n, 1)) + 0.1 * rng.standard_normal((n, N)))
    lp, kw = _sel(np.full((1, N), 10e6), n=n)
    a, r = selale.pd_hedefli(lp, 0.05, ust=2.0, cfads=cfads, **kw)
    assert r["p_temerrut"] <= 0.05 + 1e-12
    assert selale.selale(cfads=cfads, borc=selale.olcekle(lp, a * 1.05), **kw)["p_temerrut"] > 0.05


# ------------------------------------------------------------------------------------------------ motor + arayüz
@pytest.mark.veri
def test_ezine_tam_analiz_finansman(monkeypatch):
    from src import veri_katmani
    from src.kaynaklar import era5_grid

    if not veri_katmani.var_mi(f"grid/era5_tr/{era5_grid.GRID_SURUMU}/{era5_grid.dosya_adi(39.79, 26.33)}"):
        pytest.skip("Ezine ERA5 gridi yok")
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    from src.motor import KullaniciVarsayimlari, analiz_et

    s = analiz_et({"ad": "Ezine", "enlem": 39.79, "boylam": 26.33}, "tam", KullaniciVarsayimlari(), onbellek_kullan=False)
    f = s.ozet["finansman"]
    assert f and set(f["yapilar"]) <= {"tuccar", "yekdem_opsiyon", "ppa"}
    for d in f["yapilar"].values():
        assert d["borc_reel_musd"] >= 0 and 0 <= d["borc_orani"] <= 0.75 + 1e-9
        assert d["pd_hedefli"]["selale"]["p_temerrut"] <= d["pd_hedefli"]["pd_hedef"] + 1e-9
        assert 0.9 < d["kredi_p50_mc_orani"] < 1.15
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_v4_sayfa, args=(s,), default_timeout=60).run()
    assert not at.exception
    assert any("Borç kapasitesi" in m.label for m in at.metric)
    # Kapalıyken finansman yok
    s0 = analiz_et({"ad": "Ezine", "enlem": 39.79, "boylam": 26.33}, "tam", KullaniciVarsayimlari(finansman=False), onbellek_kullan=False)
    assert s0.ozet["finansman"] is None


def _v4_sayfa(s):
    import streamlit as st

    from uygulama.tasarim.stil import uygula
    from uygulama.v4_bolumler import finansman_bolumu

    st.session_state["dil"] = "TR"
    uygula()
    finansman_bolumu(s.ozet)
