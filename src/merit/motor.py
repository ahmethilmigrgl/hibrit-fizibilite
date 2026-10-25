"""
Merit order projeksiyonunu v2 motoruna bağlar: KullaniciVarsayimlari(fiyat_kaynagi="merit:<senaryo>").

Senaryonun motor parametreleri (src/merit/projeksiyon.motor_parametreleri; data/atlas/v4_merit.json) config'e yazılır:
    fiyat_senaryolari.seviye (düşük/baz/yüksek, baz = seviyelendirilmiş merit order fiyatı; düşük/yüksek aynı oranla)
    monte_carlo.fiyat_uzun_ortalama.seviye (Monte Carlo fiyat sürecinin beklenen değeri)
    fiyat_senaryolari.kanibalizasyon taban_oran / taban_yili (güneş yakalanma yolu)
    monte_carlo.kanibalizasyon_tabani üçgen(0,85 t; t; 1,2 t) — t = taban_oran (belirsizlik bandı TAHMİN)
Rüzgâr yakalanma oranı motorun tarihsel şekliyle kalır (merit order'da 0,93–0,99; bkz. docs/v4_K_merit_order.md).
"""

from __future__ import annotations

import json
from functools import lru_cache

from src import veri_katmani
from src.ayarlar import deger
from src.saha import _ata


@lru_cache(maxsize=1)
def _paket() -> dict:
    return json.loads(veri_katmani.yol("atlas/v4_merit.json").read_text(encoding="utf-8"))


def senaryolar() -> list[str]:
    try:
        return list(_paket()["motor"])
    except Exception:
        return []


def uygula(cfg: dict, senaryo: str) -> dict:
    mp = _paket()["motor"][senaryo]
    sv = dict(deger(cfg["fiyat_senaryolari"]["seviye"]))
    oran = mp["seviye"] / sv["baz"]
    _ata(cfg, "fiyat_senaryolari.seviye", {k: round(v * oran, 2) for k, v in sv.items()})
    fo = dict(deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"]))
    _ata(cfg, "monte_carlo.fiyat_uzun_ortalama", {**fo, "seviye": round(mp["seviye"], 2)})
    kan = dict(deger(cfg["fiyat_senaryolari"]["kanibalizasyon"]))
    _ata(
        cfg,
        "fiyat_senaryolari.kanibalizasyon",
        {**kan, "taban_oran": mp["kanibalizasyon_taban_oran"], "taban_yili": mp["kanibalizasyon_taban_yili"]},
    )
    kt = dict(deger(cfg["monte_carlo"]["kanibalizasyon_tabani"]))
    t = mp["kanibalizasyon_taban_oran"]
    _ata(cfg, "monte_carlo.kanibalizasyon_tabani", {**kt, "alt": round(0.85 * t, 3), "tepe": round(t, 3), "ust": round(1.2 * t, 3)})
    return mp
