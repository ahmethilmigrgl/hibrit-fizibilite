"""
Mevcut RES'e GES ve/veya bütünleşik batarya ekleme analizi (v4 Faz I).

Soru: bağlantı kapasitesi (MWe) zaten var ve rüzgâr çoğu saat onu doldurmuyor. Aynı bağlantıya yardımcı kaynak olarak ne kadar
GES ve batarya eklemeli?

Akış
    1. Profil: santralin kendi ay × saat kalibrasyon matrisi ve türbin vekiliyle ERA5 2014–2023 (atlas; gözlenen KF'yi verir).
       İsteğe bağlı kullanıcı üretim CSV'si: profilin ay × saat ortalaması kullanıcının ölçülen ay × saat ortalamasına ölçeklenir
       (hava yılları ve GES ile eşzamanlılık korunur).
    2. Artımsal ekonomi: mevcut RES'in maliyetleri (CAPEX, O&M, arazi, söküm, şebeke, TEİAŞ kapasite bedeli) sıfırlanır; iki
       durumda da ortaktır. İnşaat 1 yıl, ilk işletme yılı 2027 (config v4.ekleme).
    3. Kapasite MILP'i: santral tek "türbin" (turbin_gucu = kurulu güç, N = 1 sabit); GES ve batarya serbest; bağlantı = MWe.
       MILP toplam değeri büyütür; RES sabit olduğundan bu artımsal değeri büyütmekle aynıdır.
    4. Monte Carlo, ortak rastgele sayılarla: aynı senaryolar (fiyat, hava yılı, SFK, kesinti, ...) hem "RES + ekleme" hem
       "yalnız RES" için değerlenir; artımsal NPV_i = NPV_i(RES + ekleme) − NPV_i(yalnız RES). Fark senaryolar arasında çok daha
       az dalgalandığından standart hata bağımsız örneklemeye göre küçülür (varyans azaltma).
    5. Gelir yapıları: tüccar, PPA ve santral eski YEKDEM'deyse kalan YEKDEM yılları (yıllık opsiyon; yardımcı kaynak ve
       depolanıp verilen santral enerjisi aynı fiyattan).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import time
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku, deger
from src.ekleme.santraller import bul
from src.finans.fiyat_senaryosu import fiyat_senaryosu_uret
from src.finans.model import proje_degerle
from src.motor import mc as MC
from src.motor import tablolar
from src.motor.ortak import hazirla, milp_temsili_gun, ortam, profil_degistir, sfk_milp_carpani
from src.motor.varsayimlar import KullaniciVarsayimlari, MotorHatasi
from src.risk.degerleme import nakit_akislari
from src.risk.tasarim import Tasarim

ONBELLEK = KOK / "data" / "onbellek" / "ekleme"
YAPI_AD = {
    "tuccar": ("Tüccar", "Merchant"),
    "yekdem_opsiyon": ("Kalan eski YEKDEM + tüccar", "Remaining legacy YEKDEM + merchant"),
    "ppa": ("PPA (%70, 12 yıl)", "PPA (70%, 12 yr)"),
}


@dataclass
class EklemeVarsayimlari:
    kod: str
    baglanti_mw: float | None = None  # MWe; None → kurulu güç
    azami_ges_mw: float | None = None  # None → ges_ust_carpani × MWe
    yekdem_bitis_yili: int | None = None  # santralin eski YEKDEM hakkının son yılı (None/geçmiş → yok)
    yekdem_fiyat_usd_mwh: float | None = None  # None → config eski_yekdem_usd_mwh (nominal)
    fiyat_senaryosu: str = "baz"
    sfk_katilimi: bool = True
    gelir_yapilari: tuple[str, ...] = ("tuccar", "yekdem_opsiyon", "ppa")
    sabit_ekleme: dict | None = None  # {"ges_mw", "bess_mw", "bess_mwh"} → MILP yerine
    capex_carpani_ges: float = 1.0
    capex_carpani_bess: float = 1.0
    uretim_csv: pd.Series | None = field(default=None, repr=False)  # saatlik MW (UTC indeksli) → ay × saat ölçekleme

    def anahtar(self) -> str:
        d = asdict(self)
        d["uretim_csv"] = None if self.uretim_csv is None else hashlib.sha1(pd.util.hash_pandas_object(self.uretim_csv).values).hexdigest()
        d["gelir_yapilari"] = list(self.gelir_yapilari)
        d["veri"] = deger(config_oku()["v2"]["motor"])["veri_surumu"] + ("-kucuk" if os.environ.get("MOTOR_KUCUK") == "1" else "")
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


def artimsal_cfg(ek: dict) -> dict:
    """Mevcut RES'in ortak maliyetlerini sıfırlayan config anahtar yolları (KullaniciVarsayimlari.ekstra)."""
    c = config_oku()
    sokum = dict(deger(c["finans"]["sokum_net"]))
    sokum["res"] = 0.0
    return {
        "teknoloji.res.capex": 0.0,
        "teknoloji.res.opex_sabit": 0.0,
        "teknoloji.res.arazi": 0.0,
        "teknoloji.sebeke.capex": 0.0,
        "teknoloji.sebeke.teias_kapasite_bedeli": 0.0,
        "finans.sokum_net": sokum,
        "proje.insaat_suresi": ek["insaat_suresi"],
        "proje.capex_takvimi": [1.0 / ek["insaat_suresi"]] * ek["insaat_suresi"],
        "proje.baslangic_yili": ek["baslangic_yili"],
    }


