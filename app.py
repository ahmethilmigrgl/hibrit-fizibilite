"""
Hibrit Fizibilite — Türkiye geneli saha tarama ve analiz uygulaması (v2, Streamlit).

Sayfalar: Saha tarama ve analiz (açılış: Türkiye ön tarama haritası) · Vaka çalışması: Ezine (v1.0.0) · Yöntem.
Çalışma anında yalnız yerel veriler (src/veri_katmani.py: ERA5 ve PVGIS gridleri, GWA, atlas, piyasa paketi); kişisel kimlik
bilgisi kullanılmaz.
Yerelde:  .venv/bin/streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from uygulama.ortak import T, altbilgi

st.set_page_config(page_title="Hibrit Fizibilite Türkiye", page_icon=str(KOK / "dashboard" / "favicon.png"), layout="wide")

# Üst boşluğu daralt (gezinme çubuğu üstte); dil seçimi sağ üstte tek satır
st.markdown("<style>.block-container{padding-top:3.4rem}</style>", unsafe_allow_html=True)

if "dil" not in st.session_state:
    st.session_state["dil"] = "EN" if st.query_params.get("dil") == "EN" else "TR"
_, sag = st.columns([6, 1])
sag.radio("Dil / Language", ["TR", "EN"], horizontal=True, label_visibility="collapsed", key="dil")

sayfalar = [
    st.Page(
        str(KOK / "uygulama" / "sayfa_analiz.py"), title=T("Saha tarama ve analiz", "Site screening & analysis"), icon="🗺️", default=True
    ),
    st.Page(str(KOK / "uygulama" / "sayfa_vaka.py"), title=T("Vaka çalışması: Ezine", "Case study: Ezine"), icon="📘", url_path="vaka"),
    st.Page(str(KOK / "uygulama" / "sayfa_yontem.py"), title=T("Yöntem", "Method"), icon="📐", url_path="yontem"),
]
st.navigation(sayfalar, position="top").run()
altbilgi()
