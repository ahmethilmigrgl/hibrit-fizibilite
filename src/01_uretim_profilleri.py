"""
Aşama 1 — Seçilen saha (config.yaml → saha) için 10 yıllık üretim profilleri

Adımlar:
    1) 2014–2023 saatlik GES ve RES kapasite faktörleri (UTC) → data/processed/<kod>_profiller_<y1>_<y2>.parquet
    2) Yıllık üretim, değişkenlik ve P50/P90 (1 MW GES, 1 MW RES, 1+1 MW / 1 MW bağlantı hibrit)
    3) GES doğrulaması (10 yıl): model vs PVGIS PV hesabı
    4) Grafikler → outputs/01_uretim_modeli/

config.yaml'da bir varsayım değişince (ör. ruzgar_hiz_kalibrasyon_katsayisi) bu script
yeniden çalıştırılır; ham veriler önbellekten okunduğu için indirme yapılmaz.

Çalıştırma: .venv/bin/python src/01_uretim_profilleri.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.uretim import degiskenlik, gunes
from src.uretim.profil import saha_profilleri

CIKTI = CIKTILAR / "01_uretim_modeli"
TSI_FARK = 3  # Türkiye saati = UTC+3 (7 Eylül 2016'dan beri sabit; bkz. docs)
AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


# ---------------------------------------------------------------------------
# Hesaplamalar
# ---------------------------------------------------------------------------
def hibrit_sutunlari(df: pd.DataFrame) -> pd.DataFrame:
    """1 MW GES + 1 MW RES, 1 MW ortak bağlantı: toplam üretim, satılan ve kesilen [MW]."""
    df = df.copy()
    df["hibrit_toplam"] = df["ges_kf"] + df["res_kf"]
    df["hibrit_satilan"] = df["hibrit_toplam"].clip(upper=1.0)
    df["hibrit_kesilen"] = df["hibrit_toplam"] - df["hibrit_satilan"]
    return df


def degiskenlik_tablolari(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Yıllık tablo ve P50/P90 özet tablosu."""
    yillik = degiskenlik.yillik_uretim(df, ["ges_kf", "res_kf", "res_kf_e126", "hibrit_toplam", "hibrit_satilan", "hibrit_kesilen"])
    yillik_tablo = pd.DataFrame(
        {
            "GES KF [%]": 100 * yillik["ges_kf"] / 8760,
            "GES [MWh/MW]": yillik["ges_kf"],
            "RES KF [%]": 100 * yillik["res_kf"] / 8760,
            "RES [MWh/MW]": yillik["res_kf"],
            "RES KF E-126 [%]": 100 * yillik["res_kf_e126"] / 8760,
            "Hibrit satılan [MWh]": yillik["hibrit_satilan"],
            "Hibrit kesinti [%]": 100 * yillik["hibrit_kesilen"] / yillik["hibrit_toplam"],
            "Ort. 120 m hız [m/s]": df["v_gobek_ham"].groupby(df.index.year).mean(),
        }
    )
    ozet = pd.DataFrame(
        {
            "1 MW GES": degiskenlik.p50_p90(yillik["ges_kf"]),
            "1 MW RES": degiskenlik.p50_p90(yillik["res_kf"]),
            "1+1 MW, sınırsız bağlantı": degiskenlik.p50_p90(yillik["hibrit_toplam"]),
            "1+1 MW / 1 MW bağlantı": degiskenlik.p50_p90(yillik["hibrit_satilan"]),
        }
    )
    return yillik_tablo, ozet


def pvgis_dogrulama(kod, saha, y1, y2, cfg) -> dict:
    """10 yıllık GES doğrulama köprüsü [kWh/kWp/yıl]."""
    cg = cfg["uretim"]["gunes"]
    isinim, meta = gunes.pvgis_isinim_indir(kod, saha["enlem"], saha["boylam"], y1, y2, cg)
    pvcalc, _ = gunes.pvgis_pv_indir(kod, saha["enlem"], saha["boylam"], y1, y2, cg)
    n = y2 - y1 + 1
    pvgis = pvcalc["P"].sum() / 1000 / n
    esdeger = (
        gunes.gunes_kapasite_faktoru(
            isinim, meta, cg, dc_ac_orani=1.0, sistem_kaybi=deger(cg["dogrulama_kaybi_pvgis"]), inverter_yok=True
        ).sum()
        / n
    )
    dc_ac = deger(cg["dc_ac_orani"])
    kirpmasiz = gunes.gunes_kapasite_faktoru(isinim, meta, cg, kirpma_kaybi_uygula=False).sum() / n / dc_ac
    tasarim = gunes.gunes_kapasite_faktoru(isinim, meta, cg).sum() / n / dc_ac
    return {
        "PVGIS pvcalculation (%14 kayıp, inverter dahil)": pvgis,
        "Model, PVGIS-eşdeğer tanım": esdeger,
        "Fark (eşdeğer / PVGIS − 1) [%]": 100 * (esdeger / pvgis - 1),
        "Model, proje tasarımı (ek kırpma kaybı öncesi)": kirpmasiz,
        "Model, proje tasarımı (%1 kırpma kaybı sonrası)": tasarim,
        "Saatlik modelin hesapladığı kırpma [%]": 100 * gunes.kirpma_orani(isinim, meta, cg),
    }