def csv_olcekle(res_kf: pd.Series, uretim_mw: pd.Series, kurulu_mw: float) -> tuple[np.ndarray, dict]:
    """
    Kullanıcının saatlik üretimi (MW, UTC) ile model profilinin ay × TSİ saati oranı; model profili bu oranla ölçeklenir
    (hava yılları ve GES ile eşzamanlılık korunur). Döndürür: yeni saatlik KF ve özet.

    Ölçüm–korelasyon–tahmin (MCP) mantığı: ölçüm model dönemiyle (2014–2023) en az 300 gün örtüşüyorsa oran AYNI SAATLER
    üzerinden hesaplanır (ölçüm/model, aynı hava) → ölçüm yıllarının rüzgârlı ya da sakin olması santral farkı sanılmaz; uzun
    dönem düzeltmesi kendiliğinden yapılır. Örtüşme yoksa ölçümün ay × saat ortalaması modelin 10 yıllık ortalamasıyla
    karşılaştırılır (uzun dönem düzeltmesi yok; kısa ölçümde ±yıllar arası değişkenlik kadar sapma kalır).
    """
    u = (uretim_mw.clip(lower=0) / kurulu_mw).dropna()
    u = u[~u.index.duplicated()]
    if len(u) < 24 * 300:
        raise MotorHatasi(
            "csv", "Üretim verisi en az ~1 yıl (300 gün) saatlik olmalı.", "Production data must cover at least ~1 year (300 days) hourly."
        )
    tsi = lambda ix: (ix.hour + 3) % 24
    ortak = u.index.intersection(res_kf.index)
    mcp = len(ortak) >= 24 * 300
    if mcp:
        uo, mo = u.loc[ortak], res_kf.loc[ortak]
        mu = uo.groupby([ortak.month, tsi(ortak)]).mean()
        mm_ = mo.groupby([ortak.month, tsi(ortak)]).mean()
    else:
        mu = u.groupby([u.index.month, tsi(u.index)]).mean()
        mm_ = res_kf.groupby([res_kf.index.month, tsi(res_kf.index)]).mean().reindex(mu.index)
    oran = (mu / mm_.reindex(mu.index)).replace([np.inf, -np.inf], np.nan).dropna().clip(0.3, 3.0)
    mm = res_kf.groupby([res_kf.index.month, tsi(res_kf.index)]).mean()
    tam = pd.Series(float(oran.mean()), index=mm.index)  # eksik hücreler (kısa veri): kapsanan hücrelerin ortalama oranı
    tam.loc[oran.index] = oran.values
    carpan = tam.reindex(list(zip(res_kf.index.month, tsi(res_kf.index), strict=True))).to_numpy()
    yeni = np.clip(res_kf.to_numpy() * carpan, 0, 1)
    return yeni, {
        "kullanici_kf": float(u.mean()),
        "model_kf": float(res_kf.mean()),
        "olcekli_kf": float(yeni.mean()),
        "hucre": int(len(oran)),
        "mcp": bool(mcp),
        "ortak_saat": int(len(ortak)),
    }


