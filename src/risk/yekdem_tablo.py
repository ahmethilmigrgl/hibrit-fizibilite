"""YEKDEM moduna özgü işletme tabloları (deşarj da sözleşmeli fiyattan; φ ızgarası 0 / 1)."""
from dataclasses import replace

import numpy as np

YEKDEM_PP = [0.0, 1.0]
YEKDEM_SABIT = {"desarj_sozlesmeli": True, "ppa_fiyat": 55.0}
A_DUSUK = [0.02, 0.05, 0.10]


def yekdem_tablosu(o, t):
    """Doyum ızgaralı (a = 0 … 1) YEKDEM tablosu; t.ppa True olmalı."""
    t = replace(t, ppa=True)
    kw = dict(pp_ozel=YEKDEM_PP, sabit_ek=YEKDEM_SABIT)
    if t.bess_mw < 0.5 or not t.yan_hizmet:
        return o.tablo(t, **kw)
    sifir = o.tablo(replace(t, yan_hizmet=False), **kw)
    dusuk = o.tablo(t, A_ozel=A_DUSUK, **kw)
    ust = o.tablo(t, **kw)
    T = np.concatenate([sifir["T"], dusuk["T"], ust["T"]], axis=4)
    return {**ust, "T": T, "a": np.array([0.0] + A_DUSUK + list(ust["a"]))}