# ---------------------------------------------------------------------------
# Grafikler
# ---------------------------------------------------------------------------
def grafik_aylik(df: pd.DataFrame, y1: int, y2: int):
    """Aylık ortalama KF; gölge = yıllar arası en düşük–en yüksek aralığı."""
    aylik = df[["ges_kf", "res_kf"]].groupby([df.index.year, df.index.month]).mean()
    aylik.index.names = ["yil", "ay"]
    ort = aylik.groupby("ay").mean()
    alt, ust = aylik.groupby("ay").min(), aylik.groupby("ay").max()

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    x = np.arange(1, 13)
    for sutun, renk, ad in [("ges_kf", g.RENK_GES, "GES"), ("res_kf", g.RENK_RES, "RES")]:
        ax.fill_between(x, 100 * alt[sutun], 100 * ust[sutun], color=renk, alpha=0.15, lw=0)
        ax.plot(x, 100 * ort[sutun], color=renk, lw=2, marker="o", ms=5, markeredgecolor="white", markeredgewidth=1.5)
        ax.text(12.25, 100 * ort[sutun].iloc[-1], ad, color=g.MUREKKEP, va="center", fontsize=9)
    ax.set_xticks(x, AYLAR)
    ax.set_xlim(0.6, 12.9)
    ax.set_ylim(0, None)
    ax.set_ylabel("Kapasite faktörü [%] (AC, kayıplar sonrası)")
    g.eksen_sade(ax)
    g.baslik(
        fig,
        "Ezine: güneş yazın, rüzgâr kışın ve Ağustos'ta (meltem) güçlü",
        f"Aylık ortalama kapasite faktörü (çizgi: {y1}–{y2} ortalaması; gölge: yıllar arası en düşük–en yüksek ay)",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    g.kaynak_notu(fig)
    fig.savefig(CIKTI / "aylik_kapasite_faktoru.png")
    plt.close(fig)


def grafik_isi_haritasi(df: pd.DataFrame, y1: int, y2: int):
    """Ay × saat (TSİ) ortalama KF ısı haritası; her teknoloji kendi tek renkli skalasında."""
    saat_tsi = (df.index.hour + TSI_FARK) % 24
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, sutun, cmap, ad in [(axs[0], "ges_kf", "Oranges", "GES"), (axs[1], "res_kf", "Blues", "RES")]:
        tablo = (100 * df[sutun]).groupby([df.index.month, saat_tsi]).mean().unstack()
        im = ax.imshow(tablo.values, aspect="auto", cmap=cmap, origin="upper", vmin=0)
        ax.set_yticks(range(12), AYLAR)
        ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
        ax.set_xlabel("Saat (TSİ = UTC+3)")
        ax.set_title(f"{ad} — ortalama kapasite faktörü [%]", loc="left")
        for k in ax.spines.values():
            k.set_visible(False)
        cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
        cb.outline.set_visible(False)
        cb.ax.tick_params(colors=g.IKINCIL, labelsize=8)
    g.baslik(
        fig,
        "Günün ve yılın hangi saatlerinde üretim var?",
        f"Ay × saat ortalama kapasite faktörü, {y1}–{y2}. Rüzgârın öğle sonrası (13:00 TSİ) kırılması ERA5 kaynaklıdır (bkz. docs).",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig)
    fig.savefig(CIKTI / "ay_saat_isi_haritasi.png")
    plt.close(fig)


def grafik_yillik(yillik: pd.DataFrame, ozet: pd.DataFrame):
    """Yıllık KF çubukları + P50 (ampirik medyan) ve P90 (normal) çizgileri."""
    paneller = [
        ("GES KF [%]", "1 MW GES", g.RENK_GES, "GES"),
        ("RES KF [%]", "1 MW RES", g.RENK_RES, "RES"),
        (None, "1+1 MW / 1 MW bağlantı", g.RENK_HIBRIT, "Hibrit: bağlantı kullanım oranı"),
    ]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4), sharey=True)
    for ax, (sutun, ozet_sutun, renk, ad) in zip(axs, paneller):
        seri = yillik[sutun] if sutun else 100 * yillik["Hibrit satılan [MWh]"] / 8760
        ax.bar(seri.index, seri.values, 0.7, color=renk)
        p50 = 100 * ozet.loc["P50 (ampirik medyan)", ozet_sutun] / 8760
        p90 = 100 * ozet.loc["P90 (normal: ort − 1.282σ)", ozet_sutun] / 8760
        x0, x1 = seri.index.min() - 0.45, seri.index.max() + 0.45
        for deger_, etiket, stil, hiza in [(p50, "P50", "-", "bottom"), (p90, "P90", "--", "top")]:
            ax.hlines(deger_, x0, x1, color=g.MUREKKEP, lw=1.2, ls=stil)
            ax.text(x1 + 0.15, deger_, f"{etiket} %{deger_:.1f}", va=hiza, fontsize=8, color=g.MUREKKEP)
        ax.set_title(ad, loc="left")
        ax.set_xticks(seri.index, [f"'{str(y)[2:]}" for y in seri.index])
        ax.set_xlim(seri.index.min() - 0.6, seri.index.max() + 2.4)
        g.eksen_sade(ax)
    axs[0].set_ylabel("Yıllık kapasite faktörü [%]")
    g.baslik(
        fig,
        "Yıldan yıla üretim: rüzgâr güneşten çok daha oynak",
        "Yıllık kapasite faktörü. P50 = 10 yılın medyanı; P90 = ortalama − 1,282σ (normal dağılım varsayımı). "
        "Hibrit paneli: satılan enerji / (1 MW × 8760 h).",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig)
    fig.savefig(CIKTI / "yillik_kapasite_faktoru.png")
    plt.close(fig)


