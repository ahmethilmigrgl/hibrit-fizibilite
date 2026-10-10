"""
Açılış sayfası: Türkiye ön tarama haritası → saha seçimi (harita / koordinat / il-ilçe) → varsayımlar → hızlı tarama ve tam
analiz. Sonuçlar paylaşılabilir bağlantıyla (URL parametreleri + sonuç önbelleği) yeniden açılır.
"""

from __future__ import annotations

import threading
from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from src.motor import KullaniciVarsayimlari, MotorHatasi, analiz_et, onbellekten
from src.motor.varsayimlar import GELIR_YAPILARI, SINIRLAR, dogrula
from uygulama import harita as H
from uygulama import servis
from uygulama.ortak import GES, RES, SOLUK, T, ayar, ciz, dil, fiyat, istek_izni, md, para, sayi, sekil, uyari_bandi, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.grafik import dolgu
from uygulama.tasarim.stil import aktif_tema

YAPI_AD = {
    "tuccar": ("Tüccar (piyasa)", "Merchant"),
    "yekdem_opsiyon": ("YEKDEM yıllık opsiyon", "YEKDEM annual option"),
    "ppa": ("PPA (%70, 12 yıl)", "PPA (70%, 12 years)"),
}
ASAMA_AD = {"insaata_hazir": ("İnşaata hazır", "Ready to build"), "on_lisans": ("Ön lisans", "Pre-licence")}
FIYAT_AD = {"dusuk": ("Düşük", "Low"), "baz": ("Baz (58 $/MWh)", "Base (58 $/MWh)"), "yuksek": ("Yüksek", "High")}
KARAR_DURUM = {"yatirim": "iyi", "sinirli_teklif": "uyari", "rafa_kaldir": "kotu"}
DEGER_DURUM = {"deger": "iyi", "sinirda": "uyari", "degmez": "kotu"}
UI_ALANLAR = [
    "baglanti_mw", "proje_asamasi", "fiyat_senaryosu", "gelir_yapilari", "azami_res_mw", "azami_ges_mw", "turbin_yerlesimi",
    "yerlesim_yaricap_km", "fiyat_seviyesi", "kanibalizasyon", "wacc", "capex_carpani_res", "capex_carpani_ges",
    "capex_carpani_bess", "sfk_katilimi",
]  # fmt: skip
VARSAYILAN = KullaniciVarsayimlari()


# ---------------------------------------------------------------- paylaşım bağlantısı (URL parametreleri)
def _cevir(ad: str, metin: str):
    v0 = getattr(VARSAYILAN, ad)
    if ad == "gelir_yapilari":
        return tuple(x for x in metin.split(",") if x in GELIR_YAPILARI)
    if isinstance(v0, bool):
        return metin.lower() in ("1", "true", "evet")
    if ad in SINIRLAR or isinstance(v0, float):
        return float(metin)
    return metin


def url_oku() -> None:
    """Oturumun ilk çalışmasında URL'deki seçim ve varsayımları oturuma aktarır; sonuç önbellekteyse yükler."""
    if st.session_state.get("_url_okundu"):
        return
    st.session_state["_url_okundu"] = True
    q = st.query_params
    if "enlem" not in q or "boylam" not in q:
        return
    try:
        enlem, boylam = float(q["enlem"]), float(q["boylam"])
        kv = {a: _cevir(a, q[a]) for a in UI_ALANLAR if a in q}
        st.session_state["kv"] = {**_kv_sozluk(VARSAYILAN), **kv}
        st.session_state["secim"] = {"enlem": enlem, "boylam": boylam, "kaynak": "url"}
        k = KullaniciVarsayimlari(**{**_kv_sozluk(VARSAYILAN), **kv})
        saha = {"ad": "Paylaşılan saha", "enlem": enlem, "boylam": boylam}
        for mod in ("hizli", "tam"):
            s = onbellekten(saha, mod, k)
            if s is not None:
                st.session_state[f"sonuc_{mod}"] = s
        if q.get("mod") in ("hizli", "tam"):
            st.session_state["son_mod"] = q["mod"]
    except (ValueError, TypeError):
        st.session_state["url_hatasi"] = True


def url_yaz(mod: str | None) -> None:
    sc, kv = st.session_state["secim"], st.session_state.get("kv") or _kv_sozluk(VARSAYILAN)
    p = {"enlem": f"{sc['enlem']:.3f}", "boylam": f"{sc['boylam']:.3f}"}
    if mod:
        p["mod"] = mod
    if st.session_state.get("dil") == "EN":
        p["dil"] = "EN"
    for a in UI_ALANLAR:
        v, v0 = kv.get(a), getattr(VARSAYILAN, a)
        if a == "gelir_yapilari":
            v, v0 = tuple(v), tuple(v0)
        if v != v0 and v is not None:
            p[a] = ",".join(v) if a == "gelir_yapilari" else str(v)
    st.query_params.from_dict(p)


def _kv_sozluk(kv: KullaniciVarsayimlari) -> dict:
    return {f.name: getattr(kv, f.name) for f in fields(kv) if f.name in UI_ALANLAR}


# ---------------------------------------------------------------- seçim
def secimi_ayarla(enlem: float, boylam: float, kaynak: str) -> None:
    eski = st.session_state.get("secim")
    if eski and abs(eski["enlem"] - enlem) < 1e-4 and abs(eski["boylam"] - boylam) < 1e-4:
        return
    st.session_state["secim"] = {"enlem": round(enlem, 4), "boylam": round(boylam, 4), "kaynak": kaynak}
    for k in ("sonuc_hizli", "sonuc_tam"):
        st.session_state.pop(k, None)
    url_yaz(None)  # seçim bağlantıda: sayfa yeniden yüklenince (tema değişimi) korunur


