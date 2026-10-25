"""
Enerji verimi belirsizlik bütçesi ve P değerleri (P50, P75, P90, P95, P99; 1 ve 10 yıllık).

Bileşenler yıllık enerjiye göre bağıl standart sapmadır (σ / P50) ve iki türlüdür:
    yıllık  — her yıl yeniden çekilir, T yıllık ortalamada σ/√T'ye iner (yıllar arası değişkenlik, yıllık kullanılabilirlik)
    kalıcı  — projenin ömrü boyunca sabit kalan tahmin hatası (referans dönem, iklim temsiliyeti, model/kalibrasyon, veri seti)

    σ(T)² = Σ_yıllık σ² / T + Σ_kalıcı σ²             (bileşenler bağımsız)
    P_x(T) = P50 − z_x · σ(T) · P50                   (normal yaklaşım; z_0,90 = 1,2816)

Hibrit (RES + GES) MWh cinsinden birleştirilir: yıllar arası değişkenlik ve referans dönem terimleri iki teknoloji arasında
veriden ölçülen ρ ile ilişkili, model hataları bağımsızdır:
    Var = (E_r σ_r)² + (E_g σ_g)² + 2 ρ E_r E_g σ_r σ_g     (ilişkili terimler)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.ayarlar import deger


def z(p: float) -> float:
    """P_x için tek taraflı normal katsayı (P90 → 1,2816)."""
    return float(norm.ppf(p))


def bilesenler(yillik: pd.DataFrame, sigma_res_model: float | None, cfg: dict) -> dict[str, list[dict]]:
    """
    yillik: hava yılı başına MWh/MW (sütunlar res_kf, ges_kf; uretim_ozeti çıktısı). sigma_res_model: atlas güveninden RES model
    belirsizliği (None → kalibre v1 modu). Döndürür: teknoloji → [{ad, tur, sigma, iliskili}] (iliskili: teknolojiler arası ρ uygulanır).
    """
    v = deger(cfg["v4"]["verim"])
    n = len(yillik)
    sonuc = {}
    for tek, sut in (("res", "res_kf"), ("ges", "ges_kf")):
        s = yillik[sut].to_numpy(float)
        iav = float(s.std(ddof=1) / s.mean()) if s.mean() > 0 else 0.0
        b = [
            {"ad": "yillar_arasi", "tur": "yillik", "sigma": iav, "iliskili": True},
            {"ad": "referans_donem", "tur": "kalici", "sigma": iav / math.sqrt(n), "iliskili": True},
            {"ad": "iklim_temsiliyeti", "tur": "kalici", "sigma": v["iklim_temsiliyeti"], "iliskili": True},
        ]
        if tek == "res":
            sm = v["res_kalibre_model"] if sigma_res_model is None else sigma_res_model
            b += [
                {"ad": "model_kalibrasyon", "tur": "kalici", "sigma": float(sm), "iliskili": False},
                {"ad": "kullanilabilirlik", "tur": "yillik", "sigma": v["kullanilabilirlik_yillik"], "iliskili": False},
            ]
        else:
            b += [
                {"ad": "isinim_veri_seti", "tur": "kalici", "sigma": v["gunes_veri_seti"], "iliskili": False},
                {"ad": "pv_model", "tur": "kalici", "sigma": v["gunes_model"], "iliskili": False},
                {"ad": "kullanilabilirlik", "tur": "yillik", "sigma": v["gunes_kullanilabilirlik_yillik"], "iliskili": False},
            ]
        sonuc[tek] = b
    return sonuc


def butce(yillik: pd.DataFrame, res_mw: float, ges_mw: float, sigma_res_model: float | None, cfg: dict) -> dict:
    """
    Tasarımın (res_mw, ges_mw) brüt üretimi için P değerleri. Brüt: şebeke kısıtı ve batarya öncesi (kesinti simülasyon
    P değerlerinde, src/finansman/motor.py). Döndürür: bileşen tablosu, ρ, P tablosu (MWh) ve P_x/P50 oranları.
    """
    v = deger(cfg["v4"]["verim"])
    bl = bilesenler(yillik, sigma_res_model, cfg)
    E = {"res": res_mw * float(yillik["res_kf"].mean()), "ges": ges_mw * float(yillik["ges_kf"].mean())}
    rho = float(np.corrcoef(yillik["res_kf"], yillik["ges_kf"])[0, 1]) if len(yillik) > 2 else 0.0
    if not np.isfinite(rho):
        rho = 0.0
    P50 = E["res"] + E["ges"]

    def varyans(T: int) -> float:
        """Hibrit yıllık enerjinin T yıllık ortalamasının varyansı (MWh²)."""
        top = 0.0
        for ad in {b["ad"] for t in bl for b in bl[t]}:
            br = next((b for b in bl["res"] if b["ad"] == ad), None)
            bg = next((b for b in bl["ges"] if b["ad"] == ad), None)
            tur = (br or bg)["tur"]
            bol = T if tur == "yillik" else 1
            sr = E["res"] * br["sigma"] if br else 0.0
            sg = E["ges"] * bg["sigma"] if bg else 0.0
            capraz = 2 * rho * sr * sg if (br and bg and br["iliskili"] and bg["iliskili"]) else 0.0
            top += (sr**2 + sg**2 + capraz) / bol
        return top

    satirlar = []
    for tek in ("res", "ges"):
        if E[tek] <= 0:
            continue
        for b in bl[tek]:
            satirlar.append({"teknoloji": tek, **b, "mwh": E[tek] * b["sigma"]})
    tablo = pd.DataFrame(satirlar)
    p_tablo = []
    for T in v["ufuklar"]:
        sig = math.sqrt(varyans(T)) / P50 if P50 > 0 else 0.0
        for p in v["p_seviyeleri"]:
            p_tablo.append(
                {"ufuk": T, "p": p, "ad": f"P{round(100 * p)}", "sigma": sig, "mwh": P50 * (1 - z(p) * sig), "oran": 1 - z(p) * sig}
            )
    return {"P50_mwh": P50, "E": E, "rho_iav": rho, "bilesenler": tablo, "p": pd.DataFrame(p_tablo)}


def oran(b: dict, p: float, ufuk: int) -> float:
    """Bütçeden P_x(ufuk)/P50 oranı (tablo dışı p için normal yaklaşımla yeniden hesaplanır)."""
    t = b["p"]
    s = t[(t["ufuk"] == ufuk)]
    if len(s) == 0:
        raise ValueError(f"ufuk {ufuk} bütçede yok")
    eslesen = s[np.isclose(s["p"], p)]
    if len(eslesen):
        return float(eslesen["oran"].iloc[0])
    return float(1 - z(p) * s["sigma"].iloc[0])


def simulasyon_p(enerji: np.ndarray, p_seviyeleri: list[float]) -> dict[str, float]:
    """Simüle edilmiş enerji örneklerinden ampirik P değerleri: P_x = (1 − x) yüzdeliği (P90 = %10'luk dilim)."""
    return {f"P{round(100 * p)}": float(np.quantile(enerji, 1 - p)) for p in p_seviyeleri}
