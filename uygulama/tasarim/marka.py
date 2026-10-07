"""
Marka: "Eşik" işareti ve yazı markası (SVG). İşaret: üç sütun (RES, GES, batarya) ve yatay başabaş eşiği; eşiği aşan kısım
vurgu renginde. Yazı yolları logo_yollari.py'de (yazı tipi yüklenmeden aynı görünür). Renkler tokenlar.py'den.
"""

from __future__ import annotations

from uygulama.tasarim.logo_yollari import AD, ALT
from uygulama.tasarim.tokenlar import MARKA, TEMALAR


def _isaret_ic(metin: str, vurgu: str) -> str:
    return (
        f'<g fill="{metin}" fill-opacity="0.4"><rect x="4.5" y="16" width="6" height="12" rx="1"/>'
        f'<rect x="13" y="16" width="6" height="12" rx="1"/><rect x="21.5" y="19" width="6" height="9" rx="1"/></g>'
        f'<g fill="{vurgu}"><rect x="4.5" y="3" width="6" height="11" rx="1"/><rect x="13" y="8" width="6" height="6" rx="1"/></g>'
        f'<rect x="1.5" y="14.2" width="29" height="1.8" rx=".9" fill="{metin}"/>'
    )


def isaret(metin: str, vurgu: str, boyut: int = 32) -> str:
    """32 × 32 işaret. metin: çizgi ve sütun gövdesi rengi, vurgu: eşiği aşan kısım."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{boyut}" height="{boyut}" role="img" '
        f'aria-label="{MARKA["ad"]}">{_isaret_ic(metin, vurgu)}</svg>'
    )


def yazi_markasi(tema: str = "acik", dil: str = "TR", alt: bool = True) -> str:
    """İşaret + ad (+ alt başlık) yatay yazı markası; yükseklik 40 birim."""
    r = TEMALAR[tema]["renk"]
    alt_yol, alt_gen = ALT[dil]
    gen = 44 + max(AD[1], alt_gen if alt else 0) + 4
    ic = _isaret_ic(r["metin"], r["vurgu"])
    ad_y = 25 if alt else 28
    altg = f'<path transform="translate(44 36)" fill="{r["metin_soluk"]}" d="{alt_yol}"/>' if alt else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {gen:.0f} 40" height="40" role="img" aria-label="{MARKA["ad"]}">'
        f'<g transform="translate(2 4)">{ic}</g>'
        f'<path transform="translate(44 {ad_y})" fill="{r["metin"]}" d="{AD[0]}"/>{altg}</svg>'
    )
