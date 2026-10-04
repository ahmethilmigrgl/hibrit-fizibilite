"""Takvim modeli: CPM ileri/geri geçiş, bolluk ve kritik yol küçük bir elle hesaplanmış ağda doğru mu?"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("tk", Path(__file__).resolve().parents[1] / "src" / "07_takvim.py")
tk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tk)


def ag():
    # A(3) → C(4) → E(2);  B(5) → D(1) → E;  C ve D'nin ikisi de E'den önce
    return pd.DataFrame(
        {
            "ad": list("ABCDE"),
            "a": [2, 4, 3, 1, 1],
            "m": [3, 5, 4, 1, 2],
            "b": [4, 6, 5, 1, 3],
            "onc": [[], [], ["A"], ["B"], ["C", "D"]],
            "gecikme": 0.0,
        },
        index=list("ABCDE"),
    )


def test_cpm_el_hesabi():
    cp, _ = tk.cpm(ag())
    # A-C-E = 3+4+2 = 9; B-D-E = 5+1+2 = 8 → proje 9 ay, kritik yol A-C-E, B ve D'de 1 ay bolluk
    assert cp.loc["E", "EF"] == 9
    assert list(cp.index[cp["Kritik"]]) == ["A", "C", "E"]
    assert cp.loc["B", "Bolluk"] == 1 and cp.loc["D", "Bolluk"] == 1


def test_monte_carlo_kritiklik():
    a = ag()
    sira = tk.topolojik(a)
    _sure, _ES, EF, bel = tk.monte_carlo(a, sira, 5000, 0)
    assert np.all(EF["E"] >= np.maximum(EF["C"], EF["D"]))  # öncelikler sağlanıyor
    yol = tk.kritik_iz(bel, "E", 5000)
    assert yol["E"].mean() == 1.0  # son aktivite her zaman kritik
    assert 0.0 < yol["B"].mean() < 1.0 and yol["A"].mean() > yol["B"].mean()  # iki yol da kritik olabiliyor
    assert np.allclose(yol["A"], yol["C"])  # aynı zincirde aynı kritiklik