def grafik_sure_egrisi(df: pd.DataFrame, y1: int, y2: int):
    """Süre eğrileri; x ekseni yıla ölçeklenmiş saat (tüm yıllar birlikte sıralanır)."""
    n = len(df)
    x = np.arange(n) * 8760 / n
    sirali = {k: np.sort(df[k].values)[::-1] for k in ["ges_kf", "res_kf", "hibrit_toplam"]}
    kesinti = 100 * df["hibrit_kesilen"].sum() / df["hibrit_toplam"].sum()
    kesinti_saat = (df["hibrit_toplam"] > 1).mean() * 8760

    fig, ax = plt.subplots(figsize=(9, 4.8))
    h = sirali["hibrit_toplam"]
    ax.fill_between(x, 1.0, h, where=h > 1.0, color=g.RENK_HIBRIT, alpha=0.35, lw=0, label=f"Kesilen üretim (%{kesinti:.1f})")
    ax.plot(x, h, color=g.RENK_HIBRIT, lw=2, label="1 MW GES + 1 MW RES toplamı")
    ax.plot(x, sirali["res_kf"], color=g.RENK_RES, lw=2, label="1 MW RES")
    ax.plot(x, sirali["ges_kf"], color=g.RENK_GES, lw=2, label="1 MW GES")
    ax.axhline(1.0, color=g.MUREKKEP, lw=1.2, ls="--")
    ax.text(8760, 1.03, "1 MW şebeke bağlantısı", ha="right", va="bottom", fontsize=8, color=g.MUREKKEP)
    saat_metni = f"{kesinti_saat:,.0f}".replace(",", ".")
    ax.annotate(
        f"Yılda ~{saat_metni} saat\nbağlantı yetersiz",
        xy=(kesinti_saat * 0.5, 1.15),
        xytext=(1500, 1.55),
        fontsize=8,
        color=g.IKINCIL,
        arrowprops=dict(arrowstyle="-", color=g.SOLUK, lw=0.8),
    )
    ax.set_xlim(0, 8760)
    ax.set_ylim(0, 1.85)
    ax.set_xticks(range(0, 8761, 1460))
    ax.set_xlabel("Yılda bu değere eşit ya da üstünde geçen saat [h/yıl]")
    ax.set_ylabel("Üretim [MW]")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 0.92))
    g.eksen_sade(ax, izgara="both")
    g.baslik(
        fig,
        f"Bağlantı yılda ~{saat_metni} saat yetersiz, ama kesilen enerji yalnızca %{kesinti:.1f}",
        f"Süre eğrileri: saatlik üretim büyükten küçüğe sıralı, {y1}–{y2} (yıla ölçeklenmiş).",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig)
    fig.savefig(CIKTI / "sure_egrileri.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    cfg = config_oku()
    kod = deger(cfg["saha"]["kod"])
    saha = cfg["aday_sahalar"][kod]
    y1, y2 = deger(cfg["uretim"]["yillar_tam"])
    CIKTI.mkdir(parents=True, exist_ok=True)

    print(f"Saha: {saha['ad']} ({saha['enlem']}, {saha['boylam']}), yıllar {y1}–{y2}")
    cr = cfg["uretim"]["ruzgar"]
    yontem = deger(cr["ruzgar_kalibrasyon_yontemi"])
    kalib = (
        f"ay × saat matrisi ({deger(cr['k_matris_dosyasi'])})"
        if yontem == "ay_saat"
        else f"sabit k = {deger(cr['ruzgar_hiz_kalibrasyon_katsayisi'])}"
    )
    print(
        f"RES kalibrasyonu: {kalib} | zaman hizası: {deger(cr['zaman_hizasi'])} | "
        f"GES ek kırpma kaybı: {deger(cfg['uretim']['gunes']['kirpma_kaybi']):.1%}"
    )

    # 1) Profiller
    df, bilgi = saha_profilleri(kod, saha["enlem"], saha["boylam"], y1, y2, cfg)
    print(
        f"Saat sayısı: {len(df)}, eksik: {bilgi['eksik_saat']}, tekrar eden: {bilgi['tekrar_eden_saat']}, "
        f"ERA5 grid: {bilgi['era5_grid']}, optimum eğim: {gunes.optimum_egim(bilgi['meta'])}°"
    )
    dosya = ISLENMIS_VERI / f"{kod.split('_')[-1]}_profiller_{y1}_{y2}.parquet"
    df.reset_index().to_parquet(dosya, index=False)
    print(f"Kaydedildi: {dosya.relative_to(ISLENMIS_VERI.parents[1])}")

    # 2) Değişkenlik ve P50/P90
    df = hibrit_sutunlari(df)
    yillik, ozet = degiskenlik_tablolari(df)
    yillik.to_csv(CIKTI / "yillik_uretim.csv", encoding="utf-8-sig", float_format="%.3f")
    ozet.to_csv(CIKTI / "p50_p90_ozet.csv", encoding="utf-8-sig", float_format="%.3f")

    # Portföy etkisi: yıllık GES ve RES üretimlerinin birbiriyle korelasyonu
    yillik_kor = yillik["GES [MWh/MW]"].corr(yillik["RES [MWh/MW]"])

    # 3) Doğrulama
    dog = pvgis_dogrulama(kod, saha, y1, y2, cfg)
    pd.Series(dog).to_csv(CIKTI / "ges_dogrulama.csv", encoding="utf-8-sig", header=["kWh/kWp/yıl veya %"])

    # 4) Grafikler
    grafik_aylik(df, y1, y2)
    grafik_isi_haritasi(df, y1, y2)
    grafik_yillik(yillik, ozet)
    grafik_sure_egrisi(df, y1, y2)

    pd.set_option("display.width", 220)
    print("\n=== Yıllık üretim ===")
    print(yillik.round(2).to_string())
    print("\n=== P50 / P90 (MWh/yıl; GES ve RES MW başına, hibrit 1+1 MW / 1 MW bağlantı) ===")
    print(ozet.round(1).to_string())
    print(f"\nYıllık GES–RES üretim korelasyonu (10 yıl): {yillik_kor:.2f}")
    print(f"Saatlik GES–RES korelasyonu: {df['ges_kf'].corr(df['res_kf']):.2f}")
    print("\n=== GES doğrulama (kWh/kWp/yıl) ===")
    for k, v in dog.items():
        print(f"  {k:<50s} {v:8.2f}")
    print(
        f"\nRES 10 yıl ort. KF: E-141 %{100 * df['res_kf'].mean():.1f}, E-126 %{100 * df['res_kf_e126'].mean():.1f}; "
        f"120 m ort. hız {df['v_gobek_ham'].mean():.2f} m/s, ort. yoğunluk {df['hava_yogunlugu'].mean():.3f} kg/m³"
    )
    print(f"Grafikler: {CIKTI.relative_to(CIKTILAR.parent)}/")


if __name__ == "__main__":
    main()
