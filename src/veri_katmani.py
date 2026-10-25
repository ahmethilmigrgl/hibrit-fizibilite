"""
Veri erişim katmanı (v2 Faz C1): uygulamanın ve motorun çalışma anında okuduğu TÜM veri dosyaları buradan geçer.

Mantıksal yol → yerel dosya. Mantıksal yollar data/ altındaki göreli yollardır:
    atlas/...                      kalibrasyon atlası, GWA 1 km, sınırlar, kıyı, piyasa paketi, güven seviyeleri, santral türbinleri
    grid/era5_tr/v1/{e}_{b}.npz    ERA5 nokta gridi (rüzgâr)
    grid/pvgis_tr/v1/{e}_{b}.npz   GES KF gridi (PVGIS)
    grid/gwa_tr/v1/karolar/...     GWA 250 m karoları
    grid/rakim_tr/v1/rakim_002.npz rakım ızgarası
    tarama/v1/on_tarama.parquet    Türkiye ön tarama haritası
Modlar (config v2.veri_erisim.mod; ortam değişkeni VERI_ERISIM önceliklidir — Hugging Face Space'te "uzak"):
    "yerel" — yalnız yerel dosyalar; ağ çağrısı yok. Eksik dosya → VeriYok (iki dilli mesaj).
    "uzak"  — grid/ dosyaları yerelde yoksa Hugging Face veri deposundan indirilir (src/kaynaklar/hf_veri.py). Depo düzeni
              data/ altıyla birebir aynıdır (grid/era5_tr/v1/..., grid/cbs_tr/v1/... — hf/README.md); atlas/ uygulamayla gelir.
"""

from __future__ import annotations

from pathlib import Path

from src.ayarlar import KOK, config_oku, deger

DATA = KOK / "data"
_YOK: set[str] = set()  # uzak modda depoda bulunmayan yollar (deniz hücreleri vb.): tekrar istek atılmaz


class VeriYok(FileNotFoundError):
    """Uygulamanın ihtiyaç duyduğu veri dosyası yok (iki dilli mesaj)."""

    def __init__(self, mantiksal: str):
        super().__init__(mantiksal)
        self.mantiksal = mantiksal
        self.tr = f"Gerekli veri dosyası bulunamadı: {mantiksal}. Bu bölge için veri paketi henüz hazır olmayabilir."
        self.en = f"Required data file not found: {mantiksal}. The data package for this area may not be ready yet."


def mod() -> str:
    import os

    if os.environ.get("VERI_ERISIM") in ("yerel", "uzak"):
        return os.environ["VERI_ERISIM"]
    try:
        return deger(config_oku()["v2"]["veri_erisim"])["mod"]
    except KeyError:
        return "yerel"


def yerel_mi() -> bool:
    return mod() == "yerel"


def yol(mantiksal: str, zorunlu: bool = True) -> Path | None:
    """Mantıksal yol → okunabilir yerel dosya. Yoksa zorunlu ise VeriYok, değilse None."""
    p = DATA / mantiksal
    if p.exists():
        return p
    if not yerel_mi() and mantiksal.startswith("grid/") and mantiksal not in _YOK:
        from src.kaynaklar import hf_veri

        try:
            return hf_veri.dosya(mantiksal)
        except FileNotFoundError:
            _YOK.add(mantiksal)
        except OSError:
            pass
    if zorunlu:
        raise VeriYok(mantiksal)
    return None


def var_mi(mantiksal: str) -> bool:
    return yol(mantiksal, zorunlu=False) is not None
