"""
v3 F1 — Portföy adayları ve ortak senaryolarla değerleme (çevrimdışı, ~35–60 dk, paralel).

Aday listesi (src/portfoy/adaylar.aday_listesi) → her aday için tam analiz motoruyla 2–4 tasarım seçeneği ve SABİT sayıda
Monte Carlo senaryosu; ortak sürücüler tüm adaylarda aynı tohumla (aynı fiyat yolu, aynı ERA5 hava yılı, aynı SFK/doyum ve
düzenleyici olaylar), sahaya özgü belirsizlikler aday koduna bağlı tohumla.
Çıktılar (data/atlas/portfoy/, uygulamaya gömülen küçük paket):
    adaylar.csv        aday hücreler (konum, il/bölge, bağlantı trafosu, türbin, sığan türbin)
    tasarimlar.csv     aday × tasarım: kurulu güçler, türbin sayısı, CAPEX, E[NPV], P(NPV>0), CVaR, gelir yapısı
    npv.npz            npv [tasarım × senaryo] float32 (M$), ortak sürücü özetleri (L10, capex_res, w10, SFK senaryosu)
    parametreler.json  sinerji parametreleri (kendi bakımı ölçek maliyeti)
    lojistik.parquet   aday × bileşen × kaynak birim teslim maliyeti (çok sahalı ulaştırma modeli)
Çalıştırma: .venv/bin/python src/v3_F1_adaylar.py [--paralel 5] [--devam]
"""

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")

import numpy as np
import pandas as pd

from src.ayarlar import KOK

KLASOR = KOK / "data" / "atlas" / "portfoy"
ARA = KOK / "data" / "processed" / "portfoy_ara"


def is_(aday: dict) -> str:
    import pickle
    import warnings

    warnings.filterwarnings("ignore")
    from src.portfoy.adaylar import degerle

    p = ARA / f"{aday['kod']}.pkl"
    if p.exists():
        return f"{aday['kod']} önbellekte"
    t0 = time.time()
    try:
        r = degerle(aday)
    except Exception as ex:
        return f"{aday['kod']} HATA {type(ex).__name__}: {str(ex)[:200]}"
    p.write_bytes(pickle.dumps(r))
    return f"{aday['kod']} {aday['il']}/{aday['ilce']} {time.time() - t0:.0f} s, {len(r['tasarimlar'])} tasarım"


def paketle() -> None:
    import pickle

    from src.portfoy.adaylar import aday_listesi

    d = aday_listesi()
    ad, tas, npv, loj = [], [], [], []
    ortak = None
    for kod in d["kod"]:
        p = ARA / f"{kod}.pkl"
        if not p.exists():
            print("eksik", kod)
            continue
        r = pickle.loads(p.read_bytes())
        a = {k: v for k, v in r["aday"].items() if k != "turbin"}
        a["turbin_modeli"] = r["aday"]["turbin"]["turbin"] if isinstance(r["aday"]["turbin"], dict) else str(r["aday"]["turbin"])
        ad.append(a)
        for i, t in enumerate(r["tasarimlar"]):
            tas.append({**t, "satir": len(npv) + i})
        npv.extend(list(r["npv"]))
        ortak = ortak or r["ortak"]
        for x in r.get("lojistik") or []:
            loj.append({"kod": kod, **{k: x[k] for k in ("bilesen", "kaynak", "tur", "km", "birim_usd", "sure_ay")}})
    KLASOR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ad).to_csv(KLASOR / "adaylar.csv", index=False, encoding="utf-8-sig", float_format="%.5f")
    pd.DataFrame(tas).to_csv(KLASOR / "tasarimlar.csv", index=False, encoding="utf-8-sig", float_format="%.4f")
    np.savez_compressed(
        KLASOR / "npv.npz",
        npv=np.vstack(npv).astype(np.float32),
        senaryo=_sfk_senaryosu(len(ortak["L10"])),
        L10=ortak["L10"].astype(np.float32),
        capex_res=ortak["capex_res"].astype(np.float32),
        w10=ortak["w10"].astype(np.int8),
    )
    pd.DataFrame(loj).to_parquet(KLASOR / "lojistik.parquet", index=False)
    oz = json.loads((KOK / "outputs" / "v3E" / "E0_isletme_ozet.json").read_text())
    (KLASOR / "parametreler.json").write_text(
        json.dumps(
            {
                "kendi_degisken_usd_kw": oz["kendi_degisken_usd_kw_140"],
                "N_basabas": oz["N_basabas"],
                "kaynak": "outputs/v3E/E0_isletme_ozet.json (Faz D/E bakım DES ölçek maliyeti, 140 türbin)",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"Paket: {len(ad)} aday, {len(tas)} tasarım, npv {np.vstack(npv).shape}")


def _sfk_senaryosu(n: int) -> np.ndarray:
    """Ortak SFK/batarya doyum senaryosu (motor MC ile aynı tohum ve örnekleme; yıllardan bağımsız)."""
    from src.ayarlar import config_oku, deger
    from src.risk.doyum import ornekle_doyum

    cfg = config_oku()
    fo = float(pd.read_csv(KOK / "results" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
    return ornekle_doyum(cfg, n, np.arange(2028, 2061), fo, deger(cfg["v3"]["portfoy"])["tohum"])["senaryo"].astype("U32")


def main() -> None:
    from src.portfoy.adaylar import aday_listesi

    paralel = int(sys.argv[sys.argv.index("--paralel") + 1]) if "--paralel" in sys.argv else 5
    if "--paketle" in sys.argv:
        paketle()
        return
    ARA.mkdir(parents=True, exist_ok=True)
    d = aday_listesi()
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=paralel) as hv:
        fs = [hv.submit(is_, r) for r in d.to_dict(orient="records")]
        for i, f in enumerate(as_completed(fs), 1):
            print(f"[{i}/{len(fs)} {time.time() - t0:.0f} s] {f.result()}", flush=True)
    paketle()
    print(json.dumps({"sure_dk": (time.time() - t0) / 60}))


if __name__ == "__main__":
    main()