def secim_paneli() -> None:
    sek = st.tabs([T("Haritadan", "From map"), T("Koordinat", "Coordinates"), T("İl / ilçe", "Province / district")])
    with sek[0]:
        st.caption(
            T(
                "Haritada bir noktaya tıklayın; nokta seçilir ve bilgileri aşağıda görünür.",
                "Click a point on the map to select it; details appear below.",
            )
        )
    with sek[1]:
        c1, c2 = st.columns(2)
        sc = st.session_state.get("secim") or {"enlem": 39.79, "boylam": 26.33}
        e = c1.number_input(T("Enlem (°K)", "Latitude (°N)"), 35.5, 42.5, float(sc["enlem"]), 0.01, format="%.4f", key="giris_enlem")
        b = c2.number_input(T("Boylam (°D)", "Longitude (°E)"), 25.5, 45.0, float(sc["boylam"]), 0.01, format="%.4f", key="giris_boylam")
        if st.button(T("Bu noktayı seç", "Select this point"), key="koordinat_sec", width="stretch"):
            secimi_ayarla(e, b, "koordinat")
    with sek[2]:
        ii = servis.il_ilce()
        il = st.selectbox(
            T("İl", "Province"), sorted(ii["il"].unique()), index=None, placeholder=T("İl seçin", "Choose a province"), key="il"
        )
        ilce = None
        if il:
            ilce = st.selectbox(
                T("İlçe", "District"),
                sorted(ii.loc[ii["il"] == il, "ilce"]),
                index=None,
                placeholder=T("İlçe seçin", "Choose a district"),
                key="ilce",
            )
        if il and ilce:
            ad = servis.adaylar(il, ilce)
            st.session_state["adaylar"] = ad
            if len(ad):
                st.caption(
                    T(
                        f"İlçedeki en rüzgârlı {len(ad)} nokta (GWA 1 km, aralarında ≥ {sayi(ayar()['aday_aralik_km'], 0)} km). Haritada numaralı.",
                        f"The {len(ad)} windiest points in the district (GWA 1 km, ≥ {sayi(ayar()['aday_aralik_km'], 0)} km apart). Numbered on the map.",
                    )
                )
                secenek = [
                    f"{i}: GWA {sayi(r.gwa_1km, 1)} m/s ({sayi(r.enlem, 3)}, {sayi(r.boylam, 3)})" for i, r in enumerate(ad.itertuples(), 1)
                ]
                k = st.radio(T("Aday", "Candidate"), range(len(ad)), format_func=lambda i: secenek[i], key="aday_sec")
                if st.button(T("Adayı seç", "Select candidate"), key="aday_buton", width="stretch"):
                    secimi_ayarla(float(ad.iloc[k]["enlem"]), float(ad.iloc[k]["boylam"]), "il_ilce")
        else:
            st.session_state["adaylar"] = None


@st.cache_data(show_spinner=False, max_entries=256)
def _nokta_bilgisi(enlem: float, boylam: float, yerlesim: bool, yaricap: float, baglanti: float) -> dict:
    return servis.nokta_bilgisi(enlem, boylam, yerlesim, yaricap, baglanti)


def saha_karti(kv: dict) -> dict | None:
    sc = st.session_state.get("secim")
    if not sc:
        B.bos_durum(
            T("Henüz saha seçilmedi", "No site selected yet"),
            T(
                "Haritada bir hücreye tıklayın ya da koordinat / il-ilçe ile seçin. Tam dolu hücrelerde 30 km içinde kalibre bir "
                "santral var: rüzgâr tahmini daha güvenilir.",
                "Click a cell on the map or choose by coordinates / province. Solid cells have a calibrated wind farm within "
                "30 km: the wind estimate is more reliable.",
            ),
        )
        return None
    try:
        b = _nokta_bilgisi(
            sc["enlem"], sc["boylam"], bool(kv["turbin_yerlesimi"]), float(kv["yerlesim_yaricap_km"]), float(kv["baglanti_mw"])
        )
    except MotorHatasi as ex:
        B.uyari_kutusu(ex.mesaj(st.session_state.get("dil", "TR")), "kotu")
        return None
    with B.kart("saha"):
        st.html(f'<div class="esik-kas">{T("Seçilen saha", "Selected site")}</div>')
        st.markdown(f"#### {b['il']} / {b['ilce']} · {sayi(sc['enlem'], 4)}° K, {sayi(sc['boylam'], 4)}° D")
        st.html(B.guven_rozeti(b["guven"], T(f"Güven: {b['guven']}", f"Confidence: {({'yüksek': 'high', 'düşük': 'low'})[b['guven']]}")))
        c = st.columns(2) + st.columns(2)
        B.kpi_karti(c[0], T("GWA 100 m (nokta)", "GWA 100 m (point)"), f"{sayi(b['gwa_nokta'], 2)} m/s")
        B.kpi_karti(
            c[1],
            T("GWA (türbin yerleşimi)", "GWA (turbine layout)") if b["yerlesim"] else T("GWA (kullanılan)", "GWA (used)"),
            f"{sayi(b['gwa_saha'], 2)} m/s",
        )
        B.kpi_karti(c[2], T("Güven seviyesi", "Confidence"), T(b["guven"], {"yüksek": "high", "düşük": "low"}[b["guven"]]))
        B.kpi_karti(
            c[3],
            T("Tipik KF hatası", "Typical CF error"),
            f"±{sayi(b['guven_medyan'], 1)} {T('puan', 'pts')}",
            yardim=T(f"%90'lık hata ±{sayi(b['guven_p90'], 1)} puan", f"90th percentile error ±{sayi(b['guven_p90'], 1)} pts"),
        )
        if b["komsular"]:
            st.caption(
                T("Dayandığı kalibre santral(ler): ", "Calibrated wind farm(s) used: ")
                + "; ".join(f"{k['ad']} ({sayi(k['mesafe_km'], 1)} km)" for k in b["komsular"])
            )
            if b["tek_komsu"]:
                B.uyari_kutusu(
                    T(
                        "Tahmin tek bir komşu santrale dayanıyor: o santralin türbin konumu ve yerel özellikleri sonucu güçlü biçimde etkiler. "
                        "Sırt dışı bir nokta seçtiyseniz rüzgâr olduğundan düşük görünebilir.",
                        "The estimate relies on a single neighbouring wind farm: its turbine positions and local features strongly affect the result. "
                        "If the point is off the ridge, wind may look lower than it is.",
                    ),
                    "uyari",
                )
        else:
            st.caption(
                T(
                    "30 km içinde benzer kalibre santral yok: GWA × ulusal medyan düzeltme kullanılır.",
                    "No similar calibrated farm within 30 km: GWA × national median correction is used.",
                )
            )
        if b.get("ada"):
            B.uyari_kutusu(
                T(
                    f"**Ada ({b['ada']['ilce']}, ~{sayi(b['ada']['alan_km2'], 0)} km²):** 50 MW ölçeğinde bağlantı denizaltı kablosu "
                    f"gerektirir; bu maliyet modele dahil değil. {b['ada']['durum']}",
                    f"**Island ({b['ada']['ilce']}, ~{sayi(b['ada']['alan_km2'], 0)} km²):** a 50 MW connection requires a submarine "
                    "cable, whose cost is not modelled. Existing island links are distribution-scale; their capacity could not be verified.",
                ),
                "uyari",
            )
        if b["hucre"] and b["hucre"].get("ust_sinir"):
            B.uyari_kutusu(
                T(
                    "**Üst sınıra yakın, ihtiyatla değerlendirin:** bu hücrenin tahmini RES KF'si Türkiye'de gözlenen en yüksek santral "
                    f"KF'sinin (%{sayi(100 * ayar()['ust_sinir_kf'], 1)}) üstünde.",
                    "**Near the upper bound, treat with caution:** this cell's estimated wind CF exceeds the highest observed farm CF in "
                    f"Türkiye ({sayi(100 * ayar()['ust_sinir_kf'], 1)}%).",
                ),
                "uyari",
            )
        if b["hucre"]:
            h = b["hucre"]
            st.caption(
                md(
                    T("Ön tarama hücresi (0,25°): ", "Pre-screening cell (0.25°): ")
                    + f"RES KF {yuzde(100 * h['res_kf'], 1)} · GES KF {yuzde(100 * h['ges_kf'], 1)} · "
                    + T("en iyi standart tasarım: ", "best standard design: ")
                    + f"{h['en_iyi_tasarim']} · {T('başabaş', 'break-even')} {fiyat(h['basabas_en_iyi'])} · "
                    + T(
                        f"Türkiye hücrelerinin %{sayi(h['yuzdelik'], 0)}'inden daha cazip",
                        f"more attractive than {sayi(h['yuzdelik'], 0)}% of Türkiye's cells",
                    )
                    + (T(" (sıralama adalar hariç)", " (ranking excludes islands)") if b.get("ada") else "")
                )
            )
    return b


