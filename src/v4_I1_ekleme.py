"""
v4 Faz I1 — Mevcut RES'lere GES / batarya ekleme: Türkiye taraması, örnek santraller ve doğrulama.

1. Tarama: atlasın kalibre santrallerinin hepsi (hafif_tarama: profil + GES başabaş CAPEX'i + temsilî günlü MILP).
   → data/atlas/v4_ekleme_tarama.csv (anonim kod; uygulamanın tarama haritası) ve outputs/v4I/I1_tarama.csv
2. Örnek santraller (tam analiz, Monte Carlo): taramada GES'e en yatkın, medyan ve en az yatkın santral + eski YEKDEM'li bir
   varyant; GES CAPEX duyarlılığı (çarpan 0,6 / 0,8 / 1,0). → outputs/v4I/I1_ornekler.csv
3. Doğrulama: (a) santral kalibrasyonu: model KF ↔ gözlenen KF (tüm santraller); (b) CSV ölçekleme: modelin kendi profili
   %10 artırılıp CSV olarak verilince ölçekli KF ≈ 1,10 × model; (c) ortak rastgele sayıların varyans azaltması.
   → outputs/v4I/I1_dogrulama.json
Çalıştırma: .venv/bin/python src/v4_I1_ekleme.py [--tarama-yok]
"""

import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK
from src.ekleme.analiz import EklemeVarsayimlari, csv_olcekle, ekleme_analizi, hafif_tarama
from src.ekleme.santraller import liste

CIKTI = CIKTILAR / "v4I"


def tarama() -> pd.DataFrame:
    sat = []
    t0 = time.perf_counter()
    for i, kod in enumerate(liste().index):
        try:
            sat.append(hafif_tarama(kod))
        except Exception as ex:  # tek santralin veri sorunu taramayı durdurmasın
            print(f"  {kod}: {type(ex).__name__}: {ex}")
        if (i + 1) % 10 == 0:
            print(f"  {i + 1} santral, {time.perf_counter() - t0:.0f} s")
    d = pd.DataFrame(sat)
    d.to_csv(CIKTI / "I1_tarama.csv", index=False)
    d.round(4).to_csv(KOK / "data" / "atlas" / "v4_ekleme_tarama.csv", index=False)
    return d


def ornekler(d: pd.DataFrame) -> pd.DataFrame:
    s = d.sort_values("ges_basabas_capex")
    secim = {"en_yatkin": s.iloc[-1]["kod"], "medyan": s.iloc[len(s) // 2]["kod"], "en_az_yatkin": s.iloc[0]["kod"]}
    sat = []
    for rol, kod in secim.items():
        for cg in (0.6, 0.8, 1.0):
            for yek in (None, 2029):
                if yek and cg != 1.0:
                    continue
                r = ekleme_analizi(EklemeVarsayimlari(kod=kod, capex_carpani_ges=cg, yekdem_bitis_yili=yek), onbellek_kullan=False)
                m = r["metrik"][r["en_iyi_yapi"]]
                sat.append(
                    {
                        "rol": rol, "kod": kod, "il": r["santral"]["il"], "kurulu_mw": r["santral"]["kurulu_mw"], "ges_capex_carpani": cg,
                        "yekdem_bitis": yek, "ges_mw": r["tasarim"]["ges_mw"], "bess_mw": r["tasarim"]["bess_mw"], "bess_mwh": r["tasarim"]["bess_mwh"],
                        "en_iyi_yapi": r["en_iyi_yapi"], "e_npv": m["e_npv"], "se": m["se"], "se_bagimsiz": m["se_bagimsiz"],
                        "varyans_azaltma": m["varyans_azaltma"], "p_pozitif": m["p_pozitif"], "cvar5": m["cvar5"],
                        "baglanti_once": r["isletme"]["res"]["baglanti_kullanim"], "baglanti_sonra": r["isletme"]["ek"]["baglanti_kullanim"],
                        "kesinti_once": r["isletme"]["res"]["kesinti_orani"], "kesinti_sonra": r["isletme"]["ek"]["kesinti_orani"],
                        "korelasyon": r["santral"]["saatlik_korelasyon"], "sure_s": r["sure_s"]["toplam"],
                    }
                )  # fmt: skip
                print(
                    f"  {rol} {kod} cg={cg} yek={yek}: GES {r['tasarim']['ges_mw']} BESS {r['tasarim']['bess_mw']} E[NPV] {m['e_npv']:+.2f}"
                )
    o = pd.DataFrame(sat)
    o.to_csv(CIKTI / "I1_ornekler.csv", index=False)
    return o


def dogrulama(d: pd.DataFrame | None) -> dict:
    from src.motor import KullaniciVarsayimlari
    from src.motor.ortak import hazirla

    s = liste()
    sonuc = {}
    if d is not None and len(d):
        x = d.merge(s[["gozlenen_kf"]], left_on="kod", right_index=True)
        fark = 100 * (x["res_kf"] - x["gozlenen_kf"])
        sonuc["kalibrasyon"] = {"n": len(x), "ort_fark_puan": float(fark.mean()), "mutlak_medyan_puan": float(fark.abs().median()),
                                "mutlak_azami_puan": float(fark.abs().max())}  # fmt: skip
    r = s.iloc[0]
    kv = KullaniciVarsayimlari(kalibrasyon=f"santral:{int(r.epias_id)}", turbin=r.turbin, gobek=float(r.gobek), yerlesim_bakim=False,
                               turbin_yerlesimi=False, baglanti_mw=float(np.clip(r.kurulu_mw, 5, 300)))  # fmt: skip
    h = hazirla({"ad": "x", "enlem": r.enlem, "boylam": r.boylam}, kv)
    sentetik = (h.profil["res_kf"] * 1.10 * r.kurulu_mw).loc["2021":"2022"]
    _, b = csv_olcekle(h.profil["res_kf"], sentetik, float(r.kurulu_mw))
    sonuc["csv_olcekleme"] = {**b, "oran": b["olcekli_kf"] / b["model_kf"], "beklenen": 1.10}
    (CIKTI / "I1_dogrulama.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    return sonuc


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    if "--tarama-yok" in sys.argv:
        d = pd.read_csv(CIKTI / "I1_tarama.csv")
    else:
        print("1. Tarama")
        d = tarama()
    print(d.describe().round(3).T[["mean", "50%", "min", "max"]])
    print("2. Örnek santraller")
    o = ornekler(d)
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(
            o[
                [
                    "rol",
                    "kod",
                    "ges_capex_carpani",
                    "yekdem_bitis",
                    "ges_mw",
                    "bess_mw",
                    "en_iyi_yapi",
                    "e_npv",
                    "p_pozitif",
                    "varyans_azaltma",
                ]
            ].round(3)
        )
    print("3. Doğrulama:", dogrulama(d))


if __name__ == "__main__":
    main()
