"""
Sahanın rüzgâr gülü ve iz hesabı için akış durumları (yön × hız frekans tablosu).

Hız: üretim profilinin kalibre göbek hızı (ERA5 100 m → saatlik kayma üssüyle göbeğe → atlas ay × saat katsayısı; profilde
'v_kalibre'), yoğunluk eşdeğerine çevrilir: v_eş = v · (ρ / 1,225)^(1/3) (IEC 61400-12 düzeltmesinin düşük/orta hız
yaklaşımı). Böylece rüzgâr gülü ve iz hesabı, profildeki enerjiyle aynı rüzgârı kullanır (atlas kalibrasyonuyla tutarlı).
Yön: ERA5 100 m (src/kaynaklar/era5_yon.py). Yön verisi yoksa tek biçimli yön dağılımı (bilinmiyor bayrağıyla).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

RHO0 = 1.225


@dataclass
class AkisTablosu:
    wd: np.ndarray  # yön merkezleri [°] (n_wd)
    ws: np.ndarray  # hız merkezleri [m/s] (n_ws)
    P: np.ndarray  # frekans (n_wd, n_ws), toplam 1
    i_wd: np.ndarray  # saat → yön indeksi
    v: np.ndarray  # saatlik yoğunluk eşdeğeri hız
    yon_kaynagi: str
    eksen: float  # hâkim eksen [°] (0–180, enerji ağırlıklı)
    hakim_yon: float  # enerji ağırlıklı en sık sektör merkezi [°]

    def kaba(self, n_wd: int = 12, ws_kenar: np.ndarray | None = None) -> AkisTablosu:
        """Daha kaba yön/hız ızgarası (optimizasyon için); frekanslar toplanır, hız merkezi enerji yerine olasılık ağırlıklı."""
        ws_kenar = np.arange(0.0, 31.0, 1.5) if ws_kenar is None else ws_kenar
        n0 = len(self.wd)
        k = n0 // n_wd
        assert n0 % n_wd == 0, "yön sayısı katı olmalı"
        # 36 → 12: her kaba sektör, merkezi çevreleyen k ince sektör (kaydırarak)
        kaydir = k // 2
        Pw = np.roll(self.P, kaydir, axis=0).reshape(n_wd, k, -1).sum(1)
        j = np.clip(np.digitize(self.ws, ws_kenar) - 1, 0, len(ws_kenar) - 2)
        P2 = np.zeros((n_wd, len(ws_kenar) - 1))
        S2 = np.zeros_like(P2)
        for jj in range(len(ws_kenar) - 1):
            s = j == jj
            P2[:, jj] = Pw[:, s].sum(1)
            S2[:, jj] = (Pw[:, s] * self.ws[s]).sum(1)
        # hız merkezleri yönler arası ortak olmalı → olasılık ağırlıklı ortak merkez
        ws_m = np.where(P2.sum(0) > 0, S2.sum(0) / np.maximum(P2.sum(0), 1e-15), 0.5 * (ws_kenar[:-1] + ws_kenar[1:]))
        wd_m = np.arange(n_wd) * 360.0 / n_wd
        i_wd = ((self.i_wd + kaydir) // k) % n_wd
        return AkisTablosu(wd_m, ws_m, P2, i_wd, self.v, self.yon_kaynagi, self.eksen, self.hakim_yon)


def esdeger_hiz(v_kalibre: np.ndarray, yogunluk: np.ndarray) -> np.ndarray:
    return np.asarray(v_kalibre, float) * (np.asarray(yogunluk, float) / RHO0) ** (1 / 3)


def akis_tablosu(v: np.ndarray, yon: np.ndarray | None, n_wd: int = 36, ws_adim: float = 0.5, guc=None, kaynak: str = "") -> AkisTablosu:
    """
    v: saatlik yoğunluk eşdeğeri hız; yon: saatlik meteorolojik yön [°] (None → tek biçimli).
    guc: hız → güç fonksiyonu (hâkim yön/eksen enerji ağırlıklı bulunur); verilmezse v³.
    """
    v = np.asarray(v, float)
    ws_kenar = np.arange(0.0, 35.0 + ws_adim, ws_adim)
    ws = 0.5 * (ws_kenar[:-1] + ws_kenar[1:])
    j = np.clip(np.digitize(v, ws_kenar) - 1, 0, len(ws) - 1)
    wd = np.arange(n_wd) * 360.0 / n_wd
    if yon is None:
        P = np.tile(np.bincount(j, minlength=len(ws)) / len(v), (n_wd, 1)) / n_wd
        i_wd = np.zeros(len(v), int)
        return AkisTablosu(wd, ws, P, i_wd, v, "yok (tek biçimli)", 0.0, 0.0)
    yon = np.asarray(yon, float)[: len(v)]
    w = 360.0 / n_wd
    i_wd = (np.floor(np.mod(yon + w / 2, 360.0) / w).astype(int)) % n_wd
    P = np.zeros((n_wd, len(ws)))
    np.add.at(P, (i_wd, j), 1.0)
    P /= P.sum()
    e = guc(v) if guc is not None else np.minimum(v, 15.0) ** 3
    th = np.radians(yon)
    eksen = (0.5 * np.degrees(np.arctan2((e * np.sin(2 * th)).sum(), (e * np.cos(2 * th)).sum()))) % 180.0
    hakim = float(wd[np.argmax(np.bincount(i_wd, weights=e, minlength=n_wd))])
    return AkisTablosu(wd, ws, P, i_wd, v, kaynak, float(eksen), hakim)


def gul_tablosu(v: np.ndarray, yon: np.ndarray, n_sektor: int = 12, hiz_kenar=(0, 3, 6, 9, 12, 15, 99)) -> pd.DataFrame:
    """Gösterim için rüzgâr gülü: sektör × hız aralığı frekansı [%] (satır: sektör merkezi derece)."""
    w = 360.0 / n_sektor
    s = (np.floor(np.mod(np.asarray(yon) + w / 2, 360) / w).astype(int)) % n_sektor
    etiket = [f"{a}–{b}" if b < 99 else f"≥{a}" for a, b in pairwise(hiz_kenar)]
    k = pd.cut(np.asarray(v), list(hiz_kenar), right=False, labels=etiket)
    t = pd.crosstab(pd.Series(s * w, name="sektor"), pd.Series(k, name="hiz"), normalize=True) * 100
    return t.reindex(index=np.arange(n_sektor) * w, columns=etiket, fill_value=0.0)
