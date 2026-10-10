"""
v3 Ö1 — O&M kapsam mutabakatı ve işletme modeli: FSA ile kendi bakımı, başabaş filo büyüklüğü.

1) Kapsam tablosu: her O&M kalemi için Lazard (v1 kaynağı), LBNL (Wiser vd. 2019), Deutsche WindGuard (2024), v1 modeli,
   bakım simülasyonu (DES) ve v3 işletme modelleri (FSA / kendi) → outputs/v3E/E0_om_kapsam.csv
2) Kendi bakımının türbin başına maliyeti: Ezine profili ve hava verisiyle DES (durum stratejisi), N ∈ {7 … 140} türbin
   (ekip sayısı N ile basamaklı artar) → başabaş filo büyüklüğü (FSA merkez ve aralık uçları) → outputs/v3E/E0_isletme_basabas.csv
Çalıştırma: .venv/bin/python src/v3_E0_isletme_mutabakati.py
"""

import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import importlib.util

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger
from src.bakim import des, isletme

CIKTI = CIKTILAR / "v3E"
N_LISTE = [7, 14, 21, 28, 42, 56, 84, 112, 140]


def kapsam_tablosu(cfg: dict, des_kalem_usd_kw: dict, P_mw: float) -> pd.DataFrame:
    a = isletme.ayar(cfg)
    sh = a["sahip_kalemleri_usd_kw_yil"]
    sigorta = deger(cfg["teknoloji"]["ortak"]["sigorta"]) * deger(cfg["teknoloji"]["res"]["capex"]) / 1000
    arazi = deger(cfg["teknoloji"]["res"]["arazi"]) / 1000
    K = 1.08  # €/$
    satir = [
        # kalem, Lazard, LBNL, DWG, v1, DES, FSA, kendi, finansta ayrı mı
        (
            "Türbin planlı + plansız bakım (büyük bileşen, vinç, parça dahil)",
            "dahil (kırılımsız)",
            "14–28 (ort. 20)",
            f"{13 * K:.0f}–{17 * K:.0f} (tam bakım sözleşmesi)",
            "35 içinde",
            f"{des_kalem_usd_kw['turbin']:.1f} (kendi yaparsa)",
            f"{a['fsa']['fiyat_usd_kw_yil']:.1f}",
            f"{des_kalem_usd_kw['turbin'] * 1.0:.1f} + parça primi",
            "hayır",
        ),
        (
            "Kendi bakım organizasyonu (yönetim, depo, araç, eğitim, 7/24)",
            "dahil",
            "ölçek etkisi: 40 MW'ta 75, 250 MW'ta 45 (her şey dahil)",
            "—",
            "35 içinde",
            "yok",
            "FSA'ya dahil",
            f"{a['kendi']['organizasyon_sabit_usd_yil'] / 1e6:.1f} M$/yıl sabit",
            "hayır",
        ),
        (
            "BOP bakımı (trafo merkezi/şalt, saha içi kablo)",
            "dahil",
            "5,0 / 7,9",
            "(sonstige içinde)",
            "35 içinde",
            "yok",
            f"{sh['bop_bakimi']:.1f}",
            f"{sh['bop_bakimi']:.1f}",
            "hayır",
        ),
        (
            "Yol ve saha bakımı, O&M tesisleri",
            "dahil",
            "2,0 (O&M tesisleri)",
            "(sonstige içinde)",
            "35 içinde",
            "yok",
            f"{sh['yol_ve_saha']:.1f}",
            f"{sh['yol_ve_saha']:.1f}",
            "hayır",
        ),
        (
            "SCADA ve haberleşme",
            "dahil",
            "(varlık yönetimi içinde)",
            "(Betriebsführung içinde)",
            "35 içinde",
            "yok",
            f"{sh['scada_haberlesme']:.1f}",
            f"{sh['scada_haberlesme']:.1f}",
            "hayır",
        ),
        (
            "Varlık yönetimi ve genel giderler (teknik/ticari işletme)",
            "dahil",
            "2,2–2,6",
            f"{4 * K:.1f}–{5 * K:.1f}",
            "35 içinde",
            "yok",
            f"{sh['varlik_yonetimi']:.1f}",
            f"{sh['varlik_yonetimi']:.1f}",
            "hayır",
        ),
        (
            "Sahibin saha personeli (saha müdürü, İSG)",
            "dahil",
            "—",
            "(Betriebsführung içinde)",
            "35 içinde",
            "yok",
            f"{sh['saha_personeli']:.1f}",
            f"{sh['saha_personeli']:.1f}",
            "hayır",
        ),
        (
            "Beklenmeyen ve diğer",
            "dahil",
            "0,4 + diğer",
            f"{6 * K:.1f}–{7 * K:.1f} (sonstige)",
            "35 içinde",
            "yok",
            f"{sh['diger_beklenmeyen']:.1f}",
            f"{sh['diger_beklenmeyen']:.1f}",
            "hayır",
        ),
        (
            "Sigorta",
            "muhtemelen dahil",
            "2,6",
            f"{1 * K:.1f}",
            f"+{sigorta:.1f} ayrı (%0,35 CAPEX)",
            "yok",
            "ayrı",
            "ayrı",
            f"evet ({sigorta:.1f})",
        ),
        (
            "Arazi kirası",
            "muhtemelen dahil",
            "4,2–5,0",
            f"{18 * K:.0f}–{19 * K:.0f} (Almanya)",
            f"+{arazi:.1f} ayrı",
            "yok",
            "ayrı",
            "ayrı",
            f"evet ({arazi:.1f})",
        ),
        (
            "Emlak vergisi / yerel ödemeler",
            "muhtemelen dahil (ABD)",
            "5,0 (tahmini)",
            "—",
            "yok",
            "yok",
            "Türkiye'de RES için ayrı kalem yok",
            "—",
            "—",
        ),
        ("Şebeke (TEİAŞ) bedelleri", "—", "0,4 (grid)", "—", "ayrı", "yok", "ayrı", "ayrı", "evet"),
        ("Söküm karşılığı", "—", "—", f"{3 * K:.1f}–{4 * K:.1f}", "ayrı (ömür sonu)", "yok", "ayrı", "ayrı", "evet"),
    ]
    d = pd.DataFrame(
        satir,
        columns=[
            "kalem",
            "Lazard 2025 (24,5–40 her şey dahil)",
            "LBNL 2019 $/kW-yıl",
            "DWG 2024 $/kW-yıl",
            "v1 modeli",
            "bakım simülasyonu (DES)",
            "v3 FSA $/kW-yıl",
            "v3 kendi bakımı",
            "finansal modelde ayrı kalem",
        ],
    )
    return d


