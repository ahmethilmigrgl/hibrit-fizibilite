"""
v4 Faz K1 — Merit order fiyat modeli: kalibrasyon, örneklem dışı doğrulama, 2026–2050 projeksiyonu ve motor parametreleri.

1. Kalibrasyon: θ (arz eğrisi şekli) 2018–2023'te bağıl saatlik RMSE ile (Nelder–Mead); aylık gaz yakıt maliyeti G_m ve yıllık
   kömür bandı C_y her yıl için en küçük kareler.
2. Doğrulama: 2024–2025 örneklem dışı (θ sabit, yalnız G_m ve C_y): yıllık R², RMSE, gün içi profil korelasyonu, güneş ve rüzgâr
   yakalanma oranları, sıfır fiyatlı saatler. Ayrıca θ'nın kalibrasyon dönemine duyarlılığı (2020–2023).
3. Projeksiyon: config v4.merit.senaryolar (baz, hızlı dönüşüm, yavaş) 2026–2050; gün içi fiyat profilleri.
4. Duyarlılık (baz senaryo): gaz fiyatı ±%30, depolama ×0 / ×2, karbon ×0 / ×2.
5. Motor parametreleri: seviyelendirilmiş fiyat ve kanibalizasyon yolu (KullaniciVarsayimlari(fiyat_kaynagi="merit:<ad>")).
Çıktılar: outputs/v4K/K1_*.csv|json|png, data/atlas/v4_merit.json
Çalıştırma: .venv/bin/python src/v4_K1_merit_order.py [--hizli]
"""

import copy
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.merit import kalibrasyon as K
from src.merit import projeksiyon as P
from src.merit.model import Teta
from src.merit.veri import tarihsel

CIKTI = CIKTILAR / "v4K"


def gunici(taban, sen_ad: str, t: Teta, HR: float, yillar=(2026, 2030, 2035, 2040)) -> dict:
    cfg = config_oku()
    sen = deger(cfg["v4"]["merit"])["senaryolar"][sen_ad]
    out = {}
    for y in yillar:
        r = P.yil_simule(taban, sen, y, t, HR, cfg)
        sat = []
        for s, p in zip(taban["sekil"].values(), r["_saatlik"], strict=True):
            saat = (s["zaman"].tz_convert("Europe/Istanbul").hour if s["zaman"].tz is not None else s["zaman"].hour).to_numpy()
            sat.append(pd.Series(p).groupby(saat).mean().to_numpy())
        out[str(y)] = np.mean(sat, axis=0).round(2).tolist()
    return out


