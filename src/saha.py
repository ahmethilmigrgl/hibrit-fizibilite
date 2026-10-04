"""
v2 saha nesnesi: tüm hat (üretim, piyasa, finans, optimizasyon, risk) bir Saha ile çalışır; Ezine'ye özgü sabit yoktur.

Saha → sahaya özgü config kopyası (saha_cfg): türbin ve göbek (GWA rüzgâr sınıfına göre ya da kullanıcı), TEİAŞ 2026
iletim tarife bölgesine göre üretim sistem kullanım bedelleri, şebeke bağlantısı, RES/GES üst sınırları, kullanıcı
varsayımları (config anahtar yolu → değer). v1 config değerleri yalnız kopyada değişir.
"""

from __future__ import annotations

import copy
import math
import re
import unicodedata
from dataclasses import dataclass, field, replace

from src.ayarlar import config_oku, deger
from src.kaynaklar import gwa, sinirlar


@dataclass(frozen=True)
class Saha:
    ad: str
    enlem: float
    boylam: float
    il: str | None = None
    ilce: str | None = None
    baglanti_mw: float = 50.0
    azami_res_mw: float | None = None  # arazi/izin üst sınırı (kullanıcı); None → config varsayılanı
    azami_ges_mw: float | None = None
    turbin: str | None = None  # None → GWA rüzgâr sınıfına göre otomatik
    gobek: float | None = None
    varsayimlar: dict = field(default_factory=dict)  # {"finans.wacc_reel": 0.08, ...} — config anahtar yolu → değer

    @property
    def kod(self) -> str:
        s = unicodedata.normalize("NFKD", self.ad.replace("ı", "i").replace("İ", "I")).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def saha_olustur(ad: str, enlem: float, boylam: float, **kw) -> Saha:
    """Koordinatı doğrular (Türkiye karası) ve il/ilçeyi doldurur."""
    k = sinirlar.konum(enlem, boylam)
    if k is None:
        raise ValueError(f"Nokta Türkiye karasında değil: {enlem:.4f}, {boylam:.4f}")
    return Saha(ad=ad, enlem=enlem, boylam=boylam, il=k["il"], ilce=k["ilce"], **kw)


def ezine() -> Saha:
    """v1.0.0 sahası (config.saha + v1 türbin/göbek) — regresyon testi için."""
    cfg = config_oku()
    s = cfg["aday_sahalar"][deger(cfg["saha"]["kod"])]
    cr = cfg["uretim"]["ruzgar"]
    sb = cfg["teknoloji"]["sebeke"]
    # v1 değerleri birebir (v1 TEİAŞ bedelini 3.470 USD/MW-yıla yuvarlamıştı; 2026 tablosu 3.471,9 verir)
    v1 = {
        "teknoloji.sebeke.teias_kapasite_bedeli": deger(sb["teias_kapasite_bedeli"]),
        "teknoloji.sebeke.teias_enerji_bedeli": deger(sb["teias_enerji_bedeli"]),
    }
    return saha_olustur(
        "Çanakkale-Ezine",
        s["enlem"],
        s["boylam"],
        baglanti_mw=50.0,
        turbin=deger(cr["turbin_modeli"]),
        gobek=deger(cr["gobek_yuksekligi"]),
        varsayimlar=v1,
    )


def _buyuk(ad: str) -> str:
    ad = unicodedata.normalize("NFKD", ad).replace("̂", "")  # â, î, û → a, i, u (ör. Hakkâri)
    ad = unicodedata.normalize("NFKC", ad)
    return ad.replace("i", "İ").replace("ı", "I").upper()


def tarife_bolgesi(saha: Saha, cfg: dict | None = None) -> int:
    cfg = cfg or config_oku()
    ib = deger(cfg["v2"]["teias_2026"]["il_bolge"])
    if saha.il is None or _buyuk(saha.il) not in ib:
        raise ValueError(f"İl tarife tablosunda yok: {saha.il}")
    return int(ib[_buyuk(saha.il)])


def teias_bedelleri(saha: Saha, cfg: dict | None = None) -> tuple[float, float]:
    """(üretim kapasite bedeli USD/MW-yıl, enerji bedeli USD/MWh) — 2026 tarifesi, sabit kurla reel USD."""
    cfg = cfg or config_oku()
    t = cfg["v2"]["teias_2026"]
    kur = deger(t["kur_tl_usd"])
    return deger(t["uretim_tarifesi"])[tarife_bolgesi(saha, cfg)] / kur, deger(t["uretim_enerji_bedeli"]) / kur


