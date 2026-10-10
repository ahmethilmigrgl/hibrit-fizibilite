"""
v3 E3 — Çok kriterli saha seçimi analizi: AHP profilleri, TOPSIS sıralaması, ağırlık dayanıklılığı, mevcut santrallerle
doğrulama (ROC/AUC) ve "açığa çıkan tercih" ağırlıkları; ekonomik ile çok kriterli ilk 10 karşılaştırması.

Doğrulama etiketi: hücrede OSM rüzgâr türbini var mı (mevcut RES = geliştiricilerin gerçek kararları; 171 hücre).
Döngüsellik uyarısı: "güven" kriteri tanımı gereği kalibre santrallere yakınlıktır (30 km) → doğrulamada ayrıca dışarıda
bırakılarak raporlanır. Başabaş fiyat da atlas katsayılarını (santrallerden) kullanır; bu yüzden "rüzgâr kaynağı" (RES KF)
varyantı da raporlanır.
Çıktılar: outputs/v3E/E3_*.csv, data/atlas/v3_cok_kriterli_dogrulama.json
Çalıştırma: .venv/bin/python src/v3_E3_cok_kriterli.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK
from src.cbs import cok_kriterli as CK
from src.cbs import kriterler as KR

CIKTI = CIKTILAR / "v3E"
VK = KR.vektor()


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    d = KR.tablo().copy()
    neden = KR.dislanan(d)
    uygun = neden == ""
    K = list(KR.KRITERLER)
    sonuc: dict = {"profiller": {}, "auc": {}, "ilk10": {}}
    goster = ["il", "ilce", "res_kf", "basabas_en_iyi", "trafo_km", "egim_ort", "goc_azami", "guven", "lojistik_usd_mw"]
    # ekonomik ilk 10
    eko = d[uygun].nsmallest(10, "basabas_en_iyi")
    eko[goster].to_csv(CIKTI / "E3_ilk10_ekonomik.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    sonuc["ilk10"]["ekonomik"] = eko[["il", "ilce", "basabas_en_iyi"]].to_dict(orient="records")
    du = d[uygun].reset_index(drop=True)
    for p in KR.PROFILLER:
        a = CK.ahp(KR.profil_matrisi(p))
        X, f = KR.matris(du, K)
        c = CK.topsis(X, a["agirlik"], f, VK)
        du[f"puan_{p}"] = c
        ilk = du.nlargest(10, f"puan_{p}")
        ilk[[*goster, f"puan_{p}"]].to_csv(CIKTI / f"E3_ilk10_{p}.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
        sonuc["profiller"][p] = {"agirlik": dict(zip(K, a["agirlik"].round(4).tolist())), "CR": a["CR"]}
        sonuc["ilk10"][p] = (
            ilk[["il", "ilce", "basabas_en_iyi", f"puan_{p}"]].rename(columns={f"puan_{p}": "puan"}).to_dict(orient="records")
        )
    Xk, fk = KR.matris(du, K, standart=False)
    ck = CK.topsis(Xk, CK.ahp(KR.profil_matrisi("dengeli"))["agirlik"], fk, True)
    vk = du.assign(puan=ck).nlargest(10, "puan")
    vk[[*goster, "puan"]].to_csv(CIKTI / "E3_ilk10_dengeli_vektor.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    sonuc["ilk10"]["dengeli_vektor_normalizasyonu"] = vk[["il", "ilce", "basabas_en_iyi", "puan"]].to_dict(orient="records")
    # dayanıklılık (dengeli profil)
    X, f = KR.matris(du, K)
    w = CK.ahp(KR.profil_matrisi("dengeli"))["agirlik"]
    du["p_ilk10_dengeli"] = CK.dayaniklilik(X, w, f, K=10, n=1000, alfa=50, vektor=VK)
    du.nlargest(20, "p_ilk10_dengeli")[[*goster, "puan_dengeli", "p_ilk10_dengeli"]].to_csv(
        CIKTI / "E3_dayaniklilik.csv", index=False, encoding="utf-8-sig", float_format="%.3f"
    )
    # doğrulama: tüm hesaplanabilen hücreler (dışlananlar dahil; dışlama kısıtları geliştiricinin elinde değil)
    v = d[(d["hata"].fillna("") == "") & d["basabas_en_iyi"].notna()].reset_index(drop=True)
    y = v["mevcut_res"].to_numpy(bool)
    tek = {}
    for k in K:
        X1, f1 = KR.matris(v, [k])
        tek[k] = CK.auc(X1[:, 0] if f1[0] else -X1[:, 0], y)
    Xr, _ = KR.matris(v, ["ekonomi"], ruzgar=True)
    tek["ruzgar_kf"] = CK.auc(Xr[:, 0], y)
    sonuc["auc"]["tek_kriter"] = tek
    for p in KR.PROFILLER:
        Xv, fv = KR.matris(v, K)
        sonuc["auc"][f"profil_{p}"] = CK.auc(CK.topsis(Xv, CK.ahp(KR.profil_matrisi(p))["agirlik"], fv, VK), y)
    K_ng = [k for k in K if k != "guven"]
    Xv, fv = KR.matris(v, K_ng)
    eniyi = CK.en_iyi_agirlik(Xv, fv, y, n=4000, vektor=VK)
    Xw, fw = KR.matris(v, K_ng, ruzgar=True)
    eniyi_r = CK.en_iyi_agirlik(Xw, fw, y, n=4000, vektor=VK)
    sonuc["acik_tercih"] = {
        "guvensiz_ekonomi": {"auc": eniyi["auc"], "agirlik": dict(zip(K_ng, np.round(eniyi["agirlik"], 3).tolist()))},
        "guvensiz_ruzgar": {
            "auc": eniyi_r["auc"],
            "agirlik": dict(zip(["ruzgar" if k == "ekonomi" else k for k in K_ng], np.round(eniyi_r["agirlik"], 3).tolist())),
        },
    }
    puan = CK.topsis(Xv, eniyi["agirlik"], fv, VK)
    fp, tp = CK.roc(puan, y)
    j = np.linspace(0, len(fp) - 1, 101).astype(int)
    sonuc["roc"] = {"fp": fp[j].round(4).tolist(), "tp": tp[j].round(4).tolist(), "auc": eniyi["auc"]}
    sonuc["n_hucre"] = int(len(v))
    sonuc["n_mevcut"] = int(y.sum())
    # Belen: ekonomik ve risk/çevre sıralamasında yer
    du["sira_ekonomik"] = du["basabas_en_iyi"].rank(method="min")
    for p in KR.PROFILLER:
        du[f"sira_{p}"] = du[f"puan_{p}"].rank(ascending=False, method="min")
    bel = du[du["ilce"].isin(["Belen", "İskenderun", "Arsuz"])][
        ["il", "ilce", "basabas_en_iyi", "goc_azami", "sira_ekonomik", "sira_ekonomi", "sira_dengeli", "sira_risk_cevre"]
    ]
    bel.to_csv(CIKTI / "E3_belen.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    sonuc["belen"] = bel.to_dict(orient="records")
    sonuc["dislama_sayim"] = neden.value_counts().to_dict()
    (KOK / "data" / "atlas" / "v3_cok_kriterli_dogrulama.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=float))
    print(json.dumps({k: v_ for k, v_ in sonuc.items() if k not in ("roc", "ilk10")}, ensure_ascii=False, indent=1, default=float))
    for k in ("ekonomik", "dengeli", "risk_cevre"):
        print(k, pd.DataFrame(sonuc["ilk10"][k]).to_string())


if __name__ == "__main__":
    main()