def _kucuk() -> bool:
    return os.environ.get("MOTOR_KUCUK") == "1"


def ekleme_analizi(ev: EklemeVarsayimlari, ilerleme=None, onbellek_kullan: bool = True) -> dict:
    ilerleme = ilerleme or (lambda *_: None)
    anahtar = ev.anahtar()
    yol = ONBELLEK / f"{anahtar}.pkl"
    if onbellek_kullan and yol.exists():
        ilerleme(1.0, "Önbellekten")
        return pickle.loads(yol.read_bytes())
    t0 = time.perf_counter()
    cfg0 = config_oku()
    ek = deger(cfg0["v4"]["ekleme"])
    s = bul(ev.kod)
    C = float(s["kurulu_mw"])
    mwe = float(ev.baglanti_mw or C)
    if not 5.0 <= mwe <= 300.0:
        raise MotorHatasi("baglanti", "Bağlantı gücü 5–300 MW arasında olmalı.", "Grid connection must be 5–300 MW.")
    ges_ust = float(ev.azami_ges_mw if ev.azami_ges_mw is not None else ek["ges_ust_carpani"] * mwe)
    ekstra = artimsal_cfg(ek)
    kv = KullaniciVarsayimlari(
        baglanti_mw=mwe, azami_res_mw=C, azami_ges_mw=ges_ust, turbin_yerlesimi=False, fiyat_senaryosu=ev.fiyat_senaryosu,
        capex_carpani_ges=ev.capex_carpani_ges, capex_carpani_bess=ev.capex_carpani_bess, sfk_katilimi=ev.sfk_katilimi,
        kalibrasyon=f"santral:{int(s['epias_id'])}", turbin=str(s["turbin"]), gobek=float(s["gobek"]), yerlesim_bakim=False,
        finansman=False, ekstra=ekstra,
    )  # fmt: skip
    ilerleme(0.05, "Santral profili (kendi kalibrasyonu)")
    h = hazirla({"ad": ev.kod, "enlem": float(s["enlem"]), "boylam": float(s["boylam"])}, kv, ilerleme)
    csv_bilgi = None
    if ev.uretim_csv is not None:
        yeni, csv_bilgi = csv_olcekle(h.profil["res_kf"], ev.uretim_csv, C)
        h = profil_degistir(h, yeni)
    # Kalan eski YEKDEM: yıllık opsiyon makinesi (src/risk/monte_carlo.yekdem_katilim) sabit nominal fiyatla
    bas = int(ek["baslangic_yili"])
    k_yek = max(0, int(ev.yekdem_bitis_yili) - bas + 1) if ev.yekdem_bitis_yili else 0
    yapilar = [y for y in ev.gelir_yapilari if y != "yekdem_opsiyon" or k_yek > 0]
    if "yekdem_opsiyon" in yapilar and "tuccar" not in yapilar:
        yapilar = ["tuccar", *yapilar]
    if k_yek > 0:
        f_sent = float(ev.yekdem_fiyat_usd_mwh or ek["eski_yekdem_usd_mwh"]) / 10
        yk = dict(deger(h.cfg["yekdem"]))
        yk.update({"taban_usd_sent": f_sent - 1e-3, "tepe_usd_sent": f_sent, "tavan_usd_sent": f_sent + 1e-3, "sure_yil": min(k_yek, 10)})
        h.cfg["yekdem"] = {**h.cfg["yekdem"], "value": yk}
    o = ortam(h)
    o.opt["turbin_gucu"], o.opt["turbin_azami"] = C, 1
    o.opt["ges_azami_mw"] = ges_ust
    f = fiyat_senaryosu_uret(h.cfg, h.u, ev.fiyat_senaryosu, "devam")
    ilerleme(0.15, "Ekleme boyutlandırma (MILP)")
    t1_ = time.perf_counter()
    if ev.sabit_ekleme:
        d = {k: float(ev.sabit_ekleme.get(k, 0.0)) for k in ("ges_mw", "bess_mw", "bess_mwh")}
        milp = None
    else:
        kal = {"dz", "yekg"} | ({"yh"} if ev.sfk_katilimi else set())
        o.opt["mip_bosluk"] = 0.005
        K = 24 if _kucuk() else milp_temsili_gun(h.cfg)
        milp = o.milp(kal, ev.fiyat_senaryosu, K=K, zaman=240, yh_carpan=sfk_milp_carpani(o), sabit={"N": 1})
        d = {"ges_mw": round(milp["GES [MWac]"], 1), "bess_mw": round(milp["BESS [MW]"], 1), "bess_mwh": round(milp["BESS [MWh]"], 1)}
    sure_milp = time.perf_counter() - t1_
    asgari_sfk = deger(h.cfg["gelir_yigini"]["yan_hizmet"]["asgari_guc"])
    yh = ev.sfk_katilimi and d["bess_mw"] >= asgari_sfk - 1e-6
    t1 = Tasarim(
        "RES + ekleme", C, d["ges_mw"], d["bess_mw"], d["bess_mwh"], sebeke_mw=mwe, yan_hizmet=yh, dengesizlik_azaltim=True, yekg=True
    )
    t0_ = Tasarim("Yalnız RES", C, 0.0, 0.0, 0.0, sebeke_mw=mwe, yan_hizmet=False, dengesizlik_azaltim=True, yekg=True)
    ilerleme(0.3, "İşletme tabloları")
    sigma = MC.res_sigma(h.guven)
    seviye = "kucuk" if _kucuk() else "hafif"
    tb = {}
    for ad, t in (("ek", t1), ("res", t0_)):
        tb[ad] = (
            tablolar.tablo(o, t, seviye, sigma=sigma or 0.06),
            tablolar.tablo(o, t, seviye, yekdem=True, sigma=sigma or 0.06) if "yekdem_opsiyon" in yapilar else None,
        )
    ilerleme(0.7, "Monte Carlo (ortak rastgele sayılar)")
    mot = deger(h.cfg["v2"]["motor"])
    n = 500 if _kucuk() else int(mot["mc_baslangic"]) * 2
    cod = np.full(n, float(MC.COD_ORIJIN_AY))  # gecikme yok: ekleme mevcut sahada, inşaat 1 yıl
    r1 = MC.mc_calistir(o, t1, *tb["ek"], yapilar, cod, n, 42, sigma, ev.sfk_katilimi)
    r0 = MC.mc_calistir(o, t0_, *tb["res"], yapilar, cod, n, 42, sigma, ev.sfk_katilimi)
    metr, hist = {}, {}
    for y in yapilar:
        x = r1["npv"][y] - r0["npv"][y]
        m = MC.metrik(x)
        bag = np.sqrt((r1["npv"][y].var(ddof=1) + r0["npv"][y].var(ddof=1)) / n)  # bağımsız örneklemede standart hata
        m["se_bagimsiz"] = float(bag)
        m["varyans_azaltma"] = float(1 - (m["se"] / bag) ** 2) if bag > 0 else None
        m["capex_musd"] = float(r1["ek"][y]["capex_musd"])
        metr[y] = m
        sayi, kenar = np.histogram(x, bins=40)
        hist[y] = {"sayi": sayi.tolist(), "kenar": kenar.round(3).tolist()}
    en_iyi = max(metr, key=lambda y: metr[y]["e_npv"])
    # Deterministik işletme özeti (beklenen fiyat, hava yılları ortalaması)
    L = float(f.seviye)
    det = {}
    for ad, t, tbl in (("res", t0_, tb["res"][0]), ("ek", t1, tb["ek"][0])):
        r = nakit_akislari(t, tbl, o.c, o.beklenen_girdi(L))
        sat = float(r["satilan"][0, 0])
        uret = float(r["uretilebilir"][0, 0])
        det[ad] = {
            "satilan_mwh": sat,
            "kesinti_orani": float(r["kesilen"][0, 0] / max(uret, 1e-9)),
            "baglanti_kullanim": sat / (mwe * 8760),
            "npv_musd": float(r["npv"][0] / 1e6),
        }
    ilerleme(0.9, "GES boyutu eğrisi")
    egri = ges_egrisi(h, f, C, mwe, ges_ust, int(ek["egri_noktasi"]))
    df = h.profil
    tsi = (df.index.hour + 3) % 24
    gun = df.groupby(tsi)[["res_kf", "ges_kf"]].mean()
    sonuc = {
        "santral": {
            "kod": ev.kod,
            "il": s["il"],
            "kurulu_mw": C,
            "baglanti_mw": mwe,
            "turbin": s["turbin"],
            "gobek": float(s["gobek"]),
            "gozlenen_kf": float(s["gozlenen_kf"]),
            "model_kf": float(df["res_kf"].mean()),
            "ges_kf": float(df["ges_kf"].mean()),
            "saatlik_korelasyon": float(df["res_kf"].corr(df["ges_kf"])),
            "csv": csv_bilgi,
        },
        "varsayimlar": {**{k: v for k, v in asdict(ev).items() if k != "uretim_csv"}, "ges_ust_mw": ges_ust, "yekdem_yil": k_yek},
        "tasarim": d,
        "milp": {k: milp[k] for k in ("GES [MWac]", "BESS [MW]", "BESS [MWh]", "NPV tahmini [M USD]", "Kesinti [%]") if milp and k in milp},
        "yan_hizmet": yh,
        "metrik": metr,
        "en_iyi_yapi": en_iyi,
        "histogram": hist,
        "isletme": det,
        "ges_egrisi": egri,
        "ges_capex_usd_mw": float(h.v.capex_ges),
        "gunici": {"saat": gun.index.tolist(), "res": gun["res_kf"].round(4).tolist(), "ges": gun["ges_kf"].round(4).tolist()},
        "sure_s": {"milp": sure_milp, "toplam": time.perf_counter() - t0},
    }
    sonuc["nedenler"] = nedenler(sonuc)
    if onbellek_kullan:
        ONBELLEK.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(pickle.dumps(copy.deepcopy(sonuc)))
    ilerleme(1.0, "Tamamlandı")
    return sonuc


