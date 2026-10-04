"""Saat dilimi dönüşümleri: EPİAŞ yerel zaman damgaları → UTC (2016 öncesi yaz saati dahil)."""

import pandas as pd

from src.piyasa.veri import _tam_saatlik, _utc_cevir
from src.uretim.ruzgar import tsi_ay_saat


def _kayit(tarih, saat, deger):
    return {"date": tarih, "hour": f"{saat:02d}:00", "price": deger}


def test_ilkbahar_2016_yer_tutucu_atilir():
    # 27 Mart 2016: yerel 03:00 → 04:00 (UTC+2 → UTC+3). EPİAŞ 24 satır verir; 03:00 etiketli satır yer tutucudur.
    kay = []
    for h in range(24):
        if h < 3:
            kay.append(_kayit(f"2016-03-27T{h:02d}:00:00+02:00", h, 100 + h))
        elif h == 3:
            kay.append(_kayit("2016-03-27T04:00:00+03:00", 3, 0))  # yaşanmamış saat
        else:
            kay.append(_kayit(f"2016-03-27T{h:02d}:00:00+03:00", h, 100 + h))
    df = _utc_cevir(kay, ["price"])
    assert len(df) == 23
    assert (df["price"] > 0).all()
    beklenen = pd.date_range("2016-03-26 22:00", "2016-03-27 20:00", freq="h", tz="UTC")
    assert df.index.equals(beklenen)


def test_sonbahar_2015_eksik_saat_doldurulur():
    # 8 Kasım 2015: yerel 04:00 → 03:00 (UTC+3 → UTC+2). İki kez yaşanan 03:00'ün ilki (00:00 UTC) verilmez.
    kay = [_kayit(f"2015-11-08T{h:02d}:00:00+03:00", h, 100.0 + h) for h in range(3)]
    kay += [_kayit(f"2015-11-08T{h:02d}:00:00+02:00", h, 100.0 + h) for h in range(3, 24)]
    df = _utc_cevir(kay, ["price"])
    assert len(df) == 24
    tam = _tam_saatlik(df, pd.Timestamp("2015-11-07 21:00", tz="UTC"), pd.Timestamp("2015-11-08 21:00", tz="UTC"))
    assert len(tam) == 25
    assert tam["dolduruldu"].sum() == 1
    assert tam.loc[pd.Timestamp("2015-11-08 00:00", tz="UTC"), "dolduruldu"]
    assert tam["price"].notna().all()


def test_2016_sonrasi_sabit_utc3():
    # 30 Ekim 2016: Türkiye artık saat geri almıyor → 24 satır, 24 ardışık UTC saati
    kay = [_kayit(f"2016-10-30T{h:02d}:00:00+03:00", h, 50.0) for h in range(24)]
    df = _utc_cevir(kay, ["price"])
    assert df.index.equals(pd.date_range("2016-10-29 21:00", "2016-10-30 20:00", freq="h", tz="UTC"))


def test_tsi_ay_saat():
    ay, saat = tsi_ay_saat(pd.DatetimeIndex(["2020-01-31 22:00", "2020-06-15 09:00"], tz="UTC"))
    assert list(ay) == [2, 6] and list(saat) == [1, 12]
