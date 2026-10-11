"""
v3 kapanış G1 — Optimize edicinin laneti: beklenen hayal kırıklığı ve Bayesçi büzülme düzeltmesi (src/portfoy/lanet.py).

1. Parametreler: ampirik birini dışarıda bırak hataları (güven seviyesine göre), bölgesel öncül (ampirik Bayes), κ_jd
   (NPV'nin KF çarpanına duyarlılığı) → data/atlas/portfoy/lanet.json (uygulamanın varsayılan düzeltmesi).
2. Simülasyon (R tekrar): gerçek KF sonsaldan, yeni tahmin = gerçek + hata; portföy ve en iyi tek saha (a) saf tahminle,
   (b) büzülmüş tahminle seçilir; beklenen hayal kırıklığı = E[tahmin edilen − gerçek] ve gerçek değer.
3. Gerçek karar için: Faz F'nin saf seçimiyle bulunan portföyün tahmin edilen değeri ile sonsal (büzülmüş) değeri.
4. Duyarlılık: büzülme ağırlığını LOO kalibrasyon eğiminden (ln gözlenen ~ ln tahmin) almak.
Çıktılar: outputs/v3G/G1_*.csv|json, data/atlas/portfoy/lanet.json
Çalıştırma: .venv/bin/python src/v3_G1_optimizer_laneti.py [--tekrar 200]
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

from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.portfoy import lanet as L
from src.portfoy import model as M
from src.portfoy import veri as PV

CIKTI = CIKTILAR / "v3G"


def main() -> None:
    R = int(sys.argv[sys.argv.index("--tekrar") + 1]) if "--tekrar" in sys.argv else 200
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    a = deger(cfg["v3"]["portfoy"])
    v = PV.yukle(duzeltme=False)
    o = PV.ortak()
    t0 = time.time()
    onc = L.oncul(cfg)
    bz = L.buzulme(v, onc)
    k = L.kappa(v, o)
    hat = L.ampirik_hatalar()
    # LOO kalibrasyon eğimi (duyarlılık)
    d = pd.read_csv(KOK / "outputs" / "v2" / "A4_capraz_dogrulama.csv")
    d = d[(d["gmod"] == "turbin_konumu") & (d["yontem"] == "gwa_olcekli")]
    egim = float(np.polyfit(np.log(d["tahmin_kf"]), np.log(d["gozlenen_kf"]), 1)[0])
    paket = {
        "q": dict(zip(bz["kod"], bz["q"].round(5))),
        "w": dict(zip(bz["kod"], bz["w"].round(4))),
        "kf_tahmin": dict(zip(bz["kod"], bz["res_kf"].round(4))),
        "kf_duzeltilmis": dict(zip(bz["kod"], bz["kf_duzeltilmis"].round(4))),
        "kappa_satir": {int(s): float(x) for s, x in zip(v.tas["satir"], k.round(3))},
        "oncul": onc[["m", "tau2", "n"]].round(4).reset_index().to_dict(orient="records"),
        "hata_sigma": {g: float(np.std(x)) for g, x in hat.items()},
        "loo_kalibrasyon_egimi": egim,
        "aciklama": "ln KF büzülmesi: m_r + w (ln ĉ − m_r), w = τ_r² / (τ_r² + σ_g²); NPV düzeltmesi V + κ (q − 1)",
    }
    (KOK / "data" / "atlas" / "portfoy" / "lanet.json").write_text(json.dumps(paket, ensure_ascii=False, indent=1))
    bz[["kod", "il", "ilce", "bolge", "guven", "res_kf", "w", "kf_duzeltilmis", "q"]].to_csv(
        CIKTI / "G1_buzulme.csv", index=False, encoding="utf-8-sig", float_format="%.4f"
    )
    # gerçek karar: saf seçimin tahmin edilen ve sonsal değeri
    ay0 = M.Ayar(lam=0.0, butce_musd=a["butce_musd"], bolge_kapasite_mw=a["bolge_kapasite_mw"], trafo_kapasite_mw=a["trafo_kapasite_mw"])
    sp = M._sinerji_parametreleri(v, cfg)
    vd = L.uygula(v, dict(zip(bz["kod"], bz["q"])), k)
    r_saf = M.coz(v, ay0, cfg, sp)
    x = r_saf["x"]
    sonsal_saf = float(vd.V[x].sum(0).mean() + r_saf["psi_musd"])
    r_buz = M.coz(vd, ay0, cfg, sp)
    i_saf = int(np.argmax(v.V.mean(1)))
    i_buz = int(np.argmax(vd.V.mean(1)))
    gercek = {
        "saf_portfoy_tahmin": r_saf["e_npv"],
        "saf_portfoy_sonsal": sonsal_saf,
        "saf_portfoy_secim": list(r_saf["secim"]["kod"] + ":" + r_saf["secim"]["tasarim"]),
        "buzulmus_portfoy_tahmin": r_buz["e_npv"],
        "buzulmus_portfoy_secim": list(r_buz["secim"]["kod"] + ":" + r_buz["secim"]["tasarim"]),
        "saf_tek": f"{v.tas['kod'].iloc[i_saf]}:{v.tas['tasarim'].iloc[i_saf]}",
        "saf_tek_tahmin": float(v.V[i_saf].mean()),
        "saf_tek_sonsal": float(vd.V[i_saf].mean()),
        "buzulmus_tek": f"{v.tas['kod'].iloc[i_buz]}:{v.tas['tasarim'].iloc[i_buz]}",
        "buzulmus_tek_tahmin": float(vd.V[i_buz].mean()),
    }
    print("gerçek karar", json.dumps(gercek, ensure_ascii=False), flush=True)
    # simülasyon
    sim = L.simulasyon(v, o, R, ay0, tohum=7, cfg=cfg)
    sim.to_csv(CIKTI / "G1_simulasyon.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    oz = {}
    for ad_ in ("saf", "buzulmus"):
        for b in ("portfoy", "tek"):
            dt = sim[f"{ad_}_{b}_tahmin"] - sim[f"{ad_}_{b}_gercek"]
            oz[f"{ad_}_{b}"] = {
                "hayal_kirikligi_ort": float(dt.mean()),
                "hayal_kirikligi_se": float(dt.std(ddof=1) / np.sqrt(len(dt))),
                "hayal_kirikligi_p10_p90": [float(dt.quantile(0.1)), float(dt.quantile(0.9))],
                "tahmin_ort": float(sim[f"{ad_}_{b}_tahmin"].mean()),
                "gercek_ort": float(sim[f"{ad_}_{b}_gercek"].mean()),
            }
    sonuc = {"tekrar": R, "simulasyon": oz, "gercek_karar": gercek, "loo_kalibrasyon_egimi": egim, "sure_dk": (time.time() - t0) / 60}
    (CIKTI / "G1_ozet.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(sonuc, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
