"""
Çok senaryolu borç boyutlandırma doğrusal programı (LP).

Kümeler
    k ∈ {1, …, V}   vade içindeki işletme yılları (V: borç vadesi)
    c ∈ C            kredi veren senaryoları (ör. P50, P90-1y, P99-1y)
Parametreler
    CFADS_{c,k}      senaryo c'de yıl k'nın borç servisine esas nakit akışı [nominal USD]
    DSCR_{c,k}       senaryo c'nin yıl k'daki asgari borç servisi karşılama oranı (sözleşmeli payla harmanlanmış)
    i                nominal faiz;  g  azami borç / CAPEX;  CAPEX  nominal yatırım tutarı
Karar değişkenleri
    D ≥ 0            COD'daki borç tutarı
    s_k ≥ 0          yıl k'nın borç servisi (faiz + anapara)
    B_k ≥ 0          yıl k sonundaki borç bakiyesi (B_0 = D, B_V = 0)
Amaç
    max D
Kısıtlar
    (bakiye)    B_k = (1 + i) B_{k−1} − s_k                    ∀k
    (DSCR)      s_k ≤ CFADS_{c,k} / DSCR_{c,k}                 ∀c, k
    (anapara)   s_k ≥ i · B_{k−1}                              ∀k: min_c CFADS_{c,k} > 0  (negatif amortisman yok; isteğe bağlı)
    (kaldıraç)  D ≤ g · CAPEX

Bakiye kısıtları zincirlenince D = Σ_k s_k (1 + i)^−k olur: borç, servislerin bugünkü değeridir. Anapara kısıtı yoksa her
yılın servisi kendi en sıkı DSCR kısıtına dayanır (klasik heykelsi / sculpted geri ödeme). Dual değerler hangi senaryonun hangi
yılda bağladığını ve o kısıtı 1 $ gevşetmenin borcu ne kadar artıracağını verir (bağlayıcı DSCR kısıtında (1 + i)^−k).
Kaldıraç tavanı bağlarsa servis profili orantılı küçültülür (LP homojen olduğundan uygun kalır; v1 borc_boyutla ile aynı kural).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog


@dataclass
class BorcLP:
    borc_nom: float
    servis: np.ndarray  # (N,) nominal, vade sonrası 0
    faiz: np.ndarray
    anapara: np.ndarray
    bakiye: np.ndarray  # yıl sonu
    vade: int
    kaldirac_bagliyor: bool
    anapara_kisiti: bool  # False: kısıtla uygunsuz çıktı, kısıtsız çözüldü
    baglayici: list[dict] = field(default_factory=list)  # yıl başına bağlayan senaryo ve dual değer
    dscr: dict[str, np.ndarray] = field(default_factory=dict)  # senaryo → yıllık DSCR (vade içi)
    durum: str = "optimal"


def boyutla(
    cfads: dict[str, np.ndarray],
    dscr: dict[str, np.ndarray],
    vade: int,
    faiz: float,
    capex_nom: float,
    kaldirac: float,
    anapara_kisiti: bool = True,
) -> BorcLP:
    """cfads, dscr: senaryo adı → (N,) dizi (nominal CFADS ve yıllık asgari DSCR). Birimler USD; LP içinde M$ ölçeklenir."""
    adlar = list(cfads)
    N = len(next(iter(cfads.values())))
    V = int(min(vade, N))
    olcek = 1e6
    cap = {c: np.clip(np.asarray(cfads[c][:V], float), 0, None) / np.asarray(dscr[c][:V], float) / olcek for c in adlar}

    def coz(anapara: bool):
        nv = 1 + 2 * V  # D, s_1..s_V, B_1..B_V
        iD, iS, iB = 0, lambda k: k, lambda k: V + k  # k = 1..V
        A_eq, b_eq = np.zeros((V, nv)), np.zeros(V)
        for k in range(1, V + 1):
            A_eq[k - 1, iB(k)] = 1.0
            A_eq[k - 1, iS(k)] = 1.0
            A_eq[k - 1, iD if k == 1 else iB(k - 1)] = -(1 + faiz)
        satir, b_ub, etiket = [], [], []
        for c in adlar:
            for k in range(1, V + 1):
                a = np.zeros(nv)
                a[iS(k)] = 1.0
                satir.append(a)
                b_ub.append(cap[c][k - 1])
                etiket.append(("dscr", c, k))
        if anapara:
            for k in range(1, V + 1):
                if min(cap[c][k - 1] for c in adlar) <= 0:
                    continue  # CFADS ≤ 0 yılı (ör. batarya yenileme): servis 0, faiz bakiyeye eklenir (kısıt bu yıl uygulanmaz)
                a = np.zeros(nv)
                a[iD if k == 1 else iB(k - 1)] = faiz
                a[iS(k)] = -1.0
                satir.append(a)
                b_ub.append(0.0)
                etiket.append(("anapara", None, k))
        sinir = [(0, None)] * nv
        sinir[iB(V)] = (0, 0)
        cc = np.zeros(nv)
        cc[iD] = -1.0
        r = linprog(cc, A_ub=np.array(satir), b_ub=np.array(b_ub), A_eq=A_eq, b_eq=b_eq, bounds=sinir, method="highs")
        return r, etiket

    kisit = anapara_kisiti
    r, etiket = coz(kisit)
    if r.status != 0 and kisit:  # ör. vade içinde negatif CFADS yılı: anapara kısıtı uygunsuz → kısıtsız
        kisit = False
        r, etiket = coz(False)
    if r.status != 0:
        raise RuntimeError(f"Borç LP'si çözülemedi: {r.message}")
    x = r.x
    D = float(x[0]) * olcek
    s = np.zeros(N)
    s[:V] = x[1 : 1 + V] * olcek
    # Bağlayıcı DSCR kısıtları (dual ≠ 0): yıl başına en sıkı senaryo
    dual = -np.asarray(r.ineqlin.marginals)  # max D: 1 $ gevşetmenin D artışı (≥ 0)
    bag = []
    for k in range(1, V + 1):
        en = min(adlar, key=lambda c: cap[c][k - 1])
        idx = etiket.index(("dscr", en, k))
        bag.append({"yil": k, "senaryo": en, "dual": float(dual[idx]), "servis_tavani": float(cap[en][k - 1] * olcek)})
    tavan = kaldirac * capex_nom
    kaldirac_bag = D > tavan * (1 + 1e-9)
    if kaldirac_bag:
        a = tavan / D
        s *= a
        D = tavan
        for b in bag:
            b["dual"] = 0.0  # tavan bağlarken DSCR kısıtları gevşek
    faiz_y, anapara_y, bakiye = np.zeros(N), np.zeros(N), np.zeros(N)
    B = D
    for k in range(N):
        faiz_y[k] = B * faiz
        anapara_y[k] = s[k] - faiz_y[k]
        B = B - anapara_y[k]
        bakiye[k] = B if abs(B) > 1e-6 * max(D, 1) else 0.0
    oranlar = {c: np.where(s[:V] > 0, np.asarray(cfads[c][:V], float) / np.maximum(s[:V], 1e-9), np.inf) for c in adlar}
    return BorcLP(D, s, faiz_y, anapara_y, bakiye, V, bool(kaldirac_bag), kisit, bag, oranlar)


def metrikler(b: BorcLP, cfads_p50_nom: np.ndarray, faiz: float) -> dict:
    """Kredi metrikleri (P50): asgari/ortalama DSCR, LLCR, PLCR, ortalama ömür."""
    V, D = b.vade, b.borc_nom
    k = np.arange(1, len(cfads_p50_nom) + 1)
    df = (1 + faiz) ** -k
    d = b.dscr.get("P50", next(iter(b.dscr.values())))
    return {
        "borc_nom": D,
        "vade": V,
        "dscr_min_p50": float(np.min(d)) if len(d) else float("nan"),
        "dscr_ort_p50": float(np.mean(d[np.isfinite(d)])) if len(d) else float("nan"),
        "llcr": float((cfads_p50_nom[:V] * df[:V]).sum() / D) if D > 0 else float("nan"),
        "plcr": float((cfads_p50_nom * df).sum() / D) if D > 0 else float("nan"),
        "ortalama_omur": float((k * np.clip(b.anapara, 0, None)).sum() / D) if D > 0 else float("nan"),
    }
