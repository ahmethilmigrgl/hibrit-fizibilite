"""
v3 Ö3 — Bakım parametrelerinin tek değişkenli duyarlılık analizi ve tornado grafiği (Ezine, 14 türbin, SA yerleşimi).

Her TAHMİN parametresi alt ve üst değerine çekilir (diğerleri temel değerde); üç stratejinin toplam yıllık maliyeti
(kendi bakım maliyeti + kayıp gelir; sahip kalemleri stratejiler arasında aynı olduğundan dışarıda) ortak rastgele sayılarla
(aynı tohumlar) hesaplanır. Ölçüler:
    Δ_durum = maliyet(takvim) − maliyet(durum)       > 0 → durum bazlı (CMS) önleyiciden iyi
    Δ_takvim = maliyet(düzeltici) − maliyet(takvim)  > 0 → takvim bazlı önleyici düzelticiden iyi
Sıralamayı değiştiren parametreler için ince taramayla eşik (Δ = 0) bulunur.
Çıktılar: outputs/v3E/E0_bakim_duyarlilik.csv, E0_bakim_esikler.csv, E0_tornado.png; arayüz için data/atlas/v3_bakim_duyarlilik.json
Çalıştırma: .venv/bin/python src/v3_E0_bakim_duyarlilik.py
"""

import copy
import importlib.util
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
from src.bakim import des, isletme

CIKTI = CIKTILAR / "v3E"
N, R = 14, 60
AGIR = ("kanat_rotor", "disli_kutusu", "jenerator", "ana_yatak")


def _uygula(p: dict, ad: str, x: float) -> dict:
    p = copy.deepcopy(p)
    a = p["alt_sistemler"]
    if ad == "duzeltici_kat_carpani":
        p["onleyici"]["duzeltici_kat_carpani"] = x
    elif ad == "duzeltici_olcek_carpani":
        p["onleyici"]["duzeltici_olcek_carpani"] = x
    elif ad == "weibull_beta_carpani":
        for k in AGIR:
            a[k]["beta"] = max(1.05, a[k]["beta"] * x)
    elif ad == "cms_tespit_carpani":
        for k in a:
            a[k]["cms_tespit"] = min(0.95, a[k]["cms_tespit"] * x)
    elif ad == "pf_araligi_carpani":
        p["durum_izleme"]["pf_gun"] = [v * x for v in p["durum_izleme"]["pf_gun"]]
    elif ad == "planli_maliyet_carpani":
        p["durum_izleme"]["planli_maliyet_carpani"] = x
    elif ad == "cms_maliyeti":
        p["durum_izleme"]["cms_usd_turbin_yil"] = x
    elif ad == "ekip_saat_ucreti":
        p["ekip"]["saat_ucreti_usd"] = x
    elif ad == "vinc_maliyeti_carpani":
        p["vinc_usd"] = {k: v * x for k, v in p["vinc_usd"].items()}
    elif ad == "degisim_orani_carpani":
        for k in a:
            a[k]["lam_degisim"] = a[k]["lam_degisim"] * x
    elif ad == "onleyici_malzeme":
        p["onleyici"]["malzeme_usd"] = x
    elif ad == "tedarik_suresi_carpani":
        for k in a:
            a[k]["tedarik_gun"] = a[k]["tedarik_gun"] * x
    else:
        raise ValueError(ad)
    return p


# parametre: (etiket, temel, alt, üst)
PARAM = {
    "duzeltici_kat_carpani": ("Önleyici bakımın etkisi: bakımsız onarım oranı çarpanı", 1.4, 1.1, 1.8),
    "duzeltici_olcek_carpani": ("Önleyici bakımın etkisi: bakımsız yaşlanma (Weibull ölçek çarpanı)", 0.8, 0.65, 0.95),
    "weibull_beta_carpani": ("Weibull şekil parametreleri (çarpan)", 1.0, 0.7, 1.3),
    "cms_tespit_carpani": ("Durum izlemenin yakalama olasılığı (çarpan)", 1.0, 0.5, 1.2),
    "pf_araligi_carpani": ("P-F aralığı (çarpan; 30–120 gün)", 1.0, 0.5, 1.5),
    "planli_maliyet_carpani": ("Planlı değişimin maliyet çarpanı", 0.7, 0.5, 0.9),
    "cms_maliyeti": ("CMS maliyeti [$/türbin-yıl]", 1200.0, 600.0, 3000.0),
    "ekip_saat_ucreti": ("Teknisyen saat ücreti [$]", 45.0, 30.0, 70.0),
    "vinc_maliyeti_carpani": ("Vinç maliyeti (çarpan)", 1.0, 0.5, 1.75),
    "degisim_orani_carpani": ("Büyük bileşen değişim oranları (çarpan)", 1.0, 0.5, 2.0),
    "onleyici_malzeme": ("Önleyici bakım malzemesi [$/türbin-yıl]", 6000.0, 3000.0, 12000.0),
    "tedarik_suresi_carpani": ("Parça tedarik süreleri (çarpan)", 1.0, 0.5, 1.5),
}
STR = ("duzeltici", "takvim", "durum")


