"""
Yöntem sayfası: veri kaynakları ve atıflar, atlas ve güven seviyeleri, iki analiz modu, basitleştirmeler, doğrulama sonuçları
(results/v2_dogrulama.json — src/v2_C9_sonuclari_paketle.py), sınırlamalar, gizlilik ve kullanım sınırları.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.ayarlar import config_oku, deger
from uygulama.ortak import ATIFLAR_EN, T, ayar, sayi, tablo

KOK = Path(__file__).resolve().parents[1]


@st.cache_data(show_spinner=False)
def dogrulama() -> dict:
    p = KOK / "results" / "v2_dogrulama.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


d = dogrulama()
st.title(T("Yöntem", "Method"))
st.caption(
    T(
        "Ayrıntılı formülasyonlar ve doğrulama: docs/v2_A_veri_altyapisi.md, docs/v2_B_analiz_motoru.md, docs/v2_C_arayuz.md ve v1 belgeleri (docs/00–07).",
        "Detailed formulations and validation: docs/v2_A_veri_altyapisi.md, docs/v2_B_analiz_motoru.md, docs/v2_C_arayuz.md and the v1 documents (docs/00–07).",
    )
)

st.header(T("1. Veri kaynakları", "1. Data sources"))
kaynak = pd.DataFrame(
    [
        (
            "ERA5 (Copernicus C3S)",
            T(
                "Saatlik rüzgâr, 100/10 m, 2014–2023; Türkiye 0,25° nokta gridi (1.464 kara hücresi)",
                "Hourly wind 100/10 m, 2014–2023; Türkiye 0.25° point grid (1,464 land cells)",
            ),
            "CC-BY (C3S)",
        ),
        (
            "PVGIS-SARAH3 (JRC)",
            T("Saatlik güneş; aynı hücrelerde GES KF gridi (pvlib PVWatts)", "Hourly solar; PV CF grid on the same cells (pvlib PVWatts)"),
            T("Atıfla serbest", "Free with attribution"),
        ),
        (
            "Global Wind Atlas 3.0",
            T(
                "100 m ortalama hız (1 km ve 250 m): GWA düzeltmesi, türbin yerleşimi, aday noktalar",
                "Mean speed at 100 m (1 km and 250 m): GWA correction, turbine layout, candidates",
            ),
            "CC BY 4.0",
        ),
        (
            "EPİAŞ",
            T(
                "Santral üretimi (yalnız çevrimdışı kalibrasyon), ulusal piyasa paketi (PTF, SFK)",
                "Plant output (offline calibration only), national market package (prices, SFK)",
            ),
            T("Kaynak gösterilerek", "With attribution"),
        ),
        ("OpenStreetMap", T("RES santralleri ve türbin konumları/etiketleri", "Wind farms and turbine positions/tags"), "ODbL"),
        ("geoBoundaries, Natural Earth", T("İl/ilçe sınırları, kıyı", "Province/district boundaries, coastline"), "ODbL / CC BY-SA / PD"),
        ("Copernicus DEM GLO-90", T("Rakım ızgarası (0,02°)", "Elevation grid (0.02°)"), T("Atıfla serbest", "Free with attribution")),
    ],
    columns=[T("Kaynak", "Source"), T("Kullanım", "Use"), T("Lisans", "Licence")],
)
tablo(kaynak, hide_index=True, width="stretch")
st.caption(
    T(
        "Uygulama çalışırken hiçbir dış API'ye ve kişisel kimlik bilgisine (CDS, EPİAŞ) bağlanmaz: tüm veriler önceden hazırlanmış yerel paketlerden okunur. Harita altlığı uygulamanın kendi il sınırı ve kıyı verisinden çizilir (geoBoundaries, Natural Earth); OpenStreetMap karoları yalnız katman menüsünden seçilirse tarayıcıya yüklenir.",
        "At run time the app connects to no external API and uses no personal credentials (CDS, EPİAŞ): all data are read from pre-built local packages. The base map is drawn from the app's own province and coastline data (geoBoundaries, Natural Earth); OpenStreetMap tiles are loaded by the browser only if chosen in the layer menu.",
    )
)

st.header(T("2. Rüzgâr: atlas kalibrasyonu ve güven seviyeleri", "2. Wind: atlas calibration and confidence levels"))
st.markdown(
    T(
        """
