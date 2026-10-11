"""
v3 F1/F3 — Portföy analizleri (çevrimdışı): bölgeler arası üretim korelasyonu, etkin sınır (ε-kısıt), seçilen portföy ve en iyi
tek saha, sinerji ve çeşitlendirme ayrıştırması, fiyat ve bağlantı kapasitesi duyarlılığı, kaba kuvvet ve CVaR doğrulaması.
Girdi: data/atlas/portfoy (src/v3_F1_adaylar.py). Çıktılar: outputs/v3F/F3_*.csv|json|png, data/atlas/portfoy/analiz.json
(uygulamanın Portföy sayfası için küçük özet), data/atlas/portfoy/korelasyon.json
Varsayılan: Bayesçi büzülmeyle düzeltilmiş tahminler (data/atlas/portfoy/lanet.json); --duzeltmesiz: saf tahminler
(çıktılar _duzeltmesiz sonekiyle; önce/sonra karşılaştırması).
Çalıştırma: .venv/bin/python src/v3_F3_portfoy.py [--korelasyon-atla] [--duzeltmesiz]
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.portfoy import analiz as PA
from src.portfoy import model as M
from src.portfoy import veri as PV

CIKTI = CIKTILAR / "v3F"
ATLAS = KOK / "data" / "atlas" / "portfoy"


def korelasyon(v: M.Veri) -> dict:
    from src.motor.ortak import hazirla
    from src.motor.varsayimlar import KullaniciVarsayimlari

    kv = KullaniciVarsayimlari()
    prof = {}
    for r in v.ad.itertuples():
        h = hazirla({"ad": r.kod, "enlem": r.enlem, "boylam": r.boylam}, kv)
        prof[r.kod] = h.profil["res_kf"]
    P = pd.DataFrame(prof)
    ay = P.resample("MS").mean()
    yil = P.resample("YS").mean()
    C = {"saatlik": P.corr(), "aylik": ay.corr(), "yillik": yil.corr()}
    e, b = v.ad.set_index("kod")["enlem"], v.ad.set_index("kod")["boylam"]
    d, rs, rm, ry = [], [], [], []
    kod = list(P.columns)
    for i in range(len(kod)):
        for j in range(i + 1, len(kod)):
            d.append(M._km(e[kod[i]], b[kod[i]], e[kod[j]], b[kod[j]]))
            rs.append(C["saatlik"].iloc[i, j])
            rm.append(C["aylik"].iloc[i, j])
            ry.append(C["yillik"].iloc[i, j])
    d = np.array(d)
    uzun = {}
    for ad_, r in (("saatlik", rs), ("aylik", rm), ("yillik", ry)):
        r = np.clip(np.array(r), 1e-3, None)
        L = float(-np.sum(d * d) / np.sum(d * np.log(r)))  # ρ(d) = exp(−d/L), en küçük kareler (ln ρ = −d/L)
        uzun[ad_] = L
    bol = v.ad.set_index("kod")["bolge"]
    Pb = P.T.groupby(bol).mean().T
    Cb = {"saatlik": Pb.corr(), "aylik": Pb.resample("MS").mean().corr(), "yillik": Pb.resample("YS").mean().corr()}
    pd.DataFrame({"km": d, "saatlik": rs, "aylik": rm, "yillik": ry}).to_csv(
        CIKTI / "F1_korelasyon_mesafe.csv", index=False, float_format="%.4f"
    )
    for k_, m_ in Cb.items():
        m_.round(3).to_csv(CIKTI / f"F1_bolge_korelasyon_{k_}.csv", encoding="utf-8-sig")
    # NPV korelasyonu (MILP tasarımları arasında)
    t = v.tas
    mi = t.index[t["tasarim"] == "MILP"]
    Cn = np.corrcoef(v.V[mi])
    ust = Cn[np.triu_indices(len(mi), 1)]
    out = {
        "uzunluk_olcegi_km": uzun,
        "ortalama": {k_: float(np.nanmean(np.array(x))) for k_, x in (("saatlik", rs), ("aylik", rm), ("yillik", ry))},
        "yakin_100km": {k_: float(np.nanmean(np.array(x)[d < 100])) for k_, x in (("saatlik", rs), ("aylik", rm), ("yillik", ry))},
        "uzak_500km": {k_: float(np.nanmean(np.array(x)[d > 500])) for k_, x in (("saatlik", rs), ("aylik", rm), ("yillik", ry))},
        "bolge": {k_: {"etiket": list(m_.index), "matris": m_.round(3).to_numpy().tolist()} for k_, m_ in Cb.items()},
        "aday_aylik": {"etiket": kod, "matris": C["aylik"].round(3).to_numpy().tolist()},
        "npv_korelasyon": {"ortalama": float(ust.mean()), "min": float(ust.min()), "max": float(ust.max())},
    }
    (ATLAS / "korelasyon.json").write_text(json.dumps(out, ensure_ascii=False))
    return out


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    a = deger(cfg["v3"]["portfoy"])
    duz = "--duzeltmesiz" not in sys.argv
    sonek = "" if duz else "_duzeltmesiz"
    v = PV.yukle(duzeltme=duz)
    o = PV.ortak()
    t0 = time.time()
    oz: dict = {}
    if "--korelasyon-atla" not in sys.argv:
        oz["korelasyon"] = korelasyon(v)
        print(
            "korelasyon",
            json.dumps(
                {k: oz["korelasyon"][k] for k in ("uzunluk_olcegi_km", "ortalama", "yakin_100km", "uzak_500km", "npv_korelasyon")},
                ensure_ascii=False,
            ),
            flush=True,
        )
    ay0 = M.Ayar(lam=0.0, butce_musd=a["butce_musd"], bolge_kapasite_mw=a["bolge_kapasite_mw"], trafo_kapasite_mw=a["trafo_kapasite_mw"])
    sp = M._sinerji_parametreleri(v, cfg)
    r0 = M.coz(v, ay0, cfg, sp)
    t = v.tas
    # en iyi tek saha (E[NPV]) ve aynı CVaR'da portföy
    i1 = int(t["e_npv"].idxmax())
    tek = {
        "secim": f"{t['kod'].iloc[i1]}:{t['tasarim'].iloc[i1]}",
        "e_npv": float(v.V[i1].mean()),
        "cvar": PA.cvar(v.V[i1]),
        "capex_musd": float(t["capex_musd"].iloc[i1]),
    }
    # etkin sınır: ε-kısıt (CVaR ≥ c), c risk nötr portföyün CVaR'ından 0'a
    c_grid = np.linspace(r0["cvar"], -2.0, 10)
    sinir = [
        {
            "cvar_alt": None,
            "e_npv": r0["e_npv"],
            "cvar": r0["cvar"],
            "capex_musd": r0["capex_musd"],
            "secim": "; ".join(r0["secim"]["kod"] + ":" + r0["secim"]["tasarim"]),
            "n": len(r0["secim"]),
        }
    ]
    for c in c_grid[1:]:
        r = M.coz(v, M.Ayar(**{**ay0.__dict__, "cvar_alt": float(c), "zaman_s": 120}), cfg, sp)
        sinir.append(
            {
                "cvar_alt": float(c),
                "e_npv": r["e_npv"],
                "cvar": r["cvar"],
                "capex_musd": r["capex_musd"],
                "secim": "; ".join(r["secim"]["kod"] + ":" + r["secim"]["tasarim"]),
                "n": len(r["secim"]),
            }
        )
        print("sınır", round(c, 1), round(r["e_npv"], 2), round(r["cvar"], 2), sinir[-1]["secim"], f"{r['sure_s']:.0f} s", flush=True)
    sinir.append({"cvar_alt": 0.0, "e_npv": 0.0, "cvar": 0.0, "capex_musd": 0.0, "secim": "(yatırım yok)", "n": 0})
    pd.DataFrame(sinir).to_csv(CIKTI / f"F3_etkin_sinir{sonek}.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    # tek sahayla aynı CVaR'da portföy
    r_es = M.coz(v, M.Ayar(**{**ay0.__dict__, "cvar_alt": tek["cvar"], "zaman_s": 120}), cfg, sp)
    oz["tek_saha"] = tek
    oz["ayni_cvar_portfoy"] = {
        "e_npv": r_es["e_npv"],
        "cvar": r_es["cvar"],
        "capex_musd": r_es["capex_musd"],
        "secim": list(r_es["secim"]["kod"] + ":" + r_es["secim"]["tasarim"]),
    }
    print("tek saha", tek, "aynı CVaR portföy", oz["ayni_cvar_portfoy"], flush=True)
    # seçilen portföy (risk nötr) ayrıntısı
    sec = r0["secim"].index.to_numpy()
    oz["secilen"] = {
        "e_npv": r0["e_npv"], "cvar": r0["cvar"], "p_pozitif": r0["p_pozitif"], "capex_musd": r0["capex_musd"], "psi_musd": r0["psi_musd"],
        "kendi_bakimi": r0["kendi_bakimi"], "havuz": r0["havuz"], "indirim_kademesi": r0["indirim_kademesi"],
        "tasarimlar": r0["secim"][["kod", "tasarim", "res_mw", "bess_mw", "N", "capex_musd", "e_npv", "cvar5"]].to_dict(orient="records"),
        "turbin_toplam": int(r0["secim"]["N"].sum()),
    }  # fmt: skip
    # sinerji ayrıştırması (risk nötr, aynı bütçe): hepsi açık, hiçbiri, tek tek kapalı
    kal = ["isletme", "havuz", "indirim", "ulastirma"]
    hepsi = r0["amac"]
    yok = M.coz(v, M.Ayar(**{**ay0.__dict__, "sinerji": dict.fromkeys(kal, False)}), cfg, sp)
    ay_ = []
    for k_ in kal:
        s_ = dict.fromkeys(kal, True)
        s_[k_] = False
        if k_ == "isletme":
            s_["havuz"] = False  # havuz kendi bakımına bağlı
        r_ = M.coz(v, M.Ayar(**{**ay0.__dict__, "sinerji": s_}), cfg, sp)
        ay_.append(
            {
                "kalem": k_,
                "kalem_kapaliyken_amac": r_["amac"],
                "katki_musd": hepsi - r_["amac"],
                "secim": "; ".join(r_["secim"]["kod"] + ":" + r_["secim"]["tasarim"]),
            }
        )
    ay_.append(
        {
            "kalem": "hiçbiri",
            "kalem_kapaliyken_amac": yok["amac"],
            "katki_musd": hepsi - yok["amac"],
            "secim": "; ".join(yok["secim"]["kod"] + ":" + yok["secim"]["tasarim"]),
        }
    )
    pd.DataFrame(ay_).to_csv(CIKTI / f"F3_sinerji{sonek}.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    oz["sinerji"] = ay_
    # kesin havuz değeri (doğrusal yaklaşım kontrolü)
    from src.portfoy import sinerji as S

    if r0["havuz"]:
        gg = float(np.median(3.45 * 0.37 * 24 * 58))
        N_ = r0["secim"]["N"].to_numpy()
        tau = r0["secim"]["kod"].map(sp["tau_gun"]).to_numpy()
        ayri = sum(S.stok_maliyeti(int(n), gg, cfg)["maliyet_yil"] for n in N_)
        hv = S.stok_maliyeti(int(N_.sum()), gg, cfg)["maliyet_yil"] + sp["havuz_dogrusal"]["havuz_c_turbin_gun_yil"] * float(
            (N_ * tau).sum()
        )
        oz["havuz_kesin"] = {"ayri_yil": ayri, "havuz_yil": hv, "tasarruf_bd_musd": sp["beta"] * (ayri - hv) / 1e6, "depo": sp["depo"]}
    # çeşitlendirme ayrıştırması
    oz["cesitlendirme"] = PA.cesitlendirme(v.V[sec], o, r0["psi_musd"])
    oz["cesitlendirme_dengeli"] = (
        PA.cesitlendirme(v.V[r_es["secim"].index.to_numpy()], o, r_es["psi_musd"]) if len(r_es["secim"]) > 1 else None
    )
    mi = t.index[t["tasarim"] == "MILP"].to_numpy()
    eg = PA.egri_n(v.V[mi], o, 12)
    eg.to_csv(CIKTI / f"F3_cesitlendirme_egrisi{sonek}.csv", index=False, float_format="%.4f")
    oz["cesitlendirme_egrisi"] = eg.to_dict(orient="records")
    print("çeşitlendirme", oz["cesitlendirme"], flush=True)
    # fiyat duyarlılığı: NPV(Δ) ≈ NPV + eğim·Δ (eğim: ortak regresyonun L10 katsayısı)
    eg_f = PA.fiyat_egimleri(v.V, o)
    fy = []
    for dlt in np.arange(-24, 11, 2.0):
        vv = M.Veri(tas=t.assign(e_npv=t["e_npv"] + eg_f * dlt), ad=v.ad, V=v.V + eg_f[:, None] * dlt, lojistik=v.lojistik)
        r_ = M.coz(vv, ay0, cfg, sp)
        r2 = M.coz(vv, M.Ayar(**{**ay0.__dict__, "cvar_alt": -30.0, "zaman_s": 120}), cfg, sp)
        fy.append({"delta": float(dlt), "fiyat": 58.0 + dlt, "e_npv": r_["e_npv"], "cvar": r_["cvar"], "n": len(r_["secim"]), "capex_musd": r_["capex_musd"],
                   "secim": "; ".join(r_["secim"]["kod"] + ":" + r_["secim"]["tasarim"]), "e_npv_cvar30": r2["e_npv"], "n_cvar30": len(r2["secim"])})  # fmt: skip
        print("fiyat", dlt, round(r_["e_npv"], 2), len(r_["secim"]), "| CVaR≥−30:", round(r2["e_npv"], 2), len(r2["secim"]), flush=True)
    pd.DataFrame(fy).to_csv(CIKTI / f"F3_fiyat_duyarlilik{sonek}.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    oz["fiyat"] = fy
    oz["fiyat_egimi_medyan"] = float(np.median(eg_f))
    # yatırım yapmamanın optimal olduğu eşik (risk nötr): tüm tasarımların E + en iyi sinerji < 0 olduğu en büyük Δ (ızgaradan)
    yok_ = [f["fiyat"] for f in fy if f["n"] == 0]
    oz["yatirim_yok_esik_fiyat"] = max(yok_) if yok_ else None
    # risk ağırlığı eşiği: λ arttıkça portföy; boş portföyün optimal olduğu en küçük λ
    lt = []
    for lam in (0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5):
        r_ = M.coz(v, M.Ayar(**{**ay0.__dict__, "lam": lam, "zaman_s": 120}), cfg, sp)
        lt.append(
            {
                "lam": lam,
                "e_npv": r_["e_npv"],
                "cvar": r_["cvar"],
                "n": len(r_["secim"]),
                "secim": list(r_["secim"]["kod"] + ":" + r_["secim"]["tasarim"]),
            }
        )
        print("λ", lam, round(r_["e_npv"], 2), len(r_["secim"]), flush=True)
    oz["lambda"] = lt
    bos = [x["lam"] for x in lt if x["n"] == 0]
    oz["yatirim_yok_esik_lambda"] = min(bos) if bos else None
    # eşikte sinerjilerin rolü (risk nötr, en düşük yatırım yapılan fiyat)
    yat = [f for f in fy if f["n"] > 0]
    if yat:
        dmin = min(f["delta"] for f in yat)
        vv = M.Veri(tas=t, ad=v.ad, V=v.V + eg_f[:, None] * dmin, lojistik=v.lojistik)
        r1 = M.coz(vv, ay0, cfg, sp)
        r2 = M.coz(vv, M.Ayar(**{**ay0.__dict__, "sinerji": dict.fromkeys(("isletme", "havuz", "indirim", "ulastirma"), False)}), cfg, sp)
        oz["esik_sinerji"] = {"fiyat": 58.0 + dmin, "sinerjili_e": r1["e_npv"], "sinerjili_n": len(r1["secim"]), "sinerjisiz_e": r2["e_npv"], "sinerjisiz_n": len(r2["secim"]),
                              "tek_tek_e": [float(vv.V[i].mean()) for i in r1["secim"].index]}  # fmt: skip
    # bağlantı kapasitesi duyarlılığı
    kd = []
    for kr in (50.0, 100.0, 150.0, None):
        r_ = M.coz(v, M.Ayar(**{**ay0.__dict__, "bolge_kapasite_mw": kr}), cfg, sp)
        kd.append(
            {
                "bolge_kapasite_mw": kr,
                "e_npv": r_["e_npv"],
                "cvar": r_["cvar"],
                "n": len(r_["secim"]),
                "secim": "; ".join(r_["secim"]["kod"] + ":" + r_["secim"]["tasarim"]),
            }
        )
    for b_ in (150.0, 300.0, 600.0):
        r_ = M.coz(v, M.Ayar(**{**ay0.__dict__, "butce_musd": b_}), cfg, sp)
        kd.append(
            {
                "butce_musd": b_,
                "e_npv": r_["e_npv"],
                "cvar": r_["cvar"],
                "n": len(r_["secim"]),
                "secim": "; ".join(r_["secim"]["kod"] + ":" + r_["secim"]["tasarim"]),
            }
        )
    pd.DataFrame(kd).to_csv(CIKTI / f"F3_kapasite_butce{sonek}.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    oz["kapasite_butce"] = kd
    # doğrulama: kaba kuvvet (6 saha) ve CVaR doğrusallaştırması
    kodlar = ["A01", "A02", "A04", "A05", "A06", "A10"]
    alt = t["kod"].isin(kodlar)
    vk = M.Veri(
        tas=t[alt].reset_index(drop=True), ad=v.ad[v.ad["kod"].isin(kodlar)].reset_index(drop=True), V=v.V[alt.to_numpy()], lojistik=None
    )
    dog = []
    for lam, butce in ((0.0, 150.0), (0.2, 150.0), (0.05, 250.0)):
        ayk = M.Ayar(
            lam=lam,
            butce_musd=butce,
            bolge_kapasite_mw=a["bolge_kapasite_mw"],
            trafo_kapasite_mw=None,
            sinerji={"isletme": True, "havuz": True, "indirim": True, "ulastirma": False},
        )
        spk = M._sinerji_parametreleri(vk, cfg)
        rk = M.coz(vk, ayk, cfg, spk)
        bk = PA.kaba_kuvvet(vk, kodlar, ayk, spk)
        dog.append({"lam": lam, "butce": butce, "milp_amac": rk["amac"], "kaba_kuvvet_amac": bk["amac"], "milp_secim": list(rk["secim"]["kod"] + ":" + rk["secim"]["tasarim"]),
                    "kaba_kuvvet_secim": bk["secim"], "kombinasyon": bk["kombinasyon"], "cvar_kesin": rk["cvar"], "cvar_dogrusal": rk["cvar_dogrusal"]})  # fmt: skip
        print("doğrulama", dog[-1], flush=True)
    oz["dogrulama"] = dog
    oz["sure_dk"] = (time.time() - t0) / 60
    (CIKTI / f"F3_ozet{sonek}.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1, default=float))
    app = {
        k: oz[k]
        for k in (
            "tek_saha",
            "ayni_cvar_portfoy",
            "secilen",
            "sinerji",
            "cesitlendirme",
            "cesitlendirme_egrisi",
            "fiyat",
            "yatirim_yok_esik_fiyat",
            "kapasite_butce",
            "dogrulama",
        )
        if k in oz
    }
    app["etkin_sinir"] = sinir
    app["havuz_kesin"] = oz.get("havuz_kesin")
    (ATLAS / f"analiz{sonek}.json").write_text(json.dumps(app, ensure_ascii=False, default=float))
    print(
        json.dumps(
            {k: oz[k] for k in ("tek_saha", "ayni_cvar_portfoy", "yatirim_yok_esik_fiyat", "sure_dk")}, ensure_ascii=False, default=float
        )
    )


if __name__ == "__main__":
    main()