def ges_egrisi(h, f, C: float, mwe: float, ges_ust: float, n: int) -> list[dict]:
    """
    Bataryasız GES boyutu → artımsal NPV, kesinti ve başabaş GES CAPEX'i (kapalı form proje_degerle; artımsal maliyetlerle).
    Artımsal NPV GES CAPEX'inde doğrusaldır (amortisman vergi kalkanı dahil): NPV(c) = a − b·c. a: c = 0'daki artımsal NPV,
    b: iki noktadan eğim → başabaş c* = a / b (USD/MWac). Bu, "GES eklemesi hangi kurulum maliyetinde kâra geçer?" sorusudur.
    """
    from dataclasses import replace

    v0 = replace(h.v, capex_ges=0.0)
    taban = proje_degerle({"res_mw": C, "ges_mw": 0.0, "sebeke_mw": mwe}, h.v, f, h.u).npv
    taban0 = proje_degerle({"res_mw": C, "ges_mw": 0.0, "sebeke_mw": mwe}, v0, f, h.u).npv
    egri = []
    for g in np.linspace(0, ges_ust, n):
        k = {"res_mw": C, "ges_mw": float(g), "sebeke_mw": mwe}
        sg = proje_degerle(k, h.v, f, h.u)
        a = proje_degerle(k, v0, f, h.u).npv - taban0
        b = (a - (sg.npv - taban)) / h.v.capex_ges if g > 0 else 0.0
        egri.append(
            {
                "ges_mw": float(g),
                "artimsal_npv": (sg.npv - taban) / 1e6,
                "kesinti_%": float(sg.ozet["Kesinti oranı [%]"]),
                "lcoe_ges": sg.lcoe.get("ges"),
                "basabas_capex": float(a / b) if b > 0 else None,
            }
        )
    return egri


