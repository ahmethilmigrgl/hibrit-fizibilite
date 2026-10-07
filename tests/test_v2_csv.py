"""CSV bütünlüğü: Türkçe ondalık virgül içeren metin alanları tırnaklı olmalı (sütun kayması olmasın) ve Vaka sayfasındaki
karar yolculuğu tablosu TR ve EN modunda doğru hücreleri göstermeli."""

import csv
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DOSYALAR = sorted([*KOK.glob("results/*.csv"), *KOK.glob("data/atlas/**/*.csv")])


@pytest.mark.parametrize("yol", DOSYALAR, ids=lambda p: str(p.relative_to(KOK)))
def test_csv_alan_sayisi_tutarli(yol):
    satirlar = [r for r in csv.reader(yol.open(encoding="utf-8-sig")) if r]
    n = len(satirlar[0])
    bozuk = [i + 1 for i, r in enumerate(satirlar) if len(r) != n]
    assert not bozuk, f"{yol.name}: başlık {n} alan, bozuk satırlar {bozuk[:5]}"


def test_karar_yolculugu_tr_en():
    from streamlit.testing.v1 import AppTest

    for dil, adim, degisiklik, oneri in [
        ("TR", "Aşama 4", "Deterministik optimum: yalnız RES 58,8 MW", "Yatırım yapılamaz"),
        ("EN", "Stage 4", "Deterministic optimum: wind only 58.8 MW", "Not investable"),
    ]:
        at = AppTest.from_file(str(KOK / "uygulama" / "sayfa_vaka.py"), default_timeout=120)
        at.session_state["dil"] = dil
        at.run()
        assert not at.exception
        df = at.dataframe[0].value
        assert df.shape == (7, 4)
        ilk = df.iloc[0].tolist()
        assert ilk[0] == adim and ilk[1] == degisiklik and ilk[3] == oneri
        assert abs(float(df.iloc[0, 2]) + 1.6) < 1e-9 and abs(float(df.iloc[5, 2]) - 1.5) < 1e-9
