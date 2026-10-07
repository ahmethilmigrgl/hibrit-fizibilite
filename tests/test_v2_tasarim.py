"""v2 arayüz tasarım sistemi: belirteçler ↔ tema yapılandırması eşitliği, WCAG kontrastı, renklerin tek yerde tutulması,
grafik şablonu (koyu tema renk çevirisi), harita ve lejant, logo dosyaları, iki temada uygulamanın açılması."""

import re
from pathlib import Path

import plotly.graph_objects as go
import pytest

from uygulama.tasarim import grafik
from uygulama.tasarim.marka import isaret, yazi_markasi
from uygulama.tasarim.tokenlar import KOYU_VERI, TEMALAR, VERI, kontrast

KOK = Path(__file__).resolve().parents[1]


def test_config_belirteclerle_esit():
    from src.v2_tasarim_tema import config_metni

    assert (KOK / ".streamlit" / "config.toml").read_text(encoding="utf-8") == config_metni(), (
        "config.toml belirteçlerle uyuşmuyor: .venv/bin/python src/v2_tasarim_tema.py"
    )


@pytest.mark.parametrize("tema", list(TEMALAR))
def test_kontrast_wcag_aa(tema):
    r = TEMALAR[tema]["renk"]
    for on in ("metin", "metin_soluk", "vurgu", "iyi", "uyari", "kotu", "bilgi"):
        for arka in ("zemin", "yuzey"):
            assert kontrast(r[on], r[arka]) >= 4.5, (tema, on, arka)
    for d in ("iyi", "uyari", "kotu", "bilgi"):
        assert kontrast(r[d], r[f"{d}_zemin"]) >= 4.5, (tema, d)
        assert kontrast(r["metin"], r[f"{d}_zemin"]) >= 4.5, (tema, d)
    assert kontrast(r["vurgu_metin"], r["vurgu"]) >= 4.5
    assert min(kontrast(r["metin_silik"], r[a]) for a in ("zemin", "yuzey", "yuzey2")) >= 3.0


@pytest.mark.parametrize("tema", list(TEMALAR))
def test_veri_renkleri_grafik_nesnesi_kontrasti(tema):
    """Grafik çizgileri/çubukları yüzeye karşı ≥ 3:1 (WCAG 1.4.11); 'soluk' ikincil seri olduğundan hariç."""
    t = TEMALAR[tema]
    for k, v in t["veri"].items():
        if k not in ("soluk",):
            assert kontrast(v, t["renk"]["yuzey"]) >= 3.0, (tema, k)


def test_renk_kodlari_yalniz_belirteclerde():
    """Yeni arayüz dosyalarında onaltılık renk kodu yazılmaz (vaka sayfası v1'den aynen taşındı, hariç)."""
    dosyalar = ["app.py", "uygulama/ortak.py", "uygulama/harita.py", "uygulama/sayfa_analiz.py", "uygulama/sayfa_yontem.py",
                "uygulama/tasarim/stil.py", "uygulama/tasarim/bilesenler.py", "uygulama/tasarim/grafik.py", "uygulama/tasarim/marka.py"]  # fmt: skip
    for d in dosyalar:
        metin = (KOK / d).read_text(encoding="utf-8")
        assert not re.findall(r"#[0-9a-fA-F]{6}\b", metin), d


def test_grafik_koyu_renk_cevirisi():
    f = go.Figure([go.Scatter(y=[1, 2], line=dict(color=VERI["res"]), fill="tozeroy", fillcolor=grafik.dolgu(VERI["res"]))])
    f.add_trace(go.Bar(y=[1, 2], marker_color=[VERI["ges"], "#123456"]))
    f.add_vline(x=0, line_color=VERI["soluk"])
    grafik._koyu_renkler(f)
    assert f.data[0].line.color == KOYU_VERI["res"]
    assert f.data[0].fillcolor.startswith("rgba(90,169,255")
    assert tuple(f.data[1].marker.color) == (KOYU_VERI["ges"], "#123456")
    assert f.layout.shapes[0].line.color == KOYU_VERI["soluk"]
    for tema in TEMALAR:
        sab = grafik.sablon(tema)
        assert sab.layout.paper_bgcolor == TEMALAR[tema]["renk"]["yuzey"]


@pytest.mark.parametrize("tema", list(TEMALAR))
def test_harita_ve_lejant(tema):
    from uygulama import harita as H
    from uygulama import servis

    ot = servis.on_tarama()
    if ot is None:
        pytest.skip("ön tarama dosyası yok")
    m = H.harita(ot, "basabas_en_iyi", servis.santraller(), (39.79, 26.33), tema=tema)
    html = m.get_root().render()
    assert "tile.openstreetmap.org" in html  # isteğe bağlı katman olarak var
    assert TEMALAR[tema]["renk"]["deniz"] in html  # karosuz altlık teması
    lj = H.lejant(ot, "basabas_en_iyi", tema)
    assert lj.count('class="sinif"') == 6
    for renk in TEMALAR[tema]["harita_skala"]:
        assert renk in lj


def test_logo_dosyalari_guncel():
    for tema, t in TEMALAR.items():
        for dil in ("TR", "EN"):
            assert (KOK / "static" / "marka" / f"logo_{tema}_{dil.lower()}.svg").read_text(encoding="utf-8") == yazi_markasi(tema, dil)
        assert (KOK / "static" / "marka" / f"isaret_{tema}.svg").read_text(encoding="utf-8") == isaret(
            t["renk"]["metin"], t["renk"]["vurgu"]
        )
    for alt in ("latin", "latin-ext"):
        assert (KOK / "static" / "fonts" / f"public-sans-{alt}-wght-normal.woff2").exists()


@pytest.mark.parametrize("tema", list(TEMALAR))
def test_uygulama_iki_temada_acilir(tema):
    from streamlit.testing.v1 import AppTest

    from src.kaynaklar import gwa, sinirlar

    if not (gwa.PAKET.exists() and sinirlar.PAKET.exists()):
        pytest.skip("data/atlas paketleri yok")
    at = AppTest.from_file(str(KOK / "app.py"), default_timeout=120)
    at.session_state["tema"] = tema
    at.run()
    assert not at.exception
    assert at.session_state["tema_secim"] == tema
    assert at.title[0].value.startswith("Türkiye hibrit")