def nedenler(s: dict) -> list[dict]:
    """Kural tabanlı iki dilli açıklamalar."""
    d, sa, m, i = s["tasarim"], s["santral"], s["metrik"][s["en_iyi_yapi"]], s["isletme"]
    y = YAPI_AD[s["en_iyi_yapi"]]
    n = [
        {
            "tr": f"Bağlantı bugün %{100 * i['res']['baglanti_kullanim']:.0f} dolu (RES KF %{100 * sa['model_kf']:.0f}); ekleme sonrası "
            f"%{100 * i['ek']['baglanti_kullanim']:.0f}. Kesinti (bağlantı sınırı + fiyatın TEİAŞ enerji bedelinin altında olduğu saatler) "
            f"%{100 * i['res']['kesinti_orani']:.1f} → %{100 * i['ek']['kesinti_orani']:.1f}.",
            "en": f"The connection is {100 * i['res']['baglanti_kullanim']:.0f}% used today (wind CF {100 * sa['model_kf']:.0f}%); after the addition "
            f"{100 * i['ek']['baglanti_kullanim']:.0f}%. Curtailment (connection limit + hours priced below the TSO energy fee) "
            f"{100 * i['res']['kesinti_orani']:.1f}% → {100 * i['ek']['kesinti_orani']:.1f}%.",
        },
        {
            "tr": f"Önerilen ekleme: GES {d['ges_mw']:.0f} MWm, batarya {d['bess_mw']:.0f} MW / {d['bess_mwh']:.0f} MWh. En iyi gelir yapısı: {y[0]} — "
            f"artımsal E[NPV] {m['e_npv']:+.1f} M$ (±{m['se']:.2f}), P(>0) %{100 * m['p_pozitif']:.0f}, CVaR %5 {m['cvar5']:+.1f} M$.",
            "en": f"Recommended addition: solar {d['ges_mw']:.0f} MWp-ac, battery {d['bess_mw']:.0f} MW / {d['bess_mwh']:.0f} MWh. Best revenue structure: {y[1]} — "
            f"incremental E[NPV] {m['e_npv']:+.1f} M$ (±{m['se']:.2f}), P(>0) {100 * m['p_pozitif']:.0f}%, CVaR 5% {m['cvar5']:+.1f} M$.",
        },
        {
            "tr": f"RES ile GES saatlik korelasyonu {sa['saatlik_korelasyon']:+.2f}: düşük ya da negatif korelasyon, GES'in bağlantının boş saatlerini "
            "doldurması demektir; ekleme ne kadar büyürse iki kaynak aynı saatlerde bağlantıyı aşar ve kesinti artar.",
            "en": f"Hourly wind–solar correlation {sa['saatlik_korelasyon']:+.2f}: low or negative correlation means solar fills the connection's idle hours; "
            "the larger the addition, the more often both exceed the connection together and curtailment rises.",
        },
    ]
    e = [x for x in s["ges_egrisi"] if x["basabas_capex"]]
    if e:
        ilk, son = e[0], e[-1]
        n.append(
            {
                "tr": f"GES başabaş kurulum maliyeti: ilk {ilk['ges_mw']:.0f} MW için {ilk['basabas_capex'] / 1e3:.0f} bin $/MWac, {son['ges_mw']:.0f} MW için "
                f"{son['basabas_capex'] / 1e3:.0f} bin $/MWac (varsayım {s['ges_capex_usd_mw'] / 1e3:.0f}). Büyüdükçe düşer: kesinti ve güneş kanibalizasyonu.",
                "en": f"Solar break-even capex: {ilk['basabas_capex'] / 1e3:.0f} k$/MWac for the first {ilk['ges_mw']:.0f} MW, {son['basabas_capex'] / 1e3:.0f} k$/MWac "
                f"for {son['ges_mw']:.0f} MW (assumed {s['ges_capex_usd_mw'] / 1e3:.0f}). It falls with size: curtailment and solar cannibalisation.",
            }
        )
    if m.get("varyans_azaltma") is not None:
        n.append(
            {
                "tr": f"Ortak rastgele sayılar artımsal NPV'nin varyansını %{100 * m['varyans_azaltma']:.0f} azalttı (standart hata {m['se_bagimsiz']:.2f} → {m['se']:.2f} M$).",
                "en": f"Common random numbers cut the variance of incremental NPV by {100 * m['varyans_azaltma']:.0f}% (standard error {m['se_bagimsiz']:.2f} → {m['se']:.2f} M$).",
            }
        )
    return n


