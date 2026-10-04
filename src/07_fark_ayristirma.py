"""
Deterministik baz ile Monte Carlo beklenen NPV'si arasındaki farkın ayrıştırılması (nihai baz vaka: YEKDEM yıllık
opsiyonu (nominal) + tüccar, RES 58,8 MW + batarya 30 MW / 60 MWh).

A1 — Fiyat ortalaması: simüle edilen reel fiyat yollarının proje yılı bazında ortalaması ve iskonto ağırlıklı ömür
     ortalaması; 58 USD/MWh baz varsayımıyla karşılaştırma (log-fiyat sürecinin merkezi: monte_carlo.log_merkez).
A2 — Fark şelalesi: deterministik girdiler (Excel modeliyle aynı: L = 58 sabit, P50, ortalama hava, baz SFK yolu,
     beklenen kesinti, CAPEX = 1) sırayla stokastik karşılıklarıyla değiştirilir; her adımın E[NPV] katkısı ölçülür.
     Aynı rastgele sayılar (07_gelir_yapilari ile aynı tohumlar) kullanılır; son adım nihai baz vakayı yeniden üretir.
       S0 deterministik baz (COD 2030)
       S1 (i)   fiyat ortalaması sapması: L = simülasyonların ortalama fiyat yolu (deterministik)
       S2 (iii) fiyat oynaklığı — batarya (arbitraj + SFK) gelir satırları   } fiyat yolları stokastik, YEKDEM kapalı,
          (iv)  fiyat oynaklığı — vergi/zarar mahsubu vb. diğer satırlar     } tavan yok
       S3 (iv)  kriz yıllarında düzenleyici tavan
       S4 (ii)  YEKDEM yıllık opsiyonu (dışbükeylik) + YEKDEM fiyat belirsizliği
       S5 (iii) SFK doyum senaryoları (baz yol yerine senaryo karışımı)
       S6 (v)   hava, RES model hatası, kanibalizasyon ve sistem kesintisi belirsizliği
       S7 (iv)  CAPEX / OPEX / batarya bozunma belirsizliği
       S8       takvim: COD 2030 → takvim P50 (Kasım 2029)

Çalıştırma: .venv/bin/python src/07_fark_ayristirma.py [etiket]   (etiket: çıktı dosya son eki, ör. "once")
Çıktı: outputs/07/fiyat_ortalamasi{_etiket}.csv, fark_ayristirma{_etiket}.csv, fark_ayristirma{_etiket}.png
"""

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import src.gorsel as g
from src.ayarlar import CIKTILAR, deger
from src.risk.degerleme import nakit_akislari
from src.risk.doyum import ornekle_doyum
from src.risk.monte_carlo import log_merkez, ornekle, ucgen_ters, yekdem_katilim
from src.risk.yekdem_tablo import yekdem_tablosu

CIKTI = CIKTILAR / "07"
ETIKET = f"_{sys.argv[1]}" if len(sys.argv) > 1 else ""