# ---------------------------------------------------------------- varsayımlar
def varsayim_paneli() -> dict:
    kv = st.session_state.setdefault("kv", _kv_sozluk(VARSAYILAN))
    with st.expander(T("Varsayımlar", "Assumptions"), expanded=False):
        c = st.columns(2)
        kv["baglanti_mw"] = c[0].number_input(
            T("Şebeke bağlantısı [MW]", "Grid connection [MW]"), *SINIRLAR["baglanti_mw"], float(kv["baglanti_mw"]), 5.0,
            help=T("Santralin şebekeye verebileceği en yüksek güç (TEİAŞ bağlantı görüşü).", "Maximum export capacity (grid connection agreement)."),
        )  # fmt: skip
        kv["proje_asamasi"] = c[1].selectbox(
            T("Proje aşaması", "Project stage"), list(ASAMA_AD), index=list(ASAMA_AD).index(kv["proje_asamasi"]),
            format_func=lambda x: T(*ASAMA_AD[x]),
            help=T("Takvimi (COD dağılımı) ve YEKDEM'e yetişme olasılığını belirler.", "Sets the schedule (COD distribution) and the chance of qualifying for YEKDEM."),
        )  # fmt: skip
        kv["fiyat_senaryosu"] = c[0].selectbox(
            T("Fiyat senaryosu", "Price scenario"), list(FIYAT_AD), index=list(FIYAT_AD).index(kv["fiyat_senaryosu"]),
            format_func=lambda x: T(*FIYAT_AD[x]), help=T("Uzun vadeli reel ortalama elektrik fiyatı (beklenen değer).", "Long-term real average power price (expected value)."),
        )  # fmt: skip
        kv["gelir_yapilari"] = tuple(
            c[1].multiselect(
                T("Gelir yapıları (tam analiz)", "Revenue structures (full analysis)"),
                list(GELIR_YAPILARI),
                default=list(kv["gelir_yapilari"]),
                format_func=lambda x: T(*YAPI_AD[x]),
                help=T(
                    "Tüccar: tüm üretim piyasaya; YEKDEM: her yıl 30 Kasım'da seçilen sabit fiyat opsiyonu; PPA: üretimin %70'i 12 yıl sabit fiyatla.",
                    "Merchant: all output to market; YEKDEM: fixed-price option chosen every 30 Nov; PPA: 70% of output at a fixed price for 12 years.",
                ),
            )
        ) or ("tuccar",)
        with st.expander(T("Gelişmiş", "Advanced")):
            g = st.columns(2)
            kv["turbin_yerlesimi"] = g[0].toggle(
                T("Türbin yerleşimi", "Turbine layout"), bool(kv["turbin_yerlesimi"]),
                help=T("Açık: yarıçap içindeki en rüzgârlı GWA 250 m hücreleri (geliştiricinin türbini sırta koyacağı varsayımı). Çapraz doğrulamada noktadan daha isabetli (docs).", "On: the windiest GWA 250 m cells within the radius (assumes the developer sites turbines on ridges). More accurate than the point in cross-validation (docs)."),
            )  # fmt: skip
            kv["yerlesim_yaricap_km"] = g[1].slider(
                T("Yerleşim yarıçapı [km]", "Layout radius [km]"), 0.5, 10.0, float(kv["yerlesim_yaricap_km"]), 0.5
            )
            res_sinir = g[0].number_input(
                T("Azami RES [MW] (0 = sınırsız)", "Max wind [MW] (0 = unlimited)"), 0.0, 600.0, float(kv["azami_res_mw"] or 0.0), 5.0
            )
            ges_sinir = g[1].number_input(
                T("Azami GES [MWac] (0 = sınırsız)", "Max solar [MWac] (0 = unlimited)"), 0.0, 600.0, float(kv["azami_ges_mw"] or 0.0), 5.0
            )
            kv["azami_res_mw"], kv["azami_ges_mw"] = (res_sinir or None), (ges_sinir or None)
            serbest = g[0].toggle(T("Serbest fiyat seviyesi", "Custom price level"), kv["fiyat_seviyesi"] is not None)
            kv["fiyat_seviyesi"] = (
                g[1].number_input(
                    T("Fiyat seviyesi [$/MWh, reel]", "Price level [$/MWh, real]"), 20.0, 150.0, float(kv["fiyat_seviyesi"] or 58.0), 1.0
                )
                if serbest
                else None
            )
            kv["kanibalizasyon"] = g[0].selectbox(
                T("Güneş kanibalizasyonu", "Solar cannibalisation"), ["devam", "durur"], index=["devam", "durur"].index(kv["kanibalizasyon"]),
                format_func=lambda x: T({"devam": "Devam eder", "durur": "Durur"}[x], {"devam": "Continues", "durur": "Stops"}[x]),
            )  # fmt: skip
            wacc = g[1].number_input(
                T("Reel WACC [%] (0 = varsayılan %7)", "Real WACC [%] (0 = default 7%)"), 0.0, 15.0, 100 * float(kv["wacc"] or 0.0), 0.5
            )
            kv["wacc"] = wacc / 100 if wacc >= 3 else None
            kv["capex_carpani_res"] = g[0].slider(
                T("RES CAPEX çarpanı", "Wind CAPEX multiplier"), 0.5, 2.0, float(kv["capex_carpani_res"]), 0.05
            )
            kv["capex_carpani_ges"] = g[1].slider(
                T("GES CAPEX çarpanı", "Solar CAPEX multiplier"), 0.5, 2.0, float(kv["capex_carpani_ges"]), 0.05
            )
            kv["capex_carpani_bess"] = g[0].slider(
                T("Batarya CAPEX çarpanı", "Battery CAPEX multiplier"), 0.5, 2.0, float(kv["capex_carpani_bess"]), 0.05
            )
            kv["sfk_katilimi"] = g[1].toggle(
                T("SFK (yan hizmet) katılımı", "Ancillary services (SFK)"), bool(kv["sfk_katilimi"]),
                help=T("≥ 30 MW bataryayla sekonder frekans kontrolüne katılım; piyasa doyumu Monte Carlo'da.", "Secondary frequency control with ≥ 30 MW battery; market saturation in the Monte Carlo."),
            )  # fmt: skip
    st.session_state["kv"] = kv
    return kv


