"""
Veri erişim katmanı (v2 Faz C1): uygulamanın ve motorun çalışma anında okuduğu TÜM veri dosyaları buradan geçer.

Mantıksal yol → yerel dosya. Mantıksal yollar data/ altındaki göreli yollardır:
    atlas/...                      kalibrasyon atlası, GWA 1 km, sınırlar, kıyı, piyasa paketi, güven seviyeleri, santral türbinleri
    grid/era5_tr/v1/{e}_{b}.npz    ERA5 nokta gridi (rüzgâr)
    grid/pvgis_tr/v1/{e}_{b}.npz   GES KF gridi (PVGIS)
    grid/gwa_tr/v1/karolar/...     GWA 250 m karoları
    grid/rakim_tr/v1/rakim_002.npz rakım ızgarası
    tarama/v1/on_tarama.parquet    Türkiye ön tarama haritası
Modlar (config v2.veri_erisim.mod):
    "yerel" — yalnız yerel dosyalar; ağ çağrısı yok. Eksik dosya → VeriYok (iki dilli mesaj). (Şimdiki tek mod.)
    "uzak"  — yerelde yoksa barındırma servisinden indirilir (ileride: Hugging Face veri deposu, src/kaynaklar/hf_veri.py).
Verileri bir barındırma servisine taşırken yalnız bu modül (ve hf_veri) değişir.
"""

from __future__ import annotations

from pathlib import Path

from src.ayarlar import KOK, config_oku, deger

DATA = KOK / "data"
# Mantıksal ön ek → barındırma deposundaki ön ek (uzak mod için; hf/README.md düzeni)
UZAK_ONEK = {"grid/era5_tr/v1/": "era5_tr/v1/noktalar/", "grid/gwa_tr/v1/": "gwa_tr/v1/", "grid/pvgis_tr/v1/": "pvgis_tr/v1/noktalar/"}


class VeriYok(FileNotFoundError):
    """Uygulamanın ihtiyaç duyduğu veri dosyası yok (iki dilli mesaj)."""

    def __init__(self, mantiksal: str):
        super().__init__(mantiksal)
        self.mantiksal = mantiksal
        self.tr = f"Gerekli veri dosyası bulunamadı: {mantiksal}. Bu bölge için veri paketi henüz hazır olmayabilir."
        self.en = f"Required data file not found: {mantiksal}. The data package for this area may not be ready yet."


def mod() -> str:
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
    if not yerel_mi():
        for on, uzak in UZAK_ONEK.items():
            if mantiksal.startswith(on):
                from src.kaynaklar import hf_veri

                try:
                    return hf_veri.dosya(uzak + mantiksal[len(on) :])
                except (FileNotFoundError, OSError):
                    break
    if zorunlu:
        raise VeriYok(mantiksal)
    return None


def var_mi(mantiksal: str) -> bool:
    return yol(mantiksal, zorunlu=False) is not None
