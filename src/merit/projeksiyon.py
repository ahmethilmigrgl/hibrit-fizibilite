"""
Merit order projeksiyonu 2026–2050: senaryo (talep, güneş, rüzgâr, nükleer, depolama, yakıt, karbon) → saatlik fiyat → yıllık
ortalama fiyat, güneş/rüzgâr yakalanma oranları, sıfır fiyatlı saatler, kesinti, emisyon.

Şekil yılları (2024, 2025): talep, rüzgâr ve güneş kapasite faktörü, akarsu/jeotermal/biyokütle profilleri bu yıllardan alınır
(iki "hava/talep" yılı; sonuçlar ortalaması). Talep 2025 düzeyine ölçeklenip yıllık büyür. Barajlı hidro bütçesi 2018–2025 ay
ortalaması (ortalama hidroloji). Termik kullanılabilir kapasite 2025 + senaryo değişimi. Gaz yakıt maliyeti 2025'in kalibre
edilmiş aylık profili × senaryo çarpanı (reel); kömür bandı 2025 seviyesi × çarpan; karbon her yakıtın emisyon yoğunluğuyla eklenir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ayarlar import config_oku, deger
from src.merit.model import Teta, depolama_gunluk, fiyat, gun_derinligi, su_doldur
from src.merit.veri import yakalanma


def ara_deger(yollar: dict, yil: int) -> float:
    """{yıl: değer} noktaları arasında doğrusal ara değerleme (uçlarda sabit)."""
    x = np.array(sorted(int(k) for k in yollar))
    y = np.array([float(yollar[k] if k in yollar else yollar[str(k)]) for k in x])
    return float(np.interp(yil, x, y))


def taban_hazirla(d: pd.DataFrame, G: pd.Series, C: pd.Series) -> dict:
    """Tarihsel veriden projeksiyon tabanı: şekil yılları, hidro bütçeleri, 2025 kapasiteleri ve yakıt seviyeleri."""
    m = deger(config_oku()["v4"]["merit"])
    son = int(d["yil"].max())
    D_son = d.loc[d["yil"] == son, "D"].sum()
    sekil = {}
    for y in m["sekil_yillari"]:
        x = d[d["yil"] == y]
        x = x.iloc[: (len(x) // 24) * 24]
        olcek = D_son / x["D"].sum()
        sekil[y] = {
            "zaman": x.index,
            "D": x["D"].to_numpy() * olcek,
            "cf_w": x["W"].to_numpy() / x["K_W"].to_numpy(),
            "cf_s": x["S"].to_numpy() / x["K_S"].to_numpy(),
            "R": x["R"].to_numpy(),
            "J": x["J"].to_numpy(),
            "Bk": x["Bk"].to_numpy(),
            "ay": x.index.tz_convert("Europe/Istanbul").month if x.index.tz is not None else x.index.month,
            "gun": x.index.tz_convert("Europe/Istanbul").date if x.index.tz is not None else x.index.date,
        }
    ay = d.index.tz_convert("Europe/Istanbul").month if d.index.tz is not None else d.index.month
    hidro = d.groupby([d["yil"], ay])["H"].mean().groupby(level=1).mean()  # ay başına ortalama MW (ortalama hidroloji)
    s25 = d[d["yil"] == son].iloc[0]
    g_son = G[[k for k in G.index if k.startswith(str(son))]]
    return {
        "sekil": sekil,
        "hidro_mw": hidro.to_dict(),
        "K": {"L": float(s25["K_L"]), "C": float(s25["K_C"]), "G": float(s25["K_G"]), "H": float(s25["K_H"])},
        "G_ay": {int(k[-2:]): float(v) for k, v in g_son.items()},
        "C": float(C.loc[son]),
        "son_yil": son,
    }


def yil_simule(taban: dict, sen: dict, yil: int, t: Teta, HR_min: float, cfg: dict) -> dict:
    m = deger(cfg["v4"]["merit"])
    K = taban["K"]
    dt = sen.get("termik_gw_degisim", {})
    dk = lambda a: ara_deger(dt[a], yil) if isinstance(dt.get(a), dict) else float(dt.get(a, 0.0))
    K_L, K_C, K_G = K["L"] + 1000 * dk("linyit"), K["C"] + 1000 * dk("ithal_komur"), K["G"] + 1000 * dk("gaz")
    g = (1 + sen["talep_buyume"]) ** (yil - taban["son_yil"])
    cap_s, cap_w = 1000 * ara_deger(sen["gunes_gw"], yil), 1000 * ara_deger(sen["ruzgar_gw"], yil)
    nuk = 1000 * ara_deger(sen["nukleer_gw"], yil) * 0.90
    P_st = 1000 * ara_deger(sen["depolama_gw"], yil)
    E_st = P_st * sen["depolama_saat"]
    gaz_c, kom_c, co2 = ara_deger(sen["gaz_usd_mwh_th"], yil), ara_deger(sen["komur_carpani"], yil), ara_deger(sen["karbon_usd_t"], yil)
    e = m["emisyon_t_mwh_e"]
    eG = m["emisyon_gaz_t_mwh_th"]
    tavan = max(m["tavan_usd_mwh"], 1.25 * (t.v + (max(taban["G_ay"].values()) * gaz_c + eG * co2) * HR_min * t.r))
    sonuc = []
    for _, s in taban["sekil"].items():
        D = s["D"] * g
        W, S = s["cf_w"] * cap_w, s["cf_s"] * cap_s
        N = D - W - S - s["R"] - s["J"] - s["Bk"] - nuk
        H = np.zeros_like(N)
        for a in range(1, 13):
            i = s["ay"] == a
            H[i] = su_doldur(N[i], taban["hidro_mw"][a] * i.sum(), m["hidro_asgari_oran"] * K["H"], K["H"])
        R0 = N - H
        Dd, Ss = depolama_gunluk(R0.reshape(-1, 24), P_st, E_st, m["depolama_verim"])
        RL = R0 - Dd.ravel() + Ss.ravel()
        Kt = K_L + K_C + K_G
        der = gun_derinligi(RL, np.full_like(RL, Kt), s["gun"])
        G = np.array([taban["G_ay"][int(a)] for a in s["ay"]]) * gaz_c
        p = fiyat(
            RL, K_L, K_C, K_G, taban["C"] * kom_c, G, t, HR_min, tavan, co2, e_L=e["linyit"], e_C=e["ithal_komur"], e_G=eG, derinlik=der
        )
        pos = np.clip(RL, 0, None)
        lig, kom = np.minimum(pos, K_L), np.clip(pos - K_L, 0, K_C)
        gaz = np.clip(pos - K_L - K_C, 0, None)
        hr_ort = HR_min * (1 + (t.r - 1) * 0.5)
        emis = (lig * e["linyit"] + kom * e["ithal_komur"] + gaz * eG * hr_ort).sum() / 1e6
        kesinti = np.clip(-RL, 0, None).sum()
        sonuc.append(
            {
                "ort_fiyat": float(p.mean()),
                "gunes_yakalanma": yakalanma(p, S),
                "ruzgar_yakalanma": yakalanma(p, W),
                "gunes_yakalanan": float((p * S).sum() / max(S.sum(), 1e-9)),
                "ruzgar_yakalanan": float((p * W).sum() / max(W.sum(), 1e-9)),
                "sifir_saat": float((p < 1).mean()),
                "kesinti_twh": float(kesinti / 1e6),
                "yenilenebilir_pay": float(np.clip(W + S + s["R"] + s["J"] + s["Bk"] + H - np.clip(-RL, 0, None), 0, None).sum() / D.sum()),
                "talep_twh": float(D.sum() / 1e6),
                "emisyon_mt": float(emis),
                "gaz_pay": float(gaz.sum() / D.sum()),
                "tavan": float(tavan),
                "_p": p,
            }
        )
    ort = {k: float(np.mean([x[k] for x in sonuc])) for k in sonuc[0] if not k.startswith("_")}
    ort["yil"] = yil
    ort["_saatlik"] = [x["_p"] for x in sonuc]
    return ort


def senaryo_calistir(taban: dict, ad: str, t: Teta, HR_min: float, y1: int = 2026, y2: int = 2050) -> pd.DataFrame:
    cfg = config_oku()
    sen = deger(cfg["v4"]["merit"])["senaryolar"][ad]
    sat = []
    for y in range(y1, y2 + 1):
        r = yil_simule(taban, sen, y, t, HR_min, cfg)
        r.pop("_saatlik")
        sat.append(r)
    return pd.DataFrame(sat).set_index("yil")


def motor_parametreleri(df: pd.DataFrame, cfg: dict) -> dict:
    """
    Senaryo → v2 motorunun fiyat varsayımları (KullaniciVarsayimlari(fiyat_kaynagi="merit:<ad>")):
      seviye: proje ömrü boyunca (2028–2057; 2050 sonrası 2050 değeri) WACC ile seviyelendirilmiş baz yük fiyatı
      kanibalizasyon: motorun "taban yılına kadar doğrusal iniş, sonra sabit" güneş yakalanma yolunun merit order yoluna en iyi uyan
                      (iskonto ağırlıklı en küçük kareler, ızgara araması) taban oranı ve taban yılı
    """
    bas = deger(cfg["proje"]["baslangic_yili"])
    N = deger(cfg["proje"]["omur"])
    r = deger(cfg["finans"]["wacc_reel"])
    yil = np.arange(bas, bas + N)
    son = int(df.index.max())
    f = np.array([df["ort_fiyat"].loc[min(y, son)] for y in yil])
    h = np.array([df["gunes_yakalanma"].loc[min(y, son)] for y in yil])
    w = (1 + r) ** -(np.arange(N) + 1)
    seviye = float((f * w).sum() / w.sum())
    oran0 = float(df["gunes_yakalanma"].loc[min(2026, son)])
    en, en_hata = (0.6, 2033), np.inf
    for ty in range(2027, bas + N):
        for tb in np.arange(0.15, oran0 + 1e-9, 0.01):
            yol = np.clip(oran0 + (tb - oran0) * (yil - 2026) / (ty - 2026), min(tb, oran0), oran0)
            e = float((w * (yol - h) ** 2).sum())
            if e < en_hata:
                en, en_hata = (float(tb), int(ty)), e
    return {
        "seviye": seviye,
        "kanibalizasyon_taban_oran": round(en[0], 3),
        "kanibalizasyon_taban_yili": en[1],
        "gunes_yakalanma_2026": oran0,
        "uyum_rmse": float(np.sqrt(en_hata / w.sum())),
    }