# ---------------------------------------------------------------- analiz çalıştırma
def calistir(mod: str, kv: dict) -> None:
    sc = st.session_state["secim"]
    try:
        k = KullaniciVarsayimlari(**kv)
        dogrula(k)
    except MotorHatasi as ex:
        B.uyari_kutusu(ex.mesaj(st.session_state.get("dil", "TR")), "kotu")
        return
    izin, mesaj = istek_izni(mod)
    if not izin:
        B.uyari_kutusu(mesaj, "kotu")
        return
    saha = {"ad": f"Saha {sc['enlem']:.3f}, {sc['boylam']:.3f}", "enlem": sc["enlem"], "boylam": sc["boylam"]}
    ad = T("Hızlı tarama", "Quick scan") if mod == "hizli" else T("Tam analiz", "Full analysis")
    kutu = st.empty()  # çalışma göstergeleri tek kapsayıcıda: iş bitince hepsi birlikte kalkar
    with kutu.container():
        B.bolum_basligi(
            T(f"{ad} çalışıyor", f"{ad} running"),
            T("saniyeler sürer", "takes seconds")
            if mod == "hizli"
            else T("optimizasyon + Monte Carlo · birkaç dakika", "optimisation + Monte Carlo · a few minutes"),
        )
        cubuk = st.progress(0.0, T("Başlıyor…", "Starting…"))
        sira_kutu = st.empty()
        st.html(B.iskelet_html())
    ctx = get_script_run_ctx()

    def ilerleme(o: float, m: str) -> None:
        add_script_run_ctx(threading.current_thread(), ctx)
        sira_kutu.empty()
        cubuk.progress(min(max(float(o), 0.0), 1.0), m)

    def bekleme(no: int) -> None:
        add_script_run_ctx(threading.current_thread(), ctx)
        sira_kutu.html(
            B.sira_karti_html(
                no,
                T(
                    f"Sıradasınız: {no}. iş. Aynı anda tek bir tam analiz çalışır; sıranız gelince otomatik başlar.",
                    f"You are number {no} in the queue. One full analysis runs at a time; yours starts automatically.",
                ),
            )
        )

    try:
        s = analiz_et(saha, mod, k, ilerleme, bekleme=bekleme, sira_azami=ayar()["tam_sira_azami"])
        st.session_state[f"sonuc_{mod}"] = s
        st.session_state["son_mod"] = mod
        url_yaz(mod)
    except MotorHatasi as ex:
        B.uyari_kutusu(ex.mesaj(st.session_state.get("dil", "TR")), "kotu")
    finally:
        kutu.empty()


# ---------------------------------------------------------------- sonuç ekranları
def _metin(x: dict) -> str:
    return x["tr"] if dil() == "TR" else x["en"]


def neden_listesi(nedenler: list[dict]) -> None:
    B.liste([_metin(n) for n in nedenler])


def uyari_listesi(uyarilar: list[dict]) -> None:
    # ada ve üst sınır karar açısından önemli: görünür uyarı kutusu; diğerleri liste
    for u in uyarilar:
        if u.get("kod") in ("ada", "ust_sinir"):
            B.uyari_kutusu(_metin(u), "uyari")
    diger = [_metin(u) for u in uyarilar if u.get("kod") not in ("ada", "ust_sinir")]
    if diger:
        B.liste(diger, "uyari")


def sure_notu(s, d: int) -> None:
    st.caption(
        T(f"Süre: {sayi(s.sure_s.get('toplam', 0), d)} s", f"Time: {sayi(s.sure_s.get('toplam', 0), d)} s")
        + (T(" (önbellekten)", " (from cache)") if s.sure_s.get("onbellekten") else "")
    )


def profil_grafikleri(g: dict) -> None:
    c = st.columns(2)
    f1 = go.Figure(
        [
            go.Scatter(x=g["gunici"]["saat"], y=np.array(g["gunici"]["res"]) * 100, name="RES", line=dict(color=RES, width=2.2)),
            go.Scatter(x=g["gunici"]["saat"], y=np.array(g["gunici"]["ges"]) * 100, name="GES", line=dict(color=GES, width=2.2)),
        ]
    )
    f1.update_xaxes(dtick=3)
    with c[0]:
        ciz(sekil(f1, T("Gün içi profil", "Daily profile"), T("kapasite faktörü, %", "capacity factor, %"), T("saat (TSİ)", "hour (local time)"),
                  alt=T("Saat başına ortalama KF, 10 hava yılı", "Average CF by hour, 10 weather years")))  # fmt: skip
    f2 = go.Figure(
        [
            go.Bar(x=g["aylik"]["ay"], y=np.array(g["aylik"]["res"]) * 100, name="RES", marker_color=RES),
            go.Bar(x=g["aylik"]["ay"], y=np.array(g["aylik"]["ges"]) * 100, name="GES", marker_color=GES),
        ]
    )
    f2.update_layout(bargap=0.25, bargroupgap=0.08)
    with c[1]:
        ciz(sekil(f2, T("Aylık profil", "Monthly profile"), T("kapasite faktörü, %", "capacity factor, %"), T("ay", "month"),
                  alt=T("Aylık ortalama KF: rüzgâr kışın, güneş yazın güçlü", "Monthly average CF: wind peaks in winter, solar in summer")))  # fmt: skip


