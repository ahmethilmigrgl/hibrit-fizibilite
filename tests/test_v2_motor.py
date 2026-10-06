"""v2 analiz motoru: varsayım doğrulama, önbellek anahtarı/LRU, eşzamanlılık ve zaman aşımı, hızlı tarama duman testi."""

import threading
import time

import pytest

from src.motor import onbellek
from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi, dogrula


def test_varsayilanlar_gecerli():
    assert dogrula(KullaniciVarsayimlari()) == []


@pytest.mark.parametrize(
    "degisiklik, kod",
    [
        ({"baglanti_mw": -5}, "sinir"),
        ({"wacc": 0.9}, "sinir"),
        ({"fiyat_senaryosu": "uçuk"}, "fiyat"),
        ({"proje_asamasi": "hayal"}, "asama"),
        ({"gelir_yapilari": ("bitcoin",)}, "gelir"),
        ({"azami_res_mw": 0, "azami_ges_mw": 0}, "kapasite"),
        ({"sabit_tasarim": {"res_mw": -1}}, "tasarim"),
    ],
)
def test_hatali_varsayimlar_iki_dilli_hata(degisiklik, kod):
    with pytest.raises(MotorHatasi) as e:
        dogrula(KullaniciVarsayimlari(**degisiklik))
    assert e.value.kod == kod and e.value.tr and e.value.en


def test_dusuk_res_siniri_uyari_verir():
    u = dogrula(KullaniciVarsayimlari(baglanti_mw=50, azami_res_mw=10))
    assert [x.kod for x in u] == ["res_sinir"]


def test_onbellek_anahtari_001_derece_ve_varsayim():
    v = KullaniciVarsayimlari().sozluk()
    a = onbellek.anahtar(39.791, 26.334, "hizli", v, "s1")
    assert a == onbellek.anahtar(39.789, 26.3349, "hizli", v, "s1")  # aynı 0,01° hücre
    assert a != onbellek.anahtar(39.80, 26.33, "hizli", v, "s1")
    assert a != onbellek.anahtar(39.791, 26.334, "tam", v, "s1")
    assert a != onbellek.anahtar(39.791, 26.334, "hizli", {**v, "wacc": 0.09}, "s1")
    assert a != onbellek.anahtar(39.791, 26.334, "hizli", v, "s2")  # veri sürümü


def test_onbellek_lru_temizlik(tmp_path, monkeypatch):
    monkeypatch.setattr(onbellek, "KLASOR", tmp_path)
    for i in range(3):
        (tmp_path / f"k{i}.pkl").write_bytes(b"x" * 400_000)
        time.sleep(0.02)
    assert onbellek.oku("k0") is None  # bozuk kayıt: None döner ve silinir
    assert not (tmp_path / "k0.pkl").exists()
    onbellek.yaz("yeni", {"a": 1})  # varsayılan sınır büyük: silme yok
    assert onbellek.oku("yeni") == {"a": 1}
    assert onbellek.temizle(azami_mb=0.5) >= 1  # en eski erişilenler gider
    assert (tmp_path / "yeni.pkl").exists()


def test_tek_tam_analiz_sira_ve_zaman_asimi(tmp_path, monkeypatch):
    monkeypatch.setattr(onbellek, "KLASOR", tmp_path)
    t0 = time.monotonic()
    with pytest.raises(onbellek.ZamanAsimi) as e:
        onbellek.tek_tam_analiz(lambda: time.sleep(1.5), zaman_asimi=0.3)
    assert e.value.kod == "zaman" and time.monotonic() - t0 < 1.0  # mesaj hemen döner
    # Arka plandaki iş bitene kadar ikinci analiz sıraya girer, sonra çalışır.
    sonuc = onbellek.tek_tam_analiz(lambda: 42, zaman_asimi=5)
    assert sonuc == 42 and time.monotonic() - t0 >= 1.4

    olaylar = []

    def is_(ad):
        olaylar.append(("bas", ad))
        time.sleep(0.2)
        olaylar.append(("son", ad))

    ts = [threading.Thread(target=onbellek.tek_tam_analiz, args=(lambda a=a: is_(a), 5)) for a in "ab"]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert [o[0] for o in olaylar] == ["bas", "son", "bas", "son"]  # üst üste binmez


@pytest.mark.veri
def test_hizli_tarama_duman():
    from src.kaynaklar import gwa

    if not gwa.PAKET.exists():
        pytest.skip("data/atlas yok")
    from src.motor import analiz_et

    s = analiz_et({"kod": "ezine", "enlem": 39.79, "boylam": 26.33}, "hizli", KullaniciVarsayimlari())
    assert 0.15 < s.ozet["res_kf"] < 0.5 and s.ozet["en_iyi_tasarim"]
    assert s.nedenler and s.json()


def test_deniz_noktasi_reddedilir():
    from src.kaynaklar import gwa, sinirlar

    if not (gwa.PAKET.exists() and sinirlar.PAKET.exists()):
        pytest.skip("data/atlas yok")
    from src.motor import analiz_et

    with pytest.raises(MotorHatasi) as e:
        analiz_et({"kod": "deniz", "enlem": 40.2, "boylam": 25.3}, "hizli", KullaniciVarsayimlari())
    assert e.value.kod == "kara_disi"
