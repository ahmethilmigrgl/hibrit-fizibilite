"""v3 Faz F: ön adım (v1 çift sayım düzeltmesi, bağlantı mesafesi belirsizliği), portföy, performans izleme."""

import numpy as np
import pytest

from src.ayarlar import config_oku


@pytest.fixture(scope="module")
def cfg():
    return config_oku()


# --- Ö1: v1 çift sayım düzeltmesi
def test_v1_duzeltme_varsayilan_kapali(cfg, monkeypatch):
    from src.finans.model import Varsayimlar

    monkeypatch.delenv("V1_CIFT_SAYIM", raising=False)
    v = Varsayimlar.configten(cfg)
    assert v.arazi_res > 0 and not v.sigorta_res_haric


def test_v1_duzeltme_ortam_degiskeni(cfg, monkeypatch):
    from src.finans.model import Varsayimlar

    monkeypatch.setenv("V1_CIFT_SAYIM", "1")
    v = Varsayimlar.configten(cfg)
    assert v.arazi_res == 0 and v.sigorta_res_haric
    assert v.arazi_ges > 0  # yalnız RES kalemleri


def test_v1_duzeltme_sigorta_yalniz_res_payindan_duser(cfg, monkeypatch):
    from dataclasses import replace

    from src.finans.model import Varsayimlar
    from src.risk.degerleme import capex_kalemleri
    from src.risk.tasarim import Tasarim

    monkeypatch.delenv("V1_CIFT_SAYIM", raising=False)
    v = Varsayimlar.configten(cfg)
    t = Tasarim(ad="x", ges_mw=0, res_mw=58.8, bess_mw=30, bess_mwh=60)
    c = capex_kalemleri(t, v)
    v2 = replace(v, sigorta_res_haric=True)
    top = sum(c.values())
    fark = v.sigorta_oran * top - v2.sigorta_oran * (top - c["res"])
    assert fark == pytest.approx(0.0035 * 1.15e6 * 58.8)


# --- Ö2: bağlantı mesafesi belirsizliği
def test_baglanti_belirsizligi_carpan_ortalamasi_bir():
    from src.cbs.baglanti import carpan_ornekle

    bel = {"mu_ln": -0.3, "sigma_ln": 0.9, "sabit_usd": 5e6, "hat_usd": 3e6}
    bel["beklenen_usd"] = bel["sabit_usd"] + bel["hat_usd"] * np.exp(-0.3 + 0.81 / 2)
    m = carpan_ornekle(bel, 200_000, 1)
    assert m.mean() == pytest.approx(1.0, abs=0.01)
    assert m.min() >= bel["sabit_usd"] / bel["beklenen_usd"] - 1e-9  # sabit kalemler belirsiz değil
    assert np.all(carpan_ornekle(None, 5, 1) == 1)


@pytest.mark.veri
def test_baglanti_belirsizligi_uzak_sahada_genis(cfg):
    from src.cbs import baglanti

    ez = baglanti.maliyet(39.79, 26.33, 50.0, cfg)["belirsizlik"]
    gu = baglanti.maliyet(38.92, 37.42, 50.0, cfg)["belirsizlik"]
    assert ez["p10_usd"] < ez["beklenen_usd"] < ez["p90_usd"]
    assert (gu["p90_usd"] - gu["p10_usd"]) > 5 * (ez["p90_usd"] - ez["p10_usd"])


# --- F3: portföy MILP'i
def _kucuk_veri(S: int = 400, tohum: int = 0):
    import pandas as pd

    from src.portfoy.model import Veri

    rng = np.random.default_rng(tohum)
    ortak = rng.normal(0, 8, S)  # ortak piyasa şoku
    satir, V = [], []
    for j, (kod, _bolge) in enumerate([("A", "Ege"), ("B", "Ege"), ("C", "Marmara"), ("D", "Akdeniz")]):
        for d, (ad, olcek) in enumerate([("MILP", 1.0), ("Küçük", 0.6)]):
            V.append(olcek * (2.0 + j - 1.5 * d + ortak + rng.normal(0, 6, S)))
            satir.append({"kod": kod, "tasarim": ad, "res_mw": 40 * olcek, "N": int(10 * olcek), "capex_musd": 60 * olcek, "e_npv": 0.0,
                          "kullanilabilirlik": 0.975, "kendi_kullanilabilirlik": 0.974})  # fmt: skip
    ad = pd.DataFrame({"kod": list("ABCD"), "bolge": ["Ege", "Ege", "Marmara", "Akdeniz"], "trafo_ad": list("WXYZ"),
                       "enlem": [38.5, 38.9, 40.5, 36.8], "boylam": [27.1, 27.5, 27.9, 35.0], "turbin_mw": 4.2, "res_kf": 0.38})  # fmt: skip
    return Veri(tas=pd.DataFrame(satir), ad=ad, V=np.array(V), lojistik=None)