- **Kalibrasyon atlası:** 90 RES santralinin EPİAŞ üretimi, santralin ERA5 hücresi ve **santralin kendi türbin vekiliyle** (OSM birim gücü/üretici/rotor → windpowerlib güç eğrisi; göbek) kalibre edildi. Hız katsayısı ay × saat matrisidir; talimat/arıza şüpheli saatler hariç tutulur (sistem kesintisi finans modelinde ayrıca uygulanır).
- **Aktarım:** Santral artığı R = K / c (c = gerçek türbin konumlarındaki GWA / ERA5). Yeni sahada K = c_saha × Σ w·R (30 km içindeki benzer santraller, ters mesafe ağırlığı; yoksa ulusal medyan R). Düzeltilmiş hız sahanın göbek yüksekliğine taşınır ve **seçilen türbinin** güç eğrisinden geçer.
- **Türbin yerleşimi (varsayılan açık):** c_saha, yarıçap içindeki en rüzgârlı GWA 250 m hücrelerinden. Çapraz doğrulamada noktadan belirgin biçimde daha isabetli (aşağıda). İz kaybı, erişim, eğim ve izinler modellenmez.
- **Güven seviyesi:** 30 km içinde benzer kalibre santral varsa *yüksek*, yoksa *düşük*. Hata, birini dışarıda bırak çapraz doğrulamasıyla (santral kendi türbiniyle tahmin edilerek) ölçüldü.
""",
        """
