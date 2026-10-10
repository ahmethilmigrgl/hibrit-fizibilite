"""
Portföy sinerjileri (Faz F2): her kalemin bugünkü değere çevrilmiş parametreleri.

1. İşletme modeli (ölçek ekonomisi): portföy toplam türbin sayısı yeterliyse kendi bakımı (Faz D/E başabaş filosu).
       yıllık tasarruf = Σ türbin · P[kW] · (FSA fiyatı − kendi değişken maliyeti) − organizasyon sabit gideri
                         − bölge üssü × aktif bölge sayısı − kullanılabilirlik kaybı (FSA garantisinin yokluğu)
2. Yedek parça havuzlaması (taban stok, Poisson talep; Sherbrooke METRIC yaklaşımının tek kademeli hali):
       parça kalemi i, talep oranı Λ_i = N · λ_i (değişim / yıl), etkin tedarik süresi L_i = tedarik − vinç mobilizasyonu
       (parça vinç beklerken gelirse ek kayıp yok; Faz D stok modeliyle aynı mantık).
       Stoksuz (S = 0) her talep L_i kadar bekler; S stokla beklenen bekleyen sipariş (EBO) =
       Σ_{x > S} (x − S) · P(Poisson(Λ_i L_i) = x). Yıllık maliyet(S) = günlük gelir × 365 · EBO(S) + S · parça değeri · tutma oranı.
       Ayrı stok: her saha kendi N_j'siyle min_S. Havuz: tek depo, toplam N ile min_S + her talebe depo→saha transfer süresi τ_j.
       Havuz maliyeti N'de içbükey olduğundan MILP için [Nmin, Nmax] aralığında a + b·N + c·Σ N_j τ_j doğrusal yaklaşımı;
       seçilen portföy için kesin değer ayrıca raporlanır.
3. Toplu tedarik: toplam RES gücü eşiklerinde türbin fiyatı indirimi (çerçeve anlaşması; TAHMİN) ve çok sahalı ulaştırma
   modeli (yerli üretici kapasiteleri). Tek saha değerlemesi her bileşeni en ucuz kaynaktan alır; kapasite bağlayıcıysa
   portföyde maliyet artar (negatif sinerji).
Bugünkü değer çarpanı: vergi sonrası, COD ≈ inşaat süresi sonrası 30 yıllık anüite.
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from scipy.stats import poisson

from src.ayarlar import KOK, config_oku, deger


def bd_carpani(cfg: dict) -> float:
    """Yıllık 1 $'ın vergi sonrası bugünkü değeri (inşaat süresi sonrası işletme ömrü boyunca)."""
    r = deger(cfg["finans"]["wacc_reel"])
    vergi = deger(cfg["finans"]["kurumlar_vergisi"])
    N = deger(cfg["proje"]["omur"])
    ins = deger(cfg["proje"]["insaat_suresi"])
    return float(((1 + r) ** -(ins + np.arange(1, N + 1))).sum() * (1 - vergi))


def capex_bd_carpani(cfg: dict) -> float:
    """CAPEX'teki 1 $ düşüşün bugünkü değeri: 1 − amortisman vergi kalkanının bugünkü değeri (RES amortisman süresi)."""
    r = deger(cfg["finans"]["wacc_reel"])
    vergi = deger(cfg["finans"]["kurumlar_vergisi"])
    am = deger(cfg["finans"]["amortisman_suresi"])
    n = int(am["res"] if isinstance(am, dict) else am)
    ins = deger(cfg["proje"]["insaat_suresi"])
    return float(1 - vergi * ((1 + r) ** -(ins + np.arange(1, n + 1))).sum() / n)


