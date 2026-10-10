"""
Hava kısıtlı çalışma pencereleri.

Saatlik göbek hızı (üretim profilinin kalibre hızı) ve vardiya saatleri (TSİ) ile:
    tırmanma/nasel işi: v < tırmanma sınırı ve vardiya içi saatlerde ilerler (iş saati kadar 'uygun saat' birikince biter)
    vinçli kaldırma: v < kaldırma sınırı olan ARDIŞIK 'kaldirma_pencere_h' saatlik vardiya içi pencere gerekir
Birikimli toplamlarla her sorgu O(log n): bir işin bitiş zamanı = birikimli uygun saat sayısının hedefe ulaştığı ilk saat.
Zaman ekseni: proje ömrü boyunca saat (0 = işletme başlangıcı, 1 Ocak 00:00 UTC); yıllar ERA5 hava yıllarından örneklenir.
"""

from __future__ import annotations

import numpy as np

SAAT_YIL = 8760


class HavaZaman:
    def __init__(self, v: np.ndarray, tirmanma: float, vardiya: tuple[int, int], pencere_h: int, kaldirma_limitleri: list[float]):
        n = len(v)
        self.n = n
        tsi = (np.arange(n) + 3) % 24
        self.vardiya = (tsi >= vardiya[0]) & (tsi < vardiya[1])
        ok = (v < tirmanma) & self.vardiya
        self.cum = np.r_[0, np.cumsum(ok)]
        self.pencere_h = pencere_h
        self.sonraki: dict[float, np.ndarray] = {}
        for L in sorted(set(kaldirma_limitleri)):
            okk = ((v < L) & self.vardiya).astype(np.int32)
            ck = np.r_[0, np.cumsum(okk)]
            bas = np.zeros(n + 1, bool)
            m = n - pencere_h + 1
            bas[:m] = (ck[pencere_h : pencere_h + m] - ck[:m]) == pencere_h
            # sonraki[h]: h veya sonrasında başlayan ilk uygun pencere (yoksa n)
            idx = np.where(bas, np.arange(n + 1), n)
            self.sonraki[L] = np.minimum.accumulate(idx[::-1])[::-1]
        vv = np.where(self.vardiya, 1, 0)
        self._var_cum = np.r_[0, np.cumsum(vv)]

    def is_bitir(self, t: float, is_saati: float) -> float:
        """t anından başlayan, tırmanma koşulunda 'is_saati' uygun saat isteyen işin bitiş zamanı."""
        i = min(int(np.ceil(t)), self.n)
        hedef = self.cum[i] + is_saati
        j = int(np.searchsorted(self.cum, hedef))
        return float(min(j, self.n))

    def kaldirma(self, t: float, limit: float) -> float:
        """t'den sonraki ilk uygun kaldırma penceresinin başlangıcı."""
        i = min(int(np.ceil(t)), self.n)
        return float(self.sonraki[limit][i])

    def vardiya_basi(self, t: float) -> float:
        """t veya sonrasındaki ilk vardiya saati."""
        i = min(int(np.ceil(t)), self.n - 1)
        j = int(np.searchsorted(self._var_cum, self._var_cum[i] + 1)) - 1
        return float(min(max(j, i), self.n))


def mevsimsel_bekleme(v_yillar: np.ndarray, tirmanma: float, vardiya, pencere_h: int, limit: float, is_saati: float) -> np.ndarray:
    """
    Ay bazında (12) beklenen hava kaynaklı ek süre [gün]: ayın her günü 08:00'de başlayan vinçli değişim işinin
    (pencere + kalan iş saati) takvim süresi − hava kısıtsız süresi; 10 hava yılı ortalaması. (Arızanın mevsimine göre bekleme.)
    """
    sonuc = np.zeros(12)
    sayac = np.zeros(12)
    gun_ay = np.repeat(np.arange(12), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    for y in range(v_yillar.shape[0]):
        hz = HavaZaman(np.r_[v_yillar[y], v_yillar[(y + 1) % v_yillar.shape[0]]], tirmanma, vardiya, pencere_h, [limit])
        kisitsiz = HavaZaman(np.zeros(2 * SAAT_YIL), 99.0, vardiya, pencere_h, [99.0])
        for d in range(365):
            t = d * 24 + 5  # 08:00 TSİ = 05:00 UTC
            b = hz.kaldirma(t, limit)
            son = hz.is_bitir(b + pencere_h, max(is_saati - pencere_h, 0))
            b0 = kisitsiz.kaldirma(t, 99.0)
            son0 = kisitsiz.is_bitir(b0 + pencere_h, max(is_saati - pencere_h, 0))
            sonuc[gun_ay[d]] += (son - son0) / 24
            sayac[gun_ay[d]] += 1
    return sonuc / np.maximum(sayac, 1)