def maliyetler(g0: des.Girdi, p: dict, cfg: dict) -> dict:
    out = {}
    for s in STR:
        g = des.Girdi(g0.N, g0.P_mw, g0.pay, g0.kf_yillar, g0.v_yillar, g0.fiyat, g0.omur, p, s, g0.pm_gun, {})
        r = des.simule(g, R, p["tohum"])
        om = isletme.kendi_turbin_usd_yil(r["gider"], cfg)
        out[s] = {
            "toplam": float(om + r["kayip_gelir_yil"].mean()),
            "om": float(om),
            "kayip": float(r["kayip_gelir_yil"].mean()),
            "A": float(r["A_enerji"].mean()),
        }
    return out


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    sp = importlib.util.spec_from_file_location("d2", KOK / "src" / "v3_D2_bakim_analizi.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    _, P, pay, kf, v, fiyat = m.saha_girdileri("Çanakkale-Ezine", 39.79, 26.33)
    cfg = config_oku()
    p0 = deger(cfg["v3"]["bakim"])
    from src.bakim import cizelge

    on = p0["onleyici"]
    c, pg, _ = cizelge.gunluk_parametreler(v, kf * P, fiyat, on["is_saati"], p0["hava"]["tirmanma_limiti"], tuple(p0["hava"]["vardiya"]))
    gun = cizelge.coz(pay, c, pg, on["ekip_sayisi_cizelge"])["gun"]
    g0 = des.Girdi(N, P, pay, kf, v, fiyat, int(deger(cfg["proje"]["omur"])), p0, "durum", gun, {})
    temel = maliyetler(g0, p0, cfg)
    print("temel", {s: round(x["toplam"] / 1e3) for s, x in temel.items()}, flush=True)
    satir = []
    for ad, (etk, t0, lo, hi) in PARAM.items():
        for seviye, x in (("alt", lo), ("ust", hi)):
            r = maliyetler(g0, _uygula(p0, ad, x), cfg)
            sira = sorted(STR, key=lambda s: r[s]["toplam"])
            satir.append(
                {
                    "parametre": ad,
                    "etiket": etk,
                    "seviye": seviye,
                    "deger": x,
                    "temel_deger": t0,
                    **{f"{s}_toplam": r[s]["toplam"] for s in STR},
                    **{f"{s}_A": r[s]["A"] for s in STR},
                    "delta_durum": r["takvim"]["toplam"] - r["durum"]["toplam"],
                    "delta_takvim": r["duzeltici"]["toplam"] - r["takvim"]["toplam"],
                    "en_iyi": sira[0],
                    "siralama": " < ".join(sira),
                }
            )
            print(
                ad,
                seviye,
                x,
                satir[-1]["siralama"],
                round(satir[-1]["delta_durum"] / 1e3, 1),
                round(satir[-1]["delta_takvim"] / 1e3, 1),
                flush=True,
            )
    d = pd.DataFrame(satir)
    d.to_csv(CIKTI / "E0_bakim_duyarlilik.csv", index=False, encoding="utf-8-sig", float_format="%.1f")
    d_dur = temel["takvim"]["toplam"] - temel["durum"]["toplam"]
    d_tak = temel["duzeltici"]["toplam"] - temel["takvim"]["toplam"]
    # sıralamayı değiştiren parametrelerde eşik taraması (Δ = 0)
    esik = []
    for ad, (etk, t0, lo, hi) in PARAM.items():
        x = d[d.parametre == ad]
        for olcu, d0 in (("delta_durum", d_dur), ("delta_takvim", d_tak)):
            if (np.sign(x[olcu]) != np.sign(d0)).any():
                kenar = hi if np.sign(x.loc[x.seviye == "ust", olcu].iloc[0]) != np.sign(d0) else lo
                xs = np.linspace(t0, kenar, 7)
                ds = []
                for xx in xs:
                    r = maliyetler(g0, _uygula(p0, ad, xx), cfg)
                    ds.append(
                        r["takvim"]["toplam"] - r["durum"]["toplam"]
                        if olcu == "delta_durum"
                        else r["duzeltici"]["toplam"] - r["takvim"]["toplam"]
                    )
                ds = np.array(ds)
                i = int(np.argmax(np.sign(ds) != np.sign(ds[0])))
                xe = float(
                    np.interp(
                        0,
                        [ds[i - 1], ds[i]] if ds[i] > ds[i - 1] else [ds[i], ds[i - 1]],
                        [xs[i - 1], xs[i]] if ds[i] > ds[i - 1] else [xs[i], xs[i - 1]],
                    )
                )
                esik.append(
                    {"parametre": ad, "etiket": etk, "olcu": olcu, "temel": t0, "esik": xe, "yon": "artarsa" if kenar > t0 else "azalırsa"}
                )
                print("eşik", esik[-1], flush=True)
    e = pd.DataFrame(esik)
    e.to_csv(CIKTI / "E0_bakim_esikler.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    # tornado (Δ_durum ve Δ_takvim)
    fig, ax = plt.subplots(1, 2, figsize=(13, 6), sharey=True)
    sira = d.groupby("parametre")["delta_durum"].agg(lambda s: s.max() - s.min()).sort_values().index
    for k, (olcu, d0, bas) in enumerate(
        (
            ("delta_durum", d_dur, "Durum bazlının takvime üstünlüğü [bin $/yıl]"),
            ("delta_takvim", d_tak, "Takvimin düzelticiye üstünlüğü [bin $/yıl]"),
        )
    ):
        for j, pr in enumerate(sira):
            x = d[d.parametre == pr].set_index("seviye")
            a, u = x.loc["alt", olcu] / 1e3, x.loc["ust", olcu] / 1e3
            ax[k].barh(j, a - d0 / 1e3, left=d0 / 1e3, color="#9ec5ef")
            ax[k].barh(j, u - d0 / 1e3, left=d0 / 1e3, color="#1d4f91")
        ax[k].axvline(d0 / 1e3, color="#555", lw=1)
        ax[k].axvline(0, color="#c0392b", lw=1, ls="--")
        ax[k].set_title(bas, fontsize=10)
    ax[0].set_yticks(range(len(sira)))
    ax[0].set_yticklabels([PARAM[p][0] for p in sira], fontsize=8)
    fig.suptitle(
        "Bakım parametreleri duyarlılığı (Ezine, 14 türbin, 60 ömür; açık: alt değer, koyu: üst değer; kesikli: sıralama değişir)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(CIKTI / "E0_tornado.png", dpi=130)
    sayim = d["en_iyi"].value_counts().to_dict()
    oz = {
        "temel": {s: temel[s]["toplam"] for s in STR},
        "temel_delta_durum": d_dur,
        "temel_delta_takvim": d_tak,
        "senaryo_sayisi": int(len(d)),
        "en_iyi_sayim": sayim,
        "tornado": [
            {
                "parametre": pr,
                "etiket": PARAM[pr][0],
                "alt": float(PARAM[pr][2]),
                "ust": float(PARAM[pr][3]),
                **{
                    f"{olcu}_{sv}": float(d[(d.parametre == pr) & (d.seviye == sv)][olcu].iloc[0])
                    for olcu in ("delta_durum", "delta_takvim")
                    for sv in ("alt", "ust")
                },
            }
            for pr in reversed(list(sira))
        ],
        "esikler": esik,
    }
    (KOK / "data" / "atlas" / "v3_bakim_duyarlilik.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1, default=float))
    print(json.dumps({k: v for k, v in oz.items() if k not in ("tornado",)}, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
