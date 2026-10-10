"""
v3 Faz D motor katmanı: türbin yerleşimi (iz kaybı) ve bakım/güvenilirlik modellerinin analiz akışına bağlanması.

Taban profil (ortak.hazirla, v3 açıkken): tek referans türbin, sahanın GWA_ref konumu, izsiz, kullanılabilirlik hariç,
taban kayıp λ = 1 − 0,88 / ((1 − W_ref) · A_k) (config v3.kayip; atlas kalibrasyonuyla tutarlı göreli kural).
Hızlı tarama: önceden hesaplanmış tablolar (data/atlas/v3_hizli_tablolar.csv): iç iz kaybı W(N) ve kullanılabilirlik / O&M.
Tam analiz:
    1) MILP öncesi: sahanın aday konumları + vekil iz modeli → açgözlü iz verimi eğrisi η(N) (konum kazancı × iç iz) ×
       komşu izi (PyWake, açgözlü yerleşimde) → kapasite MILP'ine parçalı doğrusal; kullanılabilirlik/O&M tablodan.
    2) Seçilen N için yerleşim (config v3.yerlesim.yontem) → PyWake referansı (komşularla) → saatlik çiftlik profili.
    3) Ayrık olay simülasyonu (çizelge MILP + stok + üç strateji) → kullanılabilirlik, O&M, yıllık sapma → finans + MC.
"""

from __future__ import annotations

import copy
import math
import os
import time
from functools import lru_cache

import numpy as np
import pandas as pd

from src.ayarlar import deger
from src.finans.veri import UretimProfili, _standart_yil
from src.motor.ortak import Hazirlik, _ata, profil_degistir


@lru_cache(maxsize=1)
def hizli_tablo() -> pd.DataFrame | None:
    from src import veri_katmani

    p = veri_katmani.yol("atlas/v3_hizli_tablolar.csv", zorunlu=False)
    return None if p is None else pd.read_csv(p).set_index("N")


def _tablo_degeri(kolon: str, N: int, varsayilan: float) -> float:
    t = hizli_tablo()
    if t is None or kolon not in t.columns:
        return varsayilan
    N = int(min(max(N, t.index.min()), t.index.max()))
    v = float(t.loc[N, kolon])
    return v if math.isfinite(v) else varsayilan


def iz_hizli(N: int) -> float:
    """Önceden hesaplanmış medyan iç iz kaybı (açgözlü yerleşim, 2 km yarıçap, 12 örnek saha)."""
    return 0.0 if N <= 1 else _tablo_degeri("ic_iz_medyan", N, 0.04)


def bakim_hizli(N: int, cfg: dict) -> dict:
    k = deger(cfg["v3"]["kayip"])
    return {
        "A": _tablo_degeri("A_enerji", N, 0.97),
        "om_usd_mw_yil": _tablo_degeri("om_usd_mw_yil", N, deger(cfg["teknoloji"]["res"]["opex_sabit"])),
        "A_yil_sd": _tablo_degeri("A_yil_sd", N, 0.015),
        "A_tekrar_sd": _tablo_degeri("A_tekrar_sd", N, 0.003),
        "A_k": k["kalibrasyon_kullanilabilirligi"],
    }


def _bakim_cfg(cfg: dict, kv) -> tuple[dict, str]:
    c = copy.deepcopy(cfg)
    st = kv.bakim_stratejisi or deger(cfg["v3"]["bakim"])["strateji"]
    _ata(c, "v3.bakim", {**deger(cfg["v3"]["bakim"]), "strateji": st})
    return c, st


def bakim_uygula(cfg: dict, kv, A: float, om_usd_mw_yil: float, yil_sd: float, tekrar_sd: float) -> tuple[dict, float]:
    """Kullanılabilirlik ve O&M'i config'e işler. Döndürür: (yeni config, profile uygulanacak kullanılabilirlik)."""
    c = copy.deepcopy(cfg)
    if kv.bakim_modeli == "sabit":  # v2 eşdeğeri: kalibrasyondaki kullanılabilirlik, v1 OPEX
        return c, deger(cfg["v3"]["kayip"])["kalibrasyon_kullanilabilirligi"]
    _ata(c, "teknoloji.res.opex_sabit", float(om_usd_mw_yil))
    _ata(c, "monte_carlo.kullanilabilirlik", {"sim_sd": float(tekrar_sd), "yil_sd": float(yil_sd)})
    return c, float(A)


