"""
Kritik yedek parça stoku — baz stok (S−1, S) politikasının simülasyon tabanlı optimizasyonu.

Politika: başlangıçta S parça; her çekişte (değişim) hemen bir yenisi sipariş edilir, L gün sonra stoğa girer
(bekleyen talepler FIFO). Klasik özdeşlik: k'ıncı talep, (k − S)'inci talebin siparişiyle karşılanır:
    parça hazır_k = 0                       (k ≤ S)
    parça hazır_k = d_{k−S} + L              (k > S)   (d: talep zamanları, sıralı)
Parça yüzünden ek duruş = max(0, hazır_k − max(t_arıza,k, d_k + vinç mobilizasyonu)) — vinç mobilizasyonu zaten
beklenirken gelen parça ek kayıp yaratmaz. Kayıp gelir: o aralıkta türbinin beklenen saatlik geliri (yılın saati profili).
Maliyet(S) = E[kayıp gelir] + S × parça değeri × tutma oranı;  S* = argmin, S ∈ {0..azami}.
Talep akışları DES ile AYNI örnekleme yordamından (olaylari_ornekle) ve aynı tohumlarla üretilir: tüm S değerleri aynı
talep gerçekleşmelerinde değerlendirilir (ortak rastgele sayılar → farklar düşük varyanslı).
Faz F genişlemesi (havuzlama): birden çok sahanın talep akışları birleştirilip tek stok ve sahalar arası transfer süresiyle
aynı fonksiyona verilebilir (talepler parametresi saha etiketli liste).
"""

from __future__ import annotations

import numpy as np

from src.bakim.des import Girdi, olaylari_ornekle
from src.bakim.hava import SAAT_YIL


def talepler(g: Girdi, R: int, tohum: int) -> dict[str, list[list[tuple]]]:
    """Kalem → tekrar başına [(talep zamanı, arıza zamanı, türbin)] listesi (DES ile aynı tohumlar)."""
    out: dict = {ad: [] for ad, a in g.p["alt_sistemler"].items() if a["stok"]}
    for r in range(R):
        rng = np.random.default_rng(tohum + r)
        rng.integers(0, g.v_yillar.shape[0], g.omur)  # DES'teki hava yılı çekilişiyle aynı sıra
        ol = olaylari_ornekle(g, rng)
        for ad in out:
            out[ad].append(sorted((tes if tes is not None else t, t, i) for t, i, a, k, tes in ol if a == ad and k == 2))
    return out


def bekleme_kaybi(
    akis: list[tuple], S: int, L_h: float, mob_h: float, gelir_cum: np.ndarray, pay: np.ndarray, havuz_transfer_h: float = 0.0
) -> tuple[float, int]:
    """Tek tekrarın toplam kayıp geliri ve bekleyen talep sayısı."""
    d = np.array([x[0] for x in akis])
    kayip, bekleyen = 0.0, 0
    for k, (dk, tf, i) in enumerate(akis):
        hazir = 0.0 if k < S else d[k - S] + L_h
        hazir += havuz_transfer_h
        bas = max(tf, dk + mob_h)
        if hazir > bas:
            bekleyen += 1
            kayip += pay[i] * _aralik_geliri(gelir_cum, bas, hazir)
    return kayip, bekleyen


def _aralik_geliri(cum: np.ndarray, a: float, b: float) -> float:
    """Yılın saati döngüsel beklenen gelir profilinin [a, b) toplamı (cum: 8760 + 1 birikimli)."""
    tam, ka, kb = SAAT_YIL, a % SAAT_YIL, b % SAAT_YIL
    yil = int(b // tam) - int(a // tam)
    ia, ib = np.interp(ka, np.arange(tam + 1), cum), np.interp(kb, np.arange(tam + 1), cum)
    return float(yil * cum[-1] + ib - ia)


def optimize(g: Girdi, R: int, tohum: int) -> dict:
    p = g.p
    E = g.kf_yillar.mean(0) * g.P_mw * g.fiyat  # yılın saati beklenen gelir (ortalama paylı türbin)
    cum = np.r_[0.0, np.cumsum(E)]
    mob = p["lojistik"]["vinc_mobilizasyon_gun"] * 24
    akis = talepler(g, R, tohum)
    sonuc = {}
    for ad, liste in akis.items():
        a = p["alt_sistemler"][ad]
        deger_ = a["maliyet_eur"][2] * p["eur_usd"]
        satir = []
        for S in range(p["stok"]["azami"] + 1):
            k = [bekleme_kaybi(x, S, a["tedarik_gun"] * 24, mob, cum, g.pay) for x in liste]
            kayip = np.array([z[0] for z in k]) / g.omur
            talep = sum(len(x) for x in liste)
            tutma = S * deger_ * p["stok"]["tutma_orani"]
            satir.append(
                {
                    "S": S,
                    "kayip_gelir_yil": float(kayip.mean()),
                    "kayip_se": float(kayip.std(ddof=1) / np.sqrt(len(kayip))),
                    "tutma_yil": tutma,
                    "toplam_yil": float(kayip.mean() + tutma),
                    "bekleyen_oran": float(sum(z[1] for z in k) / max(talep, 1)),
                    "talep_yil": talep / (R * g.omur),
                }
            )
        en_iyi = min(satir, key=lambda x: x["toplam_yil"])
        sonuc[ad] = {"tablo": satir, "S": en_iyi["S"], "parca_degeri": deger_, "tedarik_gun": a["tedarik_gun"]}
    return sonuc
