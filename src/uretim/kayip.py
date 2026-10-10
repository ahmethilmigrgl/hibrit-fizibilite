"""
Açık RES kayıp tablosu (v3 Ö2) — IEC 61400-15 kategorileri.

Profil (motor, v3): KF(t) = brüt(K·v_t) · (1 − λ) · η_iz(t) · A
    λ (taban kayıp) = 1 − 0,88 / ((1 − W_ref) · A_k)       (göreli kural; config v3.kayip; yerlesim.analiz.taban_kayip)
Atlas katsayısı K, kalibre santrallerin GERÇEK kayıplarını içerdiği için sahaya özgü olmayan kategoriler (elektrik, türbin
performansı, çevresel) atlas referansıyla aynı alınır ve göreli kuralda sadeleşir; sahaya özgü olanlar (iz, kullanılabilirlik)
modelden gelir. λ'yı bu kategorilere ayırınca kalan pay "atlas kalibrasyon farkı"dır: v2'nin varsaydığı %12 ile kategorilerin
gerçek toplamı arasındaki fark (K'ya sapma olarak gömülü).
Kesinti (sistem kaynaklı) burada yoktur: finansal modelde ayrı (Aşama 7). Bozunma (türbin yaşlanması) finansal modelde yıllık.
"""

from __future__ import annotations

from src.ayarlar import deger

KATEGORI_AD = {
    "iz": ("İz (wake)", "Wake"),
    "kullanilabilirlik": ("Kullanılabilirlik", "Availability"),
    "elektrik": ("Elektrik", "Electrical"),
    "turbin_performansi": ("Türbin performansı (güç eğrisi, histerezis, yaw)", "Turbine performance"),
    "cevre_kirlenme_erozyon": ("Çevresel: kanat kirlenmesi/erozyon", "Environmental: soiling/erosion"),
    "cevre_sicaklik_yildirim": ("Çevresel: sıcaklık kapatması, yıldırım", "Environmental: temperature, lightning"),
    "cevre_buzlanma": ("Çevresel: buzlanma", "Environmental: icing"),
    "kalibrasyon_farki": ("Atlas kalibrasyon farkı (K'ya gömülü sapma)", "Atlas calibration residual"),
}


def tablo(cfg: dict, W_saha: float | None, A_saha: float | None) -> dict:
    """
    Kayıp tablosu: her kategori için saha değeri ve atlas referansı; uygulanan toplam ve v2 toplu %12 ile karşılaştırma.
    W_saha / A_saha None ise atlas referansı (tipik santral) kullanılır.
    """
    k = deger(cfg["v3"]["kayip"])
    t = k["tablo"]
    W_ref, A_k = k["iz_referansi"], k["kalibrasyon_kullanilabilirligi"]
    lam = 1.0 - (1.0 - k["lumped_v2"]) / ((1.0 - W_ref) * A_k)
    genel = 1.0
    for ad in ("elektrik", "turbin_performansi", "cevre_kirlenme_erozyon", "cevre_sicaklik_yildirim", "cevre_buzlanma"):
        genel *= 1.0 - t[ad]
    kalib = 1.0 - (1.0 - lam) / genel
    W = W_ref if W_saha is None else W_saha
    A = A_k if A_saha is None else A_saha
    satir = [
        {
            "kategori": "iz",
            "saha": W,
            "atlas_referansi": W_ref,
            "kaynak": "PyWake + yerleşim (sahaya özgü)" if W_saha is not None else "atlas ortalaması",
        },
        {
            "kategori": "kullanilabilirlik",
            "saha": 1 - A,
            "atlas_referansi": 1 - A_k,
            "kaynak": "işletme modeli / DES" if A_saha is not None else "kalibrasyon (kısa duruşlar)",
        },
        *[{"kategori": ad, "saha": t[ad], "atlas_referansi": t[ad], "kaynak": "Lee & Fields 2021 (config v3.kayip.tablo)"} for ad in t],
        {"kategori": "kalibrasyon_farki", "saha": kalib, "atlas_referansi": kalib, "kaynak": "0,88 / Π(kategoriler) ile kalan"},
    ]
    carp = lambda alan: _carpim(satir, alan)
    uygulanan = 1.0 - (1.0 - lam) * (1.0 - W) * A
    return {
        "satirlar": satir,
        "taban_kayip": lam,
        "toplam_saha": 1.0 - carp("saha"),
        "toplam_atlas_referansi": 1.0 - carp("atlas_referansi"),
        "uygulanan": uygulanan,
        "kategoriler_toplami_kalibrasyon_haric": 1.0 - carp("saha") / (1.0 - kalib),
        "lumped_v2": k["lumped_v2"],
        "tutarli": abs((1.0 - carp("saha")) - uygulanan) < 1e-12,
    }


def _carpim(satir: list[dict], alan: str) -> float:
    p = 1.0
    for s in satir:
        p *= 1.0 - s[alan]
    return p