@lru_cache(maxsize=1)
def isletme_parametreleri() -> dict:
    cfg = config_oku()
    i = deger(cfg["v3"]["isletme"])
    p = KOK / "data" / "atlas" / "portfoy" / "parametreler.json"
    oz = json.loads(p.read_text()) if p.exists() else {}
    return {
        "fsa_usd_kw": float(i["fsa"]["fiyat_usd_kw_yil"]),
        "kendi_degisken_usd_kw": float(oz.get("kendi_degisken_usd_kw", 10.79)),
        "organizasyon_usd_yil": float(i["kendi"]["organizasyon_sabit_usd_yil"]),
        "bolge_ussu_usd_yil": float(deger(cfg["v3"]["portfoy"])["kendi_bolge_ussu_usd_yil"]),
    }


def _kalemler(cfg: dict) -> list[dict]:
    b = deger(cfg["v3"]["bakim"])
    mob = b["lojistik"]["vinc_mobilizasyon_gun"]
    out = []
    for ad, a in b["alt_sistemler"].items():
        if a.get("stok"):
            out.append(
                {
                    "ad": ad,
                    "lam": float(a["lam_degisim"]),
                    "L_gun": max(0.0, float(a["tedarik_gun"]) - mob),
                    "deger_usd": float(a["maliyet_eur"][2]) * b["eur_usd"],
                }
            )
    return out


def ebo(lam_yil: float, N: float, L_gun: float, S: int) -> float:
    """Beklenen bekleyen sipariş (zaman ortalaması, adet) = Σ_{x>S} (x − S) P(X = x), X ~ Poisson(Λ L)."""
    m = lam_yil * N * L_gun / 365.0
    if m <= 0:
        return 0.0
    x = np.arange(S + 1, int(S + 10 + 10 * m + 10 * np.sqrt(m)) + 1)
    return float(((x - S) * poisson.pmf(x, m)).sum())


def stok_maliyeti(N: float, gelir_gun: float, cfg: dict | None = None, tau_gun: float = 0.0, azami_S: int = 6) -> dict:
    """Yıllık beklenen kayıp gelir + stok tutma (kalem başına en iyi S). tau_gun: depodan sahaya ortalama transfer."""
    cfg = cfg or config_oku()
    tut = deger(cfg["v3"]["bakim"])["stok"]["tutma_orani"]
    top, detay = 0.0, {}
    for k in _kalemler(cfg):
        en = None
        for S in range(azami_S + 1):
            kayip = gelir_gun * (365.0 * ebo(k["lam"], N, k["L_gun"], S) + k["lam"] * N * tau_gun * (S > 0))
            c = kayip + S * k["deger_usd"] * tut
            if en is None or c < en[1]:
                en = (S, c)
        detay[k["ad"]] = {"S": en[0], "maliyet_yil": en[1]}
        top += en[1]
    return {"maliyet_yil": top, "kalemler": detay}


def havuz_dogrusal(gelir_gun_turbin: float, cfg: dict | None = None, N_aralik=(20, 200)) -> dict:
    """
    Ayrı stok maliyeti (türbin başına, küçük saha ≈ S = 0 → N'de doğrusal: κ0) ve havuz maliyetinin doğrusal yaklaşımı
    a + b·N + c·Σ N_j τ_j (τ gün). Gelir günlük ve türbin başına (N ile ölçeklenir).
    """
    cfg = cfg or config_oku()
    k0 = stok_maliyeti(1, gelir_gun_turbin, cfg)["maliyet_yil"]
    Ns = np.arange(N_aralik[0], N_aralik[1] + 1, 10)
    hv = np.array([stok_maliyeti(n, gelir_gun_turbin, cfg)["maliyet_yil"] for n in Ns])
    A = np.c_[np.ones(len(Ns)), Ns]
    a, b = np.linalg.lstsq(A, hv, rcond=None)[0]
    lam_top = sum(k["lam"] for k in _kalemler(cfg))
    return {
        "ayri_turbin_basi_yil": float(k0),
        "havuz_a_yil": float(a),
        "havuz_b_turbin_yil": float(b),
        "havuz_c_turbin_gun_yil": float(gelir_gun_turbin * lam_top),  # her talepte τ gün kayıp (stoktan karşılananlar)
        "egri_N": Ns.tolist(),
        "egri_havuz_yil": hv.tolist(),
    }
