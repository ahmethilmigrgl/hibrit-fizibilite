"""
Temsilî günler: bir yılın (veya birkaç fiyat-yılının) günlerini benzerliklerine göre K kümeye ayırıp
her kümeyi tek bir GERÇEK günle (medoid) ve küme büyüklüğü kadar ağırlıkla temsil eder.

Neden? Kapasite MILP'inde 8.760 (×2) saatlik zaman boyutu modeli büyütür. Günler fiyat + GES + RES
profillerine göre kümelenirse ~24 günle yıl yaklaşık temsil edilir.

Yöntem:
    1) Her gün için öznitelik vektörü: [fiyat_24 / ortalama fiyat, GES_kf_24, RES_kf_24]  (72 boyut)
    2) k-means (k-means++ başlangıç, birkaç tekrar, en düşük küme içi kareler toplamı)
    3) Her kümede merkeze en yakın gerçek gün = medoid (ortalama alınmaz → uç saatler korunur)
    4) Ağırlık = kümedeki gün sayısı (yıl başına normalize edilir)

Sınırlar: günler arası bağlantı kopar (batarya her temsilî günün sonunda başladığı SOC'ye döner;
çok günlük depolama değeri kaybolur), uç günler kümelerde sönümlenebilir.
"""

from __future__ import annotations

import numpy as np


def _kmeans(X: np.ndarray, k: int, tekrar: int = 10, iter_: int = 100, tohum: int = 0) -> tuple[np.ndarray, np.ndarray, float]:
    rng = np.random.default_rng(tohum)
    en_iyi = (None, None, np.inf)
    for _ in range(tekrar):
        # k-means++ başlangıç
        merkez = [X[rng.integers(len(X))]]
        for _ in range(1, k):
            d2 = np.min(((X[:, None, :] - np.array(merkez)[None]) ** 2).sum(-1), axis=1)
            merkez.append(X[rng.choice(len(X), p=d2 / d2.sum())])
        C = np.array(merkez)
        for _ in range(iter_):
            etiket = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
            C_yeni = np.array([X[etiket == j].mean(0) if np.any(etiket == j) else C[j] for j in range(k)])
            if np.allclose(C_yeni, C):
                break
            C = C_yeni
        sse = float(((X - C[etiket]) ** 2).sum())
        if sse < en_iyi[2]:
            en_iyi = (etiket, C, sse)
    return en_iyi


def temsili_gunler(fiyatlar: list[np.ndarray], ges: np.ndarray, res: np.ndarray, k: int,
                   tohum: int = 0) -> dict:
    """
    fiyatlar: her fiyat-yılı için 8760'lık dizi (ör. iki şekil yılı); ges, res: 8760'lık KF dizileri.
    Döndürür: {"gunler": [(fiyat_yili_indeksi, gun_indeksi)], "agirlik": yıl başına gün sayısı,
               "etiket": tüm günlerin küme etiketi, "sse": ...}
    """
    gun_sayisi = 365
    ozellik, kaynak = [], []
    for i, p in enumerate(fiyatlar):
        P = p[:gun_sayisi * 24].reshape(gun_sayisi, 24)
        G = ges[:gun_sayisi * 24].reshape(gun_sayisi, 24)
        R = res[:gun_sayisi * 24].reshape(gun_sayisi, 24)
        ozellik.append(np.hstack([P / p.mean(), G, R]))
        kaynak += [(i, d) for d in range(gun_sayisi)]
    X = np.vstack(ozellik)
    etiket, C, sse = _kmeans(X, k, tohum=tohum)
    gunler, agirlik = [], []
    for j in range(k):
        uyeler = np.where(etiket == j)[0]
        if len(uyeler) == 0:
            continue
        medoid = uyeler[np.argmin(((X[uyeler] - C[j]) ** 2).sum(1))]
        gunler.append(kaynak[medoid])
        agirlik.append(len(uyeler) / len(fiyatlar))       # yıl başına eşdeğer gün sayısı
    return {"gunler": gunler, "agirlik": np.array(agirlik), "etiket": etiket, "sse": sse}


def segmentleri_kur(fiyatlar: list[np.ndarray], ges: np.ndarray, res: np.ndarray, k: int | None, Segment,
                    yanlar: list[np.ndarray] | None = None) -> list:
    """
    Kapasite modeli için segment listesi.
        k = None → tam yıl: her fiyat-yılı bir segment (ağırlık 1/len(fiyatlar))
        k = sayı → temsilî günler + MOMENT EŞLEŞTİRME: temsilî günlerin ağırlıklı ortalama fiyatı ve
                   GES/RES kapasite faktörleri tam yılın ortalamalarına ölçeklenir (gün içi şekil korunur).
                   Medoid günler tek başına yıllık enerjiyi ve fiyat seviyesini korumaz; bu ölçekleme
                   amaç fonksiyonundaki sistematik sapmayı giderir.
    """
    if k is None:
        return [Segment(p, ges, res, 1 / len(fiyatlar), None if yanlar is None else yanlar[i]) for i, p in enumerate(fiyatlar)]
    tg = temsili_gunler(fiyatlar, ges, res, k)
    dilim = lambda a, d: a[d * 24:(d + 1) * 24]
    P = np.array([dilim(fiyatlar[s], d) for s, d in tg["gunler"]])
    G = np.array([dilim(ges, d) for s, d in tg["gunler"]])
    R = np.array([dilim(res, d) for s, d in tg["gunler"]])
    w = tg["agirlik"] / tg["agirlik"].sum()
    hedef_p = np.mean([f.mean() for f in fiyatlar])
    aP = hedef_p / (w @ P.mean(1))
    aG = ges.mean() / (w @ G.mean(1))
    aR = res.mean() / (w @ R.mean(1))
    Y = None if yanlar is None else [dilim(yanlar[s], d) for s, d in tg["gunler"]]
    # Ağırlık = yıl başına eşdeğer gün sayısı → Σ ağırlık × 24 saat = 8760
    segs = [Segment(P[i] * aP, np.clip(G[i] * aG, 0, 1), np.clip(R[i] * aR, 0, 1), float(tg["agirlik"][i]),
                    None if Y is None else Y[i]) for i in range(len(w))]
    return segs
