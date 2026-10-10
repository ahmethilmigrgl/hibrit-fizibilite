"""
Türbin güç ve itki (CT) eğrileri.

Güç eğrisi: windpowerlib/OEP kütüphanesi (üretim modeliyle aynı; src/uretim/ruzgar.py).
İtki katsayısı CT(v): kütüphanede yok → PyWake GenericWindTurbine (DTU, MIT lisansı) aynı rotor çapı, göbek ve anma gücüyle
genel bir BEM tabanlı eğri üretir (Cp tepe ~0,49, kısmi yükte CT ≈ 0,8). Kütüphanesi bilinmeyen komşu santral türbinleri
(OSM) için güç eğrisi de GenericWindTurbine'den alınır (yalnız CT'leri, yani iz etkileri kullanılır).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

WS = np.arange(0.0, 35.01, 0.25)  # eğri ızgarası [m/s]


@dataclass(frozen=True)
class TurbinEgrisi:
    ad: str
    D: float  # rotor çapı [m]
    H: float  # göbek yüksekliği [m]
    P_mw: float  # anma gücü [MW]
    ws: tuple  # hız ızgarası
    guc: tuple  # [MW]
    ct: tuple  # [-]

    def guc_mw(self, v: np.ndarray) -> np.ndarray:
        return np.interp(v, self.ws, self.guc, left=0.0, right=0.0)

    def ct_v(self, v: np.ndarray) -> np.ndarray:
        return np.interp(v, self.ws, self.ct, left=0.0, right=0.0)

    def pywake(self):
        """PyWake WindTurbine (tablo eğrileri)."""
        from py_wake.wind_turbines import WindTurbine
        from py_wake.wind_turbines.power_ct_functions import PowerCtTabular

        return WindTurbine(
            name=self.ad,
            diameter=self.D,
            hub_height=self.H,
            powerCtFunction=PowerCtTabular(np.array(self.ws), np.array(self.guc) * 1e3, "kW", np.array(self.ct)),
        )


def _generic(D: float, H: float, P_mw: float):
    from py_wake.wind_turbines.generic_wind_turbines import GenericWindTurbine

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = GenericWindTurbine("g", diameter=D, hub_height=H, power_norm=P_mw * 1e3, turbulence_intensity=0.1)
    return g


@lru_cache(maxsize=64)
def kutuphane_turbini(model: str, gobek: float) -> TurbinEgrisi:
    """windpowerlib türbini: güç eğrisi kütüphaneden, CT GenericWindTurbine'den (aynı D, H, P)."""
    from windpowerlib import WindTurbine

    t = WindTurbine(turbine_type=model, hub_height=gobek)
    pc = t.power_curve
    P = t.nominal_power / 1e6
    guc = np.interp(WS, pc["wind_speed"].to_numpy(float), pc["value"].to_numpy(float) / 1e6, left=0.0, right=0.0)
    guc[WS > float(pc["wind_speed"].max())] = 0.0  # kesme hızı üstü
    g = _generic(float(t.rotor_diameter), gobek, P)
    ct = np.where(guc > 0, g.ct(np.maximum(WS, 0.1)), 0.0)
    return TurbinEgrisi(model, float(t.rotor_diameter), float(gobek), P, tuple(WS), tuple(guc), tuple(ct))


@lru_cache(maxsize=256)
def genel_turbin(D: float, H: float, P_mw: float) -> TurbinEgrisi:
    """Kütüphanesi bilinmeyen (OSM komşu) türbin: güç ve CT GenericWindTurbine'den."""
    g = _generic(D, H, P_mw)
    guc = g.power(np.maximum(WS, 0.1)) / 1e6
    ct = g.ct(np.maximum(WS, 0.1))
    guc[WS < 3] = 0.0
    ct[WS < 3] = 0.0
    guc[WS > 25] = 0.0
    ct[WS > 25] = 0.0
    return TurbinEgrisi(f"genel_D{D:.0f}_H{H:.0f}_{P_mw:.2f}MW", D, H, P_mw, tuple(WS), tuple(guc), tuple(ct))
