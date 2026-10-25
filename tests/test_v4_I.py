"""v4 Faz I: mevcut santrale GES/batarya ekleme — santral listesi, CSV ölçekleme, artımsal config, analiz ve arayüz."""

import numpy as np
import pandas as pd
import pytest

from src.ekleme.analiz import artimsal_cfg, csv_olcekle
from src.ekleme.santraller import liste


def test_santral_listesi_anonim_ve_dolu():
    x = liste()
    assert len(x) >= 50
    assert "ad" not in x.columns  # ad taşınmaz
    assert x.index.str.match(r"^S\d{3}$").all()
    assert (x["kurulu_mw"] > 0).all() and x[["turbin", "gobek", "epias_id"]].notna().all().all()


def test_artimsal_cfg_ortak_maliyetleri_sifirlar():
    e = artimsal_cfg({"insaat_suresi": 1, "baslangic_yili": 2027})
    for k in (
        "teknoloji.res.capex",
        "teknoloji.res.opex_sabit",
        "teknoloji.res.arazi",
        "teknoloji.sebeke.capex",
        "teknoloji.sebeke.teias_kapasite_bedeli",
    ):
        assert e[k] == 0.0
    assert e["finans.sokum_net"]["res"] == 0.0 and e["finans.sokum_net"]["ges"] > 0
    assert e["proje.capex_takvimi"] == [1.0]


def test_csv_olcekleme_ay_saat():
    """Model profili %20 artırılıp 'ölçüm' olarak verilince ölçekli profil ≈ 1,2 × model (ay × saat oranı)."""
    ix = pd.date_range("2014-01-01", "2023-12-31 23:00", freq="h")
    r = np.random.default_rng(0)
    kf = pd.Series(np.clip(0.3 + 0.15 * np.sin(2 * np.pi * ix.hour / 24) + 0.1 * r.standard_normal(len(ix)), 0, 0.8), index=ix)
    olcum = (kf * 1.2 * 50.0).loc["2020":"2021"]
    yeni, b = csv_olcekle(kf, olcum, 50.0)
    assert b["hucre"] == 288
    assert b["olcekli_kf"] / b["model_kf"] == pytest.approx(1.2, rel=0.02)
    assert yeni.max() <= 1.0


def test_csv_kisa_veri_reddedilir():
    from src.motor.varsayimlar import MotorHatasi

    ix = pd.date_range("2014-01-01", "2023-12-31 23:00", freq="h")
    kf = pd.Series(0.3, index=ix)
    with pytest.raises(MotorHatasi):
        csv_olcekle(kf, (kf * 50).iloc[: 24 * 30], 50.0)


@pytest.mark.veri
def test_ekleme_analizi_kucuk(monkeypatch):
    from src import veri_katmani
    from src.kaynaklar import era5_grid

    s = liste().iloc[0]
    if not veri_katmani.var_mi(f"grid/era5_tr/{era5_grid.GRID_SURUMU}/{era5_grid.dosya_adi(s.enlem, s.boylam)}"):
        pytest.skip("ERA5 gridi yok")
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    from src.ekleme.analiz import EklemeVarsayimlari, ekleme_analizi

    kod = liste().index[0]
    r = ekleme_analizi(EklemeVarsayimlari(kod=kod, yekdem_bitis_yili=2029), onbellek_kullan=False)
    sa = r["santral"]
    assert abs(sa["model_kf"] - sa["gozlenen_kf"]) < 0.03  # santralin kendi kalibrasyonu
    assert set(r["metrik"]) == {"tuccar", "yekdem_opsiyon", "ppa"}
    for m in r["metrik"].values():
        assert np.isfinite(m["e_npv"]) and m["se"] <= m["se_bagimsiz"] * 1.05  # ortak rastgele sayılar standart hatayı büyütmez
    e = r["ges_egrisi"]
    assert e[0]["artimsal_npv"] == 0 and all(x["basabas_capex"] > 0 for x in e[1:])
    # Başabaş CAPEX boyutla azalır (kesinti + kanibalizasyon)
    assert e[1]["basabas_capex"] >= e[-1]["basabas_capex"]
    # Sabit tasarım: yalnız batarya
    r2 = ekleme_analizi(EklemeVarsayimlari(kod=kod, sabit_ekleme={"ges_mw": 0, "bess_mw": 0, "bess_mwh": 0}, gelir_yapilari=("tuccar",)),
                        onbellek_kullan=False)  # fmt: skip
    assert abs(r2["metrik"]["tuccar"]["e_npv"]) < 1e-9  # ekleme yoksa artımsal NPV sıfır (aynı senaryolar)


@pytest.mark.veri
def test_ekleme_sayfasi_acilir():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "uygulama" / "sayfa_ekleme.py"), default_timeout=60).run()
    assert not at.exception
    assert any("Santral" in s.label for s in at.selectbox)


def test_csv_mcp_ruzgarli_yillari_santral_farki_sanmaz():
    """Ölçüm yılları (2020–21) ortalamadan %20 rüzgârlı; santral modelden %10 iyi. Aynı saatler üzerinden oran (MCP) → 1,10;
    10 yıllık ortalamayla kıyaslasaydı ~1,32 çıkardı."""
    ix = pd.date_range("2014-01-01", "2023-12-31 23:00", freq="h")
    kf = pd.Series(0.3, index=ix)
    kf.loc["2020":"2021"] = 0.36
    _, b = csv_olcekle(kf, (kf * 1.1 * 40.0).loc["2020":"2021"], 40.0)
    assert b["mcp"] and b["olcekli_kf"] / b["model_kf"] == pytest.approx(1.10, rel=1e-6)
