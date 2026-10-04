"""
Aşama 6 — Dashboard ve rapor için küçük, toplulaştırılmış sonuç dosyaları (results/, repoya girer).

Ham ve işlenmiş veri (data/) repoya girmez; dashboard yalnızca buradaki dosyalarla çalışır.
Ayrıca tasarım gezgininin yaklaşım hatası ölçülür (temsilî hava yılı + ızgara ara değerlemesi vs Aşama 5 tam model).

Çalıştırma: .venv/bin/python src/06_sonuclari_paketle.py  (Aşama 5 ve src/06_gezgin_tablolari.py'den sonra)
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, ISLENMIS_VERI, KOK, config_oku, deger
from src.risk.gezgin import gezgin_degerle, gezgin_yukle

R = KOK / "results"


def kopyala(kaynak: Path, ad: str | None = None):
    if kaynak.exists():
        shutil.copy(kaynak, R / (ad or kaynak.name))
    else:
        print(f"  UYARI: {kaynak} yok, atlandı")


def varsayim_tablosu(cfg: dict) -> pd.DataFrame:
    """config.yaml'daki {value, birim, kaynak, not} kayıtlarını düz bir tabloya çevirir."""
    satir = []

    def gez(d, yol):
        if isinstance(d, dict) and "value" in d:
            deg = d["value"]
            satir.append({"Bölüm": yol[0], "Parametre": ".".join(yol[1:]) or yol[0],
                          "Değer": json.dumps(deg, ensure_ascii=False) if isinstance(deg, (dict, list)) else deg,
                          "Birim": d.get("birim", ""), "Kaynak": d.get("kaynak", ""), "Not": d.get("not", "")})
        elif isinstance(d, dict):
            for k, v in d.items():
                gez(v, yol + [k])
    for k in ["proje", "saha", "uretim", "finans", "borc", "teknoloji", "fiyat_senaryolari", "duzenleme", "gelir_yigini",
              "monte_carlo", "stres_testi", "kesinti", "yekdem", "tesvik", "karbon", "takvim"]:
        gez(cfg[k], [k])
    df = pd.DataFrame(satir)
    df["Değer"] = df["Değer"].astype(str)
    return df


