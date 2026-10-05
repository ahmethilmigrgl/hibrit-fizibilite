"""
Hugging Face veri deposu istemcisi (v2): uygulamanın ihtiyaç duyduğu tek dosyayı indirip yerelde önbelleğe alır.

Depo düzeni (config v2.veri_deposu; herkese açık dataset, anahtar gerekmez):
    README.md                                  — veri kartı: kaynaklar, lisanslar, atıflar
    era5_tr/v1/manifest.json                   — nokta listesi, boyut, sha256
    era5_tr/v1/noktalar/{enlem:.2f}_{boylam:.2f}.npz   — 2014–2023 saatlik ERA5 noktası (era5_grid.py biçimi)
    gwa_tr/v1/karolar/{enlem0}_{boylam0}.npz   — GWA 3 100 m ortalama hız, 250 m, 1° × 1° karo (uint16 cm/s)
    gwa_tr/v1/gwa_tr_250m_ws100_cog.tif        — aynı veri, Cloud Optimized GeoTIFF (CBS kullanıcıları için)
Arama sırası: yerel önbellek (data/onbellek/hf/) → yerel üretim klasörü (data/grid/, yükleme öncesi) → HF indirme.
"""

from __future__ import annotations

from pathlib import Path

import requests

from src.ayarlar import KOK, config_oku, deger

ONBELLEK = KOK / "data" / "onbellek" / "hf"
YEREL = {"era5_tr/": KOK / "data" / "grid" / "era5_tr", "gwa_tr/": KOK / "data" / "grid" / "gwa_tr"}


def _depo() -> dict:
    return deger(config_oku()["v2"]["veri_deposu"])


def url(yol: str) -> str:
    d = _depo()
    return f"https://huggingface.co/datasets/{d['repo_id']}/resolve/{d['revizyon']}/{yol}"


def _yerel_kaynak(yol: str) -> Path | None:
    for on, klasor in YEREL.items():
        if yol.startswith(on):
            alt = yol[len(on) :].replace("noktalar/", "")  # data/grid düzeninde noktalar/ alt klasörü yok
            p = klasor / alt
            return p if p.exists() else None
    return None


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
