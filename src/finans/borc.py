"""
Basit borç boyutlandırma (heykelsi / sculpted geri ödeme) ve öz kaynak IRR.

    CFADS_y (borç servisine esas nakit akışı) = FAVÖK − vergi(kaldıraçsız) − augmentation − söküm   [reel USD]
    Nominal CFADS_y = CFADS_y × (1 + π)^(y+1)          π: ABD enflasyonu (borç nominal USD)
    Borç servisi_y  = Nominal CFADS_y / DSCR_hedef     (vadenin ilk 'vade' işletme yılı)
    Borç (COD'da)   = Σ_y Borç servisi_y / (1 + i)^(y − COD)
    Tavan: Borç ≤ azami_borc_orani × CAPEX (nominal). Tavana takılırsa servis orantılı küçülür.

Borç, inşaat yıllarında CAPEX ile orantılı çekilir (inşaat dönemi faizi ihmal edildi).
Öz kaynak nakit akışı (reel) = −(CAPEX − borç çekişi) ; işletmede CFADS − borç servisi/(1+π)^(y+1) + faiz vergi kalkanı
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy_financial as npf

from src.ayarlar import deger
from src.finans.model import Sonuc


@dataclass
class BorcSonucu:
    borc_reel: float  # COD'daki borç, reel USD (FID fiyatlarıyla)
    borc_orani: float  # borç / CAPEX
    min_dscr: float
    ozkaynak_irr_reel: float
    ozkaynak_irr_nominal: float
    tavana_takildi: bool
    servis_nominal: np.ndarray
    ozkaynak_akisi: np.ndarray


def borc_boyutlandir(boyutlama: Sonuc, cfg: dict, nakit: Sonuc | None = None) -> BorcSonucu:
    """
    boyutlama: borcun boyutlandırıldığı nakit akışı (ör. P90 üretim + baz fiyat)
    nakit    : öz kaynak IRR'ının hesaplandığı nakit akışı (ör. P50); verilmezse boyutlama kullanılır
    """
    b, f, p = cfg["borc"], cfg["finans"], cfg["proje"]
    dscr, vade, i = deger(b["hedef_dscr"]), deger(b["vade"]), deger(b["faiz_nominal"])
    tavan, pi, vergi = deger(b["azami_borc_orani"]), deger(f["abd_enflasyonu"]), deger(f["kurumlar_vergisi"])
    nb = deger(p["insaat_suresi"])
    nakit = nakit or boyutlama

    o = boyutlama.ozet
    N = len(o["favok"])
    cfads = o["favok"] - o["vergi"] - o["aug"] - o["sokum"]
    y_isl = np.arange(nb, nb + N)  # işletme yıllarının zaman indeksi
    enf = (1 + pi) ** (y_isl + 1)
    servis = np.zeros(N)
    servis[:vade] = np.maximum(cfads[:vade], 0) * enf[:vade] / dscr
    iskonto = (1 + i) ** -(np.arange(1, N + 1))  # COD = inşaat sonu
    borc_nom = float((servis * iskonto).sum())
    capex_nom = float((o["capex_akisi"][:nb] * (1 + pi) ** (np.arange(nb) + 1)).sum())
    takildi = borc_nom > tavan * capex_nom
    if takildi:
        olcek = tavan * capex_nom / borc_nom
        servis *= olcek
        borc_nom *= olcek

    # Faiz/anapara tablosu
    bakiye, faiz = borc_nom, np.zeros(N)
    for y in range(N):
        faiz[y] = bakiye * i
        bakiye = bakiye + faiz[y] - servis[y]

    # Öz kaynak akışı (reel), P50 nakit akışıyla
    on = nakit.ozet
    cfads_n = on["favok"] - on["vergi"] - on["aug"] - on["sokum"]
    borc_reel = borc_nom / (1 + pi) ** nb
    T = nb + N
    akis = np.zeros(T)
    capex_ak = on["capex_akisi"][:nb]
    akis[:nb] = -capex_ak + borc_reel * capex_ak / capex_ak.sum()
    vergi_kalkani = np.minimum(faiz * vergi, np.maximum(on["vergi"], 0) * enf)  # kalkan ödenen vergiyi aşamaz
    akis[nb:] = cfads_n - (servis - vergi_kalkani) / enf
    irr_r = float(npf.irr(akis)) if np.any(akis > 0) and np.any(akis < 0) else float("nan")
    gercek_dscr = np.where(servis[:vade] > 0, cfads[:vade] * enf[:vade] / np.maximum(servis[:vade], 1e-9), np.inf)
    return BorcSonucu(
        borc_reel=borc_reel,
        borc_orani=borc_reel / max(capex_ak.sum(), 1e-9),
        min_dscr=float(gercek_dscr.min()) if vade > 0 else float("nan"),
        ozkaynak_irr_reel=irr_r,
        ozkaynak_irr_nominal=(1 + irr_r) * (1 + pi) - 1 if np.isfinite(irr_r) else float("nan"),
        tavana_takildi=bool(takildi),
        servis_nominal=servis,
        ozkaynak_akisi=akis,
    )
