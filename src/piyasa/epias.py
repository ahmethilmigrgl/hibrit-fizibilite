"""
EPİAŞ Şeffaflık Platformu istemcisi (electricity-service v1).

Kimlik doğrulama (dokümantasyon: seffaflik.epias.com.tr/electricity-service/technical/tr/index.html):
    1) POST https://giris.epias.com.tr/cas/v1/tickets  (form: username, password) → HTTP 201, gövde: "TGT-..."
    2) Her istekte başlık:  TGT: <bilet>
    3) Bilet 2 saat geçerli. İstemci 100 dakikada bir ya da 401/403 alınca bileti kendiliğinden yeniler.

Kimlik bilgileri yalnızca .env'den okunur (EPIAS_USERNAME, EPIAS_PASSWORD) ve hiçbir yere yazdırılmaz.

Önbellek: Her istek gövdesi ham JSON olarak data/raw/epias/<servis>/<anahtar>.json altına yazılır;
aynı istek tekrarlanırsa ağ kullanılmaz.

Tarih biçimi: EPİAŞ tarihleri Türkiye saatiyle ISO-8601 ister/verir: 2023-11-14T17:30:00+03:00.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.ayarlar import HAM_VERI, KOK

GIRIS_URL = "https://giris.epias.com.tr/cas/v1/tickets"
TABAN_URL = "https://seffaflik.epias.com.tr/electricity-service"
EPIAS_KLASOR = HAM_VERI / "epias"
BILET_OMRU_SN = 100 * 60       # 2 saatlik biletin güvenli kullanım süresi
BEKLEME_SN = 0.4               # istekler arası nezaket beklemesi


class EpiasHatasi(RuntimeError):
    pass


class EpiasIstemcisi:
    def __init__(self, bekleme_sn: float = BEKLEME_SN):
        load_dotenv(KOK / ".env")
        self._kullanici = os.getenv("EPIAS_USERNAME")
        self._sifre = os.getenv("EPIAS_PASSWORD")
        if not self._kullanici or not self._sifre:
            raise EpiasHatasi(".env içinde EPIAS_USERNAME / EPIAS_PASSWORD bulunamadı.")
        self._bilet: str | None = None
        self._bilet_zamani = 0.0
        self._oturum = requests.Session()
        self._bekleme = bekleme_sn
        self._son_istek = 0.0

    # ------------------------------------------------------------------ kimlik
    def _bilet_al(self) -> str:
        yanit = self._oturum.post(
            GIRIS_URL,
            data={"username": self._kullanici, "password": self._sifre},
            headers={"Accept": "text/plain"},
            timeout=30,
        )
        if yanit.status_code != 201 or not yanit.text.startswith("TGT-"):
            # Yanıt gövdesi kimlik bilgisi içermez ama yine de kısaltarak gösteriyoruz
            raise EpiasHatasi(f"TGT alınamadı (HTTP {yanit.status_code}): {yanit.text[:200]}")
        self._bilet, self._bilet_zamani = yanit.text.strip(), time.time()
        return self._bilet

    def _gecerli_bilet(self) -> str:
        if self._bilet is None or time.time() - self._bilet_zamani > BILET_OMRU_SN:
            self._bilet_al()
        return self._bilet

    # ------------------------------------------------------------------ istek
    def istek(self, yol: str, govde: dict | None = None, yontem: str = "POST",
              deneme: int = 5) -> dict:
        """Tek bir API isteği (önbelleksiz). 401/403'te bileti yeniler, 429/5xx'te bekleyip tekrar dener."""
        url = f"{TABAN_URL}{yol}"
        for i in range(deneme):
            gecen = time.time() - self._son_istek
            if gecen < self._bekleme:
                time.sleep(self._bekleme - gecen)
            basliklar = {"TGT": self._gecerli_bilet(), "Accept": "application/json"}
            try:
                if yontem == "GET":
                    yanit = self._oturum.get(url, headers=basliklar, timeout=120)
                else:
                    yanit = self._oturum.post(url, json=govde, headers=basliklar, timeout=120)
            except requests.RequestException as e:
                self._son_istek = time.time()
                if i == deneme - 1:
                    raise EpiasHatasi(f"Bağlantı hatası: {e}") from e
                time.sleep(2 ** i)
                continue
            self._son_istek = time.time()

            if yanit.status_code == 200:
                return yanit.json()
            if yanit.status_code in (401, 403):
                self._bilet = None          # bilet süresi dolmuş olabilir → yenile
                continue
            if yanit.status_code in (429, 500, 502, 503, 504) and i < deneme - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise EpiasHatasi(f"{yol} → HTTP {yanit.status_code}: {_hata_ozeti(yanit)}")
        raise EpiasHatasi(f"{yol}: {deneme} denemede başarısız")

    def onbellekli_istek(self, servis: str, yol: str, govde: dict | None = None,
                         yontem: str = "POST", yenile: bool = False) -> dict:
        """İsteği data/raw/epias/<servis>/ altında önbelleğe alarak yapar."""
        klasor = EPIAS_KLASOR / servis
        klasor.mkdir(parents=True, exist_ok=True)
        anahtar_metni = json.dumps({"yol": yol, "govde": govde}, sort_keys=True)
        anahtar = _okunur_anahtar(govde) + "_" + hashlib.sha1(anahtar_metni.encode()).hexdigest()[:8]
        dosya = klasor / f"{anahtar}.json"
        if dosya.exists() and not yenile:
            return json.loads(dosya.read_text(encoding="utf-8"))
        veri = self.istek(yol, govde, yontem)
        dosya.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        return veri


def _hata_ozeti(yanit: requests.Response) -> str:
    """
    Hata yanıtından yalnızca hata mesajlarını döndürür. EPİAŞ hata gövdesi kullanıcı adı ve
    istemci IP'si de içerdiği için gövde asla olduğu gibi yazdırılmaz.
    """
    try:
        govde = yanit.json()
        hatalar = govde.get("errors") or []
        mesajlar = [h.get("errorMessage") or h.get("message") or str(h.get("errorCode"))
                    for h in hatalar if isinstance(h, dict)]
        return "; ".join(m for m in mesajlar if m) or str(govde.get("status", "bilinmeyen hata"))
    except ValueError:
        return "(JSON olmayan yanıt)"


def _okunur_anahtar(govde: dict | None) -> str:
    """Önbellek dosya adının okunur kısmı: başlangıç tarihi + varsa santral id."""
    if not govde:
        return "liste"
    parca = [str(govde.get("startDate", ""))[:10]]
    for k in ("powerPlantId", "powerplantId", "id"):
        if k in govde and govde[k] is not None:
            parca.append(f"s{govde[k]}")
    return "_".join(p for p in parca if p) or "istek"


def tarih_metni(zaman) -> str:
    """pandas Timestamp / datetime → EPİAŞ ISO-8601 metni (Türkiye saati ofsetiyle)."""
    import pandas as pd

    z = pd.Timestamp(zaman)
    if z.tzinfo is None:
        z = z.tz_localize("Europe/Istanbul")
    else:
        z = z.tz_convert("Europe/Istanbul")
    metin = z.strftime("%Y-%m-%dT%H:%M:%S%z")
    return metin[:-2] + ":" + metin[-2:]     # +0300 → +03:00
