"""
v3 Faz D testleri: iz modeli (PyWake ile aynı formül), yerleşim kısıtları ve yöntemler, kapasite MILP'inde iz verimi,
hava pencereleri, ayrık olay simülasyonunun tekrarlanabilirliği ve arıza oranları, bakım çizelgesi MILP'i, baz stok özdeşliği,
motor seçenekleri ve arayüz bölümleri.
"""

import warnings

import numpy as np
import pytest

from src.ayarlar import config_oku, deger
from src.yerlesim import alan as A
from src.yerlesim import iz, yontemler
from src.yerlesim.ruzgar_gulu import akis_tablosu
from src.yerlesim.turbin import kutuphane_turbini

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def turbin():
    return kutuphane_turbini("E-141/4200", 120.0)


@pytest.fixture(scope="module")
def akis():
    rng = np.random.default_rng(0)
    v = rng.weibull(2.0, 20000) * 8.0
    yon = np.where(rng.random(20000) < 0.6, rng.normal(30, 20, 20000), rng.uniform(0, 360, 20000)) % 360
    return akis_tablosu(v, yon, 36, 0.5, kaynak="test")


def _problem(turbin, akis, N=6, yaricap=1500.0):
    g = np.arange(-yaricap, yaricap + 1, 250.0)
    x, y = np.meshgrid(g, g)
    x, y = x.ravel(), y.ravel()
    ic = np.hypot(x, y) <= yaricap
    x, y = x[ic], y[ic]
    m = 1 + 0.03 * np.sin(x / 700) * np.cos(y / 900)
    ak = akis.kaba(36, np.r_[0.0, 3.0, np.arange(4.5, 16.0, 1.5), 18.0, 25.0, 35.0])
    c = iz.cift_tablosu(x, y, m, ak, turbin, 0.1)
    C = A.elips_catisma(x, y, turbin.D, 5.0, 3.0, akis.eksen)
    return yontemler.Problem(x, y, C, c, N, akis.eksen, turbin.D)


# ------------------------------------------------------------------------------------------------------------------ iz
def test_bastankhah_pywake_ile_ayni(turbin):
    """İki türbin, rüzgâr yönünde 5D: vekil formül PyWake BastankhahGaussianDeficit ile aynı etkin hızı verir."""
    import xarray as xr
    from py_wake.site import XRSite

    ws, D, ti = 8.0, turbin.D, 0.1
    x = np.array([0.0, 5 * D])
    ds = xr.Dataset({"P": (("wd", "ws"), np.ones((1, 1))), "TI": ti}, coords={"wd": [270.0], "ws": [ws]})
    wf = iz.pywake_modeli(XRSite(ds), turbin.pywake(), "bastankhah", ti)
    sim = wf(x, np.zeros(2), wd=[270.0], ws=[ws])
    d = iz.bastankhah_delta(np.array(5 * D), np.array(0.0), turbin.ct_v(np.array(ws)), D, iz.k_ti(ti))
    assert abs(float(sim.WS_eff.values[1].ravel()[0]) - ws * (1 - float(d))) < 1e-6


def test_iz_akis_yonu(turbin):
    """Rüzgâr batıdan (270°) eserken doğudaki türbin izde kalır, batıdaki kalmaz."""
    fx, fy = iz.akis_vektoru(np.array([270.0]))
    assert fx[0] > 0.99 and abs(fy[0]) < 1e-9
    d_dogu = iz.bastankhah_delta(np.array(700.0), np.array(0.0), np.array(0.8), turbin.D, 0.042)
    d_bati = iz.bastankhah_delta(np.array(-700.0), np.array(0.0), np.array(0.8), turbin.D, 0.042)
    assert d_dogu > 0.05 and d_bati == 0


def test_vekil_referansla_tutarli(turbin, akis):
    """Hızlı vekil (36 yön, kaba hız kutuları) yıllık enerjiyi PyWake referansına %1,5 içinde verir."""
    p = _problem(turbin, akis, N=8)
    S = yontemler.acgozlu(p).S
    ref = iz.referans(p.x[S], p.y[S], p.cift.m[S], turbin, akis, 0.1)
    assert abs(p.amac(S) / ref.E_ic.sum() - 1) < 0.015
    assert 0 < 1 - ref.E_ic.sum() / ref.E_serbest.sum() < 0.15  # kara santrali tipik iç iz aralığı


def test_ikili_kayip_ve_egri(turbin, akis):
    p = _problem(turbin, akis, N=10)
    assert (p.cift.a >= 0).all() and np.allclose(np.diag(p.cift.a), 0)
    _, oran = yontemler.acgozlu(p, 10, egri=True)
    assert oran[1] == pytest.approx(0, abs=1e-12)
    assert np.all(np.diff(oran[1:]) >= -0.003)  # iç içe yerleşimde iz kaybı N ile (neredeyse) artar


