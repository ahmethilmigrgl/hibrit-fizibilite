"""v3 Faz E: AHP/CR, TOPSIS, AUC, ulaştırma LP'si, mesafeye bağlı bağlantı maliyeti, CBS dışlamaları ve katmanlar."""

import json
from pathlib import Path

import numpy as np
import pytest

from src.ayarlar import config_oku, deger
from src.cbs import cok_kriterli as CK

KOK = Path(__file__).resolve().parents[1]
ATLAS = KOK / "data" / "atlas"


@pytest.fixture(scope="module")
def cfg():
    return config_oku()


# --- AHP / TOPSIS / AUC (veri gerektirmez) ---
def test_ahp_ders_kitabi_ornegi():
    # Saaty tipi 3×3 örnek: ağırlıklar ≈ (0,648; 0,230; 0,122), CR ≈ 0,003
    A = CK.ikili_matris({(0, 1): 3, (0, 2): 5, (1, 2): 2}, 3)
    a = CK.ahp(A)
    assert a["agirlik"] == pytest.approx([0.648, 0.230, 0.122], abs=2e-3)
    assert a["CR"] < 0.01 and a["tutarli"]


def test_ahp_tutarsiz_matris_uyarilir():
    A = CK.ikili_matris({(0, 1): 9, (1, 2): 9, (0, 2): 1 / 9}, 3)  # A ≫ B ≫ C ama C ≫ A
    assert CK.ahp(A)["CR"] > 0.10 and not CK.ahp(A)["tutarli"]


def test_ahp_karsiliklilik_denetimi():
    with pytest.raises(ValueError):
        CK.ahp(np.array([[1, 3], [3, 1]]))


def test_tam_tutarli_profil_cr_sifir():
    from src.cbs import kriterler as KR

    for p in KR.PROFILLER:
        a = CK.ahp(KR.profil_matrisi(p))
        assert a["CR"] == pytest.approx(0, abs=1e-9)
        s = np.array([KR.PROFILLER[p][2][k] for k in KR.KRITERLER], float)
        assert a["agirlik"] == pytest.approx(s / s.sum(), abs=1e-9)


def test_topsis_baskin_alternatif_birinci():
    X = np.array([[50.0, 2.0], [60.0, 5.0], [55.0, 10.0]])  # 1. satır her iki maliyet kriterinde en iyi
    c = CK.topsis(X, np.array([0.5, 0.5]), np.array([False, False]))
    assert np.argmax(c) == 0 and np.argmin(c) == 2
    assert np.all((c >= 0) & (c <= 1))


def test_topsis_fayda_yonu():
    X = np.array([[0.30], [0.40]])
    assert np.argmax(CK.topsis(X, np.array([1.0]), np.array([True]))) == 1
    assert np.argmax(CK.topsis(X, np.array([1.0]), np.array([False]))) == 0


def test_auc_sinirlari():
    y = np.array([0, 0, 1, 1], bool)
    assert CK.auc(np.array([1, 2, 3, 4]), y) == 1.0
    assert CK.auc(np.array([4, 3, 2, 1]), y) == 0.0
    assert CK.auc(np.array([1, 1, 1, 1]), y) == 0.5
    fp, tp = CK.roc(np.array([1, 2, 3, 4]), y)
    assert fp[0] == 0 and tp[-1] == 1 and np.all(np.diff(fp) >= 0)


def test_dayaniklilik_olasilik():
    rng = np.random.default_rng(1)
    X = rng.uniform(1, 2, (30, 3))
    p = CK.dayaniklilik(X, np.array([0.5, 0.3, 0.2]), np.array([True, False, False]), K=5, n=100)
    assert p.sum() == pytest.approx(5.0) and p.max() <= 1


# --- Ulaştırma LP'si ---
def test_ulastirma_lp_talep_ve_kapasite():
    from src.cbs.lojistik import ulastirma

    birim = {("kule", "A", 0): 10.0, ("kule", "B", 0): 20.0, ("kule", "A", 1): 30.0, ("kule", "B", 1): 15.0}
    talep = {("kule", 0): 8.0, ("kule", 1): 5.0}
    r = ulastirma(birim, talep, {("kule", "A"): 6.0})
    x = r["x"]
    assert x.get(("kule", "A", 0), 0) == pytest.approx(6.0)  # ucuz kaynak kapasitede bağlayıcı
    assert x.get(("kule", "B", 0), 0) == pytest.approx(2.0)
    assert x.get(("kule", "B", 1), 0) == pytest.approx(5.0)
    assert r["maliyet"] == pytest.approx(6 * 10 + 2 * 20 + 5 * 15)


def test_ulastirma_lp_kapasitesiz_en_ucuz():
    from src.cbs.lojistik import ulastirma

    r = ulastirma({("kanat", "A", 0): 5.0, ("kanat", "B", 0): 4.0}, {("kanat", 0): 3.0}, {})
    assert r["x"] == {("kanat", "B", 0): pytest.approx(3.0)}