@pytest.mark.parametrize("lam,butce", [(0.0, 130.0), (0.3, 130.0), (0.1, 250.0)])
def test_portfoy_milp_kaba_kuvvetle_ayni(cfg, lam, butce):
    from src.portfoy import analiz as PA
    from src.portfoy import model as M

    v = _kucuk_veri()
    ay = M.Ayar(lam=lam, butce_musd=butce, bolge_kapasite_mw=None, trafo_kapasite_mw=None,
                sinerji={"isletme": True, "havuz": True, "indirim": True, "ulastirma": False})  # fmt: skip
    sp = M._sinerji_parametreleri(v, cfg)
    r = M.coz(v, ay, cfg, sp)
    b = PA.kaba_kuvvet(v, list("ABCD"), ay, sp)
    assert r["amac"] == pytest.approx(b["amac"], abs=1e-3)


def test_cvar_dogrusallastirmasi_kesin(cfg):
    from src.portfoy import model as M

    v = _kucuk_veri()
    r = M.coz(v, M.Ayar(lam=0.4, butce_musd=200, bolge_kapasite_mw=None, trafo_kapasite_mw=None), cfg)
    if len(r["secim"]):
        assert r["cvar_dogrusal"] == pytest.approx(r["cvar"], abs=1e-6)


def test_bolge_kapasitesi_ve_butce_kisitlari(cfg):
    from src.portfoy import model as M

    v = _kucuk_veri()
    r = M.coz(v, M.Ayar(lam=0.0, butce_musd=1000, bolge_kapasite_mw=50, trafo_kapasite_mw=None), cfg)
    assert r["secim"]["kod"].isin(["A", "B"]).sum() <= 1  # Ege'de 50 MW → tek saha
    r2 = M.coz(v, M.Ayar(lam=0.0, butce_musd=70, bolge_kapasite_mw=None, trafo_kapasite_mw=None), cfg)
    assert r2["capex_musd"] <= 70 + 1e-9


def test_yatirim_yapmamak_uygun(cfg):
    from src.portfoy import model as M

    v = _kucuk_veri()
    v.V -= 40.0  # tüm tasarımlar kötü
    r = M.coz(
        v,
        M.Ayar(
            lam=0.0,
            bolge_kapasite_mw=None,
            trafo_kapasite_mw=None,
            sinerji=dict.fromkeys(("isletme", "havuz", "indirim", "ulastirma"), False),
        ),
        cfg,
    )
    assert len(r["secim"]) == 0 and r["e_npv"] == 0


def test_cesitlendirme_ayristirmasi_toplami():
    from src.portfoy import analiz as PA

    rng = np.random.default_rng(1)
    S = 3000
    L = rng.normal(58, 5, S)
    o = {"L10": L, "capex_res": rng.normal(1, 0.05, S), "senaryo": np.where(rng.random(S) < 0.5, "baz", "hizli")}
    V = np.vstack([0.8 * (L - 58) + rng.normal(0, 3, S) for _ in range(4)])
    c = PA.cesitlendirme(V, o)
    top = c["var_ortak_piyasa"] + c["var_sahaya_ozgu"] + c["var_hava_korelasyonu"] + c["var_artik"]
    assert top == pytest.approx(c["sigma_portfoy"] ** 2, rel=1e-6)
    assert c["pay_ortak_piyasa"] > 0.5 and c["cesitlendirme_sigma"] > 0


def test_havuz_stok_olcek_ekonomisi(cfg):
    from src.portfoy import sinerji as S

    g = 4.2 * 0.37 * 24 * 58
    ayri = 10 * S.stok_maliyeti(8, g, cfg)["maliyet_yil"]
    havuz = S.stok_maliyeti(80, g, cfg)["maliyet_yil"]
    assert havuz < ayri  # 10 × 8 türbin ayrı stok > 80 türbinlik ortak stok
    assert S.ebo(0.015, 10, 100, 0) == pytest.approx(0.015 * 10 * 100 / 365, rel=1e-6)  # S = 0: EBO = ΛL


# --- F4: SPC
def test_spc_kartlari_ve_arl():
    from src.izleme import spc

    rng = np.random.default_rng(3)
    Z = rng.standard_normal((3000, 300))
    par = spc.kalibre(Z, 48, 0.2, 0.5)
    assert 2.0 < par["shewhart"] < 2.6  # normal dağılımda tek yönlü ARL0 = 48 → ~2,04 (P(z < −L) = 1/48)
    assert spc.arl(Z, "ewma", par["ewma"]) == pytest.approx(48, rel=0.15)
    Z1 = Z - 1.0  # 1σ kayma
    assert spc.arl(Z1, "cusum", par["cusum"]) < spc.arl(Z1, "shewhart", par["shewhart"])  # küçük kaymada CUSUM daha hızlı


def test_ewma_cusum_eksik_donem():
    from src.izleme import spc

    z = np.array([0.0, np.nan, -3.0, -3.0])
    e, _ = spc.ewma(z, 0.2, 2.0)
    assert e[1] == e[0] and e[2] == pytest.approx(-0.6)
    c, a = spc.cusum(z, 0.5, 3.0)
    assert c[-1] == pytest.approx(5.0) and a[-1]


@pytest.mark.veri
def test_sayfalar_aciliyor():
    from streamlit.testing.v1 import AppTest

    from src.ayarlar import KOK

    for p in ("uygulama/sayfa_performans.py", "uygulama/sayfa_portfoy.py"):
        at = AppTest.from_file(str(KOK / p), default_timeout=180).run()
        assert not at.exception, p
