"""
Yeniden kullanılabilir arayüz bileşenleri. Görünüm stil.py'deki CSS sınıflarından gelir; renk kodu burada yazılmaz.

Yerleşik Streamlit öğelerini (st.metric, st.warning …) saran bileşenler testlerin okuduğu metinleri korur:
- kpi_karti(...)        → st.metric (stil.py "KPI kartı")
- uyari_kutusu(...)     → st.info / st.success / st.warning / st.error, emoji yerine Material ikon
- karar_karti(durum)    → keyed kapsayıcı (üst şerit durum renginde); içindeki öneri kutusu manşete dönüşür
- kart(ad)              → keyed kart kapsayıcısı
HTML bileşenleri: giris_onecikanlar, adim_gostergesi, guven_rozeti, rozet, bolum_basligi, karsilastirma_tablosu, liste,
bos_durum, iskelet, sira_karti, ikon.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

import streamlit as st

# Sade ikon seti: Material Symbols Rounded (Streamlit'in yerleşik ikon yazı tipi; gezinme ve düğmelerle aynı). Emoji kullanılmaz.
# st.html satır içi SVG'yi temizlediği için ikonlar yazı tipi bitişik harfleriyle (ligature) çizilir.
_IKON = {
    "pin": "location_on",
    "imlec": "ads_click",
    "ok": "arrow_forward",
    "katman": "layers",
    "uyari": "warning",
    "saat": "schedule",
    "onay": "check",
}

_UYARI = {
    "bilgi": (st.info, ":material/info:"),
    "iyi": (st.success, ":material/check_circle:"),
    "uyari": (st.warning, ":material/warning:"),
    "kotu": (st.error, ":material/error:"),
}


def ikon(ad: str, boyut: int = 16) -> str:
    return f'<span class="esik-ikon" style="font-size:{boyut}px" aria-hidden="true">{_IKON[ad]}</span>'


def _e(x: object) -> str:
    return html.escape(str(x), quote=False)


def kpi_karti(hedef, etiket: str, deger: str, yardim: str | None = None, aciklama: str | None = None) -> None:
    """KPI kartı: st.metric (etiket testlerde okunur). aciklama: değerin altında küçük not (delta yerine, renksiz)."""
    hedef.metric(etiket, deger, help=yardim, delta=aciklama, delta_color="off", delta_arrow="off")


def uyari_kutusu(metin: str, durum: str = "bilgi", hedef=None) -> None:
    fn, ik = _UYARI[durum]
    if hedef is not None:
        getattr(hedef, fn.__name__)(metin, icon=ik)
    else:
        fn(metin, icon=ik)


def kart(ad: str, **kw):
    return st.container(key=f"kart_{ad}", **kw)


def karar_karti(durum: str):
    """durum ∈ {'iyi', 'uyari', 'kotu'}"""
    return st.container(key=f"karar_{durum}")


def rozet(metin: str, durum: str = "notr") -> str:
    return f'<span class="esik-rozet {durum}">{_e(metin)}</span>'


def guven_rozeti(seviye: str, etiket: str) -> str:
    """seviye: 'yüksek' | 'düşük' (motorun değeri); etiket: görünen metin (dil)."""
    return rozet(etiket, "iyi" if seviye == "yüksek" else "uyari")


def bolum_basligi(baslik: str, alt: str = "") -> None:
    st.html(f'<div class="esik-bolum"><h3>{_e(baslik)}</h3>{f"<span>{_e(alt)}</span>" if alt else ""}</div>')


def adim_gostergesi(adimlar: Sequence[tuple[str, str]], durumlar: Sequence[str]) -> None:
    """adimlar: (ad, not) listesi; durumlar: 'tamam' | 'aktif' | '' (aynı uzunlukta)."""
    h = ""
    for i, ((ad, notu), d) in enumerate(zip(adimlar, durumlar, strict=True), 1):
        isaret = ikon("onay", 12) if d == "tamam" else str(i)
        h += f'<div class="{d}" aria-current="{"step" if d == "aktif" else "false"}"><i>{isaret}</i><span class="ad">{_e(ad)}</span>'
        h += f'<span class="not">{_e(notu)}</span></div>'
    st.html(f'<nav class="esik-adim" aria-label="Adımlar">{h}</nav>')


def giris_onecikanlar(oneler: Sequence[tuple[str, str, str]]) -> None:
    """oneler: (değer, birim, açıklama) üçlüleri."""
    h = "".join(
        f'<div class="esik-one"><b>{_e(d)}{f"<small>{_e(b)}</small>" if b else ""}</b><span>{_e(a)}</span></div>' for d, b, a in oneler
    )
    st.html(f'<div class="esik-oneler">{h}</div>')


def karsilastirma_tablosu(
    basliklar: Sequence[str],
    satirlar: Sequence[Sequence[str]],
    vurgulu: int | None = None,
    mobilde_gizle: Sequence[int] = (),
    negatif: Sequence[tuple[int, int]] = (),
) -> None:
    """Sayılar önceden biçimlenmiş metin olarak gelir (TR/EN sayı biçimi ortak.sayi ile). vurgulu: satır indisi;
    mobilde_gizle: dar ekranda gizlenen sütun indisleri; negatif: kırmızı yazılacak (satır, sütun) hücreleri."""
    gz = set(mobilde_gizle)
    ng = set(negatif)
    th = "".join(f'<th class="{"gizle-m" if j in gz else ""}" scope="col">{_e(b)}</th>' for j, b in enumerate(basliklar))
    tr = ""
    for i, s in enumerate(satirlar):
        td = "".join(
            f'<td class="{" ".join(c for c in ("gizle-m" if j in gz else "", "negatif" if (i, j) in ng else "") if c)}">{_e(v)}</td>'
            for j, v in enumerate(s)
        )
        tr += f'<tr class="{"vurgulu" if i == vurgulu else ""}">{td}</tr>'
    st.html(f'<div class="esik-tablo-kap"><table class="esik-tablo"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')


def liste(maddeler: Sequence[str], tur: str = "") -> None:
    """Madde listesi; maddeler düz metin (HTML kaçışlı)."""
    st.html(f'<ul class="esik-liste {tur}">' + "".join(f"<li>{_e(m)}</li>" for m in maddeler) + "</ul>")


def bos_durum(baslik: str, metin: str, ikon_adi: str = "pin") -> None:
    st.html(f'<div class="esik-bos">{ikon(ikon_adi, 24)}<b>{_e(baslik)}</b>{_e(metin)}</div>')


def iskelet_html(satirlar: Sequence[tuple[int, str]] = ((3, "6.5rem"), (4, "5rem"), (2, "16rem"))) -> str:
    """Yükleme iskeleti: (sütun sayısı, yükseklik) satırları."""
    h = "".join(
        f'<div class="satir" style="--n:{n}">' + "".join(f'<div class="blok" style="--h:{y}"></div>' for _ in range(n)) + "</div>"
        for n, y in satirlar
    )
    return f'<div class="esik-iskelet" aria-busy="true" aria-label="Yükleniyor">{h}</div>'


def sira_karti_html(no: int, metin: str) -> str:
    return f'<div class="esik-sira">{ikon("saat", 22)}<b>{no}</b><span>{_e(metin)}</span></div>'
