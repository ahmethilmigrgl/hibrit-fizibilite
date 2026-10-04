"""
Aşama 2 — ERA5 rüzgâr modelinin Ezine çevresindeki gerçek RES üretimiyle kalibrasyonu
(Revizyon: zaman hizalaması + ay × saat hız katsayısı matrisi)

Yöntem:
    1) Zaman hizası: EPİAŞ üretimi [t, t+1) UTC saat aralığı ortalamasıdır (saat başı etiketli);
       ERA5 hız/yoğunluk anlık değerleri (x_t + x_{t+1})/2 ile aynı aralığa çevrilir.
    2) Referans santral (Enerjisa Çanakkale RES) kendi türbinine benzer güç eğrisiyle (E-92/2350, 80 m)
       ERA5'ten modellenir; gözlenen KF = üretim / kurulu güç (≥48 saatlik duruşlar hariç).
    3a) Sabit k: modellenen ortalama KF = gözlenen.
    3b) Ay × saat k: her (ay, TSİ saati) hücresinde ortalama KF eşlenir, komşu hücrelerle yumuşatılır.
    4) Çapraz doğrulama: 2014–18'de kur → 2019–23'te test et, ve tersi.
    5) Nihai matris 2014–2023'ün tamamıyla kurulur → data/processed/ruzgar_k_ay_saat.parquet
       (ve inceleme için outputs/02_piyasa/ruzgar_k_ay_saat.csv).

config.yaml DEĞİŞTİRİLMEZ (yöntem seçimi: uretim.ruzgar.ruzgar_kalibrasyon_yontemi).
Çalıştırma: .venv/bin/python src/02_ruzgar_kalibrasyonu.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, KOK, config_oku, deger
from src.uretim import kalibrasyon as kal
from src.uretim import ruzgar

CIKTI = CIKTILAR / "02_piyasa"
REFERANS = "enerjisa_canakkale"
VEKIL_TURBIN = "E-92/2350"  # Siemens SWT-2.3-93'e en yakın spesifik güç (354 vs 339 W/m²)
VEKIL_GOBEK = 80  # m, 2011 dönemi 2.3 MW türbinler için tipik (varsayım)
DUYARLILIK = [("E-92/2350", 70), ("E-92/2350", 100), ("E-82/2300", 80), ("SWT113/2300", 80)]
UZUN_DURUS_SAAT = 48
CAPRAZ_SANTRALLER = ["enerjisa_canakkale", "camseki", "intepe"]
KAYNAK = (
    "Kaynak: EPİAŞ Şeffaflık Platformu (gerçek zamanlı üretim), ERA5 (Copernicus/ECMWF). "
    f"Model: windpowerlib {VEKIL_TURBIN} vekil türbin, {VEKIL_GOBEK} m göbek, %12 kayıp. Kendi hesaplamam."
)


def uzun_duruslar(seri: pd.Series, esik_mw: float = 0.05, min_saat: int = UZUN_DURUS_SAAT) -> pd.Series:
    """Ardışık en az min_saat sıfır üretim olan saatleri True işaretler (arıza/bakım)."""
    sifir = seri <= esik_mw
    grup = (sifir != sifir.shift()).cumsum()
    return sifir & (sifir.groupby(grup).transform("size") >= min_saat)


def degisken_kapasiteli_kf(mw: pd.Series) -> pd.Series:
    """Kapasite artırımı olan santraller: her yılın kapasitesi = o yılın %99,9 yüzdeliği; geçiş yılları hariç."""
    yil = mw.index.tz_convert("Europe/Istanbul").year
    kap_yil = mw.groupby(yil).quantile(0.999)
    degisim = (kap_yil.pct_change().abs() > 0.08) | (kap_yil.pct_change(-1).abs() > 0.08)
    kap = pd.Series(kap_yil.reindex(yil).to_numpy(), index=mw.index)
    gecis = pd.Series(degisim.reindex(yil).fillna(False).to_numpy(), index=mw.index)
    return (mw / kap).where(~uzun_duruslar(mw) & ~gecis & (kap > 1))


def main():
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    kod = deger(cfg["saha"]["kod"])
    saha = cfg["aday_sahalar"][kod]
    y1, y2 = deger(cfg["uretim"]["yillar_tam"])
    CIKTI.mkdir(parents=True, exist_ok=True)

    era5 = ruzgar.era5_coklu_yil(kod, saha["enlem"], saha["boylam"], y1, y2, cr)
    santraller = cfg["kalibrasyon_santralleri"]
    gozlenen_mw = pd.read_parquet(ISLENMIS_VERI / "ezine_res_santralleri.parquet")

    m = kal.referans_model(era5, cr, VEKIL_TURBIN, VEKIL_GOBEK)
    ref = santraller[REFERANS]
    ref_mw = gozlenen_mw[REFERANS]
    g_ref = (ref_mw / ref["kurulu_guc_mw"]).where(~uzun_duruslar(ref_mw)).reindex(m.indeks).to_numpy()
    gecerli = ~np.isnan(g_ref)
    yil = (m.indeks + pd.Timedelta(hours=3)).year.to_numpy()

    # --- Zaman hizası kontrolü: aralık ortalamasında en iyi kayma ~0 olmalı
    m1 = pd.Series(m.kf(1.0), index=m.indeks)
    gs = pd.Series(g_ref, index=m.indeks)
    gecikme = {k: round(gs.corr(m1.shift(k)), 4) for k in range(-2, 3)}
    print("Hizalı modelde saatlik korelasyon / kayma (saat):", gecikme)

    # --- 1) Çapraz doğrulama
    A = gecerli & (yil >= 2014) & (yil <= 2018)
    B = gecerli & (yil >= 2019) & (yil <= 2023)
    cv = []
    for ad, egitim, test in [("Kur 2014–18, test 2019–23", A, B), ("Kur 2019–23, test 2014–18", B, A)]:
        k = kal.sabit_k(m, g_ref, egitim)
        ham, yum = kal.k_matrisi(m, g_ref, egitim)
        for yontem, kf in [
            ("Sabit k", m.kf(k)),
            ("Ay × saat (ham)", m.kf_matris(ham.to_numpy())),
            ("Ay × saat (yumuşatılmış)", m.kf_matris(yum.to_numpy())),
        ]:
            cv.append({"Katman": ad, "Yöntem": yontem, **kal.metrikler(m, g_ref, kf, test)})
    cv = pd.DataFrame(cv)
    pd.set_option("display.width", 250)
    print("\nÇapraz doğrulama (test dönemi metrikleri):")
    print(cv.round(3).to_string(index=False))

    # --- 2) Nihai kalibrasyon, 2014–2023'ün tamamı
    k_sabit = kal.sabit_k(m, g_ref, gecerli)
    ham, yum = kal.k_matrisi(m, g_ref, gecerli)
    kf_sabit, kf_matris = m.kf(k_sabit), m.kf_matris(yum.to_numpy())
    print(
        f"\nSabit k (hizalı): {k_sabit:.4f} | matris: min {yum.values.min():.3f}, maks {yum.values.max():.3f}, "
        f"ortalama {yum.values.mean():.3f}"
    )
    tum_metrik = pd.DataFrame(
        [
            {"Yöntem": "Sabit k", **kal.metrikler(m, g_ref, kf_sabit, gecerli)},
            {"Yöntem": "Ay × saat", **kal.metrikler(m, g_ref, kf_matris, gecerli)},
        ]
    )
    print(tum_metrik.round(3).to_string(index=False))

    # Matris kaydı: data/processed (model girdisi) + outputs (inceleme)
    hedef = KOK / deger(cr["k_matris_dosyasi"])
    yum.to_parquet(hedef)
    yum.round(4).to_csv(CIKTI / "ruzgar_k_ay_saat.csv", encoding="utf-8-sig")
    ham.round(4).to_csv(CIKTI / "ruzgar_k_ay_saat_ham.csv", encoding="utf-8-sig")
    print(f"Matris kaydedildi: {hedef.relative_to(KOK)}")

    # --- 3) Vekil türbin / göbek duyarlılığı (sabit k)
    duy = [{"türbin vekili": VEKIL_TURBIN, "göbek [m]": VEKIL_GOBEK, "k": k_sabit}]
    for t, h in DUYARLILIK:
        mm = kal.referans_model(era5, cr, t, h)
        duy.append({"türbin vekili": t, "göbek [m]": h, "k": kal.sabit_k(mm, g_ref, gecerli)})
    duy = pd.DataFrame(duy)
    print("\nDuyarlılık:")
    print(duy.round(3).to_string(index=False))

    # --- 4) Yıllık tablo (referans)
    yt = pd.DataFrame({"g": g_ref, "s": kf_sabit, "m": kf_matris, "m1": m.kf(1.0), "yil": yil})[gecerli]
    tam_yil = yt.groupby("yil").size() > 8000  # yalnızca tam yıllar
    yillik = 100 * yt.groupby("yil")[["g", "m1", "s", "m"]].mean().loc[tam_yil[tam_yil].index]
    yillik.columns = ["Gözlenen KF [%]", "Model k=1 [%]", f"Model sabit k={k_sabit:.3f} [%]", "Model ay×saat [%]"]
    print("\nYıllık (referans santral):")
    print(yillik.round(2).to_string())

    # --- 5) Çapraz kontrol: üç santralin gün içi profili, model (sabit vs matris) ile
    tsi = (m.indeks.hour + 3) % 24
    profiller = {}
    for s in CAPRAZ_SANTRALLER:
        kf = degisken_kapasiteli_kf(gozlenen_mw[s]).reindex(m.indeks)
        profiller[santraller[s]["ad"]] = kf.groupby(tsi).mean()
    profiller["Model, sabit k"] = pd.Series(kf_sabit, index=m.indeks).where(gecerli).groupby(tsi).mean()
    profiller["Model, ay × saat k"] = pd.Series(kf_matris, index=m.indeks).where(gecerli).groupby(tsi).mean()
    profiller = 100 * pd.DataFrame(profiller)
    profiller.index.name = "tsi_saat"
    print("\nGün içi profil [% KF]:")
    print(profiller.round(1).to_string())

    # --- Kaydet
    cv.to_csv(CIKTI / "kalibrasyon_capraz_dogrulama.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    tum_metrik.to_csv(CIKTI / "kalibrasyon_metrikler.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    yillik.to_csv(CIKTI / "kalibrasyon_yillik.csv", encoding="utf-8-sig", float_format="%.3f")
    duy.to_csv(CIKTI / "kalibrasyon_duyarlilik.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    profiller.to_csv(CIKTI / "kalibrasyon_gun_ici_profil.csv", encoding="utf-8-sig", float_format="%.3f")
    pd.Series(
        {
            "k_sabit": k_sabit,
            "hedef_kf": float(np.nanmean(g_ref)),
            "zaman_hizasi": "aralik",
            "vekil_turbin": VEKIL_TURBIN,
            "vekil_gobek_m": VEKIL_GOBEK,
            **{f"gecikme_{k}": v for k, v in gecikme.items()},
        }
    ).to_csv(CIKTI / "kalibrasyon_ozet.csv", encoding="utf-8-sig", header=["deger"])

    grafikler(yillik, profiller, yum, k_sabit, ref["ad"])


def grafikler(yillik, profiller, matris, k_sabit, ad):
    # 1) Yıllık KF
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    x = np.arange(len(yillik))
    w = 0.2
    for i, (sutun, renk) in enumerate(zip(yillik.columns, [g.MUREKKEP, g.SOLUK, "#9ec5ef", g.RENK_RES])):
        ax.bar(x + (i - 1.5) * (w + 0.01), yillik[sutun], w, color=renk, label=sutun.replace(" [%]", ""))
    ax.set_xticks(x, yillik.index)
    ax.set_ylabel("Yıllık kapasite faktörü [%]")
    ax.set_ylim(0, yillik.max().max() * 1.25)
    ax.legend(ncols=4, loc="upper center", fontsize=8)
    g.eksen_sade(ax)
    g.baslik(fig, f"Kalibrasyon: {ad}", "Yıllık kapasite faktörü — gözlenen ve ERA5 modeli (aralık ortalaması zaman tanımı)")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "kalibrasyon_yillik.png")
    plt.close(fig)

    # 2) Gün içi profiller: üç santral + iki model; sağda k matrisi
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axs[0]
    for s, renk in zip(profiller.columns[:3], ["#0b0b0b", "#52514e", "#8a8984"]):
        ax.plot(profiller.index, profiller[s], color=renk, lw=1.8, label=f"Gözlenen: {s}")
    ax.plot(profiller.index, profiller["Model, sabit k"], color=g.RENK_RES, lw=1.6, ls="--", label=f"Model, sabit k = {k_sabit:.3f}")
    ax.plot(profiller.index, profiller["Model, ay × saat k"], color=g.RENK_RES, lw=2.4, label="Model, ay × saat k")
    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21])
    ax.set_xlabel("Saat (TSİ = UTC+3)")
    ax.set_ylabel("Ortalama kapasite faktörü [%]")
    ax.set_title("Öğleden sonra meltem piki üç santralde de var", loc="left")
    ax.legend(fontsize=7.5, loc="upper left")
    g.eksen_sade(ax, izgara="both")
    ax = axs[1]
    from matplotlib.colors import TwoSlopeNorm

    norm = TwoSlopeNorm(vcenter=1.0, vmin=min(0.75, matris.values.min()), vmax=max(1.25, matris.values.max()))
    im = ax.imshow(matris.to_numpy(), aspect="auto", cmap="RdBu_r", norm=norm)
    ax.set_yticks(range(12), ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"])
    ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_xlabel("Saat (TSİ)")
    ax.set_title("Ay × saat hız katsayısı (yumuşatılmış)", loc="left")
    for k in ax.spines.values():
        k.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cb.outline.set_visible(False)
    cb.set_label("k (1 = ERA5 hızı değişmez)", color=g.IKINCIL)
    g.baslik(
        fig,
        "ERA5 öğleden sonraki deniz meltemini kaçırıyor: ay × saat hız düzeltmesi",
        f"{ad} referanslı kalibrasyon; çapraz kontrol: Çamseki, İntepe (2014–2023)",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "kalibrasyon_aylik_gun_ici.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