def turbin_sec(saha: Saha, cfg: dict | None = None) -> dict:
    """GWA 100 m ortalama hızına göre rüzgâr sınıfı, türbin ve göbek (kullanıcı verdiyse o kullanılır)."""
    cfg = cfg or config_oku()
    v = gwa.nokta(saha.enlem, saha.boylam)["ws_ort"]
    kural = next(k for k in deger(cfg["v2"]["turbin_secimi"]) if v < k["gwa_100m_ust"])
    return {
        "gwa_100m": v,
        "sinif": kural["sinif"],
        "turbin": saha.turbin or kural["turbin"],
        "gobek": saha.gobek or kural["gobek"],
        "otomatik": saha.turbin is None,
    }


def _ata(cfg: dict, yol: str, deger_: object) -> None:
    d = cfg
    parca = yol.split(".")
    for p in parca[:-1]:
        d = d[p]
    if isinstance(d.get(parca[-1]), dict) and "value" in d[parca[-1]]:
        d[parca[-1]]["value"] = deger_
    else:
        d[parca[-1]] = deger_


def saha_cfg(saha: Saha, cfg: dict | None = None) -> dict:
    """Sahaya özgü config kopyası."""
    cfg = copy.deepcopy(cfg or config_oku())
    ts = turbin_sec(saha, cfg)
    from windpowerlib import WindTurbine

    _ata(cfg, "uretim.ruzgar.turbin_modeli", ts["turbin"])
    _ata(cfg, "uretim.ruzgar.gobek_yuksekligi", ts["gobek"])
    _ata(cfg, "optimizasyon.turbin_gucu", WindTurbine(turbine_type=ts["turbin"], hub_height=ts["gobek"]).nominal_power / 1e6)
    kap, ene = teias_bedelleri(saha, cfg)
    _ata(cfg, "teknoloji.sebeke.teias_kapasite_bedeli", round(kap, 1))
    _ata(cfg, "teknoloji.sebeke.teias_enerji_bedeli", round(ene, 3))
    _ata(cfg, "saha.sebeke_baglanti_kapasitesi", saha.baglanti_mw)
    if saha.azami_res_mw is not None:
        tg = deger(cfg["optimizasyon"]["turbin_gucu"])
        _ata(cfg, "optimizasyon.turbin_azami", int(math.floor(saha.azami_res_mw / tg + 1e-9)))
    if saha.azami_ges_mw is not None:
        _ata(cfg, "optimizasyon.ges_azami_mw", saha.azami_ges_mw)
    for yol, d in saha.varsayimlar.items():
        _ata(cfg, yol, d)
    cfg["_saha"] = {
        "ad": saha.ad,
        "kod": saha.kod,
        "enlem": saha.enlem,
        "boylam": saha.boylam,
        "il": saha.il,
        "ilce": saha.ilce,
        "tarife_bolgesi": tarife_bolgesi(saha, cfg),
        "turbin": ts,
    }
    return cfg


def ilce_adaylari(il: str, ilce: str, adet: int | None = None, cfg: dict | None = None) -> list[Saha]:
    """İlçe içinde GWA ortalama hızı en yüksek, birbirinden en az 'asgari aralık' uzak aday noktalar (ilçe merkezi değil)."""
    cfg = cfg or config_oku()
    adet = adet or deger(cfg["v2"]["aday_nokta_sayisi"])
    aralik = deger(cfg["v2"]["aday_nokta_asgari_aralik_km"])
    P = gwa._yukle()
    secim: list[tuple[float, float, float]] = []
    for e, b, v in gwa.aday_noktalar(sinirlar.ilce_maskesi(il, ilce), P["sol"], P["ust"], P["adim"], adet=200):
        if all(_km(e, b, e2, b2) >= aralik for e2, b2, _ in secim):
            secim.append((e, b, v))
        if len(secim) == adet:
            break
    return [replace(saha_olustur(f"{ilce} aday {i}", e, b), il=il, ilce=ilce) for i, (e, b, _) in enumerate(secim, 1)]


def _km(e1: float, b1: float, e2: float, b2: float) -> float:
    p = math.pi / 180
    a = math.sin((e2 - e1) * p / 2) ** 2 + math.cos(e1 * p) * math.cos(e2 * p) * math.sin((b2 - b1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))
