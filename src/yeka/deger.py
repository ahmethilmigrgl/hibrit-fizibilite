"""
YEKA yarışma projesinin (lot) değerlemesi: katkı payı sıfırken NPV dağılımı → MW başına başabaş katkı payı (€/MW).

Temsilî nokta: lotun ilindeki rüzgârlı ön tarama hücrelerinin (RES KF ≥ il 75. yüzdeliği) medyan KF'sine en yakın hücre (yarışma
alanı koordinatları yayımlanmıyor). Temsilî 100 MW RES, v2 motoru (toplu kayıp; v3 yerleşimi kapalı — tüm lotlar aynı yöntemle).
Bağlantı: TEİAŞ görüşü varsa TM + fider + hat (config v3.baglanti birim maliyetleri), yoksa en yakın uygun trafo.

Gelir: sözleşme yılından 72 ay sonra 20 yıl alım fiyatı (nominal, para biriminde sabit → reel USD'ye kur ve o para biriminin
enflasyonuyla), öncesi ve sonrası tüccar. Sözleşmeli yıllarda sistem kesintisi YEKDEM tazminiyle (v2 kuralı).

Katkı payı K (€/MW) sözleşmede peşin ödenir ve A yılda itfa edilir:
    NPV(K) = NPV(0) − K · MW · kur · f,   f = 1 − τ · Σ_{k=1..A} (1/A)(1 + r)^−k
    başabaş K* = NPV(0) / (MW · kur · f)     (senaryo başına → dağılım)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
from functools import lru_cache

import numpy as np
import pandas as pd

from src import veri_katmani
from src.ayarlar import KOK, config_oku, deger
from src.motor import mc as MC
from src.motor import tablolar
from src.motor.ortak import hazirla, ortam
from src.motor.varsayimlar import KullaniciVarsayimlari
from src.risk.tasarim import Tasarim

ONBELLEK = KOK / "data" / "onbellek" / "yeka"


def yarismalar() -> pd.DataFrame:
    return pd.DataFrame(deger(config_oku()["v4"]["yeka"])["yarismalar"]).set_index("kod")


@lru_cache(maxsize=32)
def temsili_nokta(il: str) -> dict:
    d = pd.read_parquet(veri_katmani.yol("atlas/on_tarama.parquet"))
    d = d[(d["il"] == il) & (~d["ada"].fillna(False).astype(bool)) & d["res_kf"].notna()]
    if d.empty:
        raise ValueError(f"Ön taramada il yok: {il}")
    ust = d[d["res_kf"] >= d["res_kf"].quantile(0.75)]
    hedef = float(ust["res_kf"].median())
    r = ust.iloc[int(np.argmin((ust["res_kf"] - hedef).abs().to_numpy()))]
    return {
        "enlem": float(r["enlem"]),
        "boylam": float(r["boylam"]),
        "ilce": r["ilce"],
        "on_tarama_kf": float(r["res_kf"]),
        "hucre": len(ust),
    }


def baglanti_usd_mw(lot: pd.Series, enlem: float, boylam: float, cfg: dict) -> tuple[float, str]:
    b = deger(cfg["v3"]["baglanti"])
    if pd.notna(lot.get("hat_km")):
        k = "400" if float(lot["kv"]) >= 300 else "154"
        top = b["trafo_merkezi_usd"][k] + b["fider_usd"][k] + float(lot["hat_km"]) * b["hat_usd_km"][k]
        return top / float(lot["mw"]), "teias_gorusu"
    from src.cbs.baglanti import maliyet

    return float(maliyet(enlem, boylam, float(lot["mw"]), cfg)["usd_mw"]), "en_yakin_trafo"


def katki_carpani(cfg: dict) -> float:
    """f: peşin ödenen 1 birim katkı payının vergi kalkanı sonrası bugünkü değer maliyeti."""
    y = deger(cfg["v4"]["yeka"])
    A = int(y["katki_amortisman_yil"])
    tau, r = deger(cfg["finans"]["kurumlar_vergisi"]), deger(cfg["finans"]["wacc_reel"])
    return 1.0 - tau * sum((1 / A) * (1 + r) ** -k for k in range(1, A + 1))


def lot_degerle(
    kod: str,
    onbellek_kullan: bool = True,
    n: int | None = None,
    tohum: int = 42,
    ekstra: dict | None = None,
    fiyat_sent: float | None = None,
) -> dict:
    """ekstra: ek config anahtar yolları (ör. {"teknoloji.res.capex": ...}: piyasanın ima ettiği varsayımları bulmak için).
    fiyat_sent: alım fiyatı (verilmezse lotun gerçekleşen fiyatı, yoksa taban) — fiyat aşamasının eğimi için."""
    cfg0 = config_oku()
    y = deger(cfg0["v4"]["yeka"])
    lot = yarismalar().loc[kod]
    anahtar = hashlib.sha1(
        json.dumps(
            [
                kod,
                lot.to_dict(),
                y,
                n,
                tohum,
                ekstra or {},
                fiyat_sent,
                deger(cfg0["v2"]["motor"])["veri_surumu"],
                os.environ.get("MOTOR_KUCUK"),
            ],
            default=str,
        ).encode()
    ).hexdigest()[:16]
    yol = ONBELLEK / f"{anahtar}.pkl"
    if onbellek_kullan and yol.exists():
        return pickle.loads(yol.read_bytes())
    nk = temsili_nokta(lot["il"])
    usd_mw, bag_kaynak = baglanti_usd_mw(lot, nk["enlem"], nk["boylam"], cfg0)
    MW = float(y["temsili_mw"])
    z = y["zaman"]
    kv = KullaniciVarsayimlari(
        baglanti_mw=MW,
        sabit_tasarim={"res_mw": MW, "ges_mw": 0.0, "bess_mw": 0.0, "bess_mwh": 0.0},
        yerlesim_bakim=False,
        altyapi_maliyetleri=False,
        sfk_katilimi=False,
        finansman=False,
        gelir_yapilari=("tuccar",),
        ekstra={"teknoloji.sebeke.capex": usd_mw, "proje.baslangic_yili": int(z["cod_yili"]), **(ekstra or {})},
    )
    h = hazirla({"ad": kod, "enlem": nk["enlem"], "boylam": nk["boylam"]}, kv)
    o = ortam(h)
    t = Tasarim(kod, MW, 0.0, 0.0, 0.0, sebeke_mw=MW, yan_hizmet=False, dengesizlik_azaltim=True, yekg=True)
    sigma = MC.res_sigma(h.guven)
    tb = tablolar.tablo(o, t, "kucuk" if os.environ.get("MOTOR_KUCUK") == "1" else "hafif", sigma=sigma or 0.06)
    N = o.v.omur
    yil = np.arange(o.yillar[0], o.yillar[0] + N + MC.KMAX)
    bas = int(z["sozlesme_yili"]) + math.ceil(y["mekanizma"]["serbest_donem_ay"] / 12) + 1
    phi = ((yil >= bas) & (yil < bas + y["mekanizma"]["alim_suresi_yil"])).astype(float)
    eur = lot["para"] == "EUR"
    yh = deger(h.cfg["v4"]["yeka"])  # ekstra ile değişmiş olabilir (ör. endeksli alım fiyatı: eur_enflasyonu = 0)
    pi = yh["eur_enflasyonu"] if eur else deger(h.cfg["finans"]["abd_enflasyonu"])
    if fiyat_sent is None:
        fiyat_sent = float(lot["fiyat_sent"]) if pd.notna(lot.get("fiyat_sent")) else y["mekanizma"]["taban_sent"]
    fiyat = fiyat_sent * 10 * (y["kur"]["eurusd"] if eur else 1.0) / (1 + pi) ** (yil - 2026)
    nn = n or (500 if os.environ.get("MOTOR_KUCUK") == "1" else 2 * int(deger(h.cfg["v2"]["motor"])["mc_baslangic"]))
    cod = np.full(nn, float(MC.COD_ORIJIN_AY))
    r = MC.mc_calistir(o, t, tb, None, ["tuccar", "sozlesme"], cod, nn, tohum, sigma, False, sozlesme={"phi": phi, "fiyat": fiyat})
    f = katki_carpani(h.cfg)
    kur = y["kur"]["eurusd"]
    bb = r["npv"]["sozlesme"] * 1e6 / (MW * kur * f)  # €/MW, senaryo başına başabaş katkı payı
    sonuc = {
        "kod": kod,
        "il": lot["il"],
        "mw": float(lot["mw"]),
        "nokta": nk,
        "res_kf": float(h.profil["res_kf"].mean()),
        "guven": h.guven["seviye"],
        "baglanti_usd_mw": usd_mw,
        "baglanti_kaynak": bag_kaynak,
        "sozlesme_yillari": [int(bas), int(bas + y["mekanizma"]["alim_suresi_yil"] - 1)],
        "fiyat_sent": float(fiyat_sent),
        "fiyat_reel_ilk": float(fiyat[phi > 0][0]),
        "f": f,
        "e_npv_musd_100mw": float(r["npv"]["sozlesme"].mean()),
        "e_npv_tuccar_musd_100mw": float(r["npv"]["tuccar"].mean()),
        "basabas_eur_mw": {
            "ortalama": float(bb.mean()),
            "p10": float(np.percentile(bb, 10)),
            "p50": float(np.percentile(bb, 50)),
            "p90": float(np.percentile(bb, 90)),
            "sd": float(bb.std(ddof=1)),
        },
        "ornek": bb.astype(np.float32),
    }
    ONBELLEK.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(pickle.dumps(sonuc))
    return sonuc