def res_olcekli(u: UretimProfili, carpan: float) -> UretimProfili:
    return UretimProfili(ges=u.ges, res=np.clip(u.res * carpan, 0, 1), hava_yillari=u.hava_yillari)


# ------------------------------------------------------------------------------------------------------------- hızlı tarama
def hizli_hazirla(h: Hazirlik, kv) -> tuple[Hazirlik, dict]:
    """Taban profile tablo kullanılabilirliği ve O&M'i uygular; iz kaybı tasarım başına (iz_hizli) uygulanır."""
    tg = deger(h.cfg["optimizasyon"]["turbin_gucu"])
    N_ref = max(1, math.ceil(h.saha.baglanti_mw / tg))
    b = bakim_hizli(N_ref, h.cfg)
    cfg2, A = bakim_uygula(h.cfg, kv, b["A"], b["om_usd_mw_yil"], b["A_yil_sd"], b["A_tekrar_sd"])
    h2 = profil_degistir(h, h.profil["res_kf"].to_numpy() * A, cfg2)
    bilgi = {
        "kullanilabilirlik": A,
        "om_usd_mw_yil": deger(cfg2["teknoloji"]["res"]["opex_sabit"]),
        "iz_egrisi": {n: iz_hizli(n) for n in range(0, int(deger(h.cfg["optimizasyon"]["turbin_azami"])) + 1)},
        "kaynak": "önceden hesaplanmış tablolar (data/atlas/v3_hizli_tablolar.csv)",
        "N_ref": N_ref,
    }
    return h2, bilgi


# ------------------------------------------------------------------------------------------------------------- tam analiz
def baglam_kur(h: Hazirlik):
    from src.yerlesim import analiz as Y

    cr = h.cfg["uretim"]["ruzgar"]
    kal = h.bilgi["kalibrasyon"]
    gref = kal.get("gwa_hiz") or kal.get("gwa_100m")
    if not gref:
        from src.saha import gwa_hizi

        gref = gwa_hizi(h.saha, h.cfg)["hiz"]
    return Y.hazirla(
        h.saha.enlem,
        h.saha.boylam,
        h.profil,
        deger(cr["turbin_modeli"]),
        deger(cr["gobek_yuksekligi"]),
        float(gref),
        h.saha.yerlesim_yaricap_km,
        h.cfg,
    )


def tam_once(h: Hazirlik, kv) -> dict:
    """MILP öncesi: iz verimi eğrisi, sığan en fazla türbin, tablo kullanılabilirliği/O&M ile yeni Hazırlık."""
    from src.yerlesim import analiz as Y

    t0 = time.perf_counter()
    bg = baglam_kur(h)
    tg = deger(h.cfg["optimizasyon"]["turbin_gucu"])
    n_azami = int(deger(h.cfg["optimizasyon"]["turbin_azami"]))
    n_sigan = Y.azami_turbin(bg, n_azami)
    eg = Y.iz_egrisi(bg, max(n_sigan, 1))
    N_ref = max(1, min(n_sigan, math.ceil(h.saha.baglanti_mw / tg)))
    dis = 0.0
    if len(bg.komsu) and n_sigan > 0:
        s = Y.coz(bg, N_ref, "acgozlu")
        dis = Y.degerlendir(bg, s.S)["ozet"]["dis_iz"]
    verim = [1.0] + [float(eg.loc[n, "verim"]) * (1 - dis) for n in range(1, n_sigan + 1)]
    b = bakim_hizli(N_ref, h.cfg)
    cfg2, A = bakim_uygula(h.cfg, kv, b["A"], b["om_usd_mw_yil"], b["A_yil_sd"], b["A_tekrar_sd"])
    _ata(cfg2, "optimizasyon.turbin_azami", n_sigan)
    hA = profil_degistir(h, h.profil["res_kf"].to_numpy() * A, cfg2)
    return {
        "baglam": bg,
        "egri": eg,
        "verim": verim,
        "n_sigan": n_sigan,
        "dis_iz_ref": dis,
        "hA": hA,
        "A_tablo": A,
        "sure_s": time.perf_counter() - t0,
    }