def main():
    R.mkdir(exist_ok=True)
    cfg = config_oku()
    print("Saha ve üretim...")
    kopyala(CIKTILAR / "01_saha_taramasi" / "saha_karsilastirma.csv", "saha_tarama.csv")
    kopyala(CIKTILAR / "01_uretim_modeli" / "p50_p90_ozet.csv", "p50_p90_ozet.csv")
    kopyala(CIKTILAR / "02_piyasa" / "kalibrasyon_gun_ici_profil.csv", "kalibrasyon_gun_ici.csv")
    kopyala(CIKTILAR / "02_piyasa" / "revizyon_karsilastirma.csv", "revizyon_karsilastirma.csv")
    prof = pd.read_parquet(ISLENMIS_VERI / "ezine_profiller_2014_2023.parquet")
    z = pd.to_datetime(prof["zaman_utc"], utc=True) + pd.Timedelta(hours=3)        # TSİ
    prof = prof.assign(yil=z.dt.year, ay=z.dt.month, saat=z.dt.hour)
    prof = prof[(prof.yil >= 2014) & (prof.yil <= 2023)]
    aylik = prof.groupby(["yil", "ay"])[["ges_kf", "res_kf"]].mean().groupby("ay")
    pd.concat({"ortalama": aylik.mean(), "p10": aylik.quantile(0.1), "p90": aylik.quantile(0.9)}, axis=1).round(4).to_csv(
        R / "profil_aylik.csv", encoding="utf-8-sig")
    mevsim = prof.ay.map({12: "Kış", 1: "Kış", 2: "Kış", 3: "İlkbahar", 4: "İlkbahar", 5: "İlkbahar", 6: "Yaz", 7: "Yaz", 8: "Yaz",
                          9: "Sonbahar", 10: "Sonbahar", 11: "Sonbahar"})
    prof.assign(mevsim=mevsim).groupby(["mevsim", "saat"])[["ges_kf", "res_kf"]].mean().round(4).to_csv(R / "profil_gun_ici.csv", encoding="utf-8-sig")
    yillik = prof.groupby("yil")[["ges_kf", "res_kf"]].mean().round(4)
    yillik.to_csv(R / "profil_yillik.csv", encoding="utf-8-sig")

    print("Piyasa...")
    kopyala(CIKTILAR / "02_piyasa" / "gun_ici_fiyat_profili_usd.csv", "fiyat_gun_ici.csv")
    kopyala(CIKTILAR / "02_piyasa" / "dusuk_fiyatli_saatler.csv")
    kopyala(CIKTILAR / "02_piyasa" / "ordek_egrisi_gostergesi.csv")
    yb = pd.read_csv(CIKTILAR / "02_piyasa" / "yol_b_turkiye_yakalanma.csv", header=[0, 1], index_col=0)
    ya = pd.read_csv(CIKTILAR / "02_piyasa" / "yol_a_ezine_yakalanan_fiyat.csv", header=[0, 1], index_col=0)
    yak = pd.DataFrame({"PTF ortalama [USD/MWh]": yb[("USD", "ortalama_fiyat")],
                        "Türkiye rüzgâr yakalanma oranı": yb[("USD", "ruzgar_oran")],
                        "Türkiye güneş yakalanma oranı": yb[("USD", "gunes_oran")],
                        "Ezine GES (model) yakalanma oranı": ya[("USD", "ges_kf_oran")],
                        "Ezine RES (model) yakalanma oranı": ya[("USD", "res_kf_oran")]})
    yak.index = yak.index.astype(str).str[:4]; yak.index.name = "yil"
    yak.round(4).to_csv(R / "yakalanma_trend.csv", encoding="utf-8-sig")
    yh = pd.read_parquet(ISLENMIS_VERI / "yan_hizmet_2023_guncel.parquet")
    yh.index = yh.index + pd.Timedelta(hours=3)
    yh.groupby(yh.index.strftime("%Y-%m"))[["sfk_fiyat_usd", "pfk_fiyat_usd", "ptf_usd", "sfk_miktar", "pfk_miktar"]].mean().round(2).to_csv(
        R / "yan_hizmet_aylik.csv", encoding="utf-8-sig")

    print("Finans, optimizasyon, risk...")
    kopyala(CIKTILAR / "03_finans" / "konfigurasyon_baz.csv")
    kopyala(CIKTILAR / "03_finans" / "tornado_b.csv")
    kopyala(CIKTILAR / "04_optimizasyon" / "b4_senaryo_tasarimlari.csv")
    for f in ["a3_yeniden_optimizasyon.csv", "s_metrikler.csv", "s_senaryo_npv.csv", "s_senaryo_npv_deterministik.csv", "s_pencere.csv",
              "s_minimum_pencere.csv", "s_erteleme.csv", "s_varyans_katkisi.csv", "s_sfk_carpan_yollari.csv", "s_firsat_maliyeti.csv",
              "s_npv_ornekleri.npz", "b_fiyat_yolu_yuzdelik.csv"]:
        kopyala(CIKTILAR / "05_risk" / f)
    kopyala(CIKTILAR / "05_risk" / "revizyon_oncesi" / "b_metrikler.csv", "b_metrikler_revizyon_oncesi.csv")
    kopyala(CIKTILAR / "05_risk" / "revizyon_oncesi" / "b_varyans_katkisi.csv", "b_varyans_katkisi_revizyon_oncesi.csv")
    for f in ["takvim_ozet.csv", "takvim_aktiviteler.csv", "takvim_cod_ornekleri.npz", "gelir_yapilari_metrikler.csv",
              "kesinti_sistem_yat_yillik.csv", "kesinti_referans_santraller.csv", "co2.csv", "tesvik_etkisi.csv", "risk_kaydi.csv", "baz_vaka.csv"]:
        kopyala(CIKTILAR / "07" / f)
    varsayim_tablosu(cfg).to_csv(R / "varsayimlar.csv", encoding="utf-8-sig", index=False)

    # --- Gezgin meta + yaklaşım hatası (Aşama 5 tam model ile karşılaştırma)
    print("Gezgin yaklaşım hatası...")
    fm = pd.read_csv(CIKTILAR / "05_risk" / "s_firsat_maliyeti.csv", index_col=0)["deger"]
    spec = importlib.util.spec_from_file_location("gy", Path(__file__).parent / "05_gelir_yigini.py")
    gy = importlib.util.module_from_spec(spec); spec.loader.exec_module(gy)
    o = gy.Ortam()
    yh_cfg = cfg["gelir_yigini"]["yan_hizmet"]
    meta = {"firsat_oran": float(fm["Fırsat maliyeti / 2026 seviyesi"]), "firsat_usd": float(fm["Fırsat maliyeti [USD/MW-saat]"]),
            "sfk_2026": float(fm["2026 SFK seviyesi [USD/MW-saat]"]), "oran0": float(o.oran0),
            "kan_taban": float(o.kan_taban), "a5_azalma": float(deger(yh_cfg["yillik_azalma"])), "a5_taban": float(deger(yh_cfg["taban_oran"]))}
    (R / "gezgin_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    a3 = pd.read_csv(CIKTILAR / "05_risk" / "a3_yeniden_optimizasyon.csv")
    gz = gezgin_yukle(R)
    kontrol = []
    for ad, satir, tur, ges, p, e, sfk in [("RES 58,8 (Aşama 4)", 0, 14, 0, 0, 0, "kapali"),
                                          ("RES 58,8 + BESS 40/70 + SFK (Aşama 5 C)", 1, 14, 0, 39.97, 69.98, "asama5")]:
        r = gezgin_degerle(gz, cfg, tur, ges, p, e, seviye=58.0, kanibalizasyon="devam", sfk=sfk, ppa=False)
        kontrol.append({"Tasarım": ad, "Gezgin NPV [M USD]": r["npv"], "Tam model NPV [M USD]": float(a3.loc[satir, "NPV [M USD]"]),
                        "Fark [M USD]": r["npv"] - float(a3.loc[satir, "NPV [M USD]"])})
    kontrol = pd.DataFrame(kontrol)
    kontrol.to_csv(R / "gezgin_hata.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    print(kontrol.round(2).to_string(index=False))

    boyut = sum(f.stat().st_size for f in R.iterdir()) / 1e6
    print(f"results/: {len(list(R.iterdir()))} dosya, {boyut:.2f} MB")


if __name__ == "__main__":
    main()