def hafif_tarama(kod: str, ges_oran: float = 0.25) -> dict:
    """
    Tüm santraller için hızlı, deterministik tarama (Monte Carlo yok): bağlantı kullanımı, RES–GES korelasyonu, GES başabaş
    CAPEX'i (bağlantının ges_oran'ı kadar GES için) ve temsilî günlü MILP'in önerdiği ekleme ile artımsal NPV tahmini.
    """
    cfg0 = config_oku()
    ek = deger(cfg0["v4"]["ekleme"])
    s = bul(kod)
    C = float(s["kurulu_mw"])
    mwe = float(np.clip(C, 5.0, 300.0))
    kv = KullaniciVarsayimlari(
        baglanti_mw=mwe, azami_res_mw=C, azami_ges_mw=ek["ges_ust_carpani"] * mwe, turbin_yerlesimi=False,
        kalibrasyon=f"santral:{int(s['epias_id'])}", turbin=str(s["turbin"]), gobek=float(s["gobek"]), yerlesim_bakim=False,
        finansman=False, ekstra=artimsal_cfg(ek),
    )  # fmt: skip
    h = hazirla({"ad": kod, "enlem": float(s["enlem"]), "boylam": float(s["boylam"])}, kv)
    f = fiyat_senaryosu_uret(h.cfg, h.u, "baz", "devam")
    e = ges_egrisi(h, f, C, mwe, ges_oran * mwe, 2)[-1]
    o = ortam(h)
    o.opt["turbin_gucu"], o.opt["turbin_azami"], o.opt["ges_azami_mw"] = C, 1, ek["ges_ust_carpani"] * mwe
    o.opt["mip_bosluk"] = 0.005
    m = o.milp({"dz", "yekg", "yh"}, "baz", K=24, zaman=120, yh_carpan=sfk_milp_carpani(o), sabit={"N": 1})
    m0 = o.milp({"dz", "yekg"}, "baz", K=24, zaman=120, sabit={"N": 1, "G": 0.0, "P": 0.0, "E": 0.0})
    df = h.profil
    return {
        "kod": kod,
        "il": s["il"],
        "kurulu_mw": C,
        "res_kf": float(df["res_kf"].mean()),
        "ges_kf": float(df["ges_kf"].mean()),
        "korelasyon": float(df["res_kf"].corr(df["ges_kf"])),
        "baglanti_bos_saat_orani": float((df["res_kf"] * C < 0.5 * mwe).mean()),
        "ges_basabas_capex": e["basabas_capex"],
        "ges_artimsal_npv_25": e["artimsal_npv"],
        "milp_ges_mw": float(m["GES [MWac]"]),
        "milp_bess_mw": float(m["BESS [MW]"]),
        "milp_bess_mwh": float(m["BESS [MWh]"]),
        "milp_artimsal_npv": float(m["NPV tahmini [M USD]"] - m0["NPV tahmini [M USD]"]),
    }
