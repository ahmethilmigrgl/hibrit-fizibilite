"""
Proje ömrü boyunca saatlik fiyat senaryoları (reel USD/MWh).

Yapı:  p_y(t) = L × şekil(t) × [1 − d_y · g(t)] / ortalama(şekil × [1 − d_y · g])
    L        : yıllık baz yük ortalama fiyat seviyesi (düşük / baz / yüksek), reel USD
    şekil(t) : son dönemin (2025 + Eki 2025–Eyl 2026) saatlik fiyat şekli, ortalaması 1
    g(t)     : güneş üretim şekli (Ezine GES'in 10 hava yılı ortalaması, en büyüğü 1)
    d_y      : kanibalizasyon derinliği; öğle saatlerindeki fiyat çukurunu derinleştirir.
               Her yıl, Ezine GES'in yakalanma oranı hedef değere eşit olacak şekilde çözülür.
               Payda yıllık ortalamayı L'de sabit tutar (seviye ile şekil birbirinden ayrılır).

Kanibalizasyon varyantları:
    "durur" : güneş yakalanma oranı şekil dönemindeki değerinde kalır
    "devam" : oran taban_yili'na kadar doğrusal olarak taban_oran'a iner, sonra sabit kalır

Düzenleyici tavan (opsiyonel, 2022–23 AUF dönemi örneği): belirtilen işletme yıllarında
satış fiyatı = min(p, tavan_carpani × L).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from src.ayarlar import deger
from src.finans.veri import UretimProfili, fiyat_sekil_yillari, yan_hizmet_sekil_yillari


@dataclass
class FiyatSenaryosu:
    fiyatlar: np.ndarray  # (işletme_yılı, şekil_yılı, 8760) reel USD/MWh
    yillar: list[int]  # takvim yılları
    seviye: float  # L
    ad: str
    gunes_hedef_oran: np.ndarray  # yıl başına Ezine GES yakalanma oranı hedefi
    bilgi: dict = field(default_factory=dict)
    yan_hizmet: np.ndarray | None = None  # (işletme_yılı, şekil_yılı, 8760) USD/MW-saat kapasite fiyatı


def _gunes_orani(sekil: np.ndarray, g: np.ndarray, d: float) -> float:
    p = sekil * (1 - d * g)
    return float((p * g).sum() / g.sum() / p.mean())


def _derinlik(sekil: np.ndarray, g: np.ndarray, hedef: float) -> float:
    """Ezine GES yakalanma oranını hedefe eşitleyen d (0 ≤ d < 1)."""
    if _gunes_orani(sekil, g, 0.0) <= hedef:
        return 0.0
    return brentq(lambda d: _gunes_orani(sekil, g, d) - hedef, 0.0, 0.999, xtol=1e-6)


def fiyat_senaryosu_uret(
    cfg: dict,
    uretim: UretimProfili,
    seviye: str | float = "baz",
    kanibalizasyon: str | None = None,
    duzenleyici: bool | None = None,
    taban_oran: float | None = None,
    yh_azalma: float | None = None,
) -> FiyatSenaryosu:
    """Seviye ve kanibalizasyon varyantına göre (yıl × şekil yılı × 8760) reel saatlik fiyat senaryosu üretir."""
    fs = cfg["fiyat_senaryolari"]
    bas_yil = deger(cfg["proje"]["baslangic_yili"])
    omur = deger(cfg["proje"]["omur"])
    yillar = list(range(bas_yil, bas_yil + omur))

    L = deger(fs["seviye"])[seviye] if isinstance(seviye, str) else float(seviye)
    kan = deger(fs["kanibalizasyon"])
    varyant = kanibalizasyon or kan["varyant"]
    duz = deger(fs["duzenleyici_tavan"])
    duz_aktif = duz["aktif"] if duzenleyici is None else duzenleyici

    sekil, sekil_adlari = fiyat_sekil_yillari(*deger(fs["sekil_donemi"]))
    g = uretim.ges.mean(axis=0)
    g = g / g.max()

    # Şekil dönemindeki güneş yakalanma oranı (iki şekil yılının ortalaması) — başlangıç noktası
    oran0 = float(np.mean([_gunes_orani(s, g, 0.0) for s in sekil]))
    hedef = np.full(len(yillar), oran0)
    if varyant == "devam":
        sekil_yili = 2026  # şekil döneminin merkezi ≈ 2025,9
        taban, taban_yili = (kan["taban_oran"] if taban_oran is None else taban_oran), kan["taban_yili"]
        for i, y in enumerate(yillar):
            oran = oran0 + (taban - oran0) * (y - sekil_yili) / (taban_yili - sekil_yili)
            hedef[i] = max(taban, min(oran0, oran))

    fiyatlar = np.empty((len(yillar), len(sekil), sekil.shape[1]))
    onbellek: dict[tuple[int, float], np.ndarray] = {}
    for i in range(len(yillar)):
        for j, s in enumerate(sekil):
            anahtar = (j, round(float(hedef[i]), 5))
            if anahtar not in onbellek:
                # Her şekil yılı kendi başlangıç oranından aynı miktarda iner
                fark = oran0 - hedef[i]
                hedef_j = _gunes_orani(s, g, 0.0) - fark
                d = _derinlik(s, g, hedef_j)
                p = s * (1 - d * g)
                onbellek[anahtar] = np.clip(L * p / p.mean(), 0.0, None)
            fiyatlar[i, j] = onbellek[anahtar]

    if duz_aktif:
        for k in duz["isletme_yillari"]:
            if 1 <= k <= len(yillar):
                fiyatlar[k - 1] = np.minimum(fiyatlar[k - 1], duz["tavan_carpani"] * L)

    # Yan hizmet kapasite fiyatı: 2026 seviyesinden yıllık azalma, taban oranında durur
    yh_cfg = cfg.get("gelir_yigini", {}).get("yan_hizmet")
    yan = None
    if yh_cfg is not None:
        azalma = deger(yh_cfg["yillik_azalma"]) if yh_azalma is None else yh_azalma
        carpan = np.maximum((1 - azalma) ** (np.array(yillar) - 2026), deger(yh_cfg["taban_oran"]))
        yan = carpan[:, None, None] * yan_hizmet_sekil_yillari(deger(yh_cfg["urun"]))[None]
    ad = f"{seviye if isinstance(seviye, str) else L} / kanibalizasyon {varyant}" + (" / tavan" if duz_aktif else "")
    return FiyatSenaryosu(
        fiyatlar=fiyatlar,
        yillar=yillar,
        seviye=L,
        ad=ad,
        gunes_hedef_oran=hedef,
        yan_hizmet=yan,
        bilgi={"sekil_yillari": sekil_adlari, "baslangic_gunes_orani": oran0, "varyant": varyant, "duzenleyici": duz_aktif},
    )