def tam_sonra(h: Hazirlik, kv, on: dict, N: int, fiyat_8760: np.ndarray, ilerleme=None) -> dict:
    """Seçilen N: yerleşim + PyWake + bakım DES → değerleme için yeni Hazırlık ve arayüz verileri."""
    from src.bakim.analiz import bakim_analizi
    from src.yerlesim import analiz as Y

    ilerleme = ilerleme or (lambda *_: None)
    bg = on["baglam"]
    sure = {}
    if N <= 0 or on["n_sigan"] <= 0:
        return {"h": on["hA"], "yerlesim": None, "bakim": None, "sure": sure}
    N_istenen = N
    N = min(N, on["n_sigan"])  # kullanıcı tasarımı alana sığmıyorsa: sığan sayı yerleştirilir (uyarıyla)
    t0 = time.perf_counter()
    ilerleme(0.2, "Türbin yerleşimi optimize ediliyor")
    yontem = kv.yerlesim_yontemi or bg.ayar["yontem"]
    r = Y.coz(bg, N, yontem, tohum=0)
    d = Y.degerlendir(bg, r.S)
    sure["yerlesim_s"] = time.perf_counter() - t0
    lam = Y.taban_kayip(h.cfg)
    res_cift = Y.profil_duzelt(h.profil["res_kf"].to_numpy(), d["saatlik_oran"], d["saatlik_kf_cift"], lam)
    t1 = time.perf_counter()
    bk = None
    cfgb, st = _bakim_cfg(h.cfg, kv)
    if kv.bakim_modeli == "yeni":
        ilerleme(0.25, "Bakım ve güvenilirlik simülasyonu")
        idx = h.profil.index
        yillar = sorted(set(idx.year))
        s = pd.Series(res_cift, index=idx)
        kf_y = np.vstack([_standart_yil(s.loc[str(y)]) for y in yillar])
        v_y = np.vstack([_standart_yil(h.profil.loc[str(y), "v_kalibre"]) for y in yillar])
        tur = d["turbinler"]
        pay = (tur["E_mwh"] / tur["E_mwh"].mean()).to_numpy()
        R = 10 if os.environ.get("MOTOR_KUCUK") == "1" else None  # yalnız testler
        bk = bakim_analizi(
            N, bg.turbin.P_mw, pay, kf_y, v_y, fiyat_8760, deger(cfgb["v3"]["bakim"]), int(deger(h.cfg["proje"]["omur"])), R=R
        )
        cfg2, A = bakim_uygula(h.cfg, kv, bk["A_enerji"], bk["om_usd_mw_yil"], bk["A_yil_sd"], bk["A_tekrar_sd"])
    else:
        cfg2, A = bakim_uygula(h.cfg, kv, 0, 0, 0, 0)
    sure["bakim_s"] = time.perf_counter() - t1
    h2 = profil_degistir(h, res_cift * A, cfg2)
    tur = d["turbinler"]
    yer = {
        **d["ozet"],
        "yontem": r.yontem,
        "yontem_kodu": yontem,
        "vekil_enerji_mwh": r.enerji,
        "optimizasyon_s": r.sure_s,
        "turbinler": tur[["enlem", "boylam", "gwa", "E_mwh", "ic_iz", "toplam_iz", "kf"]].round(5).to_dict(orient="records"),
        "komsu_turbinler": bg.komsu[["enlem", "boylam", "P_mw", "D_m"]].round(5).to_dict(orient="records") if len(bg.komsu) else [],
        "ruzgar_gulu": {"sektor": bg.gul.index.tolist(), "hiz": bg.gul.columns.tolist(), "frekans": bg.gul.round(3).to_numpy().tolist()},
        "iz_egrisi": on["egri"].round(5).to_dict(orient="records"),
        "dis_iz_ref": on["dis_iz_ref"],
        "n_sigan": on["n_sigan"],
        "aday_sayisi": len(bg.adaylar),
        "dislanan_aday": len(bg.dislanan),
        "yaricap_km": h.saha.yerlesim_yaricap_km,
        "turbin_D": bg.turbin.D,
        "taban_kayip": lam,
        "N_istenen": N_istenen,
        "alan_yetersiz": N_istenen > N,
    }
    if bk is not None:
        hist = bk["A_enerji_dagilim"]
        bk = {
            **{k: v for k, v in bk.items() if k != "A_enerji_dagilim"},
            "A_histogram": {"sayi": hist[0].tolist(), "kenar": hist[1].round(5).tolist()},
            "strateji": st,
        }
    return {"h": h2, "yerlesim": yer, "bakim": bk, "kullanilabilirlik": A, "sure": sure, "turbinler": tur}
