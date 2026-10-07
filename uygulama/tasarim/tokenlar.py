"""
Tasarım belirteçleri (design tokens): renk, yazı tipi, boşluk, köşe ve marka değerleri TEK yerde.

İki tema (kullanıcı üst çubuktan seçer):
- "acik" — B yönü "Yatırım raporu": kâğıt zemin, çam yeşili vurgu, Newsreader başlık + Public Sans arayüz.
- "koyu" — A yönü "Kontrol odası": koyu zemin, kehribar vurgu, IBM Plex Sans arayüz + IBM Plex Mono sayılar.

Bu dosyadan türeyenler: `.streamlit/config.toml` (src/v2_tasarim_tema.py yazar; tests/test_v2_tasarim.py eşitliği denetler),
özel CSS (stil.py), Plotly şablonu (grafik.py), harita renkleri (harita.py) ve logo SVG'leri. Başka hiçbir dosyada renk kodu
yazılmaz.

Kontrast: metin/zemin çiftleri WCAG AA (≥ 4,5:1) — `kontrast()`, testte denetlenir. `metin_silik` yalnız süs ve büyük
ikincil öğeler içindir (≥ 3:1). Harita skalası viridis (algısal olarak düzgün, renk körlüğünde sıralama korunur).
"""

from __future__ import annotations

MARKA = {"ad": "Eşik", "alt_tr": "Hibrit saha analizi", "alt_en": "Hybrid site analytics"}

# Viridis'ten 6 eşit aralıklı örnek (koyu mor → sarı)
VIRIDIS6 = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"]

# v1 kategorik veri paleti (açık tema; outputs/ ve rapor grafikleriyle aynı, renk körlüğü için doğrulanmış sıra). Sayfa kodu
# bu kanonik renkleri kullanır; koyu temada grafik.ciz() izleri aynı anahtardaki KOYU_VERI tonlarına çevirir. İki ton
# uygulamada koyulaştırıldı (beyaz yüzeyde grafik nesnesi kontrastı ≥ 3:1, WCAG 1.4.11): hibrit #1baf7a → #15966a,
# altin2 #c9a227 → #a8841a.
VERI = {
    "res": "#2a78d6",
    "ges": "#eb6834",
    "hibrit": "#15966a",
    "batarya": "#7f6bd1",
    "koyu": "#1d4f91",
    "soluk": "#8a8984",
    "altin": "#b8860b",
    "altin2": "#a8841a",
}
KOYU_VERI = {
    "res": "#5aa9ff",
    "ges": "#ff8a50",
    "hibrit": "#3fcf8e",
    "batarya": "#a993ff",
    "koyu": "#8ab4f0",
    "soluk": "#9aa39e",
    "altin": "#e0b040",
    "altin2": "#ecc95a",
}

# Vaka çalışması sayfasının (v1) ek grafik renkleri → koyu tema karşılıkları. Sıralı mavi rampalar koyu zeminde ters
# çevrilir (koyu zeminde "daha çok" = daha parlak), kırmızı vurgu koyu temanın "kötü" tonuna gider.
KOYU_EK = {
    "#c6dbf5": "#24446e",
    "#8ab4ea": "#2f6bb8",
    "#1d4f91": "#8ab4ea",
    "#0b2b57": "#c6dbf5",
    "#9ec5ef": "#3a6fae",
    "#c0392b": "#ff6f7d",
}