# ------------------------------------------------------------------------------------------------------------ yerleşim
def test_elips_kisiti():
    """Hâkim eksen kuzey–güney, D = 100 m: eksen boyunca 5D = 500 m, dik yönde 3D = 300 m."""
    x = np.array([0.0, 0.0, 350.0, 0.0, 250.0])
    y = np.array([0.0, 450.0, 0.0, 600.0, 0.0])
    C = A.elips_catisma(x, y, 100.0, 5.0, 3.0, 0.0)
    assert (C == C.T).all() and not C.diagonal().any()
    assert C[0, 1]  # kuzeyde 450 m < 500 m → çatışır
    assert not C[0, 2]  # doğuda 350 m > 300 m → çatışmaz
    assert not C[0, 3]  # kuzeyde 600 m > 500 m
    assert C[0, 4]  # doğuda 250 m < 300 m
    C90 = A.elips_catisma(x, y, 100.0, 5.0, 3.0, 90.0)  # eksen doğu–batı: roller değişir
    assert not C90[0, 1] and C90[0, 2]


@pytest.mark.parametrize("yontem", ["acgozlu", "milp", "ga", "sa", "izgara"])
def test_yontemler_olurlu(turbin, akis, yontem):
    p = _problem(turbin, akis, N=6)
    f = {
        "acgozlu": lambda: yontemler.acgozlu(p),
        "milp": lambda: yontemler.milp(p, 20.0),
        "ga": lambda: yontemler.genetik(p, 0, nufus=12, nesil=15),
        "sa": lambda: yontemler.tavlama(p, 0, adim=300),
        "izgara": lambda: yontemler.duzenli_izgara(p),
    }[yontem]
    r = f()
    assert p.olurlu_mu(r.S)
    assert r.enerji == pytest.approx(p.amac(r.S))


def test_milp_glover_kesin(turbin, akis):
    """MILP amacı = Σ E_i x_i − Σ_i Σ_j a_ij x_i x_j (Glover doğrusallaştırması seçilen çözümde kesin)."""
    p = _problem(turbin, akis, N=5)
    r = yontemler.milp(p, 20.0)
    S = r.S
    beklenen = p.cift.E_serbest[S].sum() - p.cift.a[np.ix_(S, S)].sum()
    assert r.ayrinti["amac_dogrusal"] == pytest.approx(beklenen, rel=1e-6)
    assert r.ayrinti["ust_sinir"] >= r.ayrinti["amac_dogrusal"] - 1e-6


def test_tavlama_tekrarlanabilir(turbin, akis):
    p = _problem(turbin, akis, N=6)
    a, b = yontemler.tavlama(p, 3, adim=300), yontemler.tavlama(p, 3, adim=300)
    assert np.array_equal(a.S, b.S) and a.enerji == b.enerji


# ---------------------------------------------------------------------------------------------------- kapasite MILP + iz
def test_kapasite_milp_iz_verimi():
    from src.finans.model import Varsayimlar
    from src.optimizasyon.kapasite import Ekonomi, Segment, kapasite_coz

    cfg = config_oku()
    v = Varsayimlar.configten(cfg)
    rng = np.random.default_rng(1)
    seg = [
        Segment(
            fiyat=rng.uniform(40, 90, 48),
            ges=np.clip(np.sin(np.linspace(0, 6.28, 48)), 0, None) * 0.6,
            res=rng.uniform(0.2, 0.6, 48),
            agirlik=8760 / 48,
        )
    ]
    eko = Ekonomi(10.0, 0.1, 5.0, 1.0, 1.0, 60000.0, 50000.0, 20000.0, 15000.0, 5000.0, 4.0, 60.0)
    opt = {"turbin_gucu": 4.2, "turbin_azami": 12, "ges_azami_mw": 0.0, "bess_sure_aralik": [1, 6], "verim_gd": 0.88}
    verim = [1.0] + [1.0 - 0.006 * n for n in range(1, 13)]
    r = kapasite_coz(seg, v, eko, 50.0, {**opt, "iz_verim": verim}, {}, zaman_siniri=60)
    assert r["N"] >= 1 and r["İz verimi"] == pytest.approx(verim[r["N"]], abs=1e-6)
    r0 = kapasite_coz(seg, v, eko, 50.0, opt, {}, zaman_siniri=60)
    assert r0["Amaç (yıllık eşdeğer) [M USD]"] >= r["Amaç (yıllık eşdeğer) [M USD]"] - 1e-9  # iz kaybı amacı artıramaz


