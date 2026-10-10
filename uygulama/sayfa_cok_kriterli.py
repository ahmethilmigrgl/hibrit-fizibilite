"""
Çok kriterli saha seçimi (v3 Faz E3): dışlayıcı kısıtlar → AHP ağırlıkları (hazır profil ya da ikili karşılaştırma,
tutarlılık oranı) → TOPSIS uygunluk haritası ve sıralama → ağırlık dayanıklılığı P(ilk 10) → mevcut santrallerle doğrulama.

Hesap çekirdeği src/cbs/cok_kriterli.py ve src/cbs/kriterler.py; doğrulama sayıları data/atlas/v3_cok_kriterli_dogrulama.json
(src/v3_E3_cok_kriterli.py). Görünüm "Eşik" tasarım sistemiyle.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import veri_katmani
from src.cbs import cok_kriterli as CK
from src.cbs import kriterler as KR
from uygulama import harita as H
from uygulama.ortak import RES, SOLUK, T, ciz, md, sayi, sekil, yuzde
from uygulama.tasarim import bilesenler as B
from uygulama.tasarim.stil import aktif_tema

VK = KR.vektor()
SAATY = [9.0, 7.0, 5.0, 3.0, 1.0, 1 / 3, 1 / 5, 1 / 7, 1 / 9]
SAATY_AD = {9.0: "9", 7.0: "7", 5.0: "5", 3.0: "3", 1.0: "1"}


def _saaty_metin(v: float) -> str:
    return SAATY_AD.get(v) or f"1/{round(1 / v)}"


def _ad(k: str) -> str:
    return T(KR.KRITERLER[k][0], KR.KRITERLER[k][1])


@st.cache_data(show_spinner=False)
def _tablo() -> pd.DataFrame:
    d = KR.tablo().copy()
    d["neden"] = KR.dislanan(d)
    return d


@st.cache_data(show_spinner=False)
def _dogrulama() -> dict:
    p = veri_katmani.yol("atlas/v3_cok_kriterli_dogrulama.json", zorunlu=False)
    return json.loads(p.read_text(encoding="utf-8")) if p is not None else {}


@st.cache_data(show_spinner=False, max_entries=16)
def _hesapla(kriterler: tuple[str, ...], w: tuple[float, ...], adalar: bool) -> tuple[pd.DataFrame, float]:
    d = _tablo()
    u = d[(d["neden"] == "") | (adalar & (d["neden"] == "ada"))].reset_index(drop=True)
    X, f = KR.matris(u, list(kriterler))
    u["uygunluk"] = 100 * CK.topsis(X, np.array(w), f, VK)
    u["p_ilk10"] = CK.dayaniklilik(X, np.array(w), f, K=10, n=300, alfa=50, vektor=VK)
    # doğrulama: hesaplanabilen tüm hücreler (dışlananlar dahil), etiket = hücrede mevcut RES
    v = d[(d["hata"].fillna("") == "") & d["basabas_en_iyi"].notna()].reset_index(drop=True)
    Xv, fv = KR.matris(v, list(kriterler))
    a = CK.auc(CK.topsis(Xv, np.array(w), fv, VK), v["mevcut_res"].to_numpy(bool))
    return u, a


st.title(T("Çok kriterli saha seçimi", "Multi-criteria site selection"))
st.caption(
    T(
        "Ekonomik sıralama (başabaş fiyat) yalnızca bir kriterdir. Bu sayfa şebekeye ve yola uzaklığı, eğimi, kuş göç riskini, "
        "rüzgâr tahmininin güvenini ve lojistiği de tartar: önce dışlayıcı kısıtlar hücreleri eler, kalanlar AHP ağırlıklarıyla "
        "TOPSIS yöntemiyle sıralanır. Ayrıntı: docs/v3_E_cbs_cok_kriterli_lojistik.md.",
        "The economic ranking (break-even price) is only one criterion. This page also weighs distance to the grid and roads, slope, "
        "bird-migration risk, confidence of the wind estimate and logistics: exclusion constraints remove cells first, the rest are "
        "ranked by TOPSIS with AHP weights. Details: docs/v3_E_cbs_cok_kriterli_lojistik.md.",
    )
)
try:
    d = _tablo()
except Exception:
    B.bos_durum(
        T("Ön tarama verisi yok", "No pre-screening data"),
        T("data/atlas/on_tarama.parquet ve cbs_hucre.parquet gerekli.", "data/atlas/on_tarama.parquet and cbs_hucre.parquet are required."),
    )
    st.stop()

# --- 1. Dışlayıcı kısıtlar ---
B.bolum_basligi(T("1. Dışlayıcı kısıtlar", "1. Exclusion constraints"), T("bu hücreler sıralamaya girmez", "these cells are not ranked"))
say = d["neden"].replace("", "uygun").value_counts()
NEDEN_EN = {"uygun": "eligible", "koruma alanı": "protected area", "uygun alan < %10": "eligible area < 10%", "ada": "island",
            "başabaş hesaplanamadı": "break-even not computable", "hesap hatası": "calculation error"}  # fmt: skip
c = st.columns(min(len(say), 5))
for i, (k, n) in enumerate(say.head(5).items()):
    B.kpi_karti(c[i], T(k.capitalize(), NEDEN_EN.get(k, k).capitalize()), sayi(n, 0), aciklama=T("hücre", "cells"))
st.caption(
    T(
        "Uygun alan: 2 km yarıçapta yerleşim (500 m), yol ve iletim hattı (devrilme mesafesi), havalimanı (5 km), eğim (> 15°) ve "
        "koruma alanı dışlamalarından arta kalan pay. Dışlama, ağırlıkla telafi edilemeyen kısıttır (koruma alanında yüksek rüzgâr "
        "kötü bağlantıyı dengeleyemez); değerlendirme kriterleri ise birbirini telafi edebilir.",
        "Eligible area: share left within 2 km after settlement (500 m), road and power-line (topple distance), airport (5 km), slope "
        "(> 15°) and protected-area exclusions. Exclusions cannot be compensated by weights; evaluation criteria can trade off.",
    )
)
adalar = st.toggle(T("Adaları dahil et", "Include islands"), value=False, key="ck_ada")

# --- 2. Ağırlıklar ---
B.bolum_basligi(
    T("2. Kriter ağırlıkları (AHP)", "2. Criterion weights (AHP)"),
    T("hazır profil ya da kendi ikili karşılaştırmanız", "preset profile or your own pairwise comparisons"),
)
kip = (
    st.segmented_control(
        T("Ağırlık girişi", "Weight input"),
        ["profil", "ikili"],
        default="profil",
        format_func=lambda x: T("Hazır profil", "Preset profile") if x == "profil" else T("İkili karşılaştırma", "Pairwise comparison"),
        key="ck_kip",
    )
    or "profil"
)
K = list(KR.KRITERLER)
if kip == "profil":
    p = st.radio(
        T("Profil", "Profile"),
        list(KR.PROFILLER),
        format_func=lambda x: T(KR.PROFILLER[x][0], KR.PROFILLER[x][1]),
        horizontal=True,
        index=2,
        key="ck_profil",
    )
    A = KR.profil_matrisi(p)
else:
    K = st.multiselect(T("Kriterler", "Criteria"), list(KR.KRITERLER), default=list(KR.KRITERLER), format_func=_ad, key="ck_kriter") or [
        "ekonomi"
    ]
    st.caption(
        T(
            "Saaty ölçeği: 1 eşit, 3 biraz, 5 belirgin, 7 çok, 9 son derece önemli. Sola doğru değerler soldaki kriterin, sağa doğru "
            "(1/3 … 1/9) sağdakinin daha önemli olduğunu söyler. Başlangıç değerleri 'Dengeli' profile en yakın Saaty sayılarıdır.",
            "Saaty scale: 1 equal, 3 moderate, 5 strong, 7 very strong, 9 extreme importance. Values to the left favour the left "
            "criterion, to the right (1/3 … 1/9) the right one. Defaults are the Saaty numbers closest to the 'Balanced' profile.",
        )
    )
    s0 = KR.PROFILLER["dengeli"][2]
    girdi = {}
    with st.expander(
        T(f"{len(K) * (len(K) - 1) // 2} ikili karşılaştırma", f"{len(K) * (len(K) - 1) // 2} pairwise comparisons"), expanded=True
    ):
        for i in range(len(K)):
            for j in range(i + 1, len(K)):
                r = s0[K[i]] / s0[K[j]]
                v0 = min(SAATY, key=lambda s, r=r: abs(np.log(s) - np.log(r)))
                girdi[(i, j)] = st.select_slider(
                    f"{_ad(K[i])}  ↔  {_ad(K[j])}", SAATY, value=v0, format_func=_saaty_metin, key=f"ck_{K[i]}_{K[j]}"
                )
    A = CK.ikili_matris(girdi, len(K))
ah = CK.ahp(A)
w = ah["agirlik"]
c = st.columns([1.4, 1], gap="medium")
with c[0]:
    o = np.argsort(-w)
    f = go.Figure(
        go.Bar(
            x=w[o] * 100,
            y=[_ad(K[i]) for i in o],
            orientation="h",
            marker_color=RES,
            text=[yuzde(100 * w[i], 0) for i in o],
            textposition="outside",
        )
    )
    f.update_yaxes(autorange="reversed")
    f.update_traces(cliponaxis=False)
    f.update_xaxes(range=[0, 100 * float(w.max()) * 1.18])
    ciz(sekil(f, T("AHP ağırlıkları (özvektör)", "AHP weights (eigenvector)"), "", "%", yukseklik=60 + 34 * len(K)))
with c[1]:
    B.kpi_karti(
        st,
        T("Tutarlılık oranı (CR)", "Consistency ratio (CR)"),
        sayi(max(ah["CR"], 0.0), 3),
        aciklama=f"λmaks {sayi(ah['lambda_maks'], 2)} · CI {sayi(max(ah['CI'], 0.0), 3)}",
    )
    if ah["CR"] > 0.10:
        B.uyari_kutusu(
            T("CR > 0,10: karşılaştırmalar tutarsız (ör. A > B, B > C ama C > A). Saaty'nin önerisi: en çelişkili yargıları gözden geçirin.",
              "CR > 0.10: comparisons are inconsistent (e.g. A > B, B > C but C > A). Saaty's advice: revisit the most conflicting judgements."),
            "uyari",
        )  # fmt: skip
    else:
        st.caption(T("CR ≤ 0,10: karşılaştırmalar kabul edilebilir tutarlılıkta.", "CR ≤ 0.10: comparisons are acceptably consistent."))

# --- 3. Uygunluk haritası ve sıralama ---
B.bolum_basligi(
    T("3. Uygunluk haritası ve sıralama", "3. Suitability map and ranking"),
    T("TOPSIS yakınlık katsayısı × 100", "TOPSIS closeness coefficient × 100"),
)
u, auc_kul = _hesapla(tuple(K), tuple(float(x) for x in w), adalar)
tema = aktif_tema()
c = st.columns([1.5, 1], gap="medium")
with c[0]:
    try:
        from streamlit_folium import st_folium

        m = H.harita(u, "uygunluk", tema=tema)
        st_folium(m, height=470, use_container_width=True, returned_objects=[], key="ck_harita")
    except Exception:
        pass
    st.html(H.lejant(u, "uygunluk", tema))
with c[1]:
    ilk = u.nlargest(12, "uygunluk")
    B.karsilastirma_tablosu(
        ["#", T("Hücre", "Cell"), T("Puan", "Score"), T("Başabaş", "Break-even"), "P(ilk 10)" if T("a", "b") == "a" else "P(top 10)"],
        [[str(i), f"{r.il} / {r.ilce}", sayi(r.uygunluk, 1), sayi(r.basabas_en_iyi, 1), yuzde(100 * r.p_ilk10, 0)] for i, r in enumerate(ilk.itertuples(), 1)],
        mobilde_gizle=(3,),
    )  # fmt: skip
    st.caption(
        T(
            "P(ilk 10): ağırlıklar seçilen değerlerin çevresinde Dirichlet(50·w) ile 300 kez rastgele örneklendiğinde hücrenin ilk 10'a "
            "girme sıklığı. Yüksekse sıralama ağırlık seçimine duyarsızdır.",
            "P(top 10): share of 300 random weight draws around the chosen weights (Dirichlet(50·w)) in which the cell is in the top 10. "
            "High means the ranking does not hinge on the exact weights.",
        )
    )
eko = u.nsmallest(10, "basabas_en_iyi")
ortak = len(set(eko.index) & set(u.nlargest(10, "uygunluk").index))
st.markdown(
    md(
        T(
            f"Ekonomik ilk 10 (en düşük başabaş) ile bu ağırlıklardaki ilk 10'un **{ortak}** hücresi ortak.",
            f"**{ortak}** cells are shared between the economic top 10 (lowest break-even) and the top 10 under these weights.",
        )
    )
)

# --- 4. Doğrulama ---
B.bolum_basligi(
    T("4. Doğrulama: mevcut rüzgâr santralleri", "4. Validation: existing wind farms"),
    T("geliştiricilerin gerçek seçimleri", "developers' actual choices"),
)
dg = _dogrulama()
c = st.columns([1.2, 1], gap="medium")
with c[0]:
    if dg.get("roc"):
        f = go.Figure()
        f.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line={"color": SOLUK, "dash": "dot"}, name=T("rastgele", "random")))
        f.add_trace(
            go.Scatter(
                x=dg["roc"]["fp"],
                y=dg["roc"]["tp"],
                mode="lines",
                line={"color": RES, "width": 2.5},
                name=f"AUC {sayi(dg['roc']['auc'], 2)}",
            )
        )
        ciz(sekil(f, T("ROC: en iyi ayıran ağırlıklar (güven kriteri hariç)", "ROC: best-separating weights (confidence excluded)"),
                  T("doğru pozitif oranı", "true positive rate"), T("yanlış pozitif oranı", "false positive rate"), yukseklik=340))  # fmt: skip
with c[1]:
    B.kpi_karti(st, T("Seçtiğiniz ağırlıkların AUC'si", "AUC of your weights"), sayi(auc_kul, 2),
                aciklama=T(f"{dg.get('n_mevcut', '–')} santralli hücre / {dg.get('n_hucre', '–')}", f"{dg.get('n_mevcut', '–')} cells with wind farms / {dg.get('n_hucre', '–')}"))  # fmt: skip
    if dg.get("auc"):
        tek = dg["auc"]["tek_kriter"]
        satir = [[_ad(k), sayi(v, 2)] for k, v in sorted(((k, v) for k, v in tek.items() if k in KR.KRITERLER), key=lambda x: -x[1])]
        satir.append([T("RES KF (yalnız rüzgâr)", "Wind CF (wind only)"), sayi(tek.get("ruzgar_kf"), 2)])
        B.karsilastirma_tablosu([T("Tek kriter", "Single criterion"), "AUC"], satir)
st.caption(
    T(
        "AUC: rastgele seçilen santralli bir hücrenin santralsiz bir hücreden yüksek puan alma olasılığı (0,5 = rastgele, 1 = kusursuz). "
        "Dikkat: 'güven' kriteri tanımı gereği kalibre santrallere yakınlıktır, başabaş fiyat da santrallerden kalibre edilen "
        "katsayıları kullanır; bu yüzden açığa çıkan tercih ağırlıkları güven kriteri dışarıda bırakılarak bulundu ve mevcut "
        "santraller zaten tercih edilen yerleri gösterir, en iyi yerleri değil.",
        "AUC: probability that a random cell with a wind farm scores higher than one without (0.5 = random, 1 = perfect). Caution: "
        "the 'confidence' criterion is by construction proximity to calibrated plants and the break-even uses plant-calibrated "
        "factors, so revealed-preference weights were fitted without confidence; existing plants show chosen sites, not best sites.",
    )
)
if dg.get("acik_tercih"):
    at = dg["acik_tercih"]["guvensiz_ekonomi"]
    st.markdown(
        md(
            T(
                "**Gerçek dünya tercihleri** (mevcut santralleri en iyi ayıran ağırlıklar, AUC ",
                "**Revealed preferences** (weights best separating existing plants, AUC ",
            )
            + f"{sayi(at['auc'], 2)}): "
            + " · ".join(f"{_ad(k)} {yuzde(100 * v, 0)}" for k, v in sorted(at["agirlik"].items(), key=lambda x: -x[1]))
        )
    )
