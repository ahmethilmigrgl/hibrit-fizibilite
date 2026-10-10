"""Kullanıcı varsayımları (varsayılanlı, sınır kontrollü) ve iki dilli hata/uyarı mesajları."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


class MotorHatasi(ValueError):
    """Kullanıcıya gösterilecek, iki dilli hata."""

    def __init__(self, kod: str, tr: str, en: str):
        super().__init__(tr)
        self.kod, self.tr, self.en = kod, tr, en

    def mesaj(self, dil: str = "TR") -> str:
        return self.tr if dil == "TR" else self.en


@dataclass
class Uyari:
    kod: str
    tr: str
    en: str


GELIR_YAPILARI = ("tuccar", "yekdem_opsiyon", "ppa")
SINIRLAR = {
    "baglanti_mw": (5.0, 300.0),
    "azami_res_mw": (0.0, 600.0),
    "azami_ges_mw": (0.0, 600.0),
    "yerlesim_yaricap_km": (0.5, 10.0),
    "fiyat_seviyesi": (20.0, 150.0),
    "wacc": (0.03, 0.15),
    "capex_carpani_res": (0.5, 2.0),
    "capex_carpani_ges": (0.5, 2.0),
    "capex_carpani_bess": (0.5, 2.0),
}


@dataclass
class KullaniciVarsayimlari:
    baglanti_mw: float = 50.0
    azami_res_mw: float | None = None
    azami_ges_mw: float | None = None
    turbin_yerlesimi: bool = True
    yerlesim_yaricap_km: float = 2.0
    fiyat_senaryosu: str = "baz"  # dusuk / baz / yuksek
    fiyat_seviyesi: float | None = None  # verilirse senaryonun yerine (USD/MWh reel)
    kanibalizasyon: str = "devam"  # devam / durur
    wacc: float | None = None  # None → config (%7 reel)
    capex_carpani_res: float = 1.0
    capex_carpani_ges: float = 1.0
    capex_carpani_bess: float = 1.0
    proje_asamasi: str = "insaata_hazir"  # on_lisans / insaata_hazir
    gelir_yapilari: tuple[str, ...] = GELIR_YAPILARI
    sfk_katilimi: bool = True
    sabit_tasarim: dict | None = None  # {"res_mw", "ges_mw", "bess_mw", "bess_mwh"} → optimizasyon yerine
    kalibrasyon: str = "atlas"  # atlas / gwa / v1 (yalnız Ezine regresyonu)
    ruzgar_kaynagi: str = "otomatik"  # otomatik (ERA5 grid → Open-Meteo) / grid / open_meteo / cds (çevrimdışı)
    turbin: str | None = None
    gobek: float | None = None
    # v3 Faz D: türbin yerleşimi (iz kaybı) + bakım ve güvenilirlik. False → v2 davranışı (toplu %12 kayıp, sabit OPEX).
    # kalibrasyon == "v1" (Ezine regresyonu) iken her zaman kapalı.
    yerlesim_bakim: bool = True
    yerlesim_yontemi: str | None = None  # None → config v3.yerlesim.yontem (sa / ga / milp / izgara / acgozlu)
    bakim_modeli: str = (
        "yeni"  # yeni: kullanılabilirlik ve O&M ayrık olay simülasyonundan; sabit: v1 OPEX + kalibrasyondaki kullanılabilirlik
    )
    bakim_stratejisi: str | None = None  # None → config v3.bakim.strateji (duzeltici / takvim / durum)
    isletme_modeli: str | None = None  # None → config v3.isletme.model (fsa: tam kapsamlı servis sözleşmesi / kendi: kendi bakımı)
    ekstra: dict = field(default_factory=dict)  # gelişmiş: config anahtar yolu → değer

    def v3_aktif(self) -> bool:
        return bool(self.yerlesim_bakim) and self.kalibrasyon != "v1"

    def sozluk(self) -> dict:
        d = asdict(self)
        d["gelir_yapilari"] = list(self.gelir_yapilari)
        return d


def dogrula(kv: KullaniciVarsayimlari) -> list[Uyari]:
    """Sınır ve tutarlılık kontrolü: hatada MotorHatasi, sınırda/olağan dışı durumlarda uyarı listesi."""
    uyari: list[Uyari] = []
    for ad, (alt, ust) in SINIRLAR.items():
        v = getattr(kv, ad)
        if v is not None and not (alt <= float(v) <= ust):
            raise MotorHatasi(
                "sinir",
                f"'{ad}' değeri {v} izin verilen aralığın dışında ({alt}–{ust}).",
                f"'{ad}' = {v} is outside the allowed range ({alt}–{ust}).",
            )
    if kv.fiyat_senaryosu not in ("dusuk", "baz", "yuksek"):
        raise MotorHatasi("fiyat", "Fiyat senaryosu dusuk, baz ya da yuksek olmalı.", "Price scenario must be dusuk, baz or yuksek.")
    if kv.kanibalizasyon not in ("devam", "durur"):
        raise MotorHatasi(
            "kanibalizasyon", "Kanibalizasyon varyantı devam ya da durur olmalı.", "Cannibalisation variant must be devam or durur."
        )
    if kv.proje_asamasi not in ("on_lisans", "insaata_hazir"):
        raise MotorHatasi(
            "asama", "Proje aşaması on_lisans ya da insaata_hazir olmalı.", "Project stage must be on_lisans or insaata_hazir."
        )
    if not kv.gelir_yapilari or any(g not in GELIR_YAPILARI for g in kv.gelir_yapilari):
        raise MotorHatasi(
            "gelir",
            f"Gelir yapıları şunlardan seçilmeli: {', '.join(GELIR_YAPILARI)}.",
            f"Revenue structures must be chosen from: {', '.join(GELIR_YAPILARI)}.",
        )
    if kv.yerlesim_yontemi is not None and kv.yerlesim_yontemi not in ("sa", "ga", "milp", "izgara", "acgozlu"):
        raise MotorHatasi(
            "yerlesim",
            "Yerleşim yöntemi sa, ga, milp, izgara ya da acgozlu olmalı.",
            "Layout method must be sa, ga, milp, izgara or acgozlu.",
        )
    if kv.bakim_modeli not in ("yeni", "sabit"):
        raise MotorHatasi("bakim", "Bakım modeli yeni ya da sabit olmalı.", "Maintenance model must be yeni or sabit.")
    if kv.isletme_modeli is not None and kv.isletme_modeli not in ("fsa", "kendi"):
        raise MotorHatasi("isletme", "İşletme modeli fsa ya da kendi olmalı.", "Operating model must be fsa or kendi.")
    if kv.bakim_stratejisi is not None and kv.bakim_stratejisi not in ("duzeltici", "takvim", "durum"):
        raise MotorHatasi(
            "strateji", "Bakım stratejisi duzeltici, takvim ya da durum olmalı.", "Maintenance strategy must be duzeltici, takvim or durum."
        )
    if kv.azami_res_mw == 0 and kv.azami_ges_mw == 0:
        raise MotorHatasi(
            "kapasite", "Hem RES hem GES üst sınırı sıfır: kurulacak bir şey yok.", "Both wind and solar limits are zero: nothing to build."
        )
    if kv.azami_res_mw is not None and kv.azami_res_mw < 0.5 * kv.baglanti_mw:
        uyari.append(
            Uyari(
                "res_sinir",
                "RES üst sınırı bağlantının yarısından az: bağlantı büyük ölçüde boş kalabilir.",
                "Wind limit is below half the grid connection: much of the connection may stay unused.",
            )
        )
    if kv.sabit_tasarim:
        for k in ("res_mw", "ges_mw", "bess_mw", "bess_mwh"):
            if float(kv.sabit_tasarim.get(k, 0)) < 0:
                raise MotorHatasi("tasarim", f"Sabit tasarımda '{k}' negatif olamaz.", f"Fixed design '{k}' cannot be negative.")
    return uyari
