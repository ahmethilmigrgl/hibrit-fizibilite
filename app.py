"""
Eşik — Türkiye geneli hibrit (RES + GES + batarya) saha tarama ve analiz uygulaması (v2, Streamlit).

Sayfalar: Saha tarama ve analiz (açılış: Türkiye ön tarama haritası) · Vaka çalışması: Ezine (v1.0.0) · Yöntem.
Çalışma anında yalnız yerel veriler (src/veri_katmani.py: ERA5 ve PVGIS gridleri, GWA, atlas, piyasa paketi); kişisel kimlik
bilgisi kullanılmaz. Görünüm: uygulama/tasarim/ (belirteçler, CSS, bileşenler, grafik şablonu; açık ve koyu tema).
Yerelde:  .venv/bin/streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from uygulama.ortak import T, altbilgi
from uygulama.tasarim import stil
from uygulama.tasarim.tokenlar import MARKA

st.set_page_config(
    page_title=f"{MARKA['ad']} · Hibrit Fizibilite Türkiye", page_icon=str(KOK / "static" / "marka" / "favicon.png"), layout="wide"
)

if "dil" not in st.session_state:
    st.session_state["dil"] = "EN" if st.query_params.get("dil") == "EN" else "TR"
# Dil URL'de tutulur: tema değişiminde sayfa yeniden yüklenince ve paylaşım bağlantısında dil korunur
if st.session_state["dil"] == "EN":
    st.query_params["dil"] = "EN"
elif "dil" in st.query_params:
    del st.query_params["dil"]

sayfalar = [
    st.Page(str(KOK / "uygulama" / "sayfa_analiz.py"), title=T("Saha analizi", "Site analysis"), icon=":material/map:", default=True),
    st.Page(
        str(KOK / "uygulama" / "sayfa_vaka.py"),
        title=T("Vaka çalışması: Ezine", "Case study: Ezine"),
        icon=":material/menu_book:",
        url_path="vaka",
    ),
    st.Page(
        str(KOK / "uygulama" / "sayfa_cok_kriterli.py"),
        title=T("Çok kriterli saha seçimi", "Multi-criteria site selection"),
        icon=":material/tune:",
        url_path="cok-kriterli",
    ),
    st.Page(
        str(KOK / "uygulama" / "sayfa_ekleme.py"),
        title=T("Mevcut santrale ekleme", "Add-on to existing plant"),
        icon=":material/add_circle:",
        url_path="ekleme",
    ),
    st.Page(
        str(KOK / "uygulama" / "sayfa_yeka.py"),
        title=T("YEKA teklif stratejisi", "YEKA bidding strategy"),
        icon=":material/gavel:",
        url_path="yeka",
    ),
    st.Page(str(KOK / "uygulama" / "sayfa_portfoy.py"), title=T("Portföy", "Portfolio"), icon=":material/hub:", url_path="portfoy"),
    st.Page(
        str(KOK / "uygulama" / "sayfa_performans.py"),
        title=T("Performans izleme", "Performance monitoring"),
        icon=":material/monitor_heart:",
        url_path="performans",
    ),
    st.Page(str(KOK / "uygulama" / "sayfa_yontem.py"), title=T("Yöntem", "Method"), icon=":material/functions:", url_path="yontem"),
]
sayfa = st.navigation(sayfalar, position="top")
stil.uygula(sayfa.url_path)
sayfa.run()
altbilgi()