def hizli_sonuc(s) -> None:
    o = s.ozet
    bb = o.get("basabas_en_iyi")
    yz = servis.yuzdelik(bb)
    d = o.get("tam_analize_deger") or {}
    gv = o.get("guven") or {}
    with B.karar_karti(DEGER_DURUM.get(d.get("karar"), "uyari")):
        c = st.columns([1.5, 1, 1, 1], gap="medium")
        with c[0]:
            if d:
                B.uyari_kutusu(
                    f"**{T('Tam analize değer mi?', 'Worth a full analysis?')}** {_metin(d)}"
                    + (
                        ""
                        if d.get("basabas_orani") is None
                        else f" ({T('başabaş / senaryo', 'break-even / scenario')} {sayi(d['basabas_orani'], 2)})"
                    ),
                    DEGER_DURUM[d["karar"]],
                )
            st.caption(md(T("En iyi standart tasarım: ", "Best standard design: ") + str(o.get("en_iyi_standart", "–"))
                          + f" · {T('seçilen senaryo', 'selected scenario')} {fiyat(o['fiyat_seviyesi'])}"))  # fmt: skip
        B.kpi_karti(
            c[1], T("Başabaş fiyatı (en iyi standart tasarım)", "Break-even price (best standard design)"), fiyat(bb, 1),
            yardim=T("NPV'yi sıfırlayan uzun vadeli reel ortalama elektrik fiyatı. Seçilen senaryo: ", "Long-term real average power price that sets NPV to zero. Selected scenario: ") + fiyat(o["fiyat_seviyesi"]),
        )  # fmt: skip
        B.kpi_karti(c[2], T("Türkiye sıralaması", "Rank in Türkiye"), "–" if yz is None else T(f"%{sayi(yz, 0)}'inden iyi", f"better than {sayi(yz, 0)}%"),
                    yardim=T("Başabaş fiyatı, Türkiye kara hücrelerinin (0,25°) yüzde kaçından düşük.", "Share of Türkiye's land cells (0.25°) with a higher break-even price."))  # fmt: skip
        if gv:
            B.kpi_karti(c[3], T("Güven seviyesi", "Confidence"), T(gv["seviye"], {"yüksek": "high", "düşük": "low"}.get(gv["seviye"], gv["seviye"])),
                        aciklama=T(f"tipik KF hatası ±{sayi(gv['medyan_puan'], 1)} puan", f"typical CF error ±{sayi(gv['medyan_puan'], 1)} pts"))  # fmt: skip
    u = st.columns(4)
    B.kpi_karti(u[0], T("RES kapasite faktörü", "Wind capacity factor"), yuzde(100 * o["res_kf"], 1),
                yardim=T("Bant (tipik hata): ", "Band (typical error): ") + f"{yuzde(100 * o['res_kf_bandi_medyan'][0], 1)}–{yuzde(100 * o['res_kf_bandi_medyan'][1], 1)}; P90: {yuzde(100 * o['res_kf_bandi_p90'][0], 1)}–{yuzde(100 * o['res_kf_bandi_p90'][1], 1)}",
                aciklama=T("bant ", "band ") + f"{yuzde(100 * o['res_kf_bandi_medyan'][0], 1)}–{yuzde(100 * o['res_kf_bandi_medyan'][1], 1)}")  # fmt: skip
    B.kpi_karti(u[1], T("GES kapasite faktörü", "Solar capacity factor"), yuzde(100 * o["ges_kf"], 1))
    B.kpi_karti(
        u[2],
        T("Yakalanma oranı RES / GES", "Capture rate wind / solar"),
        f"{sayi(o.get('yakalanma_res'), 2)} / {sayi(o.get('yakalanma_ges'), 2)}",
    )
    B.kpi_karti(u[3], "LCOE RES / GES", f"{sayi(o.get('lcoe_res'), 0)} / {sayi(o.get('lcoe_ges'), 0)}", aciklama="$/MWh")
    uyari_bandi()
    st.caption(
        md(
            T("RES KF belirsizlik bandı (güven seviyesinden): tipik ", "Wind CF uncertainty band (from confidence level): typical ")
            + f"{yuzde(100 * o['res_kf_bandi_medyan'][0], 1)}–{yuzde(100 * o['res_kf_bandi_medyan'][1], 1)}, %90: "
            + f"{yuzde(100 * o['res_kf_bandi_p90'][0], 1)}–{yuzde(100 * o['res_kf_bandi_p90'][1], 1)} · "
            + T("Başabaş RES / GES: ", "Break-even wind / solar: ")
            + f"{fiyat(o.get('basabas_res'))} / {fiyat(o.get('basabas_ges'))}"
        )
    )
    t = s.tablolar["tasarimlar"]
    B.bolum_basligi(T("Standart tasarımlar ve hızlı optimizasyon", "Standard designs and quick optimisation"),
                    T("seçilen fiyat senaryosunda, deterministik", "selected price scenario, deterministic"))  # fmt: skip
    en_iyi = int(np.nanargmax(t["npv_musd"].to_numpy())) if t["npv_musd"].notna().any() else None
    B.karsilastirma_tablosu(
        [
            T("Tasarım", "Design"),
            "RES MW",
            "GES MWac",
            T("Batarya MW", "Battery MW"),
            T("Batarya MWh", "Battery MWh"),
            T("NPV, M$", "NPV, M$"),
            "IRR",
            T("Kesinti %", "Curtailment %"),
        ],
        [
            [
                r["tasarim"],
                sayi(r["res_mw"], 1),
                sayi(r["ges_mw"], 1),
                sayi(r["bess_mw"], 1),
                sayi(r["bess_mwh"], 1),
                sayi(r["npv_musd"], 1),
                "–" if pd.isna(r["irr"]) else yuzde(100 * r["irr"], 1),
                sayi(r["kesinti_%"], 1),
            ]
            for _, r in t.iterrows()
        ],
        vurgulu=en_iyi,
        mobilde_gizle=(3, 4, 7),
        negatif=[(i, 5) for i, v in enumerate(t["npv_musd"]) if v < 0],
    )
    profil_grafikleri(s.grafikler)
    B.bolum_basligi(T("Neden?", "Why?"))
    neden_listesi(s.nedenler)
    uyari_listesi(s.uyarilar)
    sure_notu(s, 1)