# ----------------------------------------------------------------------------------------------------------------- bakım
def test_hava_penceresi():
    from src.bakim.hava import HavaZaman

    v = np.full(24 * 10, 5.0)
    v[24 * 2 : 24 * 4] = 20.0  # 2.–4. gün fırtına
    hz = HavaZaman(v, 15.0, (8, 18), 6, [10.0])
    # 0. gün 05 UTC = 08 TSİ: 10 saatlik vardiya; 25 saat iş → 3. vardiya günü, ama 2.–3. gün fırtınalı → 5. günde biter
    t = hz.is_bitir(5.0, 25.0)
    assert t > 4 * 24
    assert hz.kaldirma(0.0, 10.0) == 5.0
    assert hz.kaldirma(2 * 24 + 1, 10.0) >= 4 * 24


@pytest.fixture(scope="module")
def bakim_girdi():
    p = deger(config_oku()["v3"]["bakim"])
    rng = np.random.default_rng(5)
    kf = np.clip(rng.weibull(1.6, (3, 8760)) * 0.3, 0, 1)
    v = rng.weibull(2.0, (3, 8760)) * 7.5
    return p, kf, v


def test_des_tekrarlanabilir(bakim_girdi):
    from src.bakim.des import Girdi, tekrar

    p, kf, v = bakim_girdi
    g = Girdi(8, 4.2, np.ones(8), kf, v, np.full(8760, 60.0), 30, p, "takvim")
    a, b, c = tekrar(g, 11), tekrar(g, 11), tekrar(g, 12)
    assert a["A_enerji"] == b["A_enerji"] and a["gider"] == b["gider"]
    assert a["A_enerji"] != c["A_enerji"]
    assert 0.93 < a["A_enerji"] < 0.995


def test_des_ariza_oranlari_girdiyle_tutarli(bakim_girdi):
    from src.bakim.des import Girdi, simule

    p, kf, v = bakim_girdi
    g = Girdi(10, 4.2, np.ones(10), kf, v, np.full(8760, 60.0), 30, p, "takvim")
    r = simule(g, 12, 0)
    o = r["ariza_orani"]
    for a, x in p["alt_sistemler"].items():
        for k, ad in enumerate(("lam_kucuk", "lam_buyuk")):
            if x[ad] >= 0.05:
                assert o[f"{a}|{k}"] == pytest.approx(x[ad], rel=0.15), (a, k)
    assert o["disli_kutusu|2"] == pytest.approx(p["alt_sistemler"]["disli_kutusu"]["lam_degisim"], rel=0.35)


def test_weibull_olcek_yenileme():
    from src.bakim.des import weibull_olcek

    eta = weibull_olcek(0.015, 2.5, 30)
    rng = np.random.default_rng(9)
    c = np.cumsum(rng.weibull(2.5, (40000, 10)) * eta, axis=1)
    assert (c < 30).sum(1).mean() == pytest.approx(0.015 * 30, rel=0.03)


def test_cizelge_milp_kisitlar():
    from src.bakim import cizelge

    rng = np.random.default_rng(2)
    c = 1000 + 600 * np.cos(2 * np.pi * np.arange(365) / 365) + rng.normal(0, 30, 365)
    p = np.where(np.arange(365) < 90, 4, 2)
    pay = rng.uniform(0.9, 1.1, 9)
    m = cizelge.coz(pay, c, p, 1)
    assert m["durum"] == "Optimal" and len(m["gun"]) == 9
    assert cizelge.kapasite_ihlali(m["gun"], p, 1) == 0
    assert all(d + p[d] <= 365 for d in m["gun"])
    assert m["maliyet"] <= cizelge.bahar_kampanyasi(pay, c, p, 1)["maliyet"] + 1e-6
    assert m["maliyet"] <= cizelge.esit_dagitim(pay, c, p, 1)["maliyet"] + 1e-6


def test_baz_stok_ozdesligi():
    """Kapalı form (k'ıncı talep = (k−S)'inci siparişin varışı) olay bazlı stok benzetimiyle aynı bekleme sürelerini verir."""
    import heapq

    from src.bakim.stok import bekleme_kaybi

    rng = np.random.default_rng(4)
    L = 2000.0
    d = np.sort(rng.uniform(0, 3 * 8760, 25))
    cum = np.r_[0.0, np.cumsum(np.ones(8760))]  # saat başına 1 birim gelir → kayıp = toplam bekleme saati
    for S in (0, 1, 2, 3):
        kayip, _ = bekleme_kaybi([(t, t, 0) for t in d], S, L, 0.0, cum, np.ones(1))
        # olay benzetimi: eldeki stok, bekleyen talepler (FIFO), sipariş varışları
        olay = [(t, 1, k) for k, t in enumerate(d)]  # (zaman, tür: 0 varış / 1 talep, no)
        heapq.heapify(olay)
        stok, kuyruk, bekleme = S, [], 0.0
        while olay:
            t, tur, k = heapq.heappop(olay)
            if tur == 1:
                heapq.heappush(olay, (t + L, 0, k))
                if stok > 0:
                    stok -= 1
                else:
                    kuyruk.append(t)
            elif kuyruk:
                bekleme += t - kuyruk.pop(0)
            else:
                stok += 1
        assert kayip == pytest.approx(bekleme, rel=1e-9, abs=1e-6), S