TEMALAR: dict[str, dict] = {
    "acik": {
        "ad": ("Açık", "Light"),
        "streamlit": "light",
        "renk": {
            "zemin": "#f8f6f1",
            "yuzey": "#ffffff",
            "yuzey2": "#f0ede5",
            "cizgi": "#e2ddd2",
            "metin": "#1b1f1d",
            "metin_soluk": "#585f5b",
            "metin_silik": "#737a75",
            "vurgu": "#0f6b57",  # derin çam yeşili
            "vurgu_metin": "#ffffff",
            "vurgu_zemin": "#e3efe9",
            "iyi": "#1d7a4c",
            "uyari": "#8f5b00",
            "kotu": "#b3261e",
            "bilgi": "#2958a8",
            "iyi_zemin": "#e8f3ec",
            "uyari_zemin": "#fbf2df",
            "kotu_zemin": "#fbecea",
            "bilgi_zemin": "#eaf0f9",
            "deniz": "#e4eaea",
            "kara": "#fbfaf6",
            "sinir": "#cfc9bd",
            "iskelet": "#ece8df",
            "iskelet_parlak": "#f6f3ec",
        },
        "veri": VERI,
        "harita_skala": VIRIDIS6[:],  # sınıf 0 (en cazip) = koyu mor: açık altlıkta en belirgin
        "yazi": {"arayuz": "Public Sans", "sayi": "Public Sans", "baslik": "Newsreader", "kod": "IBM Plex Mono"},
        "baslik_agirlik": 500,
    },
    "koyu": {
        "ad": ("Koyu", "Dark"),
        "streamlit": "dark",
        "renk": {
            "zemin": "#0b0f0e",
            "yuzey": "#121816",
            "yuzey2": "#18201d",
            "cizgi": "#26312c",
            "metin": "#e7ece9",
            "metin_soluk": "#9aa8a1",
            "metin_silik": "#7c8a84",
            "vurgu": "#f5b53d",  # sinyal kehribarı
            "vurgu_metin": "#0b0f0e",
            "vurgu_zemin": "#2a2414",
            "iyi": "#3fcf8e",
            "uyari": "#ffa45c",
            "kotu": "#ff6f7d",
            "bilgi": "#6cb6ff",
            "iyi_zemin": "#11261c",
            "uyari_zemin": "#2a1d11",
            "kotu_zemin": "#2c1418",
            "bilgi_zemin": "#112033",
            "deniz": "#0a1416",
            "kara": "#141b19",
            "sinir": "#2c3833",
            "iskelet": "#1d2623",
            "iskelet_parlak": "#26312c",
        },
        "veri": KOYU_VERI,
        "harita_skala": VIRIDIS6[::-1],  # sınıf 0 (en cazip) = sarı: koyu altlıkta en parlak
        "yazi": {"arayuz": "IBM Plex Sans", "sayi": "IBM Plex Mono", "baslik": "IBM Plex Sans", "kod": "IBM Plex Mono"},
        "baslik_agirlik": 600,
    },
}

# Yazı tipi dosyaları: static/fonts (SIL OFL 1.1; fontsource paketlerinden, latin + latin-ext alt kümeleri). Uygulama
# kendi sunucusundan yükler: ziyaretçinin IP'si üçüncü tarafa (Google Fonts) gitmez.
YAZI_DOSYALARI = [
    ("Public Sans", "public-sans-{alt}-wght-normal.woff2", "100 900"),
    ("Newsreader", "newsreader-{alt}-wght-normal.woff2", "200 800"),
    ("IBM Plex Sans", "ibm-plex-sans-{alt}-wght-normal.woff2", "100 700"),
    ("IBM Plex Mono", "ibm-plex-mono-{alt}-400-normal.woff2", "400"),
    ("IBM Plex Mono", "ibm-plex-mono-{alt}-500-normal.woff2", "500"),
    ("IBM Plex Mono", "ibm-plex-mono-{alt}-600-normal.woff2", "600"),
]
UNICODE = {
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,"
    "U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
    "latin-ext": "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,"
    "U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF",
}

BASLIK_BOYUT = ["2.4rem", "1.75rem", "1.3rem", "1.1rem", "1rem", "0.9rem"]  # h1…h6 (giriş başlığı stil.py'de ayrıca)
BOSLUK = {"xs": 4, "s": 8, "m": 12, "l": 16, "xl": 24, "xxl": 40}
KOSE = {"kucuk": 4, "orta": 6, "buyuk": 10}
ICERIK_GENISLIK = 1400  # px: geniş ekranda içerik sütunu
METIN_GENISLIK = "74ch"  # uzun metin satır uzunluğu


def _goreli_parlaklik(hex_: str) -> float:
    r, g, b = (int(hex_.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    f = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def kontrast(on: str, arka: str) -> float:
    """WCAG kontrast oranı (1–21)."""
    a, b = sorted((_goreli_parlaklik(on), _goreli_parlaklik(arka)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def rgba(hex_: str, a: float) -> str:
    return "rgba(" + ",".join(str(int(hex_.lstrip("#")[i : i + 2], 16)) for i in (0, 2, 4)) + f",{a})"