def tam_sonuc(s) -> None:
    o = s.ozet
    k = o["karar"]
    b = o["baz"]
    gv = o.get("guven") or {}
    ts = o["tasarim"]
    with B.karar_karti(KARAR_DURUM.get(k["karar"], "uyari")):
        c = st.columns([1.5, 1, 1, 1], gap="medium")
        with c[0]:
            B.uyari_kutusu(md(f"**{T('Öneri', 'Recommendation')}:** {_metin(k)}"), KARAR_DURUM.get(k["karar"], "bilgi"))
            st.caption(
                md(
                    T("Tasarım: ", "Design: ")
                    + f"RES {sayi(ts['res_mw'], 1)} MW · GES {sayi(ts['ges_mw'], 0)} MWac · {T('batarya', 'battery')} {sayi(ts['bess_mw'], 0)} MW / {sayi(ts['bess_mwh'], 0)} MWh"
                    + (
                        T(
                            f" (optimizasyon kurulum önermedi; en iyi standart tasarım: {o['yedek_tasarim']})",
                            f" (optimisation suggested no build; best standard design: {o['yedek_tasarim']})",
                        )
                        if o.get("yedek_tasarim")
                        else ""
                    )
                    + f" · CAPEX {para(o['capex_musd'])} · {T('en iyi gelir yapısı', 'best revenue structure')}: {T(*YAPI_AD[o['en_iyi_yapi']])}"
                )
            )
        B.kpi_karti(c[1], T("Monte Carlo başabaş fiyatı", "Monte Carlo break-even"), fiyat(o.get("basabas_fiyat"), 0),
                    aciklama=T("senaryo ", "scenario ") + fiyat(o.get("fiyat_seviyesi")))  # fmt: skip
        B.kpi_karti(
            c[2], "E[NPV]", para(b["e_npv"]),
            yardim=T(f"Beklenen NPV. Standart hata ±{sayi(b['se'], 2)} M$ (n = {b['n']})", f"Expected NPV. Standard error ±{sayi(b['se'], 2)} M$ (n = {b['n']})"),
            aciklama=T(f"beklenen NPV · ±{sayi(b['se'], 2)}", f"expected NPV · ±{sayi(b['se'], 2)}"),
        )  # fmt: skip
        if gv:
            B.kpi_karti(c[3], T("Güven seviyesi", "Confidence"), T(gv["seviye"], {"yüksek": "high", "düşük": "low"}.get(gv["seviye"], gv["seviye"])),
                        aciklama=T(f"tipik KF hatası ±{sayi(gv['medyan_puan'], 1)} puan", f"typical CF error ±{sayi(gv['medyan_puan'], 1)} pts"))  # fmt: skip
    tk = o["takvim"]
    u = st.columns(4)
    B.kpi_karti(u[0], "P(NPV > 0)", yuzde(100 * b["p_pozitif"], 0), aciklama=T("pozitif NPV olasılığı", "probability of positive NPV"))
    B.kpi_karti(
        u[1], "CVaR %5" if dil() == "TR" else "CVaR 5%", para(b["cvar5"]), aciklama=T("en kötü %5'in ortalaması", "mean of the worst 5%")
    )
    B.kpi_karti(u[2], "CAPEX", para(o["capex_musd"]), aciklama=T("seçilen tasarım", "selected design"))
    B.kpi_karti(u[3], "COD P50", str(tk["cod_p50"]), aciklama=f"P80 {tk['cod_p80']}")
    uyari_bandi()
    h = s.grafikler.get("npv_histogram")
    c = st.columns([1.55, 1], gap="medium")
    with c[0]:
        if h:
            f = go.Figure()
            renk = {"tuccar": SOLUK, "yekdem_opsiyon": RES, "ppa": GES}
            for y, n in h["sayi"].items():
                e = np.array(h["kenar"][y])
                r_ = renk.get(y, SOLUK)
                f.add_trace(go.Scatter(x=(e[:-1] + e[1:]) / 2, y=n, name=T(*YAPI_AD[y]), mode="lines", line=dict(color=r_, width=2, shape="hvh"),
                                       fill="tozeroy", fillcolor=dolgu(r_, 0.12)))  # fmt: skip
            f.add_vline(x=0, line_color=SOLUK, line_dash="dot", line_width=1)
            f.update_layout(hovermode="x")
            ciz(sekil(f, T("NPV dağılımı", "NPV distribution"), T("simülasyon sayısı", "simulations"), T("NPV, milyon $ (reel)", "NPV, million $ (real)"),
                      yukseklik=380, alt=T(f"Monte Carlo, n = {b['n']} · gelir yapısına göre · noktalı çizgi NPV = 0",
                                           f"Monte Carlo, n = {b['n']} · by revenue structure · dotted line NPV = 0")))  # fmt: skip
    with c[1]:
        with B.kart("takvim"):
            st.html(f'<div class="esik-kas">{T("Takvim", "Schedule")}</div>')
            st.markdown(
                f"- {T('Aşama', 'Stage')}: {T(*ASAMA_AD[tk['proje_asamasi']])}\n- COD P50 {tk['cod_p50']} · P80 {tk['cod_p80']}\n"
                f"- {T('YEKDEM için COD ≤ 2030 olasılığı', 'Probability of COD ≤ 2030 (YEKDEM)')}: {yuzde(100 * tk['p_cod_2030_oncesi'], 0)}"
            )
            ge = o.get("guven_etkisi")
            if ge:
                st.html(f'<div class="esik-kas ara">{T("Güven seviyesinin sonuca etkisi", "Effect of the confidence level")}</div>')
                st.markdown(
                    md(
                        T(
                            f"Rüzgâr model belirsizliği σ = {yuzde(100 * (ge['sigma'] or 0), 0)} ({o['guven']['seviye']} güven). Rüzgâr tahmini "
                            f"kötü üçte birdeyse (ort. {yuzde(100 * ge['kf_degisim_alt_ust'][0], 0)}) E[NPV] {para(ge['e_npv_alt'])}, ortada "
                            f"{para(ge['e_npv_orta'])}, iyi üçte birdeyse ({yuzde(100 * ge['kf_degisim_alt_ust'][1], 0)}) {para(ge['e_npv_ust'])}. "
                            "Fark büyükse saha ölçümü (rüzgâr direği/LiDAR) kararın bilgi değeri en yüksek adımıdır.",
                            f"Wind model uncertainty σ = {sayi(100 * (ge['sigma'] or 0), 0)}% ({o['guven']['seviye']} confidence). If the wind estimate "
                            f"falls in the worst third (avg {sayi(100 * ge['kf_degisim_alt_ust'][0], 0)}%) E[NPV] is {para(ge['e_npv_alt'])}, middle "
                            f"{para(ge['e_npv_orta'])}, best third ({sayi(100 * ge['kf_degisim_alt_ust'][1], 0)}%) {para(ge['e_npv_ust'])}. "
                            "If the spread is large, an on-site measurement (met mast/LiDAR) is the highest-value next step.",
                        )
                    )
                )
    g = s.tablolar["gelir_yapilari"]
    B.bolum_basligi(T("Gelir yapıları", "Revenue structures"), T("Monte Carlo, milyon $ (reel)", "Monte Carlo, million $ (real)"))
    B.karsilastirma_tablosu(
        [T("Gelir yapısı", "Revenue structure"), "E[NPV]", T("Std. hata", "Std. error"), "P(NPV>0)", "CVaR5", "P10 / P90", "IRR P50"],
        [
            [
                T(*YAPI_AD[y]),
                sayi(r.e_npv, 1),
                f"±{sayi(r.se, 2)}",
                yuzde(100 * r.p_pozitif, 0),
                sayi(r.cvar5, 1),
                f"{sayi(r.p10, 1)} / {sayi(r.p90, 1)}",
                "–" if pd.isna(r.irr_p50) else yuzde(100 * r.irr_p50, 1),
            ]
            for y, r in zip(g.index, g.itertuples(), strict=True)
        ],
        vurgulu=list(g.index).index(o["en_iyi_yapi"]) if o.get("en_iyi_yapi") in g.index else None,
        mobilde_gizle=(2, 5, 6),
        negatif=[(i, 1) for i, v in enumerate(g["e_npv"]) if v < 0],
    )
    if o.get("v3"):  # v3 Faz D: türbin yerleşimi + işletme ve bakım
        from uygulama.v3_bolumler import bakim_bolumu, kayip_bolumu, yerlesim_bolumu

        yerlesim_bolumu(o, s.saha)
        kayip_bolumu(o)
        bakim_bolumu(o)
    B.bolum_basligi(
        T("Neyi izlemeli", "What to monitor"), T("kararı değiştirecek tetikleyiciler", "triggers that would change the decision")
    )
    neden_listesi(o.get("tetikleyiciler", []))
    B.bolum_basligi(T("Gerekçeler", "Rationale"))
    neden_listesi(s.nedenler)
    uyari_listesi(s.uyarilar)
    r = o.get("rapor") or {}
    belgeler = [
        ("html", T("Saha raporu (HTML)", "Site report (HTML)"), "text/html"),
        ("pdf", T("Saha raporu (PDF)", "Site report (PDF)"), "application/pdf"),
    ]
    var = [(t_, a, m) for t_, a, m in belgeler if r.get(t_) and Path(r[t_]).exists()]
    if var:
        B.bolum_basligi(T("Rapor", "Report"), T("seçilen saha ve varsayımlarla", "for the selected site and assumptions"))
        with st.container(key="indir_kartlari"):
            for sutun, (tur, ad, mime) in zip(st.columns(3), var, strict=False):
                sutun.download_button(ad, Path(r[tur]).read_bytes(), file_name=f"saha_raporu.{tur}", mime=mime, width="stretch",
                                      icon=":material/download:")  # fmt: skip
    y = s.tablolar.get("yakinsama")
    if y is not None and len(y):
        st.caption(
            T("Monte Carlo yakınsaması (n → standart hata): ", "Monte Carlo convergence (n → standard error): ")
            + " · ".join(f"{int(a)} → {sayi(b_, 2)}" for a, b_ in zip(y.iloc[:, 0], y.iloc[:, 1], strict=False))
        )
    sure_notu(s, 0)


