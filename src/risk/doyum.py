"""
SFK (sekonder frekans kontrol) kapasite fiyatının doyum (saturation) modeli.

Arz-talep yaklaşımı (yıl t):
    D_t = D_2026 · (1 + g)^(t − 2026)                     SFK ihtiyacı [MW]
    B_t = θ · Kurulu_t                                     SFK'ya teklif veren batarya [MW]
    x_t = B_t / D_t                                        doyum oranı
    Arz eğrisi: bataryalar fırsat maliyetiyle (c_b) teklif verir; kalan ihtiyacı geleneksel santraller
    (hidro/gaz) karşılar ve bugünkü fiyatı (p_0) onlar belirler. Batarya payı arttıkça marjinal
    geleneksel teklif aşağı kayar (doğrusal arz eğrisi):
        p_t = p_0                                  x_t ≤ x_0
        p_t = c_b + (p_0 − c_b) · (x_1 − x_t)/(x_1 − x_0)    x_0 < x_t < x_1
        p_t = c_b                                  x_t ≥ x_1   (yalnızca bataryalar rekabet eder)
    Model çarpanı a_t = p_t / p_0 (2026 seviyesi = 1) — işletme tablosunun yan hizmet boyutu.

Kalibrasyon (config.yaml → stres_testi): İngiltere DC (x ≈ 2'de fiyat −%80-90), Almanya FCR
(x ≈ 1,1'de yıllık gelir −%45; x ≈ 3'te doymuş).
Senaryo "katilamama": TEİAŞ hibrit tesisteki bataryayı SFK'ya kabul etmez → a_t = 0.
"""

from __future__ import annotations

import numpy as np

from src.ayarlar import deger

SENARYO_ADLARI = {"yavas": "Yavaş doyum", "baz": "Baz doyum", "hizli": "Hızlı doyum", "katilamama": "SFK'ya katılamama"}


def kurulu_yol(noktalar: dict, yillar: np.ndarray, kayma: float = 0.0) -> np.ndarray:
    """Kurulu batarya [MW]: çapa yılları arasında log-doğrusal, son çapadan sonra sabit; takvim 'kayma' yıl kayar."""
    xs = np.array(sorted(noktalar)) + kayma
    ys = np.log(np.array([noktalar[k] for k in sorted(noktalar)], float))
    return np.exp(np.interp(yillar, xs, ys))


def sfk_carpani(yillar: np.ndarray, kurulu: np.ndarray, st: dict, theta: float, firsat_oran: float) -> np.ndarray:
    """Doyum oranından SFK fiyat çarpanı (2026 = 1)."""
    D = deger(st["sfk_ihtiyaci"]) * (1 + deger(st["ihtiyac_buyume"])) ** (yillar - 2026)
    x = theta * kurulu / D
    x0, x1 = deger(st["doyum_baslangic"]), deger(st["doyum_tam"])
    oran = np.clip((x1 - x) / (x1 - x0), 0.0, 1.0)
    return firsat_oran + (1 - firsat_oran) * oran


def deterministik_yol(cfg: dict, senaryo: str, yillar: np.ndarray, firsat_oran: float) -> np.ndarray:
    """Senaryonun merkezî yolu (θ orta nokta, kayma 0)."""
    st = cfg["stres_testi"]
    if senaryo == "katilamama":
        return np.zeros(len(yillar))
    sc = deger(st["senaryolar"])[senaryo]
    theta = float(np.mean(deger(st["sfk_uygun_pay"])))
    return sfk_carpani(yillar, kurulu_yol(sc["kurulu_mw"], yillar), st, theta, firsat_oran)


def ornekle_doyum(cfg: dict, n: int, yillar: np.ndarray, firsat_oran: float, tohum: int) -> dict:
    """
    Her simülasyona olasılıklarla bir senaryo atanır; senaryo içinde takvim kayması, θ ve fırsat maliyeti belirsiz.
    Döndürür: a (n × N), senaryo (n, str), suruculer.
    """
    st = cfg["stres_testi"]
    rng = np.random.default_rng(tohum + 1000)
    sc = deger(st["senaryolar"])
    adlar = list(sc)
    olas = np.array([sc[k]["olasilik"] for k in adlar]); olas = olas / olas.sum()
    secim = rng.choice(len(adlar), size=n, p=olas)
    kayma = rng.uniform(*deger(st["zaman_kaymasi"]), n)
    theta = rng.uniform(*deger(st["sfk_uygun_pay"]), n)
    fc = firsat_oran * rng.uniform(*deger(st["firsat_maliyeti_carpani"]), n)
    a = np.zeros((n, len(yillar)))
    for i in range(n):
        ad = adlar[secim[i]]
        if ad != "katilamama":
            a[i] = sfk_carpani(yillar, kurulu_yol(sc[ad]["kurulu_mw"], yillar, kayma[i]), st, theta[i], fc[i])
    return {"a": a, "senaryo": np.array(adlar)[secim], "adlar": adlar,
            "suruculer": {"Doyum senaryosu": secim.astype(float), "Doyum takvim kayması": kayma,
                          "SFK'ya uygun batarya payı": theta, "Fırsat maliyeti tabanı": fc}}
