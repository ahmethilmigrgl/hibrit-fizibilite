"""v2 saha parametreleri: konum, tarife bölgesi, türbin seçimi, GWA düzeltmesi, aktarım kuralının temel davranışı."""

import numpy as np
import pytest

from src.kaynaklar import gwa, sinirlar

paket_var = pytest.mark.skipif(not (gwa.PAKET.exists() and sinirlar.PAKET.exists()), reason="data/atlas paketleri yok")


@paket_var
def test_konum_ve_kara_kontrolu():
    from src.saha import saha_olustur

    s = saha_olustur("t", 39.79, 26.33)
    assert (s.il, s.ilce) == ("Çanakkale", "Ezine")
    with pytest.raises(ValueError):
        saha_olustur("deniz", 40.2, 25.3)  # Ege denizi
    with pytest.raises(ValueError):
        saha_olustur("kibris", 35.2, 33.4)  # Türkiye karası dışı


@paket_var
def test_tarife_bolgesi_ve_bedel():
    from src.saha import saha_olustur, tarife_bolgesi, teias_bedelleri

    assert tarife_bolgesi(saha_olustur("e", 39.79, 26.33)) == 2
    assert tarife_bolgesi(saha_olustur("h", 37.57, 43.74)) == 15  # Hakkâri (şapkalı ad)
    kap, ene = teias_bedelleri(saha_olustur("e", 39.79, 26.33))
    assert abs(kap - 156234.30 / 45.0) < 1e-6 and abs(ene - 170.39 / 45.0) < 1e-9


@paket_var
def test_turbin_secimi_monoton():
    from src.saha import Saha, turbin_sec

    # kullanıcı türbini verirse o kullanılır
    assert turbin_sec(Saha("t", 39.79, 26.33, turbin="E-126/4200", gobek=100))["turbin"] == "E-126/4200"
    t = turbin_sec(Saha("t", 37.72, 33.55))
    assert t["otomatik"] and t["turbin"] == "E-141/4200" and t["gobek"] == 135  # Karapınar ~5 m/s → düşük rüzgâr sınıfı


@paket_var
def test_gwa_duzeltme_sinirli():
    v = gwa.nokta(39.79, 26.33)["ws_ort"]
    assert np.isclose(gwa.duzeltme_katsayisi(39.79, 26.33, v), 1.0)
    assert gwa.duzeltme_katsayisi(39.79, 26.33, v / 10) == 3.2