def paylasim() -> None:
    if not st.session_state.get("secim"):
        return
    q = "&".join(f"{k}={v}" for k, v in st.query_params.to_dict().items())
    if q:
        B.bolum_basligi(T("Paylaşım bağlantısı", "Share link"), T("adres çubuğundaki bağlantı bu sonucu aynı varsayımlarla yeniden açar",
                                                                   "the address-bar link reopens this result with the same assumptions"))  # fmt: skip
        st.code("?" + q, language=None)


# ---------------------------------------------------------------- sayfa
def giris(ot: pd.DataFrame | None, kompakt: bool) -> None:
    baslik = T("Türkiye hibrit santral sahaları için başabaş fiyatı, dakikalar içinde.",
               "Türkiye hybrid plant sites: the break-even power price, in minutes.")  # fmt: skip
    if kompakt:
        with st.container(key="giris_kompakt"):
            st.title(baslik)
        return
    with st.container(key="giris"):
        c = st.columns([1.45, 1], gap="large", vertical_alignment="bottom")
        with c[0]:
            st.html(f'<div class="esik-kas">{T("Türkiye · Rüzgâr + Güneş + Batarya", "Türkiye · Wind + Solar + Battery")}</div>')
            st.title(baslik)
            st.html(
                '<p class="esik-giris">'
                + T(
                    "Haritadan bir nokta seçin: rüzgâr ve güneş profili, komşu santral kalibrasyonu, piyasa ve finans modeliyle saniyeler "
                    "içinde hızlı tarama; optimizasyon ve Monte Carlo ile birkaç dakikada tam analiz.",
                    "Pick a point on the map: a quick scan in seconds with wind and solar profiles, neighbouring wind-farm calibration, "
                    "market and finance models; a full analysis with optimisation and Monte Carlo in a few minutes.",
                )
                + '</p><div class="esik-eylem">'
                + f'<a class="esik-cta" href="#harita">{B.ikon("imlec")} {T("Haritadan saha seç", "Pick a site on the map")}</a>'
                + f'<a class="esik-cta2" href="vaka" target="_self">{T("Ezine vaka çalışması", "Ezine case study")} {B.ikon("ok")}</a></div>'
            )
        with c[1]:
            if ot is not None and len(ot):
                B.giris_onecikanlar(
                    [
                        (sayi(len(ot), 0), "", T("kara hücresi ön tarandı (0,25°)", "land cells pre-screened (0.25°)")),
                        (
                            sayi(len(servis.santraller()), 0),
                            "",
                            T("EPİAŞ verisiyle kalibre RES santrali", "wind farms calibrated on EPİAŞ data"),
                        ),
                        (
                            sayi(float(ot["basabas_en_iyi"].min()), 0),
                            "$/MWh",
                            T("en düşük hücre başabaş fiyatı", "lowest cell break-even price"),
                        ),
                    ]
                )


def _saha_gecerli(sc, kv: dict) -> bool:
    if not sc:
        return False
    try:
        _nokta_bilgisi(sc["enlem"], sc["boylam"], bool(kv["turbin_yerlesimi"]), float(kv["yerlesim_yaricap_km"]), float(kv["baglanti_mw"]))
        return True
    except MotorHatasi:
        return False


def adimlar(sc, kv: dict, sh, stm) -> None:
    gecerli = _saha_gecerli(sc, kv)
    durum_tamam = [gecerli, gecerli, bool(sh), bool(stm)]
    aktif = next((i for i, t in enumerate(durum_tamam) if not t), None)
    notlar = [
        f"{sayi(sc['enlem'], 2)}, {sayi(sc['boylam'], 2)}" if sc else T("harita · koordinat · il/ilçe", "map · coordinates · province"),
        f"{sayi(kv['baglanti_mw'], 0)} MW · {T(*FIYAT_AD[kv['fiyat_senaryosu']])}",
        fiyat(sh.ozet.get("basabas_en_iyi"), 1) if sh else T("saniyeler", "seconds"),
        f"E[NPV] {para(stm.ozet['baz']['e_npv'])}" if stm else T("birkaç dakika", "a few minutes"),
    ]
    B.adim_gostergesi(
        list(
            zip(
                [T("Saha", "Site"), T("Varsayımlar", "Assumptions"), T("Hızlı tarama", "Quick scan"), T("Tam analiz", "Full analysis")],
                notlar,
                strict=True,
            )
        ),
        ["tamam" if t else ("aktif" if i == aktif else "") for i, t in enumerate(durum_tamam)],
    )