def duyarlilik(taban, t: Teta, HR: float) -> pd.DataFrame:
    cfg = config_oku()
    m = deger(cfg["v4"]["merit"])
    temel = m["senaryolar"]["baz"]
    degisim = {
        "Baz": {},
        "Gaz −%30": {"gaz_usd_mwh_th": {k: v * 0.7 for k, v in temel["gaz_usd_mwh_th"].items()}},
        "Gaz +%30": {"gaz_usd_mwh_th": {k: v * 1.3 for k, v in temel["gaz_usd_mwh_th"].items()}},
        "Depolama yok": {"depolama_gw": {k: 0.0 for k in temel["depolama_gw"]}},
        "Depolama ×2": {"depolama_gw": {k: 2 * v for k, v in temel["depolama_gw"].items()}},
        "Karbon yok": {"karbon_usd_t": {k: 0.0 for k in temel["karbon_usd_t"]}},
        "Karbon ×2": {"karbon_usd_t": {k: 2 * v for k, v in temel["karbon_usd_t"].items()}},
        "Talep %2/yıl": {"talep_buyume": 0.02},
    }
    sat = []
    for ad, d in degisim.items():
        sen = {**copy.deepcopy(temel), **d}
        df = pd.DataFrame(
            [{k: v for k, v in P.yil_simule(taban, sen, y, t, HR, cfg).items() if not k.startswith("_")} for y in (2030, 2035, 2040)]
        ).set_index("yil")
        for y, r in df.iterrows():
            sat.append({"duyarlilik": ad, "yil": y, "ort_fiyat": r["ort_fiyat"], "gunes_yakalanma": r["gunes_yakalanma"], "ruzgar_yakalanma": r["ruzgar_yakalanma"],
                        "sifir_saat": r["sifir_saat"]})  # fmt: skip
    return pd.DataFrame(sat)


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    m = deger(cfg["v4"]["merit"])
    HR = m["baslangic"]["HR_min"]
    d = tarihsel(m["kalibrasyon_yillari"][0], m["test_yillari"][1])
    k1, k2 = m["kalibrasyon_yillari"]
    print("1. Kalibrasyon", k1, "–", k2)
    t0 = Teta(5.0, 1.15, 0.4, -1.5, 3100.0, 0.43, 7.9, 1.4)  # önceki turdan sıcak başlangıç (config başlangıcından kalibre edildi)
    it = 300 if "--hizli" in sys.argv else 800
    t, info = K.kalibre(d[(d["yil"] >= k1) & (d["yil"] <= k2)], t0, HR, maxiter=it)
    print("   θ:", t, info)
    s = K.seviyeler(d, t, HR)
    met = K.metrikler(d, s["p"])
    met["donem"] = np.where(met.index <= k2, "kalibrasyon", "test")
    print(met.round(3).to_string())
    # Kalibrasyon dönemine duyarlılık: θ 2020–2023 ile
    t2, _ = K.kalibre(d[(d["yil"] >= 2020) & (d["yil"] <= k2)], t, HR, maxiter=it // 2)
    met2 = K.metrikler(d, K.seviyeler(d, t2, HR)["p"])
    print("   θ (2020–2023):", t2)
    print("3. Projeksiyon")
    taban = P.taban_hazirla(d, s["G"], s["C"])
    proj, motor, gi = {}, {}, {}
    for ad in m["senaryolar"]:
        df = P.senaryo_calistir(taban, ad, t, HR)
        proj[ad] = df
        motor[ad] = P.motor_parametreleri(df, cfg)
        gi[ad] = gunici(taban, ad, t, HR)
        print(f"   {ad}: {motor[ad]}")
        print(
            df.loc[
                [2026, 2030, 2035, 2040, 2050],
                ["ort_fiyat", "gunes_yakalanma", "ruzgar_yakalanma", "sifir_saat", "kesinti_twh", "emisyon_mt"],
            ]
            .round(3)
            .to_string()
        )
    print("4. Duyarlılık")
    du = duyarlilik(taban, t, HR)
    print(du.pivot_table(index="duyarlilik", columns="yil", values=["ort_fiyat", "gunes_yakalanma"]).round(3).to_string())
    # Çıktılar
    met.to_csv(CIKTI / "K1_dogrulama.csv")
    met2.to_csv(CIKTI / "K1_dogrulama_2020_2023.csv")
    pd.concat({k: v for k, v in proj.items()}, names=["senaryo"]).to_csv(CIKTI / "K1_projeksiyon.csv")
    du.to_csv(CIKTI / "K1_duyarlilik.csv", index=False)
    pd.DataFrame({"G_gaz_usd_mwh_th": s["G"]}).to_csv(CIKTI / "K1_gaz_seviyesi.csv")
    model = {"teta": dict(zip(["MC_L", "r", "kappa", "v", "sigma_RL", "must_oran", "alpha", "beta"], t.vektor().tolist(), strict=True)),
             "teta_2020_2023": dict(zip(["MC_L", "r", "kappa", "v", "sigma_RL", "must_oran", "alpha", "beta"], t2.vektor().tolist(), strict=True)),
             "HR_min": HR, "kalibrasyon": info, "C_komur": s["C"].to_dict(), "motor": motor}  # fmt: skip
    (CIKTI / "K1_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    x = d.assign(_p=s["p"])
    gun_dog = {}
    for y in m["test_yillari"]:
        xx = x[x["yil"] == y]
        h = xx.index.tz_convert("Europe/Istanbul").hour
        gun_dog[str(y)] = {"gozlenen": xx.groupby(h)["P"].mean().round(2).tolist(), "model": xx.groupby(h)["_p"].mean().round(2).tolist()}
    paket = {
        "teta": model["teta"],
        "dogrulama_gunici": gun_dog,
        "HR_min": HR,
        "dogrulama": json.loads(met.reset_index().to_json(orient="records")),
        "gaz_seviyesi": {k: round(float(v), 2) for k, v in s["G"].items()},
        "projeksiyon": {k: json.loads(v.reset_index().to_json(orient="records")) for k, v in proj.items()},
        "gunici": gi,
        "motor": motor,
        "duyarlilik": json.loads(du.to_json(orient="records", force_ascii=False)),
        "senaryolar": m["senaryolar"],
    }
    (KOK / "data" / "atlas" / "v4_merit.json").write_text(json.dumps(paket, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    grafik(d, s["p"], proj)


def grafik(d: pd.DataFrame, p: np.ndarray, proj: dict) -> None:
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    x = d.assign(_p=p)
    for y, renk in ((2024, "C0"), (2025, "C1")):
        xx = x[x["yil"] == y]
        h = xx.index.tz_convert("Europe/Istanbul").hour
        ax[0].plot(xx.groupby(h)["P"].mean(), color=renk, label=f"{y} gözlenen")
        ax[0].plot(xx.groupby(h)["_p"].mean(), color=renk, ls="--", label=f"{y} model")
    ax[0].set_title("Gün içi ortalama PTF (örneklem dışı)")
    ax[0].set_xlabel("saat (TSİ)")
    ax[0].set_ylabel("USD/MWh")
    ax[0].legend(fontsize=8)
    for ad, df in proj.items():
        ax[1].plot(df.index, df["ort_fiyat"], label=ad)
        ax[2].plot(df.index, df["gunes_yakalanma"], label=f"{ad} güneş")
        ax[2].plot(df.index, df["ruzgar_yakalanma"], ls=":", label=f"{ad} rüzgâr")
    ax[1].set_title("Baz yük ortalama fiyat (reel)")
    ax[1].set_ylabel("USD/MWh")
    ax[1].legend(fontsize=8)
    ax[2].set_title("Yakalanma oranı")
    ax[2].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(CIKTI / "K1_ozet.png", dpi=130)


if __name__ == "__main__":
    main()
