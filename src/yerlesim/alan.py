"""
Saha alanı, dışlama katmanları ve aday türbin konumları.

Saha alanı varsayılan olarak seçilen nokta çevresinde bir dairedir (yarıçap = türbin yerleşimi yarıçapı, kullanıcı değiştirebilir).
Dışlama katmanları bir arayüzle (DislamaKatmani) eklenir; Faz E'de yol, yerleşim, koruma alanı ve eğim katmanları aynı arayüzle
bağlanacak. Şimdilik hazır katmanlar:
    MevcutTurbinTamponu — komşu santral türbinlerine (OSM) en az k·D mesafe (başka bir santralin parselinde yer seçilmez)
    KaraMaskesi         — Türkiye karası dışındaki (deniz) hücreler

Aday konumlar: alan içindeki GWA 250 m hücre merkezleri (isteğe bağlı olarak her hücre 2×2 alt hücreye bölünür; alt hücreler
GWA hızını üst hücreden alır). Her adayın GWA hız çarpanı m_i = GWA_i / GWA_ref; GWA_ref, üretim profilinin
kalibre edildiği GWA hızıdır (v2 türbin yerleşimi kuralı: yarıçapta en rüzgârlı hücrelerin ortalaması), böylece
yerleşim atlas kalibrasyonuyla tutarlıdır: m_i = 1 olan bir konum profildeki rüzgârı görür.
Koordinatlar: saha merkezli yerel düzlem (x doğu, y kuzey, metre; eşdikdörtgen izdüşüm, 10 km içinde hata < %0,1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

R_DUNYA = 6_371_000.0


def yerel_xy(enlem, boylam, e0: float, b0: float) -> tuple[np.ndarray, np.ndarray]:
    e, b = np.asarray(enlem, float), np.asarray(boylam, float)
    x = np.radians(b - b0) * R_DUNYA * np.cos(np.radians(e0))
    y = np.radians(e - e0) * R_DUNYA
    return x, y


def enlem_boylam(x, y, e0: float, b0: float) -> tuple[np.ndarray, np.ndarray]:
    e = e0 + np.degrees(np.asarray(y, float) / R_DUNYA)
    b = b0 + np.degrees(np.asarray(x, float) / (R_DUNYA * np.cos(np.radians(e0))))
    return e, b


class DislamaKatmani(Protocol):
    """Dışlama katmanı arayüzü: True = bu konuma türbin konamaz."""

    ad: str

    def maske(self, enlem: np.ndarray, boylam: np.ndarray) -> np.ndarray: ...


@dataclass
class MevcutTurbinTamponu:
    """Mevcut (komşu) türbinlere en az 'tampon_m' mesafe."""

    enlem: np.ndarray
    boylam: np.ndarray
    tampon_m: float
    ad: str = "mevcut türbin tamponu"

    def maske(self, enlem: np.ndarray, boylam: np.ndarray) -> np.ndarray:
        if len(self.enlem) == 0:
            return np.zeros(len(enlem), bool)
        e0, b0 = float(np.mean(enlem)), float(np.mean(boylam))
        x, y = yerel_xy(enlem, boylam, e0, b0)
        xt, yt = yerel_xy(self.enlem, self.boylam, e0, b0)
        d = np.hypot(x[:, None] - xt[None], y[:, None] - yt[None])
        return (d < self.tampon_m).any(axis=1)


@dataclass
class KaraMaskesi:
    ad: str = "deniz (Türkiye karası dışı)"

    def maske(self, enlem: np.ndarray, boylam: np.ndarray) -> np.ndarray:
        from src.kaynaklar import sinirlar

        return np.array([sinirlar.konum(float(e), float(b)) is None for e, b in zip(enlem, boylam)])


@dataclass
class SahaAlani:
    enlem: float
    boylam: float
    yaricap_km: float = 2.0
    dislama: list = field(default_factory=list)  # DislamaKatmani listesi

    def adaylar(self, alt_bolme: int = 1) -> pd.DataFrame:
        """Alan içindeki aday konumlar: enlem, boylam, x, y [m], gwa [m/s], dislanan katman adı (yoksa '')."""
        from src.kaynaklar import gwa250

        E, B, V = gwa250.pencere(self.enlem, self.boylam, self.yaricap_km + 0.2)
        if len(V) == 0:  # GWA karosu yok: nokta çevresinde 250 m düzenli ızgara, hız sabit
            adim = 250.0
            k = int(self.yaricap_km * 1000 // adim)
            gx, gy = np.meshgrid(np.arange(-k, k + 1) * adim, np.arange(-k, k + 1) * adim)
            E, B = enlem_boylam(gx.ravel(), gy.ravel(), self.enlem, self.boylam)
            V = np.full(len(E), gwa250.nokta(self.enlem, self.boylam))
        if alt_bolme > 1:
            ofs = (np.arange(alt_bolme) + 0.5) / alt_bolme - 0.5
            de, db = np.meshgrid(ofs * gwa250.ADIM, ofs * gwa250.ADIM)
            E = (E[:, None] + de.ravel()[None]).ravel()
            B = (B[:, None] + db.ravel()[None]).ravel()
            V = np.repeat(V, alt_bolme**2)
        x, y = yerel_xy(E, B, self.enlem, self.boylam)
        ic = np.hypot(x, y) <= self.yaricap_km * 1000
        d = pd.DataFrame({"enlem": E[ic], "boylam": B[ic], "x": x[ic], "y": y[ic], "gwa": V[ic]})
        d["dislanan"] = ""
        for k in self.dislama:
            m = np.asarray(k.maske(d["enlem"].to_numpy(), d["boylam"].to_numpy()), bool) & (d["dislanan"] == "")
            d.loc[m, "dislanan"] = k.ad
        return d.reset_index(drop=True)


def elips_catisma(x: np.ndarray, y: np.ndarray, D: float, a_D: float, b_D: float, eksen_derece: float) -> np.ndarray:
    """
    Asgari aralık kısıtı (elips): i ve j çatışır ⇔ (u/(a·D))² + (v/(b·D))² < 1; u hâkim rüzgâr ekseni boyunca, v ona dik
    uzaklık. eksen_derece: hâkim eksen (meteorolojik, 0 = kuzey–güney ekseni). Döndürür: n × n mantıksal matris (köşegen False).
    """
    t = np.radians(eksen_derece)
    ex, ey = np.sin(t), np.cos(t)  # eksen yönündeki birim vektör (doğu, kuzey)
    dx = x[:, None] - x[None]
    dy = y[:, None] - y[None]
    u = dx * ex + dy * ey
    v = -dx * ey + dy * ex
    c = (u / (a_D * D)) ** 2 + (v / (b_D * D)) ** 2 < 1.0
    np.fill_diagonal(c, False)
    return c