def ezine_girdileri():
    sp = importlib.util.spec_from_file_location("d2", KOK / "src" / "v3_D2_bakim_analizi.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m.saha_girdileri("Çanakkale-Ezine", 39.79, 26.33)


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    _, P, _, kf, v, fiyat = ezine_girdileri()
    cfg = config_oku()
    p = deger(cfg["v3"]["bakim"])
    omur = int(deger(cfg["proje"]["omur"]))
    tb = {}
    satir = []
    for N in N_LISTE:
        g = des.Girdi(N, P, np.ones(N), kf, v, fiyat, omur, p, "durum", None, {})
        r = des.simule(g, 30, p["tohum"])
        c = isletme.kendi_turbin_usd_yil(r["gider"], cfg)
        tb[N] = c / N
        satir.append(
            {
                "N": N,
                "ekip": des.ekip_sayisi(N, p),
                "A_enerji": float(r["A_enerji"].mean()),
                "kendi_turbin_usd_kw": c / (N * P * 1000),
                **{f"des_{k}": v_ for k, v_ in r["gider"].items()},
            }
        )
        print(satir[-1], flush=True)
    bb = isletme.basabas_filo(cfg, P, tb)
    d = pd.DataFrame(satir)
    a = isletme.ayar(cfg)
    org = a["kendi"]["organizasyon_sabit_usd_yil"]
    d["kendi_toplam_usd_kw"] = d["kendi_turbin_usd_kw"] + org / (d["N"] * P * 1000)
    d["fsa_usd_kw"] = isletme.fsa_usd_kw(cfg)
    d["kendi_ucuz_mu"] = d["kendi_toplam_usd_kw"] <= d["fsa_usd_kw"]
    d.to_csv(CIKTI / "E0_isletme_basabas.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    k14 = d.loc[d.N == 14].iloc[0]
    kt = kapsam_tablosu(cfg, {"turbin": float(k14["kendi_turbin_usd_kw"])}, P)
    kt.to_csv(CIKTI / "E0_om_kapsam.csv", index=False, encoding="utf-8-sig")
    sigorta = deger(cfg["teknoloji"]["ortak"]["sigorta"]) * deger(cfg["teknoloji"]["res"]["capex"]) / 1000
    arazi = deger(cfg["teknoloji"]["res"]["arazi"]) / 1000
    oz = {
        "N_basabas": bb["N_basabas"],
        "N_basabas_fsa_14": bb["N_basabas_fsa_dusuk"],
        "N_basabas_fsa_29": bb["N_basabas_fsa_yuksek"],
        "kendi_degisken_usd_kw_140": bb["kendi_degisken_usd_kw"],
        "fsa_toplam_usd_kw": isletme.fsa_usd_kw(cfg) + isletme.sahip_usd_kw(cfg),
        "v1_toplam_usd_kw": 35.0 + sigorta + arazi,
        "v3_fsa_toplam_sigorta_arazi_dahil_usd_kw": isletme.fsa_usd_kw(cfg) + isletme.sahip_usd_kw(cfg) + sigorta + arazi,
        "faz_D_toplam_usd_kw_14": 25.5 + sigorta + arazi,
        "sigorta_usd_kw": sigorta,
        "arazi_usd_kw": arazi,
        # literatüre kalibre: kendi bakımı ölçekte türbin O&M'de %19 (IHS Markit) – %30 (Briggs 2017) tasarruf (LBNL, Wiser vd. 2019)
        **{
            f"N_basabas_literatur_tasarruf_{int(100 * t)}": int(np.ceil(org / (isletme.fsa_usd_kw(cfg) * t * P * 1000)))
            for t in (0.19, 0.25, 0.30)
        },
    }
    (CIKTI / "E0_isletme_ozet.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(oz, ensure_ascii=False, indent=1, default=float))
    print(d[["N", "ekip", "kendi_turbin_usd_kw", "kendi_toplam_usd_kw", "fsa_usd_kw", "kendi_ucuz_mu", "A_enerji"]].round(2).to_string())


if __name__ == "__main__":
    main()
