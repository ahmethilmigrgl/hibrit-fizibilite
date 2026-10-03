"""
Aşama 2 — ERA5 rüzgâr modelinin Ezine çevresindeki gerçek RES üretimiyle kalibrasyonu

Yöntem:
    1) Referans santralin (Enerjisa Çanakkale RES, Ezine) gözlenen saatlik üretimi EPİAŞ'tan alınır,
       kurulu güce bölünerek kapasite faktörüne (KF) çevrilir.
    2) Aynı santral, ERA5 Ezine grid noktasından KENDİ türbinine benzer bir güç eğrisi ve göbek
       yüksekliğiyle modellenir (E-141/120 m ile değil — eski 2.3 MW türbinleri yeni bir türbinle
       kıyaslamak elmayla armudu karşılaştırmak olur).
    3) Hız kalibrasyon katsayısı k, örtüşen yıllarda modellenen ortalama KF gözlenene eşit olacak
       şekilde bulunur (kök bulma). k rüzgâr HIZINI ölçekler; bu yüzden aynı k, proje türbinine
       (E-141, 120 m) de uygulanabilir.
    4) Duyarlılık: türbin vekili ve göbek yüksekliği değiştirilerek k aralığı raporlanır.
    5) Diğer santraller çapraz kontrol olarak raporlanır.

Bu script config.yaml'ı DEĞİŞTİRMEZ; önerilen k'yı raporlar.

Çalıştırma: .venv/bin/python src/02_ruzgar_kalibrasyonu.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq

from src import gorsel as g
from src.ayarlar import CIKTILAR, config_oku, deger
from src.piyasa.epias import EpiasIstemcisi
from src.piyasa.veri import uretim_cek
from src.uretim import ruzgar

CIKTI = CIKTILAR / "02_piyasa"
REFERANS = "enerjisa_canakkale"
VEKIL_TURBIN = "E-92/2350"     # Siemens SWT-2.3-93'e en yakın spesifik güç (354 vs 339 W/m²)
VEKIL_GOBEK = 80               # m, 2011 dönemi 2.3 MW türbinler için tipik (varsayım)
DUYARLILIK = [("E-92/2350", 70), ("E-92/2350", 100), ("E-82/2300", 80), ("SWT113/2300", 80)]
KAYDIRMA = -1                  # saat; EPİAŞ değeri [t, t+1) dönem ortalaması, ERA5 t anındaki anlık değer
                               # → ideal eşleşme ~yarım saat; -1 ve -2 korelasyonu pratikte eşit (bkz. docs)
UZUN_DURUS_SAAT = 48           # bu süreden uzun ardışık sıfır üretim = arıza/bakım, dışarıda bırakılır
TSI = 3


def uzun_duruslar(seri: pd.Series, esik_mw: float = 0.05, min_saat: int = UZUN_DURUS_SAAT) -> pd.Series:
    """Ardışık en az min_saat sıfır üretim olan saatleri True işaretler."""
    sifir = seri <= esik_mw
    grup = (sifir != sifir.shift()).cumsum()
    uzunluk = sifir.groupby(grup).transform("size")
    return sifir & (uzunluk >= min_saat)


def gecikme_testi(gozlenen: pd.Series, model: pd.Series) -> pd.Series:
    """Gözlenen ile model arasındaki saatlik korelasyonu -2..+2 saat kaydırmalarla ölçer."""
    return pd.Series({k: gozlenen.corr(model.shift(k)) for k in range(-2, 3)}, name="korelasyon")


def main():
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    saha = cfg["aday_sahalar"][deger(cfg["saha"]["kod"])]
    y1, y2 = deger(cfg["uretim"]["yillar_tam"])
    CIKTI.mkdir(parents=True, exist_ok=True)

    # --- ERA5 (Aşama 1 önbelleği) ve gözlenen santral üretimleri
    era5 = ruzgar.era5_coklu_yil(deger(cfg["saha"]["kod"]), saha["enlem"], saha["boylam"], y1, y2, cr)
    istemci = EpiasIstemcisi()
    bas, son = deger(cfg["piyasa"]["veri_baslangic"]), deger(cfg["piyasa"]["veri_bitis"])
    santraller = cfg["kalibrasyon_santralleri"]
    gozlenen_mw = pd.concat(
        {k: uretim_cek(istemci, bas, son, santral_id=s["epias_id"])["toplam"] for k, s in santraller.items()},
        axis=1)

    # --- Referans santral: gözlenen KF (uzun duruşlar hariç), ERA5 dönemiyle örtüşen saatler
    ref = santraller[REFERANS]
    ref_mw = gozlenen_mw[REFERANS]
    durus = uzun_duruslar(ref_mw)
    ref_kf = (ref_mw / ref["kurulu_guc_mw"]).where(~durus).rename("gozlenen")

    def model_kf(k: float, turbin_modeli=VEKIL_TURBIN, gobek=VEKIL_GOBEK) -> pd.Series:
        kf, _ = ruzgar.ruzgar_kapasite_faktoru(era5, cr, turbin_modeli=turbin_modeli, gobek=gobek, katsayi=k)
        return kf

    m1 = model_kf(1.0)
    gecikme = gecikme_testi(ref_kf, m1)
    kaydirma = KAYDIRMA
    print("Saatlik korelasyon, model kaydırması (saat) →", gecikme.round(3).to_dict(), f"→ kullanılan: {kaydirma}")

    def ortak(model: pd.Series) -> pd.DataFrame:
        return pd.concat([ref_kf, model.shift(kaydirma).rename("model")], axis=1, join="inner").dropna()

    hedef = ortak(m1)["gozlenen"].mean()

    def fark(k, turbin_modeli=VEKIL_TURBIN, gobek=VEKIL_GOBEK):
        return ortak(model_kf(k, turbin_modeli, gobek))["model"].mean() - hedef

    k_ana = brentq(fark, 0.7, 1.5, xtol=1e-3)
    print(f"\nReferans: {ref['ad']} — gözlenen ort. KF (örtüşen {y1}–{y2}, uzun duruşlar hariç): %{100*hedef:.2f}")
    print(f"Model (k=1, {VEKIL_TURBIN}, {VEKIL_GOBEK} m): %{100*ortak(m1)['model'].mean():.2f}")
    print(f"→ Kalibrasyon katsayısı k = {k_ana:.3f}")

    # --- Duyarlılık
    duyarlilik = []
    for t, h in DUYARLILIK:
        k = brentq(lambda x: fark(x, t, h), 0.6, 1.8, xtol=1e-3)
        duyarlilik.append({"türbin vekili": t, "göbek [m]": h, "k": k})
    duyarlilik = pd.DataFrame([{"türbin vekili": VEKIL_TURBIN, "göbek [m]": VEKIL_GOBEK, "k": k_ana}] + duyarlilik)
    print("\nDuyarlılık:"); print(duyarlilik.round(3).to_string(index=False))

    # --- Kalibrasyon öncesi / sonrası karşılaştırma (referans santral)
    mk = model_kf(k_ana)
    once, sonra = ortak(m1), ortak(mk)
    yil = once.index.tz_convert("Europe/Istanbul").year
    yillik = pd.DataFrame({
        "Gözlenen KF [%]": 100 * once["gozlenen"].groupby(yil).mean(),
        "Model k=1 [%]": 100 * once["model"].groupby(yil).mean(),
        f"Model k={k_ana:.3f} [%]": 100 * sonra["model"].groupby(yil).mean(),
        "Durus saati (hariç)": durus.groupby(durus.index.tz_convert("Europe/Istanbul").year).sum(),
    })
    saat_sayisi = once["gozlenen"].groupby(yil).size()
    yillik = yillik.loc[saat_sayisi[saat_sayisi > 8000].index]   # yalnızca tam yıllar
    ay = sonra.index.tz_convert("Europe/Istanbul").strftime("%Y-%m")
    aylik = pd.DataFrame({"gozlenen": sonra["gozlenen"].groupby(ay).mean(),
                          "model": sonra["model"].groupby(ay).mean(),
                          "model_k1": once["model"].groupby(ay).mean()})
    metrikler = {
        "Saatlik korelasyon": sonra["gozlenen"].corr(sonra["model"]),
        "Günlük korelasyon": sonra.resample("D").mean().corr().iloc[0, 1],
        "Aylık korelasyon": aylik["gozlenen"].corr(aylik["model"]),
        "Yıllık KF korelasyonu": yillik.iloc[:, 0].corr(yillik.iloc[:, 2]),
        "Saatlik RMSE [KF]": float(np.sqrt(((sonra["gozlenen"] - sonra["model"]) ** 2).mean())),
    }
    print("\nYıllık (referans santral):"); print(yillik.round(2).to_string())
    print("\nUyum metrikleri (kalibrasyon sonrası):", {k: round(v, 3) for k, v in metrikler.items()})

    # --- Proje türbinine etkisi (E-141, 120 m): ortalama KF k=1 vs k*
    e141_k1 = ruzgar.ruzgar_kapasite_faktoru(era5, cr, katsayi=1.0)[0].mean()
    e141_k = ruzgar.ruzgar_kapasite_faktoru(era5, cr, katsayi=k_ana)[0].mean()
    print(f"\nProje türbini E-141/120 m, {y1}–{y2} ort. KF: k=1 → %{100*e141_k1:.1f}, k={k_ana:.3f} → %{100*e141_k:.1f}")

    # --- Çapraz kontrol: tüm santraller. Kapasite artırımları olduğu için her yılın kapasitesi
    #     o yılın %99.9 yüzdelik üretimi alınır; kapasitenin değiştiği geçiş yılları dışarıda bırakılır.
    capraz = []
    for kod, s in santraller.items():
        mw = gozlenen_mw[kod]
        d = uzun_duruslar(mw)
        yil_y = mw.index.tz_convert("Europe/Istanbul").year
        kap_yil = mw.groupby(yil_y).quantile(0.999)
        degisim = (kap_yil.pct_change().abs() > 0.08) | (kap_yil.pct_change(-1).abs() > 0.08)
        kap = pd.Series(kap_yil.reindex(yil_y).values, index=mw.index)
        gecis = pd.Series(degisim.reindex(yil_y).fillna(False).values, index=mw.index)
        kf = (mw / kap).where(~d & ~gecis & (kap > 1))
        ort = pd.concat([kf.rename("gozlenen"), mk.shift(kaydirma).rename("m")], axis=1, join="inner").dropna()
        # Aynı vekil türbinle bu santral için (gösterge niteliğinde) k
        hedef_s = ort["gozlenen"].mean()
        def fark_s(x):
            m = model_kf(x).shift(kaydirma)
            return m.reindex(ort.index).mean() - hedef_s
        try:
            k_s = brentq(fark_s, 0.6, 1.8, xtol=1e-3)
        except ValueError:
            k_s = np.nan
        ilk = mw[mw > 0.5].index.min()
        capraz.append({
            "Santral": s["ad"], "İlçe": s["ilce"], "Türbin": s["turbin"],
            "Kurulu güç (güncel) [MW]": round(kap_yil.iloc[-1], 1),
            "Kapasite değişen yıllar": ", ".join(str(y) for y in degisim[degisim].index) or "-",
            "Gözlenen KF 2014–2023 [%]": 100 * hedef_s,
            "Gözlenen KF 2024–2026 [%]": 100 * kf[kf.index.tz_convert("Europe/Istanbul").year >= 2024].mean(),
            "ERA5 ile saatlik korelasyon": ort["gozlenen"].corr(ort["m"]),
            "Gösterge k (E-92/80 m vekili)": k_s,
            "Uzun duruş saati": int(d.sum()),
        })
    capraz = pd.DataFrame(capraz)
    pd.set_option("display.width", 220)
    print("\nÇapraz kontrol:"); print(capraz.round(2).to_string(index=False))

    # --- Kaydet
    yillik.to_csv(CIKTI / "kalibrasyon_yillik.csv", encoding="utf-8-sig", float_format="%.3f")
    duyarlilik.to_csv(CIKTI / "kalibrasyon_duyarlilik.csv", encoding="utf-8-sig", index=False, float_format="%.4f")
    capraz.to_csv(CIKTI / "kalibrasyon_santraller.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    pd.Series({**metrikler, "k": k_ana, "kaydirma_saat": kaydirma, "hedef_kf": hedef,
               "e141_kf_k1": e141_k1, "e141_kf_k": e141_k}).to_csv(
        CIKTI / "kalibrasyon_ozet.csv", encoding="utf-8-sig", header=["deger"])

    grafikler(once, sonra, yillik, aylik, k_ana, ref["ad"])


def grafikler(once, sonra, yillik, aylik, k, ad):
    kaynak = (f"Kaynak: EPİAŞ Şeffaflık Platformu (gerçek zamanlı üretim), ERA5 (Copernicus/ECMWF). "
              f"Model: windpowerlib {VEKIL_TURBIN} vekil türbin, {VEKIL_GOBEK} m göbek, %12 kayıp. Kendi hesaplamam.")
    # 1) Yıllık KF: gözlenen vs model
    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = np.arange(len(yillik)); w = 0.27
    for i, (sutun, renk, etiket) in enumerate([
            (yillik.columns[0], g.MUREKKEP, "Gözlenen (EPİAŞ)"),
            (yillik.columns[1], g.SOLUK, "ERA5 modeli, k = 1"),
            (yillik.columns[2], g.RENK_RES, f"ERA5 modeli, k = {k:.3f}")]):
        ax.bar(x + (i - 1) * (w + 0.02), yillik[sutun], w, color=renk, label=etiket)
    ax.set_xticks(x, yillik.index)
    ax.set_ylabel("Yıllık kapasite faktörü [%]")
    ax.legend(ncols=3, loc="upper center", bbox_to_anchor=(0.5, 1.02))
    ax.set_ylim(0, max(yillik.iloc[:, :3].max()) * 1.2)
    g.eksen_sade(ax)
    g.baslik(fig, f"Kalibrasyon: {ad}", "Yıllık kapasite faktörü, gözlenen ve ERA5 modeli (kalibrasyon öncesi ve sonrası)")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, kaynak)
    fig.savefig(CIKTI / "kalibrasyon_yillik.png"); plt.close(fig)

    # 2) Aylık KF serisi + gün içi profil
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [2.2, 1]})
    t = pd.to_datetime(aylik.index)
    axs[0].plot(t, 100 * aylik["gozlenen"], color=g.MUREKKEP, lw=1.6, label="Gözlenen")
    axs[0].plot(t, 100 * aylik["model"], color=g.RENK_RES, lw=1.6, label=f"Model, k = {k:.3f}")
    axs[0].set_ylabel("Aylık kapasite faktörü [%]")
    axs[0].set_title(f"Aylık KF (korelasyon {aylik['gozlenen'].corr(aylik['model']):.2f})", loc="left")
    axs[0].legend(loc="upper left", ncols=2)
    saat = (sonra.index.hour + TSI) % 24
    prof = sonra.groupby(saat).mean() * 100
    prof1 = once.groupby((once.index.hour + TSI) % 24)["model"].mean() * 100
    axs[1].plot(prof.index, prof["gozlenen"], color=g.MUREKKEP, lw=2, label="Gözlenen")
    axs[1].plot(prof1.index, prof1, color=g.SOLUK, lw=1.5, ls="--", label="Model, k = 1")
    axs[1].plot(prof.index, prof["model"], color=g.RENK_RES, lw=2, label=f"Model, k = {k:.3f}")
    axs[1].set_xticks([0, 6, 12, 18, 23]); axs[1].set_xlabel("Saat (TSİ = UTC+3)")
    axs[1].set_title("Ortalama gün içi profil [% KF]", loc="left")
    axs[1].legend(fontsize=8)
    for ax in axs:
        g.eksen_sade(ax)
    g.baslik(fig, "ERA5 mevsimselliği iyi yakalıyor ama öğleden sonraki rüzgâr pikini kaçırıyor",
             f"{ad}: gözlenen ve kalibre edilmiş model")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, kaynak)
    fig.savefig(CIKTI / "kalibrasyon_aylik_gun_ici.png"); plt.close(fig)


if __name__ == "__main__":
    main()
