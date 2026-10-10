"""
v3 F ön adım Ö2 — Bağlantı mesafesi belirsizliği: TEİAŞ'ın atadığı hat uzunluğu / modelin hat uzunluğu oranı.

Veri: data/atlas/teias_yeka_baglanti.csv (YEKA RES-2025 ve RES-2026 bağlantı görüşleri; 14 santral alanı).
Yarışma alanlarının koordinatları yayımlanmadığı için "aynı yer" il düzeyinde yaklaşıklanır: projenin ilindeki rüzgârlı
ön tarama hücreleri (il içinde RES KF ≥ 75. yüzdelik; YEKA alanları rüzgâr ölçümüyle seçilir) için modelin bulduğu en yakın
uygun gerilimli trafo merkezi (atanan gerilim 400 kV ise ≥ 380 kV, değilse ≥ 154 kV) uzaklığının medyanı × güzergâh çarpanı.

    oran_i = atanan hat uzunluğu_i / (medyan en yakın uzaklık_il × 1,25)

Dağılım: log-normal, ln oran ~ N(μ, σ) en çok olabilirlikle; μ ve σ'nın belirsizliği bootstrap ile (2.000 tekrar) raporlanır.
Çıktılar: data/atlas/baglanti_oranlari.csv, data/atlas/baglanti_orani.json, outputs/v3F/O2_oran_dagilimi.png
Çalıştırma: .venv/bin/python src/v3_O2_baglanti_orani.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import gorsel as g
from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.cbs import baglanti

ATLAS = KOK / "data" / "atlas"


def main() -> None:
    cfg = config_oku()
    gc = deger(cfg["v3"]["baglanti"])["guzergah_carpani"]
    y = pd.read_csv(ATLAS / "teias_yeka_baglanti.csv")
    ot = pd.read_parquet(ATLAS / "on_tarama.parquet")
    ot = ot[(ot["hata"] == "") & ~ot["ada"].fillna(False)]
    satir = []
    for r in y.itertuples():
        iller = r.il.split("/")
        h = ot[ot["il"].isin(iller)]
        h = h[h["res_kf"] >= h["res_kf"].quantile(0.75)]
        kv_asgari = 380.0 if r.kv >= 300 else 154.0
        d = np.array([baglanti.en_yakin_trafo(e, b, kv_asgari)["km"] for e, b in zip(h["enlem"], h["boylam"])])
        model_hat = float(np.median(d)) * gc
        satir.append(
            {
                "proje": r.proje,
                "il": r.il,
                "mw": r.mw,
                "kv": r.kv,
                "atanan_hat_km": r.hat_km,
                "hucre_sayisi": len(h),
                "model_en_yakin_km_medyan": float(np.median(d)),
                "model_hat_km": model_hat,
                "oran": r.hat_km / model_hat,
                "girdi_cikti": "girdi-çıktı" in str(r.trafo_merkezi),
            }
        )
    d = pd.DataFrame(satir)
    d.to_csv(ATLAS / "baglanti_oranlari.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    lo = np.log(d["oran"].to_numpy())
    mu, sd = float(lo.mean()), float(lo.std(ddof=1))
    rng = np.random.default_rng(0)
    bs = np.array([(lambda s: (s.mean(), s.std(ddof=1)))(rng.choice(lo, len(lo))) for _ in range(2000)])
    q = lambda x: [float(np.exp(mu + sd * x))]
    oz = {
        "n": int(len(d)),
        "mu_ln": mu,
        "sigma_ln": sd,
        "medyan": float(np.exp(mu)),
        "ortalama": float(np.exp(mu + sd**2 / 2)),
        "p10": q(-1.2816)[0],
        "p90": q(1.2816)[0],
        "gozlenen_min": float(d["oran"].min()),
        "gozlenen_max": float(d["oran"].max()),
        "mu_bootstrap_p5_p95": [float(np.percentile(bs[:, 0], 5)), float(np.percentile(bs[:, 0], 95))],
        "sigma_bootstrap_p5_p95": [float(np.percentile(bs[:, 1], 5)), float(np.percentile(bs[:, 1], 95))],
        "girdi_cikti_haric_medyan": float(np.exp(np.log(d.loc[~d["girdi_cikti"], "oran"]).mean())),
        "yontem": "il içi rüzgârlı hücrelerde (RES KF ≥ il 75. yüzdeliği) en yakın uygun gerilimli TM medyanı × güzergâh çarpanı; log-normal",
    }
    (ATLAS / "baglanti_orani.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1))
    (CIKTILAR / "v3F").mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = np.sort(d["oran"].to_numpy())
    ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=g.RENK_RES, lw=2, label="Gözlenen (14 santral alanı)")
    xx = np.geomspace(0.05, 30, 300)
    from scipy.stats import norm

    ax.plot(
        xx, norm.cdf((np.log(xx) - mu) / sd), color=g.MUREKKEP, lw=1.2, ls="--", label=f"Log-normal (medyan {np.exp(mu):.2f}, σ {sd:.2f})"
    )
    ax.axvline(1, color=g.IKINCIL, lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("Atanan hat / modelin hat uzunluğu")
    ax.set_ylabel("Birikimli olasılık")
    ax.legend(fontsize=8.5, loc="lower right")
    g.eksen_sade(ax)
    fig.tight_layout()
    fig.savefig(CIKTILAR / "v3F" / "O2_oran_dagilimi.png", dpi=150)
    print(d.round(2).to_string(index=False))
    print(json.dumps(oz, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
