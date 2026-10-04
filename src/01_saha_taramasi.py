"""
Aşama 1 — Saha taraması

Aday sahaların her biri için (config.yaml → aday_sahalar, yillar_tarama):
    • GES ve RES yıllık kapasite faktörü
    • Saatlik GES–RES korelasyonu (düşük/negatif = daha iyi tamamlayıcılık)
    • 1 MW GES + 1 MW RES, 1 MW ortak bağlantı: satılabilir MWh/yıl ve kesinti (curtailment) oranı
    • GES doğrulaması: model vs PVGIS'in kendi PV hesabı

Çıktılar: outputs/01_saha_taramasi/ (tablo CSV + grafikler)
          data/processed/tarama_profilleri.parquet (saatlik kapasite faktörleri, UTC)

Çalıştırma: .venv/bin/python src/01_saha_taramasi.py
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.uretim import gunes, hibrit, ruzgar

# Grafik renkleri (doğrulanmış kategorik paletin ilk iki slotu)
RENK_GES, RENK_RES = "#eb6834", "#2a78d6"
MUREKKEP, IKINCIL, IZGARA = "#0b0b0b", "#52514e", "#e4e3df"

CIKTI = CIKTILAR / "01_saha_taramasi"


def saha_verisini_hazirla(kod: str, saha: dict, cfg: dict) -> dict:
    """Bir sahanın indirmelerini yapar (önbellekli) ve kapasite faktörlerini hesaplar."""
    y1, y2 = deger(cfg["uretim"]["yillar_tarama"])
    cg, cr = cfg["uretim"]["gunes"], cfg["uretim"]["ruzgar"]
    lat, lon = saha["enlem"], saha["boylam"]

    isinim, meta = gunes.pvgis_isinim_indir(kod, lat, lon, y1, y2, cg)
    pvcalc, _ = gunes.pvgis_pv_indir(kod, lat, lon, y1, y2, cg)
    era5 = ruzgar.era5_coklu_yil(kod, lat, lon, y1, y2, cr)

    ges_kf = gunes.gunes_kapasite_faktoru(isinim, meta, cg)
    res_kf, ara = ruzgar.ruzgar_kapasite_faktoru(era5, cr)
    res_kf_alt, _ = ruzgar.ruzgar_kapasite_faktoru(era5, cr, deger(cr["turbin_duyarlilik"]))

    # --- GES doğrulama köprüsü (kWh/kWp/yıl)
    yil_sayisi = y2 - y1 + 1
    pvgis_kwh_kwp = pvcalc["P"].sum() / 1000 / yil_sayisi  # W → kWh
    # (a) PVGIS ile aynı tanım: DC/AC=1, kırpma yok, %14 toplam kayıp (inverter dahil)
    esdeger = gunes.gunes_kapasite_faktoru(
        isinim, meta, cg, dc_ac_orani=1.0, sistem_kaybi=deger(cg["dogrulama_kaybi_pvgis"]), inverter_yok=True
    )
    model_esdeger_kwh_kwp = esdeger.sum() / yil_sayisi  # MWh/MWp = kWh/kWp
    # (b) Proje tasarımı: DC/AC=1.2, %14 kayıp + %96 inverter + kırpma
    dc_ac = deger(cg["dc_ac_orani"])
    model_tasarim_kwh_kwp = ges_kf.sum() / dc_ac / yil_sayisi

    return {
        "kod": kod,
        "saha": saha,
        "meta": meta,
        "ges_kf": ges_kf,
        "res_kf": res_kf,
        "res_kf_alt": res_kf_alt,
        "ara": ara,
        "era5_grid": (float(era5["latitude"].iloc[0]), float(era5["longitude"].iloc[0])),
        "pvgis_kwh_kwp": pvgis_kwh_kwp,
        "model_esdeger_kwh_kwp": model_esdeger_kwh_kwp,
        "model_tasarim_kwh_kwp": model_tasarim_kwh_kwp,
        "kirpma": gunes.kirpma_orani(isinim, meta, cg),
    }


def ozet_satiri(s: dict) -> dict:
    """Bir sahanın sonuçlarını tablo satırına çevirir."""
    df = pd.concat([s["ges_kf"], s["res_kf"]], axis=1, join="inner").dropna()
    h = hibrit.ortak_baglanti(df["ges_kf"], df["res_kf"])
    gunluk = df.resample("D").mean()
    return {
        "Saha": s["saha"]["ad"],
        "Enlem": s["saha"]["enlem"],
        "Boylam": s["saha"]["boylam"],
        "ERA5 grid": f"{s['era5_grid'][0]:.2f}, {s['era5_grid'][1]:.2f}",
        "Optimum eğim [°]": gunes.optimum_egim(s["meta"]),
        "GES KF [%]": 100 * df["ges_kf"].mean(),
        "GES kWh/kWp (model)": s["model_tasarim_kwh_kwp"],
        "GES kırpma kaybı [%]": 100 * s["kirpma"],
        "PVGIS kWh/kWp": s["pvgis_kwh_kwp"],
        "Model (PVGIS-eşdeğer) kWh/kWp": s["model_esdeger_kwh_kwp"],
        "Doğrulama farkı [%]": 100 * (s["model_esdeger_kwh_kwp"] / s["pvgis_kwh_kwp"] - 1),
        "100 m ort. hız [m/s]": s["ara"]["v100"].mean(),
        "120 m ort. hız [m/s]": s["ara"]["v_gobek"].mean(),
        "Medyan kayma üssü": s["ara"]["alfa"].median(),
        "Ort. hava yoğunluğu [kg/m³]": s["ara"]["yogunluk"].mean(),
        "RES KF E-141 [%]": 100 * df["res_kf"].mean(),
        "RES KF E-126 [%]": 100 * s["res_kf_alt"].mean(),
        "Saatlik korelasyon": df["ges_kf"].corr(df["res_kf"]),
        "Günlük korelasyon": gunluk["ges_kf"].corr(gunluk["res_kf"]),
        "Hibrit satılan [MWh/yıl/MW bağlantı]": h["satilan_mwh_yil"],
        "Hibrit kesinti [%]": 100 * h["kesinti_orani"],
        "Bağlantı kullanım oranı [%]": 100 * h["baglanti_kf"],
    }


# ---------------------------------------------------------------------------
# Grafikler
# ---------------------------------------------------------------------------
def _eksen_sade(ax):
    for k in ("top", "right"):
        ax.spines[k].set_visible(False)
    ax.spines["left"].set_color(IZGARA)
    ax.spines["bottom"].set_color(IZGARA)
    ax.tick_params(colors=IKINCIL, labelsize=9)
    ax.grid(axis="y", color=IZGARA, linewidth=0.8)
    ax.set_axisbelow(True)


def grafik_kf_karsilastirma(tablo: pd.DataFrame):
    """Sahalara göre GES ve RES kapasite faktörü (gruplu çubuk)."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(tablo))
    w = 0.36
    for i, (sutun, renk, etiket) in enumerate([("GES KF [%]", RENK_GES, "GES"), ("RES KF E-141 [%]", RENK_RES, "RES (E-141)")]):
        cubuk = ax.bar(x + (i - 0.5) * (w + 0.02), tablo[sutun], w, color=renk, label=etiket)
        ax.bar_label(cubuk, fmt="%.1f", fontsize=8, color=IKINCIL, padding=2)
    ax.set_xticks(x, tablo["Saha"])
    ax.set_ylabel("Kapasite faktörü [%]", color=IKINCIL)
    ax.set_title("Yıllık ortalama kapasite faktörü (AC, kayıplar sonrası)", loc="left", color=MUREKKEP, fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _eksen_sade(ax)
    fig.tight_layout()
    fig.savefig(CIKTI / "kapasite_faktorleri.png", dpi=150)
    plt.close(fig)


def grafik_hibrit(tablo: pd.DataFrame):
    """Ortak bağlantı göstergeleri: satılan enerji ve kesinti oranı (iki ayrı panel, tek eksen)."""
    fig, axs = plt.subplots(1, 3, figsize=(12, 4))
    x = np.arange(len(tablo))
    for ax, sutun, baslik, fmt in [
        (axs[0], "Saatlik korelasyon", "Saatlik GES–RES korelasyonu\n(düşük = daha iyi tamamlayıcılık)", "%.2f"),
        (axs[1], "Hibrit satılan [MWh/yıl/MW bağlantı]", "1 MW GES + 1 MW RES, 1 MW bağlantı:\nsatılabilir enerji [MWh/yıl]", "%.0f"),
        (axs[2], "Hibrit kesinti [%]", "Aynı düzen: kesilen üretim\n[% toplam üretim]", "%.1f"),
    ]:
        cubuk = ax.bar(x, tablo[sutun], 0.6, color=IKINCIL)
        ax.bar_label(cubuk, fmt=fmt, fontsize=8, color=IKINCIL, padding=2)
        ax.set_xticks(x, tablo["Saha"], rotation=20, ha="right")
        ax.set_title(baslik, loc="left", color=MUREKKEP, fontsize=10)
        ax.axhline(0, color=IKINCIL, linewidth=0.8)
        _eksen_sade(ax)
    fig.tight_layout()
    fig.savefig(CIKTI / "hibrit_gostergeleri.png", dpi=150)
    plt.close(fig)


def grafik_gun_ici_profil(sahalar: list[dict]):
    """Her saha için ortalama gün içi profil (UTC ve TSİ saat) — tamamlayıcılığın görsel kanıtı."""
    fig, axs = plt.subplots(1, len(sahalar), figsize=(13, 3.6), sharey=True)
    for ax, s in zip(axs, sahalar):
        df = pd.concat([s["ges_kf"], s["res_kf"]], axis=1, join="inner")
        profil = df.groupby(df.index.hour).mean()
        tsi = (profil.index + 3) % 24  # Türkiye saati = UTC+3
        profil = profil.set_axis(tsi).sort_index()
        ax.plot(profil.index, profil["ges_kf"], color=RENK_GES, lw=2, label="GES")
        ax.plot(profil.index, profil["res_kf"], color=RENK_RES, lw=2, label="RES")
        ax.set_title(s["saha"]["ad"], loc="left", color=MUREKKEP, fontsize=10)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xlabel("Saat (TSİ)", color=IKINCIL, fontsize=9)
        _eksen_sade(ax)
    axs[0].set_ylabel("Ortalama kapasite faktörü", color=IKINCIL)
    axs[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Ortalama gün içi üretim profili", x=0.01, ha="left", color=MUREKKEP, fontsize=11)
    fig.tight_layout()
    fig.savefig(CIKTI / "gun_ici_profil.png", dpi=150)
    plt.close(fig)


def grafik_aylik_profil(sahalar: list[dict]):
    """Her saha için aylık ortalama kapasite faktörü — mevsimsel tamamlayıcılık."""
    fig, axs = plt.subplots(1, len(sahalar), figsize=(13, 3.6), sharey=True)
    aylar = ["O", "Ş", "M", "N", "M", "H", "T", "A", "E", "E", "K", "A"]
    for ax, s in zip(axs, sahalar):
        df = pd.concat([s["ges_kf"], s["res_kf"]], axis=1, join="inner")
        profil = df.groupby(df.index.month).mean()
        ax.plot(profil.index, profil["ges_kf"], color=RENK_GES, lw=2, marker="o", ms=4, label="GES")
        ax.plot(profil.index, profil["res_kf"], color=RENK_RES, lw=2, marker="o", ms=4, label="RES")
        ax.set_xticks(range(1, 13), aylar)
        ax.set_title(s["saha"]["ad"], loc="left", color=MUREKKEP, fontsize=10)
        _eksen_sade(ax)
    axs[0].set_ylabel("Ortalama kapasite faktörü", color=IKINCIL)
    axs[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Aylık ortalama kapasite faktörü", x=0.01, ha="left", color=MUREKKEP, fontsize=11)
    fig.tight_layout()
    fig.savefig(CIKTI / "aylik_profil.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    cfg = config_oku()
    CIKTI.mkdir(parents=True, exist_ok=True)
    ISLENMIS_VERI.mkdir(parents=True, exist_ok=True)
    adaylar = cfg["aday_sahalar"]

    print(f"Saha taraması — yıllar {deger(cfg['uretim']['yillar_tarama'])}, {len(adaylar)} saha")
    print("İndirmeler (önbellekte yoksa) paralel yapılıyor...")
    with ThreadPoolExecutor(max_workers=4) as havuz:
        sahalar = list(havuz.map(lambda kv: saha_verisini_hazirla(kv[0], kv[1], cfg), adaylar.items()))

    tablo = pd.DataFrame([ozet_satiri(s) for s in sahalar])
    tablo.to_csv(CIKTI / "saha_karsilastirma.csv", index=False, encoding="utf-8-sig")

    # Saatlik profiller (UTC) — uzun formatta tek parquet
    profiller = pd.concat([pd.concat([s["ges_kf"], s["res_kf"]], axis=1, join="inner").assign(saha=s["kod"]) for s in sahalar])
    profiller.index.name = "zaman_utc"
    profiller.to_parquet(ISLENMIS_VERI / "tarama_profilleri.parquet")

    grafik_kf_karsilastirma(tablo)
    grafik_hibrit(tablo)
    grafik_gun_ici_profil(sahalar)
    grafik_aylik_profil(sahalar)

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda v: f"{v:.2f}")
    print("\n=== Saha karşılaştırması ===")
    print(tablo.set_index("Saha").T.to_string())
    print(f"\nKaydedildi: {CIKTI.relative_to(CIKTI.parents[1])}/")


if __name__ == "__main__":
    main()
