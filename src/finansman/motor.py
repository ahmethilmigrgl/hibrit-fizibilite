"""
Tam analize finansman katmanı (v4 Faz H): verim bütçesi → kredi veren senaryoları → borç LP'si → Monte Carlo şelalesi.

Kredi veren senaryosu (yapı başına, deterministik): Monte Carlo'nun gecikmesiz ortalama girdi yolları (fiyat — tavanlı kriz
yılları hariç —, kanibalizasyon, SFK, sistem kesintisi), fiyat × fiyat_carpani; hava yılları ortalaması; enerji çarpanı = hibrit P_x(ufuk)/P50 (RES m ve GES m_ges).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from src.ayarlar import deger
from src.finansman import borc_lp, selale, verim
from src.risk.degerleme import nakit_akislari


def _vade(cfg: dict, yapi: str) -> int:
    if yapi == "tuccar":
        return int(deger(cfg["borc"]["vade"]))
    if yapi == "ppa":
        return int(deger(cfg["gelir_yigini"]["ppa"]["borc_vadesi"]))
    return int(deger(cfg["yekdem"])["borc_vadesi"])


def kredi_senaryosu(
    o, t, tb_T, tb_Y, yapi: str, ort: dict, katilim: list[float] | None, oran: float, fiyat_carpani: float, yh_carpani: float = 1.0
) -> dict:
    """Tek senaryo (enerji oranı `oran`) için yıllık reel CFADS, sözleşmeli ve batarya gelir payları."""
    N = o.v.omur
    g = o.beklenen_girdi(1.0)
    g.update({"L": (ort["L_tavansiz"] * fiyat_carpani)[None, :], "h": ort["h"][None, :], "a": (ort["a"] * yh_carpani)[None, :]})
    g["m"] = g["m"] * oran
    g["m_ges"] = np.full((1, N), oran)
    g["m_disdeger"] = True
    c = o.c
    tt = t
    if yapi == "yekdem_opsiyon":
        yk = deger(o.cfg["yekdem"])
        phi = np.zeros(N)
        phi[: yk["sure_yil"]] = np.asarray(katilim if katilim is not None else np.ones(yk["sure_yil"]))[: yk["sure_yil"]]
        g.update(
            {
                "phi": phi[None, :],
                "ip": (phi[None, :] >= 0.5).astype(int),
                "ppa_fiyat": ort["yk_reel"][None, :],
                "desarj_sozlesmeli": True,
                "kesinti_gelir": (phi * ort["kes_y"][0] + (1 - phi) * ort["kes_m"][0])[None, :],
                "kesinti_enerji": (phi * ort["kes_y"][1] + (1 - phi) * ort["kes_m"][1])[None, :],
            }
        )
        c = replace(o.c, ppa_pay=1.0, ppa_vade=yk["sure_yil"], ppa_fiyat=float(ort["yk_reel"][: yk["sure_yil"]].mean()))
        tt, tb = replace(t, ppa=True), tb_Y
    else:
        g.update({"kesinti_gelir": ort["kes_m"][0][None, :], "kesinti_enerji": ort["kes_m"][1][None, :]})
        tb = tb_T
        if yapi == "ppa":
            g["tuccar_dispatch"] = True
            tt = replace(t, ppa=True)
    r = nakit_akislari(tt, tb, c, g)
    k = np.arange(1, N + 1)
    if "phi" in g:
        phi_k = g["phi"][0]
        fiyat = g["ppa_fiyat"][0]
        soz = phi_k * fiyat * (r["E_res"] + r["E_ges"])[0]
    elif tt.ppa:
        phi_k = np.where(k <= c.ppa_vade, c.ppa_pay, 0.0)
        soz = phi_k * c.ppa_fiyat * (r["E_res"] + r["E_ges"])[0]
    else:
        soz = np.zeros(N)
    gelir = (r["gelir_spot"] + r["gelir_bess"] + np.broadcast_to(r["gelir_yh"], r["gelir_spot"].shape) + r["gelir_yekg"])[0]
    pay = np.clip(np.where(gelir > 0, soz / np.maximum(gelir, 1e-9), 0.0), 0, 1)
    bat = (r["gelir_bess"] + np.broadcast_to(r["gelir_yh"], r["gelir_spot"].shape))[0]
    pay_b = np.clip(np.where(gelir > 0, bat / np.maximum(gelir, 1e-9), 0.0), 0, 1 - pay)
    return {"cfads": r["cfads"][0], "pay": pay, "pay_b": pay_b, "satilan": r["satilan"][0], "capex": float(r["capex_top"][0])}


def finansman_analizi(o, t, tb_T, tb_Y, mc: dict, yapilar: list[str], yillik, sigma_res: float | None) -> dict:
    """
    mc: yakinsayan_mc(..., finans=True) sonucu. yillik: hava yılı başına MWh/MW (uretim_ozeti). Döndürür: verim bütçesi ve
    yapı başına borç, kredi metrikleri, bağlayıcı kısıtlar ve şelale olasılıkları (JSON'a uygun).
    """
    cfg = o.cfg
    fz = deger(cfg["v4"]["finansman"])
    vv = deger(cfg["v4"]["verim"])
    b = verim.butce(yillik, t.res_mw, t.ges_mw, sigma_res, cfg)
    pi = deger(cfg["finans"]["abd_enflasyonu"])
    faiz = deger(cfg["borc"]["faiz_nominal"])
    kaldirac = deger(cfg["borc"]["azami_borc_orani"])
    nb = o.v.insaat_suresi
    N = o.v.omur
    enf = (1 + pi) ** (nb + np.arange(1, N + 1))
    fin = mc["finans"]
    ort = fin["ortalama"]
    sonuc = {"verim": {
        "P50_mwh": b["P50_mwh"], "E": b["E"], "rho_iav": b["rho_iav"],
        "bilesenler": b["bilesenler"].to_dict(orient="records"), "p": b["p"].to_dict(orient="records"),
    }, "yapilar": {}}  # fmt: skip
    # Simülasyon P değerleri (şebeke kısıtı, batarya ve kesinti sonrası satılan enerji): ilk yıl ve ilk 10 yılın ortalaması
    y0 = yapilar[0]
    sat = fin["yapilar"][y0]["satilan"]
    sonuc["verim"]["simulasyon"] = {
        "1": verim.simulasyon_p(sat[:, 0], vv["p_seviyeleri"]),
        "10": verim.simulasyon_p(sat[:, :10].mean(1), vv["p_seviyeleri"]),
    }
    capex_carp = float((np.asarray(o.v.capex_takvimi) * (1 + pi) ** (np.arange(nb) + 1)).sum())

    def yapi_boyutla(y: str, butce_: dict) -> tuple[dict, borc_lp.BorcLP, float]:
        """Yapı y için kredi veren senaryoları + borç LP'si. Döndürür: senaryolar, LP sonucu, CAPEX (reel)."""
        katilim = (mc.get("ek", {}).get(y) or {}).get("katilim_yil")
        dur = {}
        for d in fz["durumlar"]:
            r = verim.oran(butce_, d["p"], d["ufuk"])
            ks = kredi_senaryosu(
                o, t, tb_T, tb_Y, y, ort, katilim, r, fz["fiyat_carpani"] * d.get("fiyat_carpani", 1.0), d.get("yh_carpani", 1.0)
            )
            p_t = 1 - ks["pay"] - ks["pay_b"]
            dscr = 1.0 / (ks["pay"] / d["dscr_sozlesmeli"] + ks["pay_b"] / d.get("dscr_batarya", d["dscr_tuccar"]) + p_t / d["dscr_tuccar"])
            dur[d["ad"]] = {**ks, "oran": r, "dscr": dscr}
        capex_ = next(iter(dur.values()))["capex"]
        lp_ = borc_lp.boyutla(
            {a: v["cfads"] * enf for a, v in dur.items()},
            {a: v["dscr"] for a, v in dur.items()},
            _vade(cfg, y), faiz, capex_ * capex_carp, kaldirac, fz["negatif_amortisman_yasak"],
        )  # fmt: skip
        return dur, lp_, capex_

    # Saha ölçümü sonrası (rüzgâr direği/LiDAR + uzun dönem düzeltmesi): RES model belirsizliği olcumlu_model'e iner
    b_olcum = verim.butce(yillik, t.res_mw, t.ges_mw, vv["olcumlu_model"], cfg) if t.res_mw > 0 else None
    if b_olcum is not None:
        sonuc["verim"]["olcum_sonrasi_p"] = b_olcum["p"].to_dict(orient="records")
    for y in yapilar:
        dur, lp, capex = yapi_boyutla(y, b)
        capex_nom = capex * capex_carp
        vade = lp.vade
        p50 = dur.get("P50", next(iter(dur.values())))
        met = borc_lp.metrikler(lp, p50["cfads"] * enf, faiz)
        fy = fin["yapilar"][y]
        kw = dict(
            cfads=fy["cfads"], vergi=fy["vergi"], capex_top=fy["capex_top"], capex_takvimi=list(o.v.capex_takvimi), enf=enf,
            faiz=faiz, vergi_orani=o.v.vergi, dsra_ay=fz["dsra_ay"], kilit_dscr=fz["kilit_dscr"],
            ozkaynak_maliyeti=fz["ozkaynak_maliyeti_reel"],
        )  # fmt: skip
        sl = selale.selale(borc=lp, **kw)
        # Olasılık tabanlı boyutlandırma: aynı profil şekliyle P(temerrüt) ≤ pd_hedef olan en büyük borç (kaldıraç tavanı içinde)
        ust = min(2.0, kaldirac * capex_nom / lp.borc_nom) if lp.borc_nom > 0 else 0.0
        a_pd, sl_pd = selale.pd_hedefli(lp, fz["pd_hedef"], ust=ust, **kw) if ust > 0 else (0.0, sl)
        borc_reel = lp.borc_nom / (1 + pi) ** nb
        # Temerrüt olasılığı – borç oranı eğrisi: kural tabanlı servis profili, kaldıraç tavanına kadar ölçeklenerek
        egri = []
        if lp.borc_nom > 0:
            for oran_ in np.linspace(0.05, kaldirac, 15):
                a_ = oran_ * capex / borc_reel
                egri.append({"borc_orani": float(oran_), "p_temerrut": selale.selale(borc=selale.olcekle(lp, a_), **kw)["p_temerrut"]})
        bag_say = {}
        for bb in lp.baglayici:
            if bb["dual"] > 1e-9:
                bag_say[bb["senaryo"]] = bag_say.get(bb["senaryo"], 0) + 1
        sonuc["yapilar"][y] = {
            "vade": vade,
            "borc_reel_musd": borc_reel / 1e6,
            "borc_orani": borc_reel / capex,
            "kaldirac_bagliyor": lp.kaldirac_bagliyor,
            "anapara_kisiti": lp.anapara_kisiti,
            "baglayan_senaryo_yil": bag_say,
            "baglayici": lp.baglayici,
            **{k: v for k, v in met.items() if k != "borc_nom"},
            "dscr_senaryo_min": {a: float(np.min(v)) for a, v in lp.dscr.items()},
            "senaryo_oranlari": {a: v["oran"] for a, v in dur.items()},
            "sozlesmeli_pay_ilk5": float(np.mean(p50["pay"][:5])),
            "batarya_pay_ilk5": float(np.mean(p50["pay_b"][:5])),
            # kredi veren P50 senaryosu / Monte Carlo ortalaması (vade içi CFADS toplamı; vergi ve tavan doğrusalsızlığı farkı)
            "kredi_p50_mc_orani": float(p50["cfads"][:vade].sum() / max(fy["cfads"][:, :vade].mean(0).sum(), 1e-9)),
            "servis_reel": (lp.servis / enf).tolist(),
            "cfads_reel": {a: v["cfads"].tolist() for a, v in dur.items()},
            "cfads_mc_reel": {
                "ortalama": fy["cfads"].mean(0).tolist(),
                "p10": np.percentile(fy["cfads"], 10, axis=0).tolist(),
                "p90": np.percentile(fy["cfads"], 90, axis=0).tolist(),
            },
            "selale": {k: v for k, v in sl.items() if not k.startswith("_")},
            "olcum_sonrasi_borc_reel_musd": (yapi_boyutla(y, b_olcum)[1].borc_nom / (1 + pi) ** nb / 1e6) if b_olcum is not None else None,
            "pd_egrisi": egri,
            "pd_hedefli": {
                "pd_hedef": fz["pd_hedef"],
                "olcek": a_pd,
                "borc_reel_musd": a_pd * borc_reel / 1e6,
                "borc_orani": a_pd * borc_reel / capex,
                "dscr_min_p50_kredi": float(np.min(lp.dscr.get("P50", [np.nan])) / a_pd) if a_pd > 0 else None,
                "selale": {k: v for k, v in sl_pd.items() if not k.startswith("_")},
            },
        }
    return sonuc
