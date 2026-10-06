"""v2 web uygulaması (Streamlit AppTest): açılış, üç saha seçim yolu, hatalı girdiler, paylaşım bağlantısı, istek sınırı,
hızlı tarama ve küçük ayarlı tam analiz (son ikisi yerel grid verisi ister: veri işareti)."""

import os
import time
from pathlib import Path

import pytest

from src.kaynaklar import gwa, sinirlar

KOK = Path(__file__).resolve().parents[1]
APP = str(KOK / "app.py")
paket_var = pytest.mark.skipif(not (gwa.PAKET.exists() and sinirlar.PAKET.exists()), reason="data/atlas paketleri yok")


def _uygulama(zaman=120):
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(APP, default_timeout=zaman)


def _koordinat(at, e, b):
    at.number_input(key="giris_enlem").set_value(e)
    at.number_input(key="giris_boylam").set_value(b)
    return at.button(key="koordinat_sec").click().run()


def _kutular(at) -> list[str]:
    return [x.value for x in [*at.success, *at.warning, *at.error, *at.info]]


def _gercek_hatalar(at) -> list[str]:
    """Öneri kutusu (rafa kaldır → st.error) dışındaki hata kutuları."""
    return [x.value for x in at.error if not x.value.startswith("**Öneri:**")]


def _grid_var(e, b) -> bool:
    from src import veri_katmani
    from src.kaynaklar import era5_grid, pvgis_grid

    return veri_katmani.var_mi(f"grid/era5_tr/v1/{era5_grid.dosya_adi(e, b)}") and veri_katmani.var_mi(
        f"grid/pvgis_tr/v1/{pvgis_grid.dosya_adi(e, b)}"
    )


@paket_var
def test_acilis_ve_sayfalar():
    at = _uygulama().run()
    assert not at.exception
    assert at.title[0].value.startswith("Türkiye hibrit")
    for sayfa in ("uygulama/sayfa_yontem.py", "uygulama/sayfa_vaka.py"):
        from streamlit.testing.v1 import AppTest

        a = AppTest.from_file(str(KOK / sayfa), default_timeout=120).run()
        assert not a.exception, sayfa


@paket_var
def test_koordinat_ile_secim_ve_saha_karti():
    at = _koordinat(_uygulama().run(), 39.79, 26.33)
    assert not at.exception
    assert any(m.value.startswith("#### Çanakkale / Ezine") for m in at.markdown)
    etiket = {m.label: m.value for m in at.metric}
    assert etiket["Güven seviyesi"] == "yüksek"
    assert any("SARES" in c.value for c in at.caption)  # dayandığı komşu santraller


@paket_var
def test_il_ilce_adaylari():
    at = _uygulama().run()
    at.selectbox(key="il").set_value("Çanakkale").run()
    at.selectbox(key="ilce").set_value("Ezine").run()
    assert len(at.radio(key="aday_sec").options) >= 3
    at.button(key="aday_buton").click().run()
    assert not at.exception
    assert at.session_state["secim"]["kaynak"] == "il_ilce"
    assert any(m.value.startswith("#### Çanakkale / Ezine") for m in at.markdown)


@paket_var
def test_haritadan_tiklama(monkeypatch):
    import streamlit_folium

    monkeypatch.setattr(streamlit_folium, "st_folium", lambda *a, **k: {"last_clicked": {"lat": 38.63, "lng": 26.51}})
    at = _uygulama().run()
    assert not at.exception
    assert at.session_state["secim"]["kaynak"] == "harita"
    assert any(w.value.startswith("Tahmin tek bir komşu") for w in at.warning)  # Karaburun: tek komşu uyarısı


@paket_var
@pytest.mark.parametrize("e, b", [(40.2, 25.6), (36.3, 38.0)])  # Ege denizi; Suriye
def test_hatali_girdi_kara_disi(e, b):
    at = _koordinat(_uygulama().run(), e, b)
    assert not at.exception
    assert any("Türkiye karası dışında" in x.value for x in at.error)
    assert not [x for x in at.button if x.key == "hizli_buton"]  # analiz düğmeleri gösterilmez


@paket_var
def test_paylasim_baglantisi_varsayimlari_yukler():
    at = _uygulama()
    at.query_params.update({"enlem": "39.790", "boylam": "26.330", "mod": "hizli", "baglanti_mw": "80.0", "proje_asamasi": "on_lisans"})
    at.run()
    assert not at.exception
    assert at.session_state["secim"]["kaynak"] == "url"
    assert at.session_state["kv"]["baglanti_mw"] == 80.0
    assert at.session_state["kv"]["proje_asamasi"] == "on_lisans"


@paket_var
def test_istek_siniri():
    at = _koordinat(_uygulama().run(), 39.79, 26.33)
    at.session_state["_istekler_hizli"] = [time.time()] * 30
    at.button(key="hizli_buton").click().run()
    assert any("en fazla 30 hızlı tarama" in x.value for x in at.error)


@pytest.mark.veri
@paket_var
def test_hizli_tarama_ve_paylasim():
    e, b = 39.79, 26.33
    if not _grid_var(e, b):
        pytest.skip("Ezine hücresi için ERA5/PVGIS gridi yok")
    at = _koordinat(_uygulama(300).run(), e, b)
    at.button(key="hizli_buton").click().run()
    assert not at.exception and not _gercek_hatalar(at)
    etiket = {m.label: m.value for m in at.metric}
    assert "Başabaş fiyatı (en iyi standart tasarım)" in etiket
    assert any("Tam analize değer mi?" in x for x in _kutular(at))
    assert at.query_params["enlem"] in ("39.790", ["39.790"])
    # Paylaşım bağlantısıyla yeni oturum: sonuç önbellekten gelir
    yeni = _uygulama()
    yeni.query_params.update({"enlem": "39.790", "boylam": "26.330", "mod": "hizli"})
    yeni.run()
    assert yeni.session_state["sonuc_hizli"].sure_s.get("onbellekten")


@pytest.mark.veri
@paket_var
def test_tam_analiz_kucuk_ayar(monkeypatch):
    e, b = 39.79, 26.33
    if not _grid_var(e, b):
        pytest.skip("Ezine hücresi için ERA5/PVGIS gridi yok")
    monkeypatch.setenv("MOTOR_KUCUK", "1")
    monkeypatch.setenv("MOTOR_CEKIRDEK", os.environ.get("MOTOR_CEKIRDEK", "2"))
    at = _koordinat(_uygulama(900).run(), e, b)
    at.button(key="tam_buton").click().run()
    assert not at.exception and not _gercek_hatalar(at)
    etiket = {m.label: m.value for m in at.metric}
    assert "E[NPV]" in etiket and "P(NPV > 0)" in etiket
    assert any(x.startswith("**Öneri:**") for x in _kutular(at))
