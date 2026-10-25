"""
v4 Faz H1 — Bankaya sunulabilir verim ve proje finansmanı: doğrulama ve Ezine sonuçları.

1. LP ↔ kapalı form: tek senaryo, anapara kısıtı yok → borç LP'si v1 heykelsi borç formülüyle aynı (fark ≈ 0).
2. İki tasarım (motorun seçtiği hibrit ve 50,4 MW yalnız RES): analitik ve simülasyon P değerleri, belirsizlik bütçesi.
3. Gelir yapısı başına borç: DSCR kuralları, temerrüt hedefli (PD ≤ %5), saha ölçümü sonrası; kredi metrikleri, bağlayan
   kısıtlar ve Monte Carlo şelale olasılıkları.
4. Temerrüt olasılığı – borç oranı eğrisi (kural tabanlı servis profili kaldıraç tavanına kadar ölçeklenerek).
5. Saha ölçümünün değeri: ölçüm sonrası RES model belirsizliğine göre borç kapasitesi (yalnız RES tasarımı).
Çıktılar: outputs/v4H/H1_*.csv|json|png
Çalıştırma: .venv/bin/python src/v4_H1_finansman.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR
from src.finansman import borc_lp
from src.motor import KullaniciVarsayimlari, analiz_et

CIKTI = CIKTILAR / "v4H"
SAHA = {"ad": "Ezine", "enlem": 39.79, "boylam": 26.33}
TASARIMLAR = {
    "hibrit_milp": None,
    "res_50": {"res_mw": 50.4, "ges_mw": 0.0, "bess_mw": 0.0, "bess_mwh": 0.0},
}


def lp_kapali_form() -> dict:
    """Tek senaryo, anapara kısıtı yok: LP = Σ (CFADS/DSCR)(1 + i)^−k."""
    rng = np.random.default_rng(0)
    cf = 8e6 * (1 + 0.1 * rng.standard_normal(25))
    i, V = 0.08, 15
    lp = borc_lp.boyutla({"P90": cf}, {"P90": np.full(25, 1.3)}, V, i, 1e12, 0.75, anapara_kisiti=False)
    kf = float((cf[:V] / 1.3 * (1 + i) ** -np.arange(1, V + 1)).sum())
    return {"lp_musd": lp.borc_nom / 1e6, "kapali_form_musd": kf / 1e6, "goreli_fark": lp.borc_nom / kf - 1}


def calistir(ad: str, tasarim: dict | None, ekstra: dict | None = None):
    kv = KullaniciVarsayimlari(sabit_tasarim=tasarim, ekstra=ekstra or {})
    t0 = time.perf_counter()
    s = analiz_et(SAHA, "tam", kv, onbellek_kullan=False)
    print(f"  {ad}: {time.perf_counter() - t0:.0f} s, tasarım {s.ozet['tasarim']}")
    return s


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    ozet = {"lp_kapali_form": lp_kapali_form()}
    print("LP ↔ kapalı form:", ozet["lp_kapali_form"])
    p_sat, b_sat, borc_sat, egri = [], [], [], []
    for ad, tas in TASARIMLAR.items():
        s = calistir(ad, tas)
        f = s.ozet["finansman"]
        v = f["verim"]
        ozet[ad] = {"tasarim": s.ozet["tasarim"], "e_npv": s.ozet["baz"]["e_npv"], "rho_iav": v["rho_iav"], "P50_mwh": v["P50_mwh"]}
        for x in v["p"]:
            p_sat.append({"tasarim": ad, "tur": "analitik_brut", "ufuk": x["ufuk"], "p": x["ad"], "mwh": x["mwh"], "oran": x["oran"]})
        for x in v.get("olcum_sonrasi_p") or []:
            p_sat.append({"tasarim": ad, "tur": "olcum_sonrasi", "ufuk": x["ufuk"], "p": x["ad"], "mwh": x["mwh"], "oran": x["oran"]})
        for uf, d in v["simulasyon"].items():
            for k_, m in d.items():
                p_sat.append({"tasarim": ad, "tur": "simulasyon_satilan", "ufuk": int(uf), "p": k_, "mwh": m, "oran": m / d["P50"]})
        for x in v["bilesenler"]:
            b_sat.append({"tasarim": ad, **x})
        for y, d in f["yapilar"].items():
            sl, pdh = d["selale"], d["pd_hedefli"]
            borc_sat.append(
                {
                    "tasarim": ad, "yapi": y, "vade": d["vade"], "borc_kural_musd": d["borc_reel_musd"], "oran_kural": d["borc_orani"],
                    "borc_pd5_musd": pdh["borc_reel_musd"], "oran_pd5": pdh["borc_orani"],
                    "borc_olcum_sonrasi_musd": d["olcum_sonrasi_borc_reel_musd"], "dscr_min_p50": d["dscr_min_p50"], "llcr": d["llcr"],
                    "ortalama_omur": d["ortalama_omur"], "kaldirac_bagliyor": d["kaldirac_bagliyor"],
                    "baglayan": json.dumps(d["baglayan_senaryo_yil"], ensure_ascii=False), "kredi_p50_mc_orani": d["kredi_p50_mc_orani"],
                    "p_temerrut_kural": sl["p_temerrut"], "p_dsra_kural": sl["p_dsra_kullanim"], "p_kilit_kural": sl["p_kilit"],
                    "irr_p50_kural": sl["irr_p50"], "irr_p50_pd5": pdh["selale"]["irr_p50"],
                    "sozlesmeli_pay_ilk5": d["sozlesmeli_pay_ilk5"], "batarya_pay_ilk5": d["batarya_pay_ilk5"],
                }
            )  # fmt: skip
        egri += pd_egrisi(s, ad)
    pd.DataFrame(p_sat).to_csv(CIKTI / "H1_p_degerleri.csv", index=False)
    pd.DataFrame(b_sat).to_csv(CIKTI / "H1_belirsizlik_butcesi.csv", index=False)
    borc = pd.DataFrame(borc_sat)
    borc.to_csv(CIKTI / "H1_borc.csv", index=False)
    eg = pd.DataFrame(egri)
    eg.to_csv(CIKTI / "H1_pd_egrisi.csv", index=False)
    ozet["olcum_degeri"] = olcum_degeri()
    (CIKTI / "H1_ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    grafik(eg)
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(
            borc[
                [
                    "tasarim",
                    "yapi",
                    "borc_kural_musd",
                    "oran_kural",
                    "p_temerrut_kural",
                    "borc_pd5_musd",
                    "oran_pd5",
                    "borc_olcum_sonrasi_musd",
                ]
            ].round(3)
        )
    print("Ölçüm değeri:", ozet["olcum_degeri"])


def pd_egrisi(s, ad: str) -> list[dict]:
    """Kural ve PD hedefli noktalar + motorun ürettiği temerrüt olasılığı – borç oranı eğrisi (kural profili ölçeklenerek)."""
    sat = []
    for y, d in s.ozet["finansman"]["yapilar"].items():
        sat.append({"tasarim": ad, "yapi": y, "borc_orani": d["borc_orani"], "p_temerrut": d["selale"]["p_temerrut"], "nokta": "kural"})
        p = d["pd_hedefli"]
        sat.append({"tasarim": ad, "yapi": y, "borc_orani": p["borc_orani"], "p_temerrut": p["selale"]["p_temerrut"], "nokta": "pd_hedef"})
        for k in d.get("pd_egrisi", []):
            sat.append({"tasarim": ad, "yapi": y, "borc_orani": k["borc_orani"], "p_temerrut": k["p_temerrut"], "nokta": "egri"})
    return sat


def olcum_degeri() -> list[dict]:
    """Yalnız RES tasarımında ölçüm sonrası RES model belirsizliğine göre borç kapasitesi (DSCR kuralları)."""
    sat = []
    for sm in (0.04, 0.06, 0.08, 0.10):
        s = calistir(f"res_50 σ_ölçüm={sm}", TASARIMLAR["res_50"], {"v4.verim.value.olcumlu_model": sm})
        for y, d in s.ozet["finansman"]["yapilar"].items():
            sat.append(
                {"sigma_olcum": sm, "yapi": y, "borc_atlas_musd": d["borc_reel_musd"], "borc_olcum_musd": d["olcum_sonrasi_borc_reel_musd"]}
            )
    pd.DataFrame(sat).to_csv(CIKTI / "H1_olcum_degeri.csv", index=False)
    return sat


def grafik(eg: pd.DataFrame) -> None:
    e = eg[eg["nokta"] == "egri"]
    if e.empty:
        return
    fig, ax = plt.subplots(1, len(e["tasarim"].unique()), figsize=(11, 4), sharey=True)
    ax = np.atleast_1d(ax)
    for a, (tas, g) in zip(ax, e.groupby("tasarim"), strict=False):
        for y, gg in g.groupby("yapi"):
            a.plot(100 * gg["borc_orani"], 100 * gg["p_temerrut"], label=y)
        a.axhline(5, color="grey", ls=":", lw=1)
        a.set_title(f"{tas}: temerrüt olasılığı – borç oranı")
        a.set_xlabel("Borç / CAPEX (%)")
        a.legend(fontsize=8)
    ax[0].set_ylabel("Vade boyunca temerrüt olasılığı (%)")
    fig.tight_layout()
    fig.savefig(CIKTI / "H1_pd_egrisi.png", dpi=130)


if __name__ == "__main__":
    main()
