"""
CBS katmanlarına çalışma anı erişimi (v3 E1–E2) ve Faz D dışlama arayüzüne bağlanan dışlama katmanları.

Karolar (veri katmanı; GWA 250 m ile hizalı 1° karolar, 0,0025°):
    grid/cbs_tr/v1/{e}_{b}.npz  yerlesim, otoyol, devlet, ikincil, hat, havalimani (10 m adımlı mesafe), koruma (0/1), goc (0/1/2)
    grid/egim_tr/v1/{e}_{b}.npz egim_ort (×4), egim_azami (°), rakim (m)
Karo yoksa (ör. veri paketi kurulmamış) değerler None döner ve dışlama uygulanmaz (uyarıyla).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.ayarlar import config_oku, deger

ADIM = 0.0025


@lru_cache(maxsize=24)
def _karo(tur: str, e0: int, b0: int) -> dict | None:
    from src import veri_katmani

    p = veri_katmani.yol(f"grid/{tur}/v1/{e0}_{b0}.npz", zorunlu=False)
    if p is None:
        return None
    z = np.load(p)
    return {k: z[k] for k in z.files}


def degerler(enlem, boylam) -> dict[str, np.ndarray] | None:
    """Noktaların 250 m hücre değerleri: mesafeler [m], eğim [°], rakım, koruma, göç. Hiç karo yoksa None."""
    enlem = np.atleast_1d(np.asarray(enlem, float))
    boylam = np.atleast_1d(np.asarray(boylam, float))
    out: dict[str, np.ndarray] = {}
    var = False
    alanlar = {
        "cbs_tr": ("yerlesim", "otoyol", "devlet", "ikincil", "hat", "havalimani", "koruma", "goc"),
        "egim_tr": ("egim_ort", "egim_azami", "rakim"),
    }
    for tur, adlar in alanlar.items():
        for a in adlar:
            out[a] = np.full(len(enlem), np.nan)
        for k in {(int(math.floor(e)), int(math.floor(b))) for e, b in zip(enlem, boylam)}:
            z = _karo(tur, *k)
            if z is None:
                continue
            var = True
            s = (np.floor(enlem) == k[0]) & (np.floor(boylam) == k[1])
            i = np.clip(((z["ust"] - enlem[s]) / z["adim"]).astype(int), 0, 399)
            j = np.clip(((boylam[s] - z["sol"]) / z["adim"]).astype(int), 0, 399)
            for a in adlar:
                v = z[a][i, j].astype(float)
                if tur == "cbs_tr" and a not in ("koruma", "goc"):
                    v = v * 10.0  # m
                if a == "egim_ort":
                    v = v / 4.0
                out[a][s] = v
    return out if var else None


def tampon_m(cfg: dict, gobek: float, D: float) -> dict[str, float]:
    t = deger(cfg["v3"]["cbs"])["tampon"]
    HL = gobek + D / 2.0
    return {
        "yerlesim": t["yerlesim_m"],
        "otoyol": t["otoyol_kat"] * HL,
        "devlet": t["devlet_il_yolu_kat"] * HL,
        "hat": t["iletim_hatti_kat"] * HL,
        "havalimani": t["havalimani_km"] * 1000.0,
        "egim": t["egim_azami_derece"],
    }


@dataclass
class CBSDislama:
    """Faz D DislamaKatmani arayüzü: tek bir CBS kuralı (ad + koşul)."""

    ad: str
    kural: str
    esik: float

    def maske(self, enlem: np.ndarray, boylam: np.ndarray) -> np.ndarray:
        d = degerler(enlem, boylam)
        if d is None:
            return np.zeros(len(np.atleast_1d(enlem)), bool)
        if self.kural == "koruma":
            return d["koruma"] > 0
        if self.kural == "egim":
            return d["egim_ort"] > self.esik
        return d[self.kural] < self.esik


def dislama_katmanlari(cfg: dict | None = None, gobek: float = 120.0, D: float = 141.0) -> list:
    cfg = cfg or config_oku()
    t = tampon_m(cfg, gobek, D)
    k = [
        CBSDislama("yerleşim tamponu", "yerlesim", t["yerlesim"]),
        CBSDislama("otoyol tamponu", "otoyol", t["otoyol"]),
        CBSDislama("devlet/il yolu tamponu", "devlet", t["devlet"]),
        CBSDislama("iletim hattı tamponu", "hat", t["hat"]),
        CBSDislama("havalimanı tamponu", "havalimani", t["havalimani"]),
        CBSDislama("aşırı eğim", "egim", t["egim"]),
    ]
    if deger(cfg["v3"]["cbs"])["tampon"]["koruma_alani"]:
        k.append(CBSDislama("koruma alanı", "koruma", 0.0))
    return k


def alan_ozeti(
    enlem: float, boylam: float, yaricap_km: float, cfg: dict | None = None, gobek: float = 120.0, D: float = 141.0
) -> dict | None:
    """Saha yarıçapındaki 250 m hücrelerin dışlama kesişimleri, eğim ve göç riski özeti (saha kartı için)."""
    from src.kaynaklar import gwa250

    E, B, _ = gwa250.pencere(enlem, boylam, yaricap_km)
    if len(E) == 0:
        return None
    d = degerler(E, B)
    if d is None:
        return None
    cfg = cfg or config_oku()
    oz = {"hucre": int(len(E)), "dislanan": {}}
    hepsi = np.zeros(len(E), bool)
    for k in dislama_katmanlari(cfg, gobek, D):
        m = k.maske(E, B)
        oz["dislanan"][k.ad] = float(m.mean())
        hepsi |= m
    oz["uygun_oran"] = float(1 - hepsi.mean())
    oz["goc_azami"] = int(np.nanmax(d["goc"]))
    oz["egim_ort"] = float(np.nanmean(d["egim_ort"]))
    oz["egim_azami"] = float(np.nanmax(d["egim_azami"]))
    oz["koruma_oran"] = float(np.nanmean(d["koruma"] > 0))
    oz["yerlesim_en_yakin_m"] = float(np.nanmin(d["yerlesim"]))
    return oz