def yukle(ad):
    spec = importlib.util.spec_from_file_location(ad, Path(__file__).parent / f"{ad}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tr(x: float, fmt: str = "+.2f") -> str:
    return format(x, fmt).replace(".", ",").replace("-", "−")


def main():
    gyp, bv = yukle("07_gelir_yapilari"), yukle("07_baz_vaka")
    pm = yukle("08_excel_model").PythonModel()  # deterministik baz (Excel ile birebir mutabık)
    o, cfg = pm.o, pm.cfg
    v = o.v
    N, n = v.omur, deger(cfg["monte_carlo"]["senaryo_sayisi"])
    tohum = deger(cfg["monte_carlo"]["tohum"])
    Kmax, KD = 3, 2  # KD: deterministik modelin COD'u 2030 = model COD + 2
    yil_ext = np.arange(o.yillar[0], o.yillar[0] + N + Kmax)
    assert o.yillar[0] + KD == pm.yillar[0]

    # --- 07_gelir_yapilari ile aynı kurulum (yalnız GYo) ---------------------------------------------------------
    yk = deger(cfg["yekdem"])
    pi = deger(cfg["finans"]["abd_enflasyonu"])
    rng = np.random.default_rng(tohum + 7)
    yk_nom = 10 * ucgen_ters(rng.random(n), yk["taban_usd_sent"], yk["tepe_usd_sent"], yk["tavan_usd_sent"])
    yk_reel = yk_nom[:, None] / (1 + pi) ** (yil_ext - 2026)[None]
    c_y = replace(o.c, ppa_pay=1.0, ppa_vade=yk["sure_yil"], ppa_fiyat=float(yk_reel[:, : yk["sure_yil"]].mean()))
    ad = {k: v_ for k, v_ in json.loads((CIKTILAR / "05_risk" / "adaylar.json").read_text()).items()}
    from src.risk.tasarim import Tasarim

    C_ = Tasarim(**next(v_ for k, v_ in ad.items() if k[0] == "C"))
    es = deger(cfg["stres_testi"]["esnek_tasarimlar"])["asamali"]
    F2Y60 = replace(replace(C_, ad="F2a", bess_mw=es["ilk_mw"], bess_mwh=es["ilk_mwh"]), ad="F2Y60", bess_mw=30, bess_mwh=60)
    tb = yekdem_tablosu(o, F2Y60)
    t = replace(replace(C_, ad="G", bess_mw=30, bess_mwh=60), ppa=True)
    gx = ornekle(cfg, n, yil_ext, o.oran0, tohum)["girdi"]
    fo = float(pd.read_csv(CIKTILAR / "05_risk" / "s_firsat_maliyeti.csv", index_col=0).loc["Fırsat maliyeti / 2026 seviyesi", "deger"])
    dy = ornekle_doyum(cfg, n, yil_ext, fo, tohum)
    gx["a"] = dy["a"]
    os_ = deger(cfg["ortak_surucu"])
    emme = lambda mw, yil: np.clip(
        mw * os_["sure_saat"] * os_["fazla_gun"] * os_["verim"] / (os_["fazla_2026_twh"] * 1e6 * (1 + os_["fazla_buyume"]) ** (yil - 2026)),
        0,
        1,
    )
    a_abs = emme(dy["kurulu_mw"], yil_ext[None, :])
    a26 = float(emme(1000.0, 2026))
    gx["h"] = gx["h"] + (o.oran0 - gx["h"]) * a_abs * os_["kanibalizasyon_geri_alma"]
    kesl = pd.read_csv(CIKTILAR / "07" / "kesinti_batarya_kurtarma.csv", index_col=0)
    kurtarma = float(kesl.loc["30 MW / 52,5 MWh", "Batarya kurtarma payı [%]"]) / 100
    df_ = float(
        kesl.loc["Bataryasız", "Kayıp [M USD]"] / (deger(cfg["kesinti"])["oran_2026"] * kesl.loc["Bataryasız", "Kesintisiz gelir [M USD]"])
    )
    kw = dict(carp_ozel=(1 - a_abs) / (1 - a26))
    kes_yb = gyp.kesinti_ornekle(cfg, n, yil_ext, dy["senaryo"], np.random.default_rng(tohum + 11), True, kurtarma, df_, yekdem=True, **kw)
    kes_b = gyp.kesinti_ornekle(cfg, n, yil_ext, dy["senaryo"], np.random.default_rng(tohum + 11), True, kurtarma, df_, **kw)
    esik = deger(cfg["yekdem_opsiyon"])["esik_carpani"]
    yk_det_ext = pm.yk_nom * 10 / (1 + pi) ** (yil_ext - 2026)
    dfk = (1 + v.wacc) ** -(v.insaat_suresi + np.arange(N) + 1.0)

    # --- A1: fiyat ortalaması ----------------------------------------------------------------------------------------
    L_proj = gx["L"][:, KD : KD + N]
    DFp = (1 + v.wacc) ** -(np.arange(N) + 1 + v.insaat_suresi + KD)
    fs_ = deger(cfg["monte_carlo"]["fiyat_sureci"])
    fo_ = deger(cfg["monte_carlo"]["fiyat_uzun_ortalama"])
    durağan = np.exp(log_merkez(cfg) + fo_["log_sd"] ** 2 / 2 + fs_["sigma"] ** 2 / (2 * (1 - fs_["phi"] ** 2)))
    a1 = pd.DataFrame(
        {
            "Proje yılı": np.arange(1, N + 1),
            "Takvim yılı": pm.yillar,
            "Ortalama reel fiyat [USD/MWh]": L_proj.mean(0),
            "Medyan [USD/MWh]": np.median(L_proj, 0),
            "Tavanlı yıl payı [%]": 100 * gx["tavan"][:, KD : KD + N].mean(0),
        }
    )
    ozet = {
        "Baz varsayım [USD/MWh]": 58.0,
        "Log-süreç merkezi exp(m) [USD/MWh]": float(np.exp(log_merkez(cfg))),
        "Durağan beklenen fiyat, kriz hariç (analitik) [USD/MWh]": float(durağan),
        "Simüle ortalama, ömür boyu (basit) [USD/MWh]": float(L_proj.mean()),
        "Simüle ortalama, iskonto ağırlıklı [USD/MWh]": float((L_proj.mean(0) * DFp).sum() / DFp.sum()),
        "Simüle medyan, iskonto ağırlıklı [USD/MWh]": float((np.median(L_proj, 0) * DFp).sum() / DFp.sum()),
        "Fiyat tanımı (config)": fo_.get("tanim", "medyan"),
    }
    a1.to_csv(CIKTI / f"fiyat_ortalamasi{ETIKET}.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    pd.Series(ozet, name="değer").to_csv(CIKTI / f"fiyat_ortalamasi_ozet{ETIKET}.csv", encoding="utf-8-sig")
    print("A1 — fiyat ortalaması:")
    [print(f"  {k}: {v_:.2f}" if isinstance(v_, float) else f"  {k}: {v_}") for k, v_ in ozet.items()]

    # --- A2: sıralı ayrıştırma ------------------------------------------------------------------------------------
    def tile(x):
        return np.tile(np.asarray(x, float)[None, :], (n, 1))

    def kesinti_det(katil):
        kap = tile(pm.kappa)
        kg = np.where(
            katil,
            kap * (1 - pm.tazmin * pm.deger_faktoru) * (1 - pm.kurtarma_y),
            kap * pm.deger_faktoru * (1 - pm.tazmin) * (1 - pm.kurtarma_m),
        )
        return kg, kap * (1 - pm.kurtarma_y)

    def kesinti_mc(katil, kd):
        sl = slice(kd, kd + N)
        return (
            np.where(katil, kes_yb["kesinti_gelir"][:, sl], kes_b["kesinti_gelir"][:, sl]),
            np.where(katil, kes_yb["kesinti_enerji"][:, sl], kes_b["kesinti_enerji"][:, sl]),
        )

    def degerle(adim: int, kd: int = KD):
        """adim'a kadarki bileşenler stokastik, diğerleri deterministik; (E[NPV], batarya geliri PV) döndürür."""
        sl = slice(kd, kd + N)
        L = tile(np.full(N, 58.0)) if adim < 1 else (tile(gx["L"][:, sl].mean(0)) if adim < 2 else gx["L"][:, sl])
        tav = gx["tavan"][:, sl] if adim >= 3 else np.zeros((n, N), bool)
        if adim >= 4:
            yol = yk_reel[:, sl]
            katil = yekdem_katilim(cfg, gx["L"], yk_reel, kd, N, esik, yk["sure_yil"])
        else:
            yol = tile(pm.yekdem_reel(False))
            if adim == 0:  # Excel/Python deterministik kuralı: YEKDEM reel > eşik × 58
                katil = tile((pm.yekdem_reel(False) > esik * 58.0) & (np.arange(1, N + 1) <= yk["sure_yil"])).astype(bool)
            elif adim == 1:  # ortalama fiyat yolu ve ortalama YEKDEM fiyatıyla aynı karar kuralı
                katil = yekdem_katilim(cfg, tile(gx["L"].mean(0)), tile(yk_det_ext), kd, N, esik, yk["sure_yil"])
            else:  # S2–S3: YEKDEM kapalı (saf tüccar değerlemesi)
                katil = np.zeros((n, N), bool)
        a = gx["a"][:, sl] if adim >= 5 else tile(pm.a_sfk)
        gk = {
            "L": L,
            "tavan": tav,
            "a": a,
            "phi": katil.astype(float),
            "ip": katil.astype(int),
            "ppa_fiyat": yol,
            "desarj_sozlesmeli": True,
        }
        if adim >= 6:
            gk.update({"w": gx["w"][:, sl], "s": gx["s"][:, sl], "m": gx["m"][:, sl], "h": gx["h"][:, sl]})
            gk["kesinti_gelir"], gk["kesinti_enerji"] = kesinti_mc(katil, kd)
        else:
            gk.update({"ws_ortalama": True, "m": np.ones((n, N)), "h": tile(pm.h)})
            gk["kesinti_gelir"], gk["kesinti_enerji"] = kesinti_det(katil)
        if adim >= 7:
            gk.update(
                {
                    "capex_res": gx["capex_res"],
                    "capex_ges": gx["capex_ges"],
                    "opex": gx["opex"],
                    "bozunma": gx["bozunma"],
                    "capex_bess": gx["capex_bess"] * (1 - deger(cfg["stres_testi"]["bess_capex_dususu"])) ** kd,
                }
            )
        else:
            gk.update({k: np.ones(n) for k in ["capex_res", "capex_ges", "capex_bess", "opex", "bozunma"]})
        r = nakit_akislari(t, tb, c_y, gk)
        iskonto = (1 + v.wacc) ** -kd
        bat = ((r["gelir_bess"] + np.atleast_2d(r["gelir_yh"])) @ dfk) * iskonto
        return float(r["npv"].mean() * iskonto / 1e6), float(bat.mean() / 1e6), r["npv"] * iskonto / 1e6

    e0 = pm.sonuc("YEKDEM nominal", "Baz", "P50", True)["NPV [M USD]"]
    sonuc = {i: degerle(i) for i in range(8)}
    print(f"S0 deterministik: Excel/Python {e0:.3f} | ayrıştırma çalıştırıcısı {sonuc[0][0]:.3f}")
    # S8: takvim P50 gecikmesi (07_baz_vaka ile aynı ara değerleme)
    k_cod, cod = bv.gecikme(CIKTI / "takvim_ozet.csv")
    k0 = int(np.floor(k_cod))
    w = k_cod - k0
    x_son = (1 - w) * degerle(7, k0)[2] + w * degerle(7, k0 + 1)[2] if k0 != KD or w > 1e-9 else sonuc[7][2]
    z = np.load(CIKTI / "gelir_yapilari_npv_erteleme.npz")
    referans = bv.dagilim(z, "GYo", k_cod).mean()
    print(f"Son adım: {x_son.mean():.3f} | baz vaka (07_gelir_yapilari) {referans:.3f}")

    d_bat = sonuc[2][1] - sonuc[1][1]
    satir = [
        ("Deterministik baz (58 USD/MWh sabit, COD 2030)", "—", sonuc[0][0]),
        ("Fiyat ortalaması sapması", "(i)", sonuc[1][0] - sonuc[0][0]),
        ("Fiyat oynaklığı: batarya (arbitraj + SFK) gelirleri", "(iii)", d_bat),
        ("Fiyat oynaklığı: vergi, mahsup ve diğer satırlar", "(iv)", sonuc[2][0] - sonuc[1][0] - d_bat),
        ("Kriz yıllarında düzenleyici tavan", "(iv)", sonuc[3][0] - sonuc[2][0]),
        ("YEKDEM yıllık opsiyonu (dışbükeylik)", "(ii)", sonuc[4][0] - sonuc[3][0]),
        ("SFK doyum senaryoları (karışım ≠ baz yol)", "(iii)", sonuc[5][0] - sonuc[4][0]),
        ("Hava, model hatası, kanibalizasyon, kesinti", "(v)", sonuc[6][0] - sonuc[5][0]),
        ("CAPEX / OPEX / bozunma belirsizliği", "(iv)", sonuc[7][0] - sonuc[6][0]),
        (f"Takvim: COD 2030 → {cod} (P50)", "—", float(x_son.mean()) - sonuc[7][0]),
        ("Monte Carlo beklenen NPV (baz vaka)", "—", float(x_son.mean())),
    ]
    tablo = pd.DataFrame(satir, columns=["Adım", "Bileşen", "E[NPV] katkısı [M USD]"])
    tablo.to_csv(CIKTI / f"fark_ayristirma{ETIKET}.csv", encoding="utf-8-sig", index=False, float_format="%.3f")
    print(tablo.round(3).to_string(index=False))
    grafik(tablo, ozet)


def grafik(tablo: pd.DataFrame, ozet: dict):
    fig, ax = plt.subplots(figsize=(12.5, 5.6))
    deg = tablo["E[NPV] katkısı [M USD]"].to_numpy()
    kum = deg[0]
    yol = np.r_[deg[0], deg[0] + np.cumsum(deg[1:-1])]
    ax.set_ylim(min(yol.min(), deg[-1], 0) - 0.6, max(yol.max(), deg[-1], 0) + 0.7)
    for i, d in enumerate(deg):
        if i == 0 or i == len(deg) - 1:
            ax.bar(i, d, color=g.RENK_RES if i else g.SOLUK, width=0.62)
            ax.text(
                i,
                d + (0.25 if d >= 0 else -0.25),
                tr(d, "+.2f"),
                ha="center",
                va="bottom" if d >= 0 else "top",
                fontsize=9,
                fontweight="bold",
            )
            continue
        ax.bar(i, d, bottom=kum, color=g.RENK_HIBRIT if d >= 0 else g.RENK_GES, width=0.62)
        ax.text(i, max(kum, kum + d) + 0.25, tr(d), ha="center", va="bottom", fontsize=8.5)
        kum += d
    etiket = [f"{a}\n{b}" if b != "—" else a for a, b in zip(tablo["Adım"], tablo["Bileşen"])]
    import textwrap

    ax.set_xticks(
        range(len(deg)),
        [textwrap.fill(e.split("\n")[0], 16) + ("\n" + e.split("\n")[1] if "\n" in e else "") for e in etiket],
        fontsize=7.6,
    )
    ax.axhline(0, color=g.MUREKKEP, lw=0.8)
    ax.set_ylabel("Beklenen NPV [M USD]")
    g.eksen_sade(ax)
    g.baslik(
        fig,
        "Deterministik baz ile Monte Carlo beklenen NPV'si arasındaki fark",
        f"Nihai baz vaka (YEKDEM yıllık opsiyonu + tüccar). Bileşenler sırayla stokastik yapıldı; aynı rastgele sayılar. "
        f"Simüle fiyat ortalaması (iskonto ağırlıklı): {tr(ozet['Simüle ortalama, iskonto ağırlıklı [USD/MWh]'], '.1f')} USD/MWh",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    g.kaynak_notu(fig, "Kaynak: kendi modelim (Monte Carlo 10.000 simülasyon, ortak rastgele sayılar). Reel 2026 USD.")
    fig.savefig(CIKTI / f"fark_ayristirma{ETIKET}.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
