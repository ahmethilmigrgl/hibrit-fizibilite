"""
Sonuç önbelleği ve eşzamanlılık.

Anahtar: 0,01° yuvarlatılmış koordinat + mod + kullanıcı varsayımları + veri sürümü (sha1). Kayıt: pickle
(data/onbellek/sonuc/). Toplam boyut config v2.motor.onbellek_azami_mb'yi aşarsa en eski erişilenler silinir.
Tam analiz: aynı anda en fazla bir tane (süreç içi kilit + süreçler arası dosya kilidi); bekleyenler sıraya girer;
tam_zaman_asimi_s içinde başlayamayan ya da bitmeyen analiz ZamanAsimi ile anlaşılır mesajla sonlanır.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout

from src.ayarlar import KOK, config_oku, deger
from src.motor.varsayimlar import MotorHatasi

KLASOR = KOK / "data" / "onbellek" / "sonuc"
_KILIT = threading.Lock()


class ZamanAsimi(MotorHatasi):
    pass


class SiraDolu(MotorHatasi):
    pass


def anahtar(enlem: float, boylam: float, mod: str, varsayimlar: dict, surum: str) -> str:
    a = [round(float(enlem), 2), round(float(boylam), 2), mod, varsayimlar, surum]
    return hashlib.sha1(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()


def oku(k: str):
    yol = KLASOR / f"{k}.pkl"
    if not yol.exists():
        return None
    try:
        s = pickle.loads(yol.read_bytes())
        yol.touch()  # son erişim (LRU)
        return s
    except Exception:  # bozuk kayıt
        yol.unlink(missing_ok=True)
        return None


def yaz(k: str, sonuc) -> None:
    KLASOR.mkdir(parents=True, exist_ok=True)
    gecici = KLASOR / f"{k}.pkl.part"
    gecici.write_bytes(pickle.dumps(sonuc))
    gecici.rename(KLASOR / f"{k}.pkl")
    temizle()


def temizle(azami_mb: float | None = None) -> int:
    azami = (azami_mb if azami_mb is not None else deger(config_oku()["v2"]["motor"])["onbellek_azami_mb"]) * 1e6
    dosyalar = sorted(KLASOR.glob("*.pkl"), key=lambda p: p.stat().st_mtime)
    toplam = sum(p.stat().st_size for p in dosyalar)
    silinen = 0
    while dosyalar and toplam > azami:
        p = dosyalar.pop(0)
        toplam -= p.stat().st_size
        p.unlink(missing_ok=True)
        silinen += 1
    return silinen


_SIRA: list[int] = []  # bekleyen işlerin kimlikleri (süreç içi; geliş sırasıyla)
_SIRA_KILIDI = threading.Lock()


def sira_durumu() -> dict:
    """Arayüz için: çalışan iş var mı ve kaç iş bekliyor."""
    return {"calisan": _KILIT.locked(), "bekleyen": len(_SIRA)}


def tek_tam_analiz(is_, zaman_asimi: float | None = None, bekleme=None, sira_azami: int | None = None):
    """
    Tam analizi kilit altında çalıştırır; bekleme + çalışma toplamı zaman aşımını geçerse ZamanAsimi.
    bekleme(sira_no): sırada beklerken saniyede bir çağrılır (1 = sıradaki ilk iş). sira_azami: bekleyen iş sınırı;
    aşılırsa SiraDolu.
    """
    zaman_asimi = zaman_asimi or deger(config_oku()["v2"]["motor"])["tam_zaman_asimi_s"]
    t0 = time.monotonic()
    kimlik = id(object())
    with _SIRA_KILIDI:
        if sira_azami is not None and _KILIT.locked() and len(_SIRA) >= sira_azami:
            raise SiraDolu(
                "sira_dolu",
                f"Tam analiz sırası dolu ({len(_SIRA)} iş bekliyor). Lütfen birkaç dakika sonra tekrar deneyin.",
                f"The full-analysis queue is full ({len(_SIRA)} jobs waiting). Please try again in a few minutes.",
            )
        _SIRA.append(kimlik)
    try:
        while not _KILIT.acquire(timeout=1.0):
            if bekleme is not None:
                with _SIRA_KILIDI:
                    no = _SIRA.index(kimlik) + 1
                bekleme(no)
            if time.monotonic() - t0 > zaman_asimi:
                raise ZamanAsimi(
                    "sira",
                    "Şu anda başka bir tam analiz çalışıyor ve sıra zaman aşımına uğradı. Lütfen birkaç dakika sonra tekrar deneyin.",
                    "Another full analysis is running and the queue timed out. Please try again in a few minutes.",
                )
    finally:
        with _SIRA_KILIDI:
            _SIRA.remove(kimlik)
    KLASOR.mkdir(parents=True, exist_ok=True)
    kilit_dosyasi = open(KLASOR / ".tam_analiz.lock", "w")

    def birak(_=None):
        fcntl.flock(kilit_dosyasi, fcntl.LOCK_UN)
        kilit_dosyasi.close()
        _KILIT.release()

    try:
        while True:  # süreçler arası kilit (çok işçili sunucu)
            try:
                fcntl.flock(kilit_dosyasi, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - t0 > zaman_asimi:
                    raise ZamanAsimi(
                        "sira", "Sıra zaman aşımına uğradı; lütfen tekrar deneyin.", "Queue timed out; please try again."
                    ) from None
                time.sleep(1)
    except BaseException:
        birak()
        raise
    hv = ThreadPoolExecutor(max_workers=1)
    gorev = hv.submit(is_)
    hv.shutdown(wait=False)
    try:
        sonuc = gorev.result(timeout=zaman_asimi - (time.monotonic() - t0))
    except FutTimeout:
        # İş parçacığı zorla durdurulamaz: kullanıcıya hemen haber verilir, kilit iş gerçekten bitince bırakılır
        # (böylece arka planda süren analizle yeni bir tam analiz üst üste binmez).
        gorev.add_done_callback(birak)
        raise ZamanAsimi(
            "zaman",
            f"Tam analiz {zaman_asimi:.0f} saniyede bitmedi ve durduruldu. Hızlı taramayı deneyin ya da varsayımları sadeleştirin.",
            f"The full analysis did not finish within {zaman_asimi:.0f} s and was stopped. Try the quick scan or simplify assumptions.",
        ) from None
    except BaseException:
        birak()
        raise
    birak()
    return sonuc
