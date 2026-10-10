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