def sayfa() -> None:
    url_oku()
    tema = aktif_tema()
    ot = servis.on_tarama()
    sc = st.session_state.get("secim")
    sh, stm = st.session_state.get("sonuc_hizli"), st.session_state.get("sonuc_tam")
    giris(ot, kompakt=bool(sc or sh or stm))
    kv = st.session_state.setdefault("kv", _kv_sozluk(VARSAYILAN))
    adimlar(sc, kv, sh, stm)
    if st.session_state.pop("url_hatasi", False):
        B.uyari_kutusu(T("Bağlantıdaki parametreler okunamadı.", "The link parameters could not be read."), "kotu")
    sol, sag = st.columns([1.85, 1], gap="medium")
    with sol, st.container(key="harita_kart"):
        st.html(
            f'<div id="harita" class="esik-kas">{T("Ön tarama haritası", "Pre-screening map")}</div>'
            '<div class="esik-not">'
            + T("0,25° kara hücreleri, varsayılan ayarlar · bir hücreye tıklayarak saha seçin",
                "0.25° land cells, default settings · click a cell to choose a site") + "</div>"
        )  # fmt: skip
        kolon = st.pills(
            T("Harita katmanı", "Map layer"), list(H.KATMANLAR), format_func=lambda k: T(*H.KISA_AD[k]), key="katman",
            default="basabas_en_iyi", required=True, label_visibility="collapsed",
        )  # fmt: skip
        if ot is None:
            B.uyari_kutusu(
                T(
                    "Ön tarama dosyası henüz yok (src/v2_C2_on_tarama.py). Harita yalnız santralleri gösteriyor.",
                    "Pre-screening file not built yet (src/v2_C2_on_tarama.py). The map shows wind farms only.",
                ),
                "bilgi",
            )
        sc = st.session_state.get("secim")
        ad = st.session_state.get("adaylar")
        if ad is not None and len(ad):  # il/ilçe seçildi: adaylara odaklan
            merkez, zoom = (float(ad["enlem"].mean()), float(ad["boylam"].mean())), 10
        elif sc:
            merkez, zoom = (sc["enlem"], sc["boylam"]), 9
        else:
            merkez, zoom = (39.0, 35.2), 6
        m = H.harita(
            ot, kolon, servis.santraller(), (sc["enlem"], sc["boylam"]) if sc else None, st.session_state.get("adaylar"), None, merkez, zoom,
            tema=tema,
        )  # fmt: skip
        try:
            from streamlit_folium import st_folium

            out = st_folium(m, height=520, use_container_width=True, returned_objects=["last_clicked"], key="harita")
        except Exception:  # bileşen yüklenemezse (ör. test ortamı)
            out = None
        st.html(H.lejant(ot, kolon, tema))
        if ot is not None:
            with st.expander(T("Başabaş fiyatı en düşük 10 hücre", "10 cells with the lowest break-even price")):
                adalar = st.toggle(T("Adaları dahil et", "Include islands"), False, key="ilk10_ada")
                t10 = servis.ilk_n(10, adalar)
                notlar = [
                    " · ".join(x for x in (T("ada", "island") if a else "", T("üst sınıra yakın", "near upper bound") if u else "") if x)
                    for a, u in zip(t10.get("ada", [False] * len(t10)), t10.get("ust_sinir", [False] * len(t10)), strict=True)
                ]
                B.karsilastirma_tablosu(
                    ["#", T("İl / ilçe", "Province / district"), T("Nokta", "Point"), "RES KF", T("Güven", "Confidence"),
                     T("Başabaş, $/MWh", "Break-even, $/MWh"), T("Not", "Note")],
                    [
                        [str(n), f"{r.il} / {r.ilce}", f"{sayi(r.enlem, 2)}, {sayi(r.boylam, 2)}", yuzde(100 * r.res_kf, 1),
                         T(r.guven, {"yüksek": "high", "düşük": "low"}.get(r.guven, r.guven)), sayi(r.basabas_en_iyi, 1), nt]
                        for n, (r, nt) in enumerate(zip(t10.itertuples(), notlar, strict=True), 1)
                    ],
                    vurgulu=0,
                    mobilde_gizle=(2, 4),
                )  # fmt: skip
        tik = (out or {}).get("last_clicked")
        if tik and tik != st.session_state.get("_son_tik"):
            st.session_state["_son_tik"] = tik
            secimi_ayarla(float(tik["lat"]), float(tik["lng"]), "harita")
            st.rerun()
    with sag:
        with B.kart("secim"):
            st.html(f'<div class="esik-kas">{T("1 · Saha seçimi", "1 · Choose a site")}</div>')
            secim_paneli()
        kv = varsayim_paneli()
        b = saha_karti(kv)
        if b is not None:
            if st.button(T("Hızlı tarama", "Quick scan"), type="primary", width="stretch", key="hizli_buton", icon=":material/bolt:"):
                st.session_state["_istek"] = "hizli"
            if st.button(T("Tam analiz (birkaç dakika)", "Full analysis (a few minutes)"), width="stretch", key="tam_buton",
                         icon=":material/query_stats:"):  # fmt: skip
                st.session_state["_istek"] = "tam"
    istek = st.session_state.pop("_istek", None)
    if istek and b is not None:
        calistir(istek, kv)
    sh, stm = st.session_state.get("sonuc_hizli"), st.session_state.get("sonuc_tam")
    # Sekme yok: Streamlit seçili sekmeyi etiketiyle hatırladığından yeni sonuç gizli sekmede kalabiliyordu (tarayıcı testi
    # yakaladı). En son çalıştırılan (ya da bağlantıda istenen) mod üstte, diğeri altında açılır bölümde.
    son = st.session_state.get("son_mod", "tam" if stm else "hizli")
    bloklar = {"tam": (T("Tam analiz", "Full analysis"), stm, tam_sonuc), "hizli": (T("Hızlı tarama", "Quick scan"), sh, hizli_sonuc)}
    ust, alt = (bloklar["tam"], bloklar["hizli"]) if (son == "tam" and stm) or not sh else (bloklar["hizli"], bloklar["tam"])
    if ust[1]:
        st.subheader(ust[0], anchor="sonuc")
        ust[2](ust[1])
    if alt[1]:
        with st.expander(T(f"{alt[0]} sonucu", f"{alt[0]} result")):
            alt[2](alt[1])
    if sh or stm:
        paylasim()


sayfa()