# --- Bağlantı ve katmanlar (veri gerektirir) ---
@pytest.mark.veri
def test_gerilim_kurali(cfg):
    from src.cbs.baglanti import gerilim

    assert gerilim(20, cfg) == pytest.approx(34.5)
    assert gerilim(50, cfg) == pytest.approx(154)
    assert gerilim(500, cfg) == pytest.approx(400)


@pytest.mark.veri
def test_baglanti_maliyeti_mesafeyle_artar(cfg, monkeypatch):
    from src.cbs import baglanti

    yakin = baglanti.maliyet(39.79, 26.33, 50.0, cfg)  # Ezine: TEİAŞ Ezine TM yakın
    assert yakin["kv"] == pytest.approx(154)
    assert yakin["hedef_trafo"]["kv"] >= 154
    assert sum(yakin["kalemler_usd"].values()) == pytest.approx(yakin["toplam_usd"])
    uzak = dict(yakin["hedef_trafo"])
    monkeypatch.setattr(baglanti, "en_yakin_trafo", lambda e, b, k: {**uzak, "km": uzak["km"] + 30})
    assert baglanti.maliyet(39.79, 26.33, 50.0, cfg)["toplam_usd"] > yakin["toplam_usd"]


@pytest.mark.veri
def test_cbs_dislamalari_yerlesimi_daraltir(cfg):
    from src.cbs import katmanlar
    from src.yerlesim.alan import SahaAlani

    serbest = SahaAlani(39.79, 26.33, 2.0, []).adaylar()
    kisitli = SahaAlani(39.79, 26.33, 2.0, katmanlar.dislama_katmanlari(cfg, 120, 141)).adaylar()
    assert len(kisitli) == len(serbest)
    assert (kisitli["dislanan"] != "").sum() > (serbest["dislanan"] != "").sum()


@pytest.mark.veri
def test_tamponlar_turbin_boyutuyla(cfg):
    from src.cbs.katmanlar import tampon_m

    a, b = tampon_m(cfg, 94, 112), tampon_m(cfg, 120, 141)
    assert b["otoyol"] > a["otoyol"] and a["yerlesim"] == b["yerlesim"]


@pytest.mark.veri
def test_saha_lojistigi_plan(cfg):
    from src.cbs.lojistik import saha_lojistigi

    lj = saha_lojistigi(39.79, 26.33, 10, cfg, "E-141/4200", 4.2)
    assert {p["bilesen"] for p in lj["plan"]} == set(deger(cfg["v3"]["lojistik"])["bilesenler"])
    for c in {p["bilesen"] for p in lj["plan"]}:
        assert sum(p["set"] for p in lj["plan"] if p["bilesen"] == c) == pytest.approx(10)
    assert 0 < lj["usd_mw"] < 200_000 and lj["teslim_ay"] > 0


@pytest.mark.veri
def test_atlas_katmanlari_kucuk_ve_gecerli():
    for ad in ("katman_agir_yol", "katman_hat", "katman_koruma", "katman_goc"):
        p = ATLAS / f"{ad}.geojson"
        assert p.stat().st_size < 3e6
        g = json.loads(p.read_text())
        assert g["type"] == "FeatureCollection" and len(g["features"]) > 0


@pytest.mark.veri
def test_hucre_tablosu_tam():
    import pandas as pd

    d = pd.read_parquet(ATLAS / "cbs_hucre.parquet")
    assert len(d) == 1464
    assert d["baglanti_usd_mw"].notna().mean() > 0.99
    assert d["mevcut_res"].sum() > 100


def test_deger_fonksiyonu_standardizasyonu():
    import pandas as pd

    from src.cbs import kriterler as KR

    d = pd.DataFrame({"basabas_en_iyi": [50.0, 70.0, 95.0], "trafo_km": [0.0, 20.0, 50.0]})
    V, f = KR.matris(d, ["ekonomi", "sebeke"], standart=True)
    assert f.all()
    assert V[:, 0] == pytest.approx([1.0, 0.5, 0.0])  # 50 en iyi, 90 kabul edilemez (kırpılır)
    assert V[:, 1] == pytest.approx([1.0, 0.5, 0.0])  # 0 km en iyi, 40 km kabul edilemez
    assert np.argmax(CK.topsis(V, np.array([0.5, 0.5]), f, vektor=False)) == 0


@pytest.mark.veri
def test_cok_kriterli_sayfa_profil_ve_ikili():
    from streamlit.testing.v1 import AppTest

    a = AppTest.from_file(str(KOK / "uygulama" / "sayfa_cok_kriterli.py"), default_timeout=180).run()
    assert not a.exception
    cr = next(m for m in a.metric if m.label.startswith("Tutarlılık oranı"))
    assert cr.value == "0,000"  # hazır profil tam tutarlı
    a.segmented_control(key="ck_kip").set_value("ikili").run()
    assert not a.exception
    a.select_slider(key="ck_ekonomi_sebeke").set_value(1 / 9).run()  # dengeli profille çelişen yargı → CR artar
    assert not a.exception
    assert len(a.warning) >= 1