def test_taban_kayip():
    from src.yerlesim.analiz import taban_kayip

    cfg = config_oku()
    k = deger(cfg["v3"]["kayip"])
    lam = taban_kayip(cfg)
    assert (1 - lam) * (1 - k["iz_referansi"]) * k["kalibrasyon_kullanilabilirligi"] == pytest.approx(0.88)


# ------------------------------------------------------------------------------------------------------------------ motor
def test_v3_varsayimlari():
    from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi, dogrula

    assert KullaniciVarsayimlari().v3_aktif()
    assert not KullaniciVarsayimlari(kalibrasyon="v1").v3_aktif()
    assert not KullaniciVarsayimlari(yerlesim_bakim=False).v3_aktif()
    for k, v in (("yerlesim_yontemi", "x"), ("bakim_modeli", "x"), ("bakim_stratejisi", "x")):
        with pytest.raises(MotorHatasi):
            dogrula(KullaniciVarsayimlari(**{k: v}))


@pytest.mark.veri
def test_ezine_tam_analiz_v3_bolumleri(monkeypatch):
    """Küçük tam analiz: yerleşim ve bakım çıktıları dolu, yerleşim olurlu, arayüz iki bölümü çizer."""
    from src import veri_katmani
    from src.kaynaklar import era5_grid

    if not veri_katmani.var_mi(f"grid/era5_tr/{era5_grid.GRID_SURUMU}/{era5_grid.dosya_adi(39.79, 26.33)}"):
        pytest.skip("Ezine ERA5 gridi yok")
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    from src.motor import KullaniciVarsayimlari, analiz_et

    s = analiz_et({"ad": "Ezine", "enlem": 39.79, "boylam": 26.33}, "tam", KullaniciVarsayimlari())
    y, b = s.ozet["yerlesim"], s.ozet["bakim"]
    assert y["N"] == len(y["turbinler"]) >= 1 and 0 <= y["ic_iz"] < 0.2
    assert 0.9 < b["A_enerji"] < 1.0 and b["cizelge"]["kapasite_ihlali"] == 0 and b["cizelge"]["kazanc_bahar"] >= 0
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_v3_sayfa, args=(s,), default_timeout=60).run()
    assert not at.exception
    etiket = {m.label for m in at.metric}
    assert {"İç iz kaybı", "Kullanılabilirlik (enerji)", "Çizelge kazancı"} <= etiket


def _v3_sayfa(s):
    import streamlit as st

    from uygulama.tasarim.stil import uygula
    from uygulama.v3_bolumler import bakim_bolumu, yerlesim_bolumu

    st.session_state["dil"] = "TR"
    uygula()
    yerlesim_bolumu(s.ozet, s.saha)
    bakim_bolumu(s.ozet)


@pytest.mark.veri
def test_sigmayan_sabit_tasarim_uyarili(monkeypatch):
    """1 km yarıçapa sığmayan 20 türbinlik sabit tasarım: sığan sayı yerleştirilir, tetikleyicide uyarı çıkar."""
    from src import veri_katmani
    from src.kaynaklar import era5_grid

    if not veri_katmani.var_mi(f"grid/era5_tr/{era5_grid.GRID_SURUMU}/{era5_grid.dosya_adi(39.79, 26.33)}"):
        pytest.skip("Ezine ERA5 gridi yok")
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    from src.motor import KullaniciVarsayimlari, analiz_et

    kv = KullaniciVarsayimlari(yerlesim_yaricap_km=1.0, sabit_tasarim={"res_mw": 84.0, "ges_mw": 0, "bess_mw": 0, "bess_mwh": 0})
    s = analiz_et({"ad": "Ezine", "enlem": 39.79, "boylam": 26.33}, "tam", kv, onbellek_kullan=False)
    y = s.ozet["yerlesim"]
    assert y["alan_yetersiz"] and y["N"] < 20 == y["N_istenen"]
    assert "sığmıyor" in s.ozet["tetikleyiciler"][0]["tr"]
