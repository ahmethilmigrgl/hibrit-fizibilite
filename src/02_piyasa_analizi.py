"""
Aşama 2 — Piyasa analizi: yakalanan fiyat, kanibalizasyon ve batarya ön göstergeleri

Girdi (önce src/02_piyasa_verisi.py ve src/01_uretim_profilleri.py çalıştırılmalı):
    data/processed/ptf_2014_guncel.parquet, uretim_turkiye_2014_guncel.parquet,
    ezine_profiller_2014_2023.parquet, auf_2022_2023.parquet

Analizler:
    Yol A — Ezine GES, RES ve 1+1 MW / 1 MW bağlantı hibritinin (satılan üretim) yakalanan fiyatı,
            aynı yılın saatlik PTF'siyle (2014–2023). AUF dönemi için ayrıca duyarlılık.
    Yol B — Türkiye geneli rüzgâr ve güneş üretim ŞEKİLLERİYLE yıllık yakalanma oranı (2014/2019–2026).
    Batarya — gün içi fiyat profili, günlük spread, düşük fiyatlı saatler, ay × saat ısı haritası.

Para birimi: Ana anlatı USD ve yakalanma oranıdır. TL'de yıl içi enflasyon (2022'de >%70) yılın
geç aylarındaki saatlere daha yüksek nominal fiyat verdiği için yıllık TL yakalanma oranı mevsimsel
olarak çarpıktır; bu yüzden TL için oran AYLIK hesaplanıp üretim ağırlığıyla yıllığa toplanır.

Çıktılar: outputs/02_piyasa/*.png, *.csv
Çalıştırma: .venv/bin/python src/02_piyasa_analizi.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, ISLENMIS_VERI, config_oku, deger
from src.piyasa import analiz as a

CIKTI = CIKTILAR / "02_piyasa"
KAYNAK = "Kaynak: EPİAŞ Şeffaflık Platformu (PTF, gerçek zamanlı üretim). Kendi hesaplamam."
KAYNAK_A = ("Kaynak: EPİAŞ Şeffaflık Platformu (PTF), PVGIS-SARAH3, ERA5 (kalibre). "
            "Ezine üretim profilleri: kendi modelim (Aşama 1).")
AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def tl_aylik_oran(fiyat_tl: pd.Series, uretimler: pd.DataFrame) -> pd.DataFrame:
    """TL yakalanma oranı: önce aylık oran, sonra üretim ağırlıklı yıllık ortalama (enflasyon etkisini ayıklar)."""
    aylik = a.yakalanan_fiyat(fiyat_tl, uretimler, "M")
    df = pd.concat([fiyat_tl.rename("_f"), uretimler], axis=1, join="inner").dropna()
    ay = a.yerel_donem(df.index, "M")
    sonuc = {}
    for s in uretimler.columns:
        agirlik = df[s].groupby(ay).sum()
        oran = aylik[f"{s}_oran"]
        yil = pd.Index(oran.index.str.slice(0, 4).astype(int), name="yil")
        sonuc[s] = (oran * agirlik).groupby(yil).sum() / agirlik.groupby(yil).sum()
    return pd.DataFrame(sonuc)


def auf_fiyati(ptf: pd.DataFrame, auf: pd.DataFrame) -> pd.DataFrame:
    """
    AUF döneminde (Nis 2022 – Eyl 2023) yenilenebilir üreticinin fiilen aldığı fiyat ≈ min(PTF, AUF_yenilenebilir).
    USD karşılığı aynı saatin PTF kuru ile çevrilir.
    """
    ay = a.yerel_donem(ptf.index, "M")
    tavan = pd.Series(auf["auf_yenilenebilir"].reindex(ay).values, index=ptf.index)
    etkin_tl = np.where(tavan.notna(), np.minimum(ptf["ptf_tl"], tavan), ptf["ptf_tl"])
    kur = (ptf["ptf_tl"] / ptf["ptf_usd"]).replace([np.inf, -np.inf], np.nan).ffill()
    return pd.DataFrame({"etkin_tl": etkin_tl, "etkin_usd": etkin_tl / kur, "auf_donemi": tavan.notna()},
                        index=ptf.index)


# ---------------------------------------------------------------------------
# Grafikler
# ---------------------------------------------------------------------------
def grafik_yol_a_usd(yol_a: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    seriler = [("ortalama_fiyat", g.MUREKKEP, "Ortalama PTF (baz yük)", "--"),
               ("ges_kf_yakalanan", g.RENK_GES, "GES yakalanan", "-"),
               ("res_kf_yakalanan", g.RENK_RES, "RES yakalanan", "-"),
               ("hibrit_satilan_yakalanan", g.RENK_HIBRIT, "Hibrit (1+1 MW / 1 MW) yakalanan", "-")]
    for s, renk, etiket, stil in seriler:
        ax.plot(yol_a.index, yol_a[s], color=renk, lw=2, ls=stil, marker="o", ms=4, label=etiket,
                markeredgecolor="white", markeredgewidth=1)
    ax.axvspan(2021.5, 2023.5, color=g.IZGARA, alpha=0.5, lw=0)
    ax.text(2022.5, ax.get_ylim()[1] * 0.97, "Enerji krizi +\nAUF dönemi", ha="center", va="top", fontsize=8, color=g.IKINCIL)
    ax.set_ylabel("Fiyat [USD/MWh]")
    ax.set_xticks(yol_a.index)
    ax.legend(loc="upper left")
    g.eksen_sade(ax)
    g.baslik(fig, "Ezine: rüzgâr ortalamaya yakın, güneş giderek ortalamanın altında satıyor",
             "Yıllık ortalama PTF ve üretim ağırlıklı yakalanan fiyat (USD/MWh), aynı yılın saatlik fiyatlarıyla")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK_A)
    fig.savefig(CIKTI / "yillik_fiyat_yakalanan_usd.png"); plt.close(fig)


def grafik_yakalanma_trendi(yol_a: pd.DataFrame, yol_b: pd.DataFrame, son_yil_kismi: int, uzanti: pd.DataFrame):
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for s, renk, ad in [("ges_kf_oran", g.RENK_GES, "GES"), ("res_kf_oran", g.RENK_RES, "RES"),
                        ("hibrit_satilan_oran", g.RENK_HIBRIT, "Hibrit")]:
        axs[0].plot(yol_a.index, 100 * yol_a[s], color=renk, lw=2, marker="o", ms=4, label=ad,
                    markeredgecolor="white", markeredgewidth=1)
    # 2024+ uzantısı: 10 hava yılı ortalaması, eşzamanlılık düzeltmeli (kesikli, içi boş)
    for kisa, uzun, renk in [("ges", "ges_kf_oran", g.RENK_GES), ("res", "res_kf_oran", g.RENK_RES),
                             ("hibrit", "hibrit_satilan_oran", g.RENK_HIBRIT)]:
        x = [yol_a.index[-1]] + list(uzanti.index)
        y = [100 * yol_a[uzun].iloc[-1]] + list(100 * uzanti[f"{kisa}_oran_duzeltilmis"])
        axs[0].plot(x, y, color=renk, lw=1.6, ls="--", marker="o", ms=5, markerfacecolor="white")
    axs[0].axvspan(yol_a.index[-1] + 0.5, uzanti.index[-1] + 0.4, color=g.IZGARA, alpha=0.45, lw=0)
    axs[0].text(uzanti.index[0] + 0.5, 121, "2024–26: 10 hava yılı ×\ngerçek fiyat (düzeltilmiş)",
                ha="center", va="top", fontsize=7.5, color=g.IKINCIL)
    axs[0].set_title("Yol A — Ezine profilleri (2014–2023, 2024–26 uzantı)", loc="left")
    for s, renk, ad in [("gunes_oran", g.RENK_GES, "Güneş (lisanslı GES şekli)"), ("ruzgar_oran", g.RENK_RES, "Rüzgâr")]:
        d = yol_b[s].dropna()
        axs[1].plot(d.index, 100 * d, color=renk, lw=2, marker="o", ms=4, label=ad,
                    markeredgecolor="white", markeredgewidth=1)
    axs[1].annotate(f"{son_yil_kismi}: Oca–Eyl", xy=(son_yil_kismi, 100 * yol_b["gunes_oran"].iloc[-1]),
                    xytext=(son_yil_kismi - 3.2, 100 * yol_b["gunes_oran"].iloc[-1] + 1), fontsize=8, color=g.IKINCIL,
                    va="center", arrowprops=dict(arrowstyle="-", color=g.SOLUK, lw=0.8))
    axs[1].set_title("Yol B — Türkiye geneli üretim şekilleri (2014–2026)", loc="left")
    for ax in axs:
        ax.axhline(100, color=g.MUREKKEP, lw=1, ls="--")
        ax.legend(loc="lower left")
        g.eksen_sade(ax)
    axs[0].set_ylabel("Yakalanma oranı [%] (yakalanan / ortalama PTF, USD)")
    g.baslik(fig, "Güneşin yakalanma oranı düşüyor: kanibalizasyon başladı",
             "100% = baz yük ortalama fiyatı. Yakalanma oranı aynı yılın fiyatlarının oranı olduğundan kur ve enflasyondan bağımsızdır.")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK_A)
    fig.savefig(CIKTI / "yakalanma_orani_trendi.png"); plt.close(fig)


def grafik_kapasite_yakalanma(yol_b: pd.DataFrame, kurulu: dict):
    gunes = pd.Series(kurulu["gunes"]) / 1000
    oran = 100 * yol_b["gunes_oran"].dropna()
    ortak = oran.index.intersection(gunes.index)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
    axs[0].bar(gunes.index, gunes.values, 0.7, color=g.RENK_GES)
    axs[0].set_title("Türkiye kurulu güneş gücü, yıl sonu [GW]", loc="left")
    axs[0].set_xticks(gunes.index[::2])
    axs[1].plot(gunes[ortak], oran[ortak], color=g.RENK_GES, lw=1.5, marker="o", ms=7,
                markeredgecolor="white", markeredgewidth=1.5)
    for y in ortak:
        axs[1].annotate(str(y), (gunes[y], oran[y]), xytext=(6, 4), textcoords="offset points", fontsize=8, color=g.IKINCIL)
    axs[1].set_xlabel("Kurulu güneş gücü [GW]")
    axs[1].set_ylabel("Güneş yakalanma oranı [%]")
    axs[1].set_title("Kurulu güç arttıkça güneşin yakalanma oranı", loc="left")
    for ax in axs:
        g.eksen_sade(ax)
    g.baslik(fig, "Güneş kapasitesi 5 yılda 4 katına çıktı, öğle fiyatları baskılandı",
             "Sağ: Yol B güneş yakalanma oranı (USD) ile yıl sonu kurulu güç. Kurulu güç: TEİAŞ / IRENA / GENSED (config.yaml).")
    fig.tight_layout(rect=(0, 0, 1, 0.88)); g.kaynak_notu(fig, KAYNAK + " Kurulu güç: TEİAŞ, IRENA, GENSED.")
    fig.savefig(CIKTI / "gunes_kapasite_ve_yakalanma.png"); plt.close(fig)


def grafik_gun_ici(profil: pd.DataFrame, yillar: list[int]):
    """Yıllara göre gün içi fiyat profili, yıl ortalamasına bölünmüş (1 = yıl ortalaması)."""
    norm = profil.div(profil.mean(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    renkler = plt.cm.Blues(np.linspace(0.3, 1.0, len(yillar)))
    for y, r in zip(yillar, renkler):
        vurgulu = y == yillar[-1]
        ax.plot(norm.columns, norm.loc[y], color=g.MUREKKEP if vurgulu else r, lw=2.6 if vurgulu else 1.6,
                label=f"{y}" + (" (Oca–Eyl)" if vurgulu else ""))
    ax.axhline(1, color=g.MUREKKEP, lw=1, ls="--")
    ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_xlabel("Saat (TSİ)")
    ax.set_ylabel("Saatlik ortalama PTF / yıllık ortalama")
    ax.legend(ncols=2, fontsize=8, loc="lower left")
    g.eksen_sade(ax, izgara="both")
    g.baslik(fig, "Ördek eğrisi oluşuyor: öğle fiyatları akşamın çok altına indi",
             "Yıllara göre ortalama gün içi PTF profili (USD), yıl ortalamasına göre normalize")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "gun_ici_fiyat_profili.png"); plt.close(fig)


def grafik_isi_haritasi(ptf_usd: pd.Series, yil: int):
    yerel = ptf_usd.index.tz_convert("Europe/Istanbul")
    maske = yerel.year == yil
    s = ptf_usd[maske]
    t = s.groupby([yerel[maske].month, yerel[maske].hour]).mean().unstack()
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    im = ax.imshow(t.values, aspect="auto", cmap="Blues", vmin=0)
    ax.set_yticks(range(12), AYLAR)
    ax.set_xticks(range(0, 24, 3), [f"{h:02d}" for h in range(0, 24, 3)])
    ax.set_xlabel("Saat (TSİ)")
    for k in ax.spines.values():
        k.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.outline.set_visible(False)
    cb.set_label("Ortalama PTF [USD/MWh]", color=g.IKINCIL)
    g.baslik(fig, f"{yil}: bahar öğlelerinde fiyat çöküyor, akşam pik pahalı",
             f"Ay × saat ortalama PTF, {yil} (USD/MWh)")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / f"ay_saat_fiyat_isi_haritasi_{yil}.png"); plt.close(fig)


def grafik_spread(spread: pd.DataFrame):
    yil = spread.index.year
    yillar = sorted(set(yil))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    veri = [spread.loc[yil == y, "spread"].dropna().values for y in yillar]
    bp = ax.boxplot(veri, positions=yillar, widths=0.55, patch_artist=True, showfliers=False,
                    medianprops=dict(color=g.MUREKKEP, lw=1.5), whiskerprops=dict(color=g.SOLUK),
                    capprops=dict(color=g.SOLUK))
    for k in bp["boxes"]:
        k.set_facecolor("#cfe0f5"); k.set_edgecolor(g.RENK_RES)
    med4 = spread["spread_4s"].groupby(yil).median()
    ax.plot(med4.index, med4.values, color=g.RENK_RES, lw=2, marker="o", ms=5, markeredgecolor="white",
            label="Medyan: en pahalı 4 saat − en ucuz 4 saat")
    ax.set_ylabel("Günlük fiyat farkı [USD/MWh]")
    ax.set_xticks(yillar, [str(y) if y != yillar[-1] else f"{y}*" for y in yillar])
    ax.legend(loc="upper left")
    g.eksen_sade(ax)
    g.baslik(fig, "2026'da günlük fiyat farkı ortalama fiyatın 1,4 katına çıktı: batarya için zemin",
             "Kutu: günlük en yüksek − en düşük saatlik PTF dağılımı (çeyrekler arası, bıyıklar 1,5×IQR). *2026: Oca–Eyl")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "gunluk_spread.png"); plt.close(fig)


def grafik_dusuk_fiyat(dusuk: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    x = np.arange(len(dusuk)); w = 0.38
    for i, (s, renk) in enumerate(zip(dusuk.columns, ["#9ec5ef", g.RENK_RES])):
        c = ax.bar(x + (i - 0.5) * (w + 0.02), dusuk[s], w, color=renk, label=s.replace("<=", "≤"))
        ax.bar_label(c, fontsize=7, color=g.IKINCIL, padding=2)
    ax.set_xticks(x, [str(y) if y != dusuk.index[-1] else f"{y}*" for y in dusuk.index])
    ax.set_ylabel("Saat sayısı / yıl")
    ax.legend(loc="upper left")
    g.eksen_sade(ax)
    g.baslik(fig, "Çok ucuz saatler 2026'da patladı",
             "PTF'nin eşik değerin altında ya da eşit olduğu saat sayısı (USD/MWh). *2026: yalnızca Ocak–Eylül")
    fig.tight_layout(rect=(0, 0, 1, 0.9)); g.kaynak_notu(fig, KAYNAK)
    fig.savefig(CIKTI / "dusuk_fiyatli_saatler.png"); plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    cfg = config_oku()
    CIKTI.mkdir(parents=True, exist_ok=True)
    ptf = pd.read_parquet(ISLENMIS_VERI / "ptf_2014_guncel.parquet")
    tr = pd.read_parquet(ISLENMIS_VERI / "uretim_turkiye_2014_guncel.parquet")
    auf = pd.read_parquet(ISLENMIS_VERI / "auf_2022_2023.parquet")
    prof = pd.read_parquet(ISLENMIS_VERI / "ezine_profiller_2014_2023.parquet").set_index("zaman_utc")
    prof["hibrit_satilan"] = (prof["ges_kf"] + prof["res_kf"]).clip(upper=1.0)
    ezine = prof[["ges_kf", "res_kf", "hibrit_satilan"]]
    son_yil = ptf.index.tz_convert("Europe/Istanbul").year.max()

    # --- Yol A
    yol_a_usd = a.yakalanan_fiyat(ptf["ptf_usd"], ezine, "Y")
    yol_a_usd = yol_a_usd[yol_a_usd["saat"] > 8000]               # yalnızca tam yıllar
    yol_a_tl = a.yakalanan_fiyat(ptf["ptf_tl"], ezine, "Y").loc[yol_a_usd.index]
    yol_a_tl_aylik = tl_aylik_oran(ptf["ptf_tl"], ezine).loc[yol_a_usd.index]
    aylik_a = a.yakalanan_fiyat(ptf["ptf_usd"], ezine, "M")

    # AUF duyarlılığı (2022–2023): yenilenebilir üreticinin fiilen aldığı fiyat
    etkin = auf_fiyati(ptf, auf)
    auf_usd = a.yakalanan_fiyat(etkin["etkin_usd"], ezine, "Y").loc[[2022, 2023]]
    auf_tablo = pd.DataFrame({
        "Ortalama PTF [USD]": yol_a_usd.loc[[2022, 2023], "ortalama_fiyat"],
        "GES yakalanan, PTF [USD]": yol_a_usd.loc[[2022, 2023], "ges_kf_yakalanan"],
        "GES yakalanan, AUF sonrası [USD]": auf_usd["ges_kf_yakalanan"],
        "RES yakalanan, PTF [USD]": yol_a_usd.loc[[2022, 2023], "res_kf_yakalanan"],
        "RES yakalanan, AUF sonrası [USD]": auf_usd["res_kf_yakalanan"],
        "Hibrit yakalanan, PTF [USD]": yol_a_usd.loc[[2022, 2023], "hibrit_satilan_yakalanan"],
        "Hibrit yakalanan, AUF sonrası [USD]": auf_usd["hibrit_satilan_yakalanan"],
    })
    auf_saat_payi = etkin.loc[etkin["auf_donemi"]].pipe(lambda d: (ptf.loc[d.index, "ptf_tl"] > d["etkin_tl"]).mean())

    # Yol A uzantısı: profil yılları 2014–2023; 2024+ fiyat yıllarına 10 hava yılı uygulanır (ortalama ve aralık)
    son_profil_yili = int(yol_a_usd.index.max())
    yeni_yillar = list(range(son_profil_yili + 1, son_yil + 1))
    uzanti_ham = a.hava_yillari_ile_yakalanan(ptf["ptf_usd"], ezine, yeni_yillar)
    uzanti = uzanti_ham.groupby("fiyat_yili").agg(
        ortalama_fiyat=("ortalama_fiyat", "mean"),
        ges_oran=("ges_kf_oran", "mean"), ges_oran_min=("ges_kf_oran", "min"), ges_oran_max=("ges_kf_oran", "max"),
        res_oran=("res_kf_oran", "mean"), res_oran_min=("res_kf_oran", "min"), res_oran_max=("res_kf_oran", "max"),
        hibrit_oran=("hibrit_satilan_oran", "mean"), hibrit_oran_min=("hibrit_satilan_oran", "min"),
        hibrit_oran_max=("hibrit_satilan_oran", "max"),
        ges_yakalanan=("ges_kf_yakalanan", "mean"), res_yakalanan=("res_kf_yakalanan", "mean"),
        hibrit_yakalanan=("hibrit_satilan_yakalanan", "mean"))
    # Aynı yöntemin 2014–2023'te 'aynı yıl' yöntemiyle ne kadar örtüştüğünü kontrol et (yöntem farkı)
    kontrol = a.hava_yillari_ile_yakalanan(ptf["ptf_usd"], ezine, [2021, 2022, 2023]).groupby("fiyat_yili")[
        ["ges_kf_oran", "res_kf_oran", "hibrit_satilan_oran"]].mean()
    # Eşzamanlılık düzeltmesi: hava yılları karıştırılınca rüzgârlı saat ↔ düşük fiyat ilişkisi kaybolur
    # (RES ve hibrit oranı fazla çıkar). 2021–2023'te ölçülen ortalama fark uzantıdan düşülür.
    yontem_farki = (kontrol - yol_a_usd.loc[[2021, 2022, 2023], kontrol.columns]).mean()
    for kisa, uzun in [("ges", "ges_kf_oran"), ("res", "res_kf_oran"), ("hibrit", "hibrit_satilan_oran")]:
        uzanti[f"{kisa}_oran_duzeltilmis"] = uzanti[f"{kisa}_oran"] - yontem_farki[uzun]

    # Gün içi şekil duyarlılığı: ERA5 öğleden sonraki rüzgâr pikini kaçırıyor (bkz. kalibrasyon).
    # Referans santralin GÖZLENEN saatlik şekli, model ile aynı ortalamaya ölçeklenip RES profili yerine kullanılır.
    ref = cfg["kalibrasyon_santralleri"]["enerjisa_canakkale"]
    gozlenen = pd.read_parquet(ISLENMIS_VERI / "ezine_res_santralleri.parquet")["enerjisa_canakkale"] / ref["kurulu_guc_mw"]
    d = pd.concat([prof["ges_kf"], prof["res_kf"], gozlenen.rename("gozlenen")], axis=1, join="inner").dropna()
    ust = 1 - deger(cfg["uretim"]["ruzgar"]["toplam_kayip"])
    olcekli = (d["gozlenen"] * d["res_kf"].mean() / d["gozlenen"].mean()).clip(upper=ust)
    d["gozlenen_sekil"] = olcekli * d["res_kf"].mean() / olcekli.mean()
    sekil = []
    for ad, sutun in [("ERA5 modeli (k kalibreli)", "res_kf"), ("Gözlenen gün içi şekil (aynı ortalama)", "gozlenen_sekil")]:
        top = d["ges_kf"] + d[sutun]; sat = top.clip(upper=1.0)
        yk = a.yakalanan_fiyat(ptf["ptf_usd"], pd.DataFrame({"res": d[sutun], "hibrit": sat}), "Y")
        yk = yk[yk["saat"] > 8000]
        sekil.append({"RES profili": ad, "Ort. KF [%]": 100 * d[sutun].mean(),
                      "GES–RES saatlik korelasyon": d["ges_kf"].corr(d[sutun]),
                      "Hibrit kesinti [%]": 100 * (1 - sat.sum() / top.sum()),
                      "RES yakalanma oranı (10 yıl ort.)": yk["res_oran"].mean(),
                      "Hibrit yakalanma oranı (10 yıl ort.)": yk["hibrit_oran"].mean(),
                      "RES yakalanma oranı 2023": yk.loc[2023, "res_oran"]})
    sekil = pd.DataFrame(sekil)

    # --- Yol B
    gunes_bas = deger(cfg["piyasa"]["yol_b_gunes_baslangic"])
    yol_b_usd = a.yakalanan_fiyat(ptf["ptf_usd"], tr[["ruzgar", "gunes"]], "Y")
    yol_b_usd.loc[yol_b_usd.index < gunes_bas, ["gunes_yakalanan", "gunes_oran"]] = np.nan
    yol_b_tl_aylik = tl_aylik_oran(ptf["ptf_tl"], tr[["ruzgar", "gunes"]])
    yol_b_tl_aylik.loc[yol_b_tl_aylik.index < gunes_bas, "gunes"] = np.nan

    # --- Batarya göstergeleri
    profil = a.gun_ici_profil(ptf["ptf_usd"])
    spread = a.gunluk_spread(ptf["ptf_usd"])
    spread_ozet = pd.DataFrame({
        "Medyan günlük spread [USD]": spread["spread"].groupby(spread.index.year).median(),
        "P90 günlük spread [USD]": spread["spread"].groupby(spread.index.year).quantile(0.9),
        "Medyan 4s-4s spread [USD]": spread["spread_4s"].groupby(spread.index.year).median(),
        "Ort. PTF [USD]": ptf["ptf_usd"].groupby(a.yerel_donem(ptf.index)).mean(),
    })
    spread_ozet["Medyan spread / ort. PTF"] = spread_ozet["Medyan günlük spread [USD]"] / spread_ozet["Ort. PTF [USD]"]
    dusuk = a.dusuk_fiyat_saatleri(ptf["ptf_usd"], deger(cfg["piyasa"]["dusuk_fiyat_esikleri"]))
    dusuk["= 0 TL"] = (ptf["ptf_tl"] <= 0).groupby(a.yerel_donem(ptf.index)).sum()
    norm = profil.div(profil.mean(axis=1), axis=0)
    ordek = pd.DataFrame({
        "Öğle (11–15) / ortalama": norm.loc[:, 11:15].mean(axis=1),
        "Akşam (18–22) / ortalama": norm.loc[:, 18:22].mean(axis=1),
    })
    ordek["Akşam / öğle"] = ordek.iloc[:, 1] / ordek.iloc[:, 0]

    # --- Kaydet tablolar
    yol_a_cikti = pd.concat({"USD": yol_a_usd, "TL (yıllık)": yol_a_tl, "TL oranı (aylık bazda)": yol_a_tl_aylik}, axis=1)
    yol_a_cikti.to_csv(CIKTI / "yol_a_ezine_yakalanan_fiyat.csv", encoding="utf-8-sig", float_format="%.4f")
    aylik_a.to_csv(CIKTI / "yol_a_ezine_aylik.csv", encoding="utf-8-sig", float_format="%.4f")
    pd.concat({"USD": yol_b_usd, "TL oranı (aylık bazda)": yol_b_tl_aylik}, axis=1).to_csv(
        CIKTI / "yol_b_turkiye_yakalanma.csv", encoding="utf-8-sig", float_format="%.4f")
    uzanti.to_csv(CIKTI / "yol_a_ezine_2024_sonrasi_hava_yillari.csv", encoding="utf-8-sig", float_format="%.4f")
    sekil.to_csv(CIKTI / "gun_ici_sekil_duyarliligi.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    auf_tablo.to_csv(CIKTI / "auf_duyarlilik.csv", encoding="utf-8-sig", float_format="%.2f")
    spread_ozet.to_csv(CIKTI / "gunluk_spread_ozet.csv", encoding="utf-8-sig", float_format="%.2f")
    dusuk.to_csv(CIKTI / "dusuk_fiyatli_saatler.csv", encoding="utf-8-sig")
    ordek.to_csv(CIKTI / "ordek_egrisi_gostergesi.csv", encoding="utf-8-sig", float_format="%.3f")
    profil.to_csv(CIKTI / "gun_ici_fiyat_profili_usd.csv", encoding="utf-8-sig", float_format="%.2f")

    # --- Grafikler
    grafik_yol_a_usd(yol_a_usd)
    grafik_yakalanma_trendi(yol_a_usd, yol_b_usd, son_yil, uzanti)
    grafik_kapasite_yakalanma(yol_b_usd, cfg["kurulu_guc_turkiye"])
    grafik_gun_ici(profil, [2015, 2018, 2020, 2022, 2023, 2024, 2025, son_yil])
    grafik_isi_haritasi(ptf["ptf_usd"], son_yil - 1)
    grafik_spread(spread)
    grafik_dusuk_fiyat(dusuk)

    # --- Konsol özeti
    pd.set_option("display.width", 230); pd.set_option("display.float_format", lambda v: f"{v:.3f}")
    print("=== Yol A — Ezine (USD/MWh ve oran) ===")
    print(yol_a_usd.drop(columns="saat").to_string())
    print("\nTL yakalanma oranı (aylık bazda, enflasyondan arındırılmış):"); print(yol_a_tl_aylik.to_string())
    print("\n10 yıl ort. oran (USD):", yol_a_usd[["ges_kf_oran", "res_kf_oran", "hibrit_satilan_oran"]].mean().round(3).to_dict())
    print("\n=== Yol A uzantısı: 2024+ fiyatları × 10 hava yılı (ortalama [min–maks]) ===")
    print(uzanti.to_string()); print("Yöntem farkı (düşülen):", yontem_farki.round(3).to_dict())
    print("Yöntem kontrolü (2021–2023, 10 hava yılı ort. oran vs aynı yıl):")
    print(pd.concat([kontrol, yol_a_usd.loc[[2021, 2022, 2023], ["ges_kf_oran", "res_kf_oran", "hibrit_satilan_oran"]]],
                    axis=1, keys=["10 hava yılı", "aynı yıl"]).to_string())
    print("\n=== Gün içi rüzgâr şekli duyarlılığı ===")
    print(sekil.to_string(index=False))
    print("\n=== AUF duyarlılığı ===")
    print(auf_tablo.to_string()); print(f"AUF döneminde PTF > AUF olan saat payı: %{100*auf_saat_payi:.1f}")
    print("\n=== Yol B — Türkiye (USD oran) ===")
    print(yol_b_usd[["ortalama_fiyat", "ruzgar_oran", "gunes_oran", "saat"]].to_string())
    print("\nTL oranı (aylık bazda):"); print(yol_b_tl_aylik.to_string())
    print("\n=== Batarya göstergeleri ===")
    print(spread_ozet.to_string()); print(); print(dusuk.to_string()); print(); print(ordek.to_string())


if __name__ == "__main__":
    main()
