"""
Arayüz tasarımı — tema dosyalarını belirteçlerden (uygulama/tasarim/tokenlar.py) üretir.

Çıktılar:
- .streamlit/config.toml — Streamlit'in açık ([theme.light]) ve koyu ([theme.dark]) temaları, yerel yazı tipleri, araç
  çubuğu ve statik dosya sunumu. Elle düzenlenmez; tests/test_v2_tasarim.py dosyanın belirteçlerle eşit olduğunu denetler.
- static/marka/logo_{acik,koyu}_{tr,en}.svg (yazı markası), isaret_{acik,koyu}.svg, favicon.png.

Çalıştırma: .venv/bin/python src/v2_tasarim_tema.py
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from uygulama.tasarim.marka import isaret, yazi_markasi
from uygulama.tasarim.tokenlar import BASLIK_BOYUT, KOSE, TEMALAR, UNICODE, YAZI_DOSYALARI

CONFIG = KOK / ".streamlit" / "config.toml"
MARKA_KLASOR = KOK / "static" / "marka"


def _tema(t: dict) -> str:
    r, y = t["renk"], t["yazi"]
    veri = t["veri"]
    s = [
        f'primaryColor = "{r["vurgu"]}"',
        f'backgroundColor = "{r["zemin"]}"',
        f'secondaryBackgroundColor = "{r["yuzey2"]}"',
        f'textColor = "{r["metin"]}"',
        f'borderColor = "{r["cizgi"]}"',
        f'linkColor = "{r["vurgu"]}"',
        f'codeTextColor = "{r["metin"]}"',
        f'codeBackgroundColor = "{r["yuzey2"]}"',
        f'dataframeBorderColor = "{r["cizgi"]}"',
        f'dataframeHeaderBackgroundColor = "{r["yuzey2"]}"',
        f'dataframeHeaderTextColor = "{r["metin_soluk"]}"',
        f'font = "{y["arayuz"]}, system-ui, sans-serif"',
        f'headingFont = "{y["baslik"]}, {"Georgia, serif" if y["baslik"] == "Newsreader" else "system-ui, sans-serif"}"',
        f'codeFont = "{y["kod"]}, ui-monospace, monospace"',
        f"headingFontWeights = [{t['baslik_agirlik']}, 600]",
        f'baseRadius = "{KOSE["orta"] if t["streamlit"] == "dark" else KOSE["kucuk"]}px"',
        f'buttonRadius = "{KOSE["orta"] if t["streamlit"] == "dark" else KOSE["kucuk"]}px"',
    ]
    for ad, (on, zemin) in {"green": ("iyi", "iyi_zemin"), "orange": ("uyari", "uyari_zemin"), "red": ("kotu", "kotu_zemin"),
                            "blue": ("bilgi", "bilgi_zemin"), "yellow": ("uyari", "uyari_zemin")}.items():  # fmt: skip
        s += [f'{ad}Color = "{r[on]}"', f'{ad}TextColor = "{r[on]}"', f'{ad}BackgroundColor = "{r[zemin]}"']
    s.append("chartCategoricalColors = [" + ", ".join(f'"{veri[k]}"' for k in ("res", "ges", "hibrit", "batarya", "koyu", "soluk")) + "]")
    return "\n".join(s)


def config_metni() -> str:
    yuzler = []
    for aile, desen, agirlik in YAZI_DOSYALARI:
        for alt, aralik in UNICODE.items():
            yuzler.append(
                f'[[theme.fontFaces]]\nfamily = "{aile}"\nurl = "app/static/fonts/{desen.format(alt=alt)}"\n'
                f'weight = "{agirlik}"\nunicodeRange = "{aralik}"\n'
            )
    return (
        "# Bu dosya src/v2_tasarim_tema.py tarafından uygulama/tasarim/tokenlar.py'den üretilir; elle düzenlemeyin.\n\n"
        '[client]\ntoolbarMode = "viewer"\n\n'
        "[server]\nheadless = true\nenableStaticServing = true\n\n"
        "[theme]\nshowWidgetBorder = true\n"
        f"headingFontSizes = [{', '.join(repr(x).replace(chr(39), chr(34)) for x in BASLIK_BOYUT)}]\n\n"
        + "\n".join(yuzler)
        + f"\n[theme.light]\n{_tema(TEMALAR['acik'])}\n\n[theme.dark]\n{_tema(TEMALAR['koyu'])}\n"
    )


def favicon(yol: Path) -> None:
    from PIL import Image, ImageDraw

    r = TEMALAR["acik"]["renk"]
    olcek = 4  # 32 birimlik işaret → 128 px, sonra 64 px'e küçült (kenar yumuşatma)
    im = Image.new("RGBA", (32 * olcek, 32 * olcek), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, 32 * olcek - 1, 32 * olcek - 1], radius=7 * olcek, fill=r["yuzey"])
    gri = "#9aa09c"

    def kutu(x, y, w, h, renk):
        d.rounded_rectangle([x * olcek, y * olcek, (x + w) * olcek, (y + h) * olcek], radius=olcek, fill=renk)

    kutu(4.5, 16, 6, 12, gri), kutu(13, 16, 6, 12, gri), kutu(21.5, 19, 6, 9, gri)
    kutu(4.5, 3, 6, 11, r["vurgu"]), kutu(13, 8, 6, 6, r["vurgu"]), kutu(1.5, 14.2, 29, 1.8, r["metin"])
    im.resize((64, 64), Image.LANCZOS).save(yol)


def main() -> None:
    CONFIG.write_text(config_metni(), encoding="utf-8")
    MARKA_KLASOR.mkdir(parents=True, exist_ok=True)
    for tema, t in TEMALAR.items():
        for dil in ("TR", "EN"):
            (MARKA_KLASOR / f"logo_{tema}_{dil.lower()}.svg").write_text(yazi_markasi(tema, dil), encoding="utf-8")
        (MARKA_KLASOR / f"isaret_{tema}.svg").write_text(isaret(t["renk"]["metin"], t["renk"]["vurgu"]), encoding="utf-8")
    favicon(MARKA_KLASOR / "favicon.png")
    print(CONFIG, "·", sorted(p.name for p in MARKA_KLASOR.iterdir()))


if __name__ == "__main__":
    main()
