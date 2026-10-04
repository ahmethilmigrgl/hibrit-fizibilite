"""
Nihai baz vaka (config.yaml → nihai_baz_vaka): tüm ana sayıların tek kaynağı.

Monte Carlo (doyum + sistem kesintisi + ortak batarya sürücüsü) NPV dağılımları, takvimden gelen COD gecikmesi için
(k yıl; kesirliyse komşu tam yıllar arasında simülasyon bazında doğrusal ara değerleme) değerlendirilir:
E[NPV], P(NPV>0), CVaR %5, P10/P90 ve azami edinim primi (= max(E[NPV], 0)). Edinim primi parametresi NPV'den düşülür.

Ayrıca üç tutarlılık düzeltmesinin (YEKDEM yıllık opsiyonu, ortak batarya sürücüsü, inşaata hazır takvim) etkisi:
sıralı (şelale) ve her biri tek başına.

Girdi: outputs/07/gelir_yapilari_npv_erteleme.npz (+ ortak_surucu_kapali/), takvim_ozet.csv (+ _duzeltme_oncesi)
Çıktı: outputs/07/baz_vaka.csv, baz_vaka_duzeltmeler.csv; results/ kopyaları
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger

CIKTI = CIKTILAR / "07"
YAPILAR = {"yekdem_opsiyon": ("GYo", "YEKDEM yıllık opsiyonu (nominal) + tüccar"),
           "yekdem_opsiyon_endeksli": ("GYoe", "YEKDEM yıllık opsiyonu (endeksli) + tüccar"),
           "yekdem_nominal_sabit": ("GY", "YEKDEM 10 yıl sabit (nominal)"),
           "ppa": ("GP", "PPA (%70 P90, 12 yıl)"), "tuccar": ("G", "Tüccar")}
MODEL_COD = pd.Timestamp("2028-01-01")


def gecikme(takvim_csv: Path) -> tuple[float, str]:
    t = pd.read_csv(takvim_csv)
    r = t[(t["Proje olgunluğu"] == "İnşaata hazır proje") & t["Politika"].str.startswith("B1")].iloc[0]
    cod = pd.Timestamp(r["RES COD P50"] + "-01")
    return (cod - MODEL_COD).days / 365.25, r["RES COD P50"]


def dagilim(z, kod: str, k: float) -> np.ndarray:
    k0 = int(np.floor(k)); w = k - k0
    a = z[f"{kod}_k{k0}"].astype(float)
    return a if w < 1e-9 else (1 - w) * a + w * z[f"{kod}_k{k0 + 1}"].astype(float)


def metrik(x: np.ndarray, prim: float) -> dict:
    x = x - prim
    kotu = np.sort(x)[: int(0.05 * len(x))]
    return {"Beklenen NPV [M USD]": x.mean(), "P(NPV > 0) [%]": 100 * (x > 0).mean(), "CVaR %5 [M USD]": kotu.mean(),
            "NPV P10 [M USD]": np.percentile(x, 10), "NPV P90 [M USD]": np.percentile(x, 90),
            "Azami edinim primi [M USD]": max(x.mean() + prim, 0.0)}


def main():
    cfg = config_oku()
    b = deger(cfg["nihai_baz_vaka"])
    prim = float(b["edinim_primi_musd"])
    z = np.load(CIKTI / "gelir_yapilari_npv_erteleme.npz")
    z_kap = np.load(CIKTI / "ortak_surucu_kapali" / "gelir_yapilari_npv_erteleme.npz")
    k, cod = gecikme(CIKTI / "takvim_ozet.csv")
    k_eski, cod_eski = gecikme(CIKTI / "takvim_ozet_duzeltme_oncesi.csv")
    k_eski = 2.0                                           # önceki baz vaka yıllık modelde COD 2030 (k = 2) kullanıyordu
    met = pd.read_csv(CIKTI / "gelir_yapilari_metrikler.csv").set_index("Seçenek")

    satir = []
    for anahtar in [b["gelir_yapisi"]] + list(b["karsilastirma"]):
        kod, ad = YAPILAR[anahtar]
        m = met[met.index.str.startswith(f"{kod}:")].iloc[0]
        satir.append({"Senaryo": ad, "Baz vaka": anahtar == b["gelir_yapisi"], "COD": cod,
                      **metrik(dagilim(z, kod, k), prim),
                      "E[NPV], COD 2028 (model takvimi) [M USD]": float(z[f"{kod}_k0"].mean()) - prim,
                      "Borç kapasitesi, muhafazakâr [M USD]": m["Borç kapasitesi, muhafazakâr [M USD]"],
                      "P(DSCR < 1), muhafazakâr borç [%] (COD 2028)": m["P(DSCR < 1), muhafazakâr borç [%]"],
                      "SFK geliri, ilk 10 yıl [M USD/yıl]": m["SFK geliri, ilk 10 yıl [M USD/yıl]"]})
    df = pd.DataFrame(satir)
    df.to_csv(CIKTI / "baz_vaka.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    (KOK / "results").mkdir(exist_ok=True)
    df.to_csv(KOK / "results" / "baz_vaka.csv", encoding="utf-8-sig", index=False, float_format="%.3f")

    # Düzeltmelerin etkisi: önceki baz vaka = YEKDEM sabit nominal, sürücüler bağımsız, COD 2030 (k = 2)
    adimlar = [("Önceki baz vaka (YEKDEM 10 yıl sabit nominal, bağımsız sürücüler, COD 2030)", dagilim(z_kap, "GY", k_eski)),
               ("+ (1) YEKDEM yıllık opsiyonu + tüccar", dagilim(z_kap, "GYo", k_eski)),
               ("+ (2) ortak batarya sürücüsü", dagilim(z, "GYo", k_eski)),
               (f"+ (3) inşaata hazır takvim (COD {cod})", dagilim(z, "GYo", k))]
    sel = []
    onceki = None
    for ad, x in adimlar:
        mt = metrik(x, prim)
        sel.append({"Adım": ad, **mt, "Adımın katkısı (E[NPV]) [M USD]": np.nan if onceki is None else mt["Beklenen NPV [M USD]"] - onceki})
        onceki = mt["Beklenen NPV [M USD]"]
    tek = {"(1) yalnız YEKDEM opsiyonu": dagilim(z_kap, "GYo", k_eski).mean() - dagilim(z_kap, "GY", k_eski).mean(),
           "(2) yalnız ortak sürücü": dagilim(z, "GY", k_eski).mean() - dagilim(z_kap, "GY", k_eski).mean(),
           "(3) yalnız takvim": dagilim(z_kap, "GY", k).mean() - dagilim(z_kap, "GY", k_eski).mean()}
    sel = pd.DataFrame(sel)
    sel["Tek başına etkisi (önceki baz vakaya göre) [M USD]"] = [np.nan, tek["(1) yalnız YEKDEM opsiyonu"],
                                                                tek["(2) yalnız ortak sürücü"], tek["(3) yalnız takvim"]]
    sel.to_csv(CIKTI / "baz_vaka_duzeltmeler.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    sel.to_csv(KOK / "results" / "baz_vaka_duzeltmeler.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    opsiyon_degeri = {"model takvimi": float(z["GYo_k0"].mean() - z["G_k0"].mean()),
                      "baz vaka takvimi": float(dagilim(z, "GYo", k).mean() - dagilim(z, "G", k).mean()),
                      "endeksli, baz vaka takvimi": float(dagilim(z, "GYoe", k).mean() - dagilim(z, "G", k).mean())}
    pd.Series(opsiyon_degeri, name="YEKDEM opsiyonunun değeri (opsiyonlu − tüccar) [M USD]").to_csv(
        CIKTI / "yekdem_opsiyon_degeri.csv", encoding="utf-8-sig", float_format="%.3f")
    # --- Bilginin değeri ve durum tespiti (DD) bütçesi: karar = edin / edinme (NPV < 0 ise vazgeç)
    from src.ayarlar import deger as d_
    from src.risk.doyum import ornekle_doyum
    x = dagilim(z, "GYo", k) - prim
    ev = max(x.mean(), 0.0)
    evpi = np.maximum(x, 0).mean() - ev
    def evppi_grup(etiket):
        return sum((etiket == g_).mean() * max(x[etiket == g_].mean(), 0.0) for g_ in np.unique(etiket)) - ev
    st_ = cfg["stres_testi"]; N_ext = 33
    yil_ext = np.arange(2028, 2028 + N_ext)
    fo = float(pd.read_csv(CIKTILAR / "05_risk" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
    senaryo = ornekle_doyum(cfg, len(x), yil_ext, fo, d_(cfg["monte_carlo"]["tohum"]))["senaryo"]
    dt = d_(cfg["durum_tespiti"])
    p_t, kayip_t = dt["tesvik_ret_olasiligi"], dt["tesvik_kaybi_musd"]
    p_o, kayip_o = dt["ornitoloji_olasiligi"], dt["ornitoloji_kaybi_musd"]
    ikili = lambda p_, kayip: p_ * max(kayip - x.mean(), 0.0)    # olumsuz cevap gelirse NPV < 0 → vazgeçilir, kayıp önlenir
    bilgi = {
        "EVPI (tüm belirsizlik) [M USD]": evpi,
        "EVPPI — TEİAŞ SFK kabulü (katılamama senaryosu) [M USD]": evppi_grup(senaryo == "katilamama"),
        "EVPPI — batarya doyum senaryosu [M USD]": evppi_grup(senaryo),
        "EVPPI — teşvik belgesi (KDV) [M USD]": ikili(p_t, kayip_t),
        "EVPPI — ornitoloji (göç dönemi durdurma) [M USD]": ikili(p_o, kayip_o),
        "EVPPI — YEKDEM endeksleme (karar değişmez: iki varyantta da E[NPV] > 0) [M USD]": 0.0,
    }
    # COD / takvim teyidi: inşaata hazır COD dağılımı → koşullu E[NPV] (gecikme eğrisi), karar edin/edinme
    cods = np.load(CIKTI / "takvim_cod_ornekleri.npz")["insaata_hazir_B1_cod"]
    kk = np.clip((cods - 15) / 12, 0, 3)
    egri_ = np.array([z[f"GYo_k{j}"].mean() for j in range(4)]) - prim
    e_k = np.interp(kk, np.arange(4), egri_)
    bilgi["EVPPI — COD / takvim teyidi [M USD]"] = np.maximum(e_k, 0).mean() - max(e_k.mean(), 0.0)
    dd_kalem = [k_ for k_ in bilgi if k_.startswith("EVPPI") and "doyum senaryosu" not in k_]
    bilgi["Durum tespiti kalemlerinin EVPPI toplamı (doyum hariç: DD ile çözülemez) [M USD]"] = sum(bilgi[k_] for k_ in dd_kalem)
    bilgi["Önerilen DD bütçesi tavanı [M USD]"] = min(bilgi["Durum tespiti kalemlerinin EVPPI toplamı (doyum hariç: DD ile çözülemez) [M USD]"], evpi)
    pd.Series(bilgi, name="değer").to_csv(CIKTI / "durum_tespiti_bilgi_degeri.csv", encoding="utf-8-sig", float_format="%.3f")
    pd.Series(bilgi, name="değer").to_csv(KOK / "results" / "durum_tespiti_bilgi_degeri.csv", encoding="utf-8-sig", float_format="%.3f")
    print(pd.Series(bilgi).round(3).to_string())
    pd.set_option("display.width", 250)
    print(f"COD P50 {cod} → gecikme {k:.2f} yıl")
    print(df.round(2).to_string(index=False)); print(sel.round(2).to_string(index=False)); print(opsiyon_degeri)


if __name__ == "__main__":
    main()
