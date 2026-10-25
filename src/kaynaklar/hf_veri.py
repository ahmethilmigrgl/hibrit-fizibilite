"""
Hugging Face veri deposu istemcisi: uygulamanın ihtiyaç duyduğu tek dosyayı indirip yerelde önbelleğe alır.

Depo düzeni (config v2.veri_deposu; herkese açık dataset, anahtar gerekmez) data/ altıyla birebir aynıdır:
    README.md                                   — veri kartı: kaynaklar, lisanslar, atıflar (hf/README.md)
    grid/era5_tr/v1/{enlem:.2f}_{boylam:.2f}.npz — 2014–2023 saatlik ERA5 noktası (+ manifest.json)
    grid/pvgis_tr/v1/...                         — PVGIS GES kapasite faktörü gridi
    grid/gwa_tr/v1/karolar/...                   — GWA 3 100 m, 250 m karolar (+ COG GeoTIFF)
    grid/era5_yon_tr/v1/..., grid/cbs_tr/v1/..., grid/egim_tr/v1/..., grid/lojistik_tr/v1/ag.npz, grid/rakim_tr/v1/rakim_002.npz
Arama sırası: yerel önbellek (data/onbellek/hf/) → yerel üretim klasörü (data/, yükleme öncesi) → HF indirme.
"""

from __future__ import annotations

from pathlib import Path

import requests

from src.ayarlar import KOK, config_oku, deger

ONBELLEK = KOK / "data" / "onbellek" / "hf"


def _depo() -> dict:
    return deger(config_oku()["v2"]["veri_deposu"])


def url(yol: str) -> str:
    d = _depo()
    return f"https://huggingface.co/datasets/{d['repo_id']}/resolve/{d['revizyon']}/{yol}"


def _yerel_kaynak(yol: str) -> Path | None:
    p = KOK / "data" / yol
    return p if p.exists() else None


def dosya(yol: str, zaman_asimi: float = 60) -> Path:
    """Depo içi göreli yolu yerel dosya yoluna çevirir (gerekirse indirir). Bulunamazsa FileNotFoundError."""
    hedef = ONBELLEK / yol
    if hedef.exists():
        return hedef
    yerel = _yerel_kaynak(yol)
    if yerel is not None:
        return yerel
    r = requests.get(url(yol), timeout=zaman_asimi)
    if r.status_code == 404:
        raise FileNotFoundError(f"Veri deposunda yok: {yol}")
    r.raise_for_status()
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_suffix(hedef.suffix + ".part")
    gecici.write_bytes(r.content)
    gecici.rename(hedef)
    return hedef
