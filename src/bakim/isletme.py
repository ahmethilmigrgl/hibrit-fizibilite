"""
İşletme modeli (v3 Ö1): mutlak O&M seviyesi ve ortalama kullanılabilirlik buradan gelir; bakım simülasyonu (DES)
kullanılabilirlik dağılımı, stratejiler arası fark, bakım takvimi ve yedek parça kararları için kullanılır.

İki model (config v3.isletme):
  (i)  FSA — üreticiyle tam kapsamlı servis sözleşmesi:
         O&M = FSA fiyatı (türbin planlı + plansız bakım, büyük bileşenler, vinç, yedek parça) + sahip kalemleri
         kullanılabilirlik: zaman bazlı garanti (eksiği tazminatla karşılanır) → E[max(A_sim, A_garanti)]
  (ii) Kendi bakımı:
         O&M = DES türbin bakım maliyeti (ekip, malzeme × (1 + parça primi), vinç, önleyici, CMS, stok)
               + organizasyon sabit gideri / MW (bakım müdürü, mühendislik, depo, araç, eğitim, 24/7 izleme)
               + sahip kalemleri
         kullanılabilirlik: E[A_sim]
Sahip kalemleri (her iki modelde; bakım modelinin kapsamadığı): BOP (trafo merkezi/şalt, saha içi kablo) bakımı, yol ve
saha bakımı, SCADA ve haberleşme, varlık yönetimi ve genel giderler, sahibin saha personeli, beklenmeyen giderler.
Sigorta (CAPEX oranı), arazi kirası, TEİAŞ bedelleri ve söküm finansal modelde ayrı kalemlerdir (burada yok).
"""

from __future__ import annotations

import math

import numpy as np

from src.ayarlar import deger


def ayar(cfg: dict) -> dict:
    return deger(cfg["v3"]["isletme"])


def sahip_usd_kw(cfg: dict) -> float:
    return float(sum(ayar(cfg)["sahip_kalemleri_usd_kw_yil"].values()))


def fsa_usd_kw(cfg: dict) -> float:
    return float(ayar(cfg)["fsa"]["fiyat_usd_kw_yil"])


def kendi_turbin_usd_yil(gider: dict, cfg: dict) -> float:
    """DES gider kalemlerinden (yıllık ortalama, $) kendi bakımının türbin bakım maliyeti; malzemeye parça primi."""
    k = ayar(cfg)["kendi"]
    prim = 1 + k["parca_primi"]
    return float(
        gider["sabit_ekip"]
        + gider["duzeltici_malzeme"] * prim
        + gider["vinc"]
        + gider["onleyici_malzeme"] * prim
        + gider["cms"]
        + gider["stok_tutma"]
    )


def opex(cfg: dict, model: str, MW: float, gider: dict | None = None) -> dict:
    """Yıllık O&M [$/MW-yıl] ve kalemleri [$/kW-yıl]."""
    a = ayar(cfg)
    sahip = {k: float(v) for k, v in a["sahip_kalemleri_usd_kw_yil"].items()}
    if model == "fsa":
        kal = {"fsa": fsa_usd_kw(cfg), **sahip}
    elif model == "kendi":
        if gider is None:
            raise ValueError("Kendi bakımı için DES gider kalemleri gerekli")
        kal = {
            "kendi_turbin_bakimi": kendi_turbin_usd_yil(gider, cfg) / (MW * 1000),
            "organizasyon_sabit": a["kendi"]["organizasyon_sabit_usd_yil"] / (MW * 1000),
            **sahip,
        }
    else:
        raise ValueError(model)
    return {"model": model, "usd_mw_yil": 1000 * sum(kal.values()), "kalemler_usd_kw_yil": kal}


def kullanilabilirlik(cfg: dict, model: str, A_ornek: np.ndarray | None, A_tablo: float | None = None) -> float:
    """FSA: garantinin altı tazmin edilir → E[max(A, A_g)]; kendi: E[A]."""
    g = ayar(cfg)["fsa"]["kullanilabilirlik_garantisi"]
    if A_ornek is None or len(A_ornek) == 0:
        A = A_tablo if A_tablo is not None else g
        return float(max(A, g)) if model == "fsa" else float(A)
    A_ornek = np.asarray(A_ornek, float)
    return float(np.maximum(A_ornek, g).mean()) if model == "fsa" else float(A_ornek.mean())


def basabas_filo(cfg: dict, P_mw: float, kendi_turbin_basina: dict[int, float]) -> dict:
    """
    Kendi bakımının FSA'dan ucuzlaştığı filo büyüklüğü. kendi_turbin_basina: {N: DES türbin bakım maliyeti / türbin [$/yıl]}
    (türbin sayısına göre ekip basamaklarıyla). Sahip kalemleri iki modelde aynı olduğundan karşılaştırmaya girmez.
        maliyet_kendi(N) = N · c(N) + organizasyon sabit gideri;   maliyet_fsa(N) = N · P · FSA fiyatı
    Döndürür: N* (ilk N ki her N' ≥ N için kendi ≤ FSA; ızgara içinde yoksa None) ve eğri; FSA fiyat aralığı için de N*.
    """
    a = ayar(cfg)
    org = a["kendi"]["organizasyon_sabit_usd_yil"]
    Ns = np.array(sorted(kendi_turbin_basina))
    c = np.array([kendi_turbin_basina[n] for n in Ns])
    grid = np.arange(1, int(Ns.max()) + 1)
    c_g = np.interp(grid, Ns, c)

    def ilk(fsa_kw: float) -> int | None:
        fark = grid * c_g + org - grid * P_mw * 1000 * fsa_kw
        ok = fark <= 0
        for i in range(len(grid)):
            if ok[i:].all():
                return int(grid[i])
        return None

    egri = [
        {"N": int(n), "kendi_usd_kw": float((n * cc + org) / (n * P_mw * 1000)), "fsa_usd_kw": fsa_usd_kw(cfg)}
        for n, cc in zip(grid, c_g)
        if n in set(Ns.tolist()) | {5, 10, 15, 20, 25, 30, 40, 50, 75, 100}
    ]
    lo, hi = a["fsa"]["aralik_usd_kw_yil"]
    return {
        "N_basabas": ilk(fsa_usd_kw(cfg)),
        "N_basabas_fsa_dusuk": ilk(lo),
        "N_basabas_fsa_yuksek": ilk(hi),
        "egri": egri,
        "kendi_degisken_usd_kw": float(c[-1] / (P_mw * 1000)),
        "organizasyon_sabit_usd_yil": org,
        "yorum_N_esik": math.ceil(org / max(P_mw * 1000 * fsa_usd_kw(cfg) - c[-1], 1e-9))
        if P_mw * 1000 * fsa_usd_kw(cfg) > c[-1]
        else None,
    }
