"""
Arayüz tasarımı — logo yazısını SVG yoluna çevirir (yazı tipi yüklenmeden her yerde aynı görünsün diye).

Çıktı: uygulama/tasarim/logo_yollari.py (ad ve alt başlık yolları + genişlikleri). Marka adı değişirse yeniden çalıştırılır.
fontTools + brotli ister; ana .venv'e eklemeden geçici ortamla çalıştırın:
  uv run --no-project --with fonttools --with brotli python src/v2_tasarim_logo.py
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from uygulama.tasarim.tokenlar import MARKA

F = KOK / "static" / "fonts"


def fontlar(desen: str, agirlik: float | None) -> list:
    sonuc = []
    for alt in ("latin", "latin-ext"):
        f = TTFont(F / desen.format(alt=alt))
        if "fvar" in f and agirlik:
            f = instancer.instantiateVariableFont(f, {"wght": agirlik})
        sonuc.append((f, f.getGlyphSet(), f.getBestCmap()))
    return sonuc


def yol(metin: str, fl: list, boyut: float, izleme: float) -> tuple[str, float]:
    x, parca = 0.0, []
    for ch in metin:
        f, gs, cmap = next(t for t in fl if ord(ch) in t[2])
        s = boyut / f["head"].unitsPerEm
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[cmap[ord(ch)]].draw(TransformPen(pen, (s, 0, 0, -s, x, 0)))
        parca.append(pen.getCommands())
        x += gs[cmap[ord(ch)]].width * s + izleme
    return "".join(parca), round(x - izleme, 2)


def main() -> None:
    ad = yol(MARKA["ad"], fontlar("ibm-plex-sans-{alt}-wght-normal.woff2", 600), 23, -0.3)
    mono = fontlar("ibm-plex-mono-{alt}-500-normal.woff2", None)
    tr = yol(MARKA["alt_tr"].replace("i", "İ").upper(), mono, 6.6, 1.4)  # Türkçe büyük harf: i → İ
    en = yol(MARKA["alt_en"].upper(), mono, 6.6, 1.4)
    hedef = KOK / "uygulama" / "tasarim" / "logo_yollari.py"
    hedef.write_text(
        '"""Logo yazı yolları (src/v2_tasarim_logo.py üretir; elle düzenlemeyin)."""\n\n'
        f'AD = ({ad[0]!r}, {ad[1]})\nALT = {{\n    "TR": ({tr[0]!r}, {tr[1]}),\n    "EN": ({en[0]!r}, {en[1]}),\n}}\n',
        encoding="utf-8",
    )
    print(hedef, ad[1], tr[1], en[1])


if __name__ == "__main__":
    main()
