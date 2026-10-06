"""
Analiz motoru giriş noktası (arayüzden bağımsız):
    analiz_et(saha, mod, kullanici_varsayimlari, ilerleme_geri_cagirimi) → Sonuc
mod ∈ {"hizli", "tam"}. saha: Saha nesnesi ya da {"ad", "enlem", "boylam"} sözlüğü. ilerleme(oran 0–1, mesaj).
Sonuçlar önbelleklenir (anahtar: 0,01° koordinat + varsayımlar + veri sürümü); tam analiz aynı anda tek çalışır.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from src.ayarlar import config_oku, deger
from src.motor import onbellek
from src.motor.ortak import hazirla
from src.motor.sonuc import Sonuc
from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi, dogrula


def analiz_et(
    saha,
    mod: str = "hizli",
    kullanici_varsayimlari: KullaniciVarsayimlari | None = None,
    ilerleme=None,
    onbellek_kullan: bool = True,
    zaman_asimi: float | None = None,
) -> Sonuc:
    kv = kullanici_varsayimlari or KullaniciVarsayimlari()
    ilerleme = ilerleme or (lambda *_: None)
    if mod not in ("hizli", "tam"):
        raise MotorHatasi("mod", "Mod 'hizli' ya da 'tam' olmalı.", "Mode must be 'hizli' or 'tam'.")
    uyarilar = dogrula(kv)
    surum = deger(config_oku()["v2"]["motor"])["veri_surumu"]
    enlem = saha["enlem"] if isinstance(saha, dict) else saha.enlem
    boylam = saha["boylam"] if isinstance(saha, dict) else saha.boylam
    anahtar = onbellek.anahtar(enlem, boylam, mod, kv.sozluk(), surum)
    if onbellek_kullan:
        s = onbellek.oku(anahtar)
        if s is not None:
            ilerleme(1.0, "Önbellekten")
            s.sure_s["onbellekten"] = True
            return s

    def calis() -> Sonuc:
        t0 = time.perf_counter()
        h = hazirla(saha, kv, ilerleme)
        t_h = time.perf_counter() - t0
        if mod == "hizli":
            from src.motor.hizli import hizli_tarama

            r = hizli_tarama(h, kv, ilerleme)
        else:
            from src.motor.tam import tam_analiz

            r = tam_analiz(h, kv, ilerleme)
        sonuc = Sonuc(
            mod=mod,
            saha={
                **{k: v for k, v in asdict(h.saha).items() if k != "varsayimlar"},
                "kod": h.saha.kod,
                "tarife_bolgesi": h.cfg["_saha"]["tarife_bolgesi"],
                "turbin": h.cfg["_saha"]["turbin"],
                "kalibrasyon": h.bilgi["kalibrasyon"],
                "ruzgar_kaynagi": h.bilgi.get("ruzgar_kaynagi"),
            },
            varsayimlar=kv.sozluk(),
            ozet={**r["ozet"], "guven": h.guven},
            tablolar=r["tablolar"],
            grafikler=r["grafikler"],
            nedenler=r["nedenler"],
            uyarilar=[asdict(u) for u in [*uyarilar, *h.uyarilar]],
            sure_s={"hazirlik": t_h, **r["sure"], "toplam": time.perf_counter() - t0},
            veri_surumu=surum,
        )
        if mod == "tam":
            from src.motor import rapor

            ilerleme(0.95, "Saha raporu (HTML/PDF)")
            try:
                sonuc.ozet["rapor"] = rapor.uret(sonuc, anahtar)
            except Exception as ex:  # rapor üretimi analizi düşürmesin
                sonuc.uyarilar.append(
                    {
                        "kod": "rapor",
                        "tr": f"Rapor üretilemedi ({type(ex).__name__}).",
                        "en": f"Report could not be produced ({type(ex).__name__}).",
                    }
                )
        if onbellek_kullan:
            onbellek.yaz(anahtar, sonuc)
        ilerleme(1.0, "Tamamlandı")
        return sonuc

    if mod == "tam":
        return onbellek.tek_tam_analiz(calis, zaman_asimi)
    return calis()
