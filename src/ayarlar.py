"""
Ortak yardımcılar: proje yolları, config.yaml okuma ve kimlik bilgileri.

Kimlik bilgileri yalnızca .env dosyasından okunur ve hiçbir zaman yazdırılmaz.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from dotenv import load_dotenv

if TYPE_CHECKING:
    import cdsapi

KOK = Path(__file__).resolve().parents[1]
HAM_VERI = KOK / "data" / "raw"
ISLENMIS_VERI = KOK / "data" / "processed"
CIKTILAR = KOK / "outputs"


def bulut_mu() -> bool:
    """Streamlit Community Cloud'da mı çalışıyoruz? (repo /mount/src/<repo> altına klonlanır; bellek ~2,7 GB ile sınırlı)."""
    return KOK.as_posix().startswith("/mount/src/")


def config_oku() -> dict:
    """config.yaml'ı sözlük olarak döndürür."""
    with open(KOK / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def deger(d: dict | object) -> Any:
    """config'teki {value, birim, kaynak, not} sözlüğünden sadece değeri döndürür."""
    return d["value"] if isinstance(d, dict) and "value" in d else d


def cds_istemcisi() -> "cdsapi.Client":
    """CDS API istemcisini .env'deki bilgilerle açıkça oluşturur."""
    import cdsapi

    load_dotenv(KOK / ".env")
    url, key = os.getenv("CDS_URL"), os.getenv("CDS_KEY")
    if not url or not key:
        raise RuntimeError(".env içinde CDS_URL / CDS_KEY bulunamadı (bkz. .env.example).")
    return cdsapi.Client(url=url, key=key, quiet=True, progress=False)