- **Calibration atlas:** EPİAŞ output of 90 wind farms was calibrated against each farm's ERA5 cell **with the farm's own turbine proxy** (OSM unit rating/manufacturer/rotor → windpowerlib power curve; hub height). The speed factor is a month × hour matrix; hours suspected of curtailment/outage are excluded (system curtailment is applied separately in the finance model).
- **Transfer:** Farm residual R = K / c (c = GWA at the actual turbine positions / ERA5). At a new site K = c_site × Σ w·R (similar farms within 30 km, inverse-distance weights; otherwise the national median R). The corrected speed is moved to the site's hub height and passed through **the selected turbine's** power curve.
- **Turbine layout (on by default):** c_site from the windiest GWA 250 m cells within the radius. Markedly more accurate than the point in cross-validation (below). Wake losses, access, slope and permits are not modelled.
- **Confidence level:** *high* if a similar calibrated farm lies within 30 km, otherwise *low*. Error measured by leave-one-out cross-validation (each farm predicted with its own turbine).
""",
    )
)
if d.get("guven"):
    g = pd.DataFrame(d["guven"])
    tablo(
        pd.DataFrame(
            {
                T("Seviye", "Level"): g["guven"],
                "n": g["santral"].astype(int).astype(str),
                T("Medyan |hata| [puan]", "Median |error| [pts]"): [
                    f"{sayi(a, 1)} ({sayi(b, 1)}–{sayi(c, 1)})"
                    for a, b, c in zip(g["mutlak_medyan"], g["medyan_alt"], g["medyan_ust"], strict=True)
                ],
                T("P90 |hata| [puan]", "P90 |error| [pts]"): [
                    f"{sayi(a, 1)} ({sayi(b, 1)}–{sayi(c, 1)})" for a, b, c in zip(g["mutlak_p90"], g["p90_alt"], g["p90_ust"], strict=True)
                ],
                T("Ort. hata", "Mean error"): g["ort_hata"],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(T("Parantez içinde bootstrap %90 güven aralığı.", "Bootstrap 90% confidence intervals in brackets."))
if d.get("cv"):
    cv = pd.DataFrame(d["cv"])
    st.markdown(
        T("**Saha GWA modu karşılaştırması (GWA ölçekli kural, 90 santral):**", "**Site GWA mode comparison (GWA-scaled rule, 90 farms):**")
    )
    tablo(cv, hide_index=True, width="stretch")

st.header(T("3. İki analiz modu", "3. Two analysis modes"))
tablo(
    pd.DataFrame(
        [
            (
                T("Hızlı tarama", "Quick scan"),
                T("Saniyeler", "Seconds"),
                T(
                    "KF ve belirsizlik bandı, yakalanma oranları, LCOE, başabaş fiyatı, 4 standart tasarımın deterministik NPV'si, 24 temsilî günlük kapasite MILP'i",
                    "CFs and uncertainty band, capture rates, LCOE, break-even, deterministic NPV of 4 standard designs, 24-representative-day capacity MILP",
                ),
            ),
            (
                T("Tam analiz", "Full analysis"),
                T("1–6 dakika", "1–6 minutes"),
                T(
                    "Tam yıl MILP (%0,5 boşluk), çalışma anında işletme tabloları, yakınsamalı Monte Carlo (fiyat, hava, kanibalizasyon, SFK doyumu, kesinti, CAPEX, takvim, güven seviyesinden rüzgâr σ), gelir yapıları, karar kuralı ve tetikleyiciler, HTML/PDF rapor",
                    "Full-year MILP (0.5% gap), run-time dispatch tables, converging Monte Carlo (price, weather, cannibalisation, SFK saturation, curtailment, CAPEX, schedule, wind σ from confidence), revenue structures, decision rule and triggers, HTML/PDF report",
                ),
            ),
        ],
        columns=[T("Mod", "Mode"), T("Süre", "Time"), T("Kapsam", "Scope")],
    ),
    hide_index=True,
    width="stretch",
)

st.header(T("4. Basitleştirmeler", "4. Simplifications"))
st.markdown(
    T(
        "- Güneş profili sahanın 0,25° hücresinin temsilî kara noktasından (PVGIS), sabit güneye bakan optimum eğim.\n"
        "- Piyasa ulusaldır: bölgesel fiyat ve bölgesel sistem kesintisi farkı yok.\n"
        "- Tam analiz işletme tabloları seyrek ızgarada (doğrulama: v1 ızgarasına göre −0,01 M$).\n"
        '- Hızlı tarama karar vermez; yalnız "tam analize değer mi" sorusunu yanıtlar.\n'
        "- Ön tarama haritası hücre başına tek nokta ve varsayılan varsayımlarla üretildi; sahaya özgü analizin yerini tutmaz.",
        "- The solar profile comes from the representative land point of the site's 0.25° cell (PVGIS), fixed south-facing optimum tilt.\n"
        "- The market is national: no regional price or regional curtailment differences.\n"
        "- Full-analysis dispatch tables use a sparse grid (validation: −0.01 M$ vs the v1 grid).\n"
        '- The quick scan does not decide; it only answers "is a full analysis worthwhile".\n'
        "- The pre-screening map uses one point per cell and default assumptions; it does not replace a site-specific analysis.",
    )
)

st.header(T("5. Doğrulama", "5. Validation"))
for anahtar, baslik in [
    (
        "ezine",
        T("Ezine: atlas aktarımı kontrolü (aynı veri, E-141/4200 @ 120 m)", "Ezine: atlas transfer check (same data, E-141/4200 @ 120 m)"),
    ),
    (
        "regresyon",
        T(
            "Ezine regresyonu: tam analiz (v1 kalibrasyonu) vs v1 nihai baz vaka",
            "Ezine regression: full analysis (v1 calibration) vs v1 final base case",
        ),
    ),
    ("tutarlilik", T("Hızlı ↔ tam tutarlılığı (3 saha)", "Quick ↔ full consistency (3 sites)")),
    ("bes_saha", T("Beş saha tipi — hızlı tarama", "Five site types — quick scan")),
    ("sure", T("Süreler (2 çekirdek benzetimi)", "Run times (2-core simulation)")),
]:
    if d.get(anahtar):
        st.markdown(f"**{baslik}**")
        tablo(pd.DataFrame(d[anahtar]), hide_index=True, width="stretch")

st.header(T("6. Sınırlamalar", "6. Limitations"))
st.markdown(
    T(
        "- **Saha ölçümü yok:** rüzgâr tahmini yeniden analiz + komşu santral kalibrasyonuna dayanır; düşük güvenli bölgelerde tipik hata ±6, %90'da ±12 puan KF.\n"
        "- **Santral türbinleri vekildir:** OSM etiketleri eksik olduğunda birim güç kapasite / türbin adedinden, özgül güç güç sınıfından tahmin edilir.\n"
        "- **Tek komşu:** yüksek güvenli bir tahmin tek bir santrale dayanabilir; uygulama bunu ayrıca uyarır.\n"
        "- **Modellenmeyenler:** arazi, imar ve izinler; türbinler arası iz etkisi (toplam kayıp %12 içinde ortalama); şebeke bağlantı kapasitesi ve TEİAŞ görüşü; yerel koşullar.\n"
        "- **SFK, YEKDEM ve PPA varsayımları** (fiyat, doyum, iskonto) tahmine dayanır; ayrıntı v1 belgelerinde.",
        "- **No on-site measurement:** the wind estimate relies on reanalysis + neighbouring farm calibration; in low-confidence areas the typical error is ±6, 90% ±12 CF points.\n"
        "- **Farm turbines are proxies:** when OSM tags are missing, unit rating is estimated from capacity / turbine count and specific power from the rating class.\n"
        "- **Single neighbour:** a high-confidence estimate may rely on one farm; the app flags this.\n"
        "- **Not modelled:** land, zoning and permits; turbine wakes (averaged within the 12% total loss); grid connection capacity and TEİAŞ opinion; local conditions.\n"
        "- **SFK, YEKDEM and PPA assumptions** (prices, saturation, discount) are estimates; see the v1 documents.",
    )
)

st.header(T("7. Gizlilik ve kullanım sınırları", "7. Privacy and usage limits"))
a = ayar()
mot = deger(config_oku()["v2"]["motor"])
mb, dk = mot["onbellek_azami_mb"], mot["tam_zaman_asimi_s"] / 60
st.markdown(
    T(
        f"- Kişisel veri toplanmaz; hesap yok, çerez tabanlı izleme yok. Sonuç önbelleğinde yalnız 0,01°'ye yuvarlatılmış koordinat ve analiz varsayımları tutulur (en fazla {sayi(mb, 0)} MB, en eski kayıtlar silinir).\n"
        f"- Kötüye kullanımı önlemek için oturum başına saatte en fazla {a['istek_siniri']['hizli']['azami']} hızlı tarama ve {a['istek_siniri']['tam']['azami']} tam analiz; aynı anda tek tam analiz çalışır, en fazla {a['tam_sira_azami']} iş sırada bekleyebilir; tam analiz zaman aşımı {sayi(dk, 0)} dakika.\n"
        "- Paylaşım bağlantısı yalnız koordinatı ve varsayılandan farklı varsayımları içerir.",
        f"- No personal data is collected; no accounts, no cookie-based tracking. The result cache stores only coordinates rounded to 0.01° and analysis assumptions (at most {sayi(mb, 0)} MB, oldest entries evicted).\n"
        f"- To prevent abuse: at most {a['istek_siniri']['hizli']['azami']} quick scans and {a['istek_siniri']['tam']['azami']} full analyses per session per hour; one full analysis runs at a time and at most {a['tam_sira_azami']} jobs may queue; full-analysis timeout {sayi(dk, 0)} minutes.\n"
        "- A share link contains only the coordinates and the assumptions that differ from the defaults.",
    )
)

st.header(T("8. Atıflar", "8. Attributions"))
st.caption(ATIFLAR_EN)
st.caption(
    T(
        "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr). Ayrıntı: DATA_SOURCES.md.",
        "Source: EPİAŞ Transparency Platform (seffaflik.epias.com.tr). Details: DATA_SOURCES.md.",
    )
)
with st.expander(T("Hakkında", "About")):
    st.markdown(
        T(
            "**Ahmet Hilmi Görgülü** — endüstri mühendisliği öğrencisi. Bu uygulama, yenilenebilir enerji yatırımı ve proje geliştirme için hazırladığım kişisel bir fizibilite çalışmasının (portföy) parçasıdır.",
            "**Ahmet Hilmi Görgülü** — industrial engineering student. This app is part of a personal feasibility study (portfolio) for renewable energy investment and project development.",
        )
    )
