"""
Ayrık olay simülasyonu (SimPy, MIT lisansı): proje ömrü boyunca türbin bazında arızalar, onarım kuyruğu ve kaynak kısıtları.

Varlıklar ve kaynaklar
    türbinler (N, her biri üretim payıyla), teknisyen ekipleri (simpy.Resource, kapasite = ekip sayısı),
    büyük vinç (simpy.Resource, kapasite = vinç sayısı; her iş mobilizasyon süresi ister),
    kritik yedek parça stokları (simpy.Container; baz stok (S−1, S) politikası: her çekişte bir parça sipariş edilir,
    tedarik süresi sonra stoğa girer).
Olaylar (önceden örneklenir; kuyruk ve bekleme SimPy'de)
    küçük / büyük onarım: Poisson süreci (alt sistem × sınıf oranı); müdahale gecikmesi + ekip + tırmanma koşullu iş süresi
    büyük değişim: Weibull yenileme süreci (aşınma, β > 1); parça (stok ya da tedarik) + vinç mobilizasyonu + ardışık
                   kaldırma penceresi (rüzgâr < sınır) + kalan iş; durum izlemede tespit edilenler planlı yapılır
    uzaktan/yerinde sıfırlama: Poisson, kısa duruş, ekip gerekmez
    yıllık önleyici bakım (takvim/durum stratejilerinde): çizelgedeki gün, ekip + tırmanma koşullu iş saatleri
Çıktılar (tekrar başına): zaman ve enerji bazlı kullanılabilirlik, kayıp enerji ve gelir (saatlik fiyatla), O&M gideri
kalemleri, arıza sayıları, hava ve parça beklemeleri.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import simpy
from scipy.optimize import brentq

from src.bakim.hava import SAAT_YIL, HavaZaman

KATLAR = ("kucuk", "buyuk", "degisim")


@dataclass
class Girdi:
    N: int
    P_mw: float
    pay: np.ndarray  # (N,) türbin üretim payı (ortalama 1)
    kf_yillar: np.ndarray  # (Y, 8760) çiftlik saatlik KF (MW başına; iz ve elektrik kaybı dahil, kullanılabilirlik hariç)
    v_yillar: np.ndarray  # (Y, 8760) göbek hızı [m/s]
    fiyat: np.ndarray  # (8760,) USD/MWh
    omur: int
    p: dict  # config v3.bakim
    strateji: str = "durum"  # duzeltici | takvim | durum
    pm_gun: np.ndarray | None = None  # (N,) yılın günü (0–364) önleyici bakım başlangıcı
    stok: dict = field(default_factory=dict)  # alt sistem → baz stok S


@lru_cache(maxsize=128)
def weibull_olcek(lam: float, beta: float, T_yil: float) -> float:
    """
    Weibull yenileme sürecinin ölçeği η [yıl]: ömür boyu beklenen değişim sayısı (yenileme fonksiyonu) M(T) = λ·T olacak
    şekilde (ortak rastgele sayılarla 20.000 örnekli Monte Carlo + kök bulma). β = 1'de η = 1/λ (Poisson).
    """
    if abs(beta - 1.0) < 1e-9:
        return 1.0 / lam
    u = np.random.default_rng(12345).weibull(beta, (20000, 12))
    c = np.cumsum(u, axis=1)

    def M(eta: float) -> float:
        return float((c * eta < T_yil).sum(1).mean())

    return float(brentq(lambda e: M(e) - lam * T_yil, 0.05 * T_yil, 1e4 * T_yil, xtol=1e-3))


def ekip_sayisi(N: int, p: dict) -> int:
    """Saha teknisyen ekibi sayısı: her 'turbin_basina' türbine bir ekip (en az 1)."""
    return max(1, math.ceil(N / p["ekip"]["turbin_basina"]))


def olaylari_ornekle(g: Girdi, rng: np.random.Generator) -> list[tuple]:
    """(zaman_saat, türbin, alt_sistem, sınıf, tespit_zamanı | None) listesi."""
    p = g.p
    T_yil = g.omur
    T = T_yil * SAAT_YIL
    duz = g.strateji == "duzeltici"
    on = p["onleyici"]
    kat_c = on["duzeltici_kat_carpani"] if duz else 1.0
    olc_c = on["duzeltici_olcek_carpani"] if duz else 1.0
    ol = []
    for ad, a in p["alt_sistemler"].items():
        for k, lam in ((0, a["lam_kucuk"] * kat_c), (1, a["lam_buyuk"] * kat_c)):
            if lam <= 0:
                continue
            n = rng.poisson(lam * T_yil, g.N)
            for i in range(g.N):
                for t in rng.uniform(0, T, n[i]):
                    ol.append((float(t), i, ad, k, None))
        lam = a["lam_degisim"]
        if lam > 0:
            eta = weibull_olcek(lam, a["beta"], T_yil) * olc_c * SAAT_YIL
            for i in range(g.N):
                t = 0.0
                while True:
                    t += eta * rng.weibull(a["beta"])
                    if t >= T:
                        break
                    tespit = None
                    if g.strateji == "durum" and a["cms_tespit"] > 0 and rng.random() < a["cms_tespit"]:
                        pf = rng.uniform(*p["durum_izleme"]["pf_gun"]) * 24
                        tespit = t - pf if t - pf > 0 else None
                    ol.append((float(t), i, ad, 2, tespit))
    s = p["sifirlama"]
    n = rng.poisson(s["lam"] * T_yil, g.N)
    for i in range(g.N):
        for t in rng.uniform(0, T, n[i]):
            ol.append((float(t), i, "sifirlama", -1, None))
    ol.sort(key=lambda x: x[0] if x[4] is None else x[4])
    return ol


def tekrar(g: Girdi, tohum: int) -> dict:
    """Tek tekrar (bir ömür)."""
    rng = np.random.default_rng(tohum)
    p = g.p
    lo, hv = p["lojistik"], p["hava"]
    T = g.omur * SAAT_YIL
    yi = rng.integers(0, g.v_yillar.shape[0], g.omur)
    v = g.v_yillar[yi].ravel()
    E_h = g.kf_yillar[yi].ravel() * g.P_mw  # MWh/saat, ortalama paylı türbin
    R_h = E_h * np.tile(g.fiyat, g.omur)
    limitler = [a["kaldirma_limiti"] for a in p["alt_sistemler"].values() if a["vinc"]] or [10.0]
    hz = HavaZaman(v, hv["tirmanma_limiti"], tuple(hv["vardiya"]), lo["kaldirma_pencere_h"], limitler)
    olaylar = olaylari_ornekle(g, rng)
    env = simpy.Environment()
    ekip = simpy.Resource(env, capacity=ekip_sayisi(g.N, p))
    vinc = simpy.Resource(env, capacity=lo["vinc_sayisi"])
    stoklar = {ad: simpy.Container(env, init=int(g.stok.get(ad, 0))) for ad, a in p["alt_sistemler"].items() if a["stok"]}
    eur = p["eur_usd"]
    kayit = {"aralik": [[] for _ in range(g.N)], "pm": [], "maliyet": {"duzeltici_malzeme": 0.0, "vinc": 0.0, "onleyici_malzeme": 0.0}}
    sayac: dict = {}
    beklemeler = []  # değişim işleri: (ay, hava beklemesi [saat], parça beklemesi [saat], toplam duruş [saat], planli)

    def siparis(ad: str, gecikme_h: float):
        yield env.timeout(gecikme_h)
        yield stoklar[ad].put(1)

    def parca_al(ad: str, a: dict):
        if ad in stoklar:
            env.process(siparis(ad, a["tedarik_gun"] * 24))
            yield stoklar[ad].get(1)
        else:
            yield env.timeout(a["tedarik_gun"] * 24)

    def onarim(t, i, ad, k):
        yield env.timeout(max(t - env.now, 0))
        a = p["alt_sistemler"][ad]
        bas = env.now
        gecikme = lo["mudahale_h"] if k == 0 else lo["buyuk_parca_h"]
        yield env.timeout(hz.vardiya_basi(bas + gecikme) - env.now)
        with ekip.request() as r:
            yield r
            yield env.timeout(hz.is_bitir(env.now, a["sure_h"][k]) - env.now)
        kayit["aralik"][i].append((bas, env.now))
        kayit["maliyet"]["duzeltici_malzeme"] += a["maliyet_eur"][k] * eur
        sayac[(ad, k)] = sayac.get((ad, k), 0) + 1

    def degisim(t, i, ad, tespit):
        a = p["alt_sistemler"][ad]
        planli = tespit is not None
        yield env.timeout(max((tespit if planli else t) - env.now, 0))
        bas = env.now
        yield env.process(parca_al(ad, a))
        t_parca = env.now
        if a["vinc"]:
            with vinc.request() as rv:
                yield rv
                yield env.timeout(max(bas + lo["vinc_mobilizasyon_gun"] * 24 - env.now, 0))
                with ekip.request() as re:
                    yield re
                    hazir = env.now
                    w = hz.kaldirma(env.now, a["kaldirma_limiti"])
                    yield env.timeout(max(w - env.now, 0))
                    yield env.timeout(lo["kaldirma_pencere_h"])
                    kalan = max(a["sure_h"][2] - lo["kaldirma_pencere_h"], 0)
                    yield env.timeout(hz.is_bitir(env.now, kalan) - env.now)
            kayit["maliyet"]["vinc"] += p["vinc_usd"]["kanat" if ad == "kanat_rotor" else "buyuk"]
            hava_bekleme = w - hazir
        else:
            with ekip.request() as re:
                yield re
                hazir = env.now
                yield env.timeout(hz.is_bitir(env.now, a["sure_h"][2]) - env.now)
            hava_bekleme = 0.0
            w = hazir
        son = env.now
        if planli:
            dur_bas = min(t, w)  # planlı iş arızadan önce başladıysa duruş iş başlangıcından; yoksa arızadan itibaren
            carp = p["durum_izleme"]["planli_maliyet_carpani"] if w <= t else 1.0
        else:
            dur_bas, carp = bas, 1.0
        kayit["aralik"][i].append((dur_bas, son))
        kayit["maliyet"]["duzeltici_malzeme"] += a["maliyet_eur"][2] * eur * carp
        sayac[(ad, 2)] = sayac.get((ad, 2), 0) + 1
        ay = int((t % SAAT_YIL) // 730.0) % 12
        beklemeler.append((ay, hava_bekleme, t_parca - bas, son - dur_bas, planli and w <= t))

    def sifirlama(t, i):
        yield env.timeout(max(t - env.now, 0))
        kayit["aralik"][i].append((env.now, env.now + p["sifirlama"]["sure_h"]))
        sayac[("sifirlama", -1)] = sayac.get(("sifirlama", -1), 0) + 1

    def onleyici(i, gun):
        on = p["onleyici"]
        for y in range(g.omur):
            yield env.timeout(max((y * 365 + gun) * 24 + 5 - env.now, 0))
            with ekip.request() as r:
                yield r
                b = env.now
                yield env.timeout(hz.is_bitir(env.now, on["is_saati"]) - env.now)
            kayit["pm"].append((i, b, env.now, on["is_saati"]))
            kayit["maliyet"]["onleyici_malzeme"] += on["malzeme_usd"]

    for t, i, ad, k, tespit in olaylar:
        if k == -1:
            env.process(sifirlama(t, i))
        elif k < 2:
            env.process(onarim(t, i, ad, k))
        else:
            env.process(degisim(t, i, ad, tespit))
    if g.strateji in ("takvim", "durum"):
        gunler = g.pm_gun if g.pm_gun is not None else np.linspace(90, 90 + 4 * g.N, g.N).astype(int) % 365
        for i in range(g.N):
            env.process(onleyici(i, int(gunler[i])))
    env.run(until=T)

    # --- duruşların birleşimi ve kayıplar
    agirlik = np.zeros(T + 1)
    agirlik_kisa = np.zeros(T + 1)
    dur_saat = 0.0
    for i in range(g.N):
        ar = sorted((max(a, 0.0), min(b, T)) for a, b in kayit["aralik"][i] if a < T)
        birlesik = []
        for a, b in ar:
            if birlesik and a <= birlesik[-1][1]:
                birlesik[-1][1] = max(birlesik[-1][1], b)
            else:
                birlesik.append([a, b])
        for a, b in birlesik:
            ia, ib = int(math.floor(a)), int(math.ceil(b))
            agirlik[ia] += g.pay[i]
            agirlik[ib] -= g.pay[i]
            if b - a < 48:
                agirlik_kisa[ia] += g.pay[i]
                agirlik_kisa[ib] -= g.pay[i]
            dur_saat += b - a
    for i, a, b, h in kayit["pm"]:  # önleyici bakım: yalnız çalışılan saatlerde duruş (vardiya içi)
        ia, ib = int(a), int(math.ceil(b))
        oran = h / max(b - a, 1e-9)
        agirlik[ia] += g.pay[i] * oran
        agirlik[ib] -= g.pay[i] * oran
        dur_saat += h
    w = np.minimum(np.cumsum(agirlik)[:T], g.pay.sum())
    wk = np.minimum(np.cumsum(agirlik_kisa)[:T], g.pay.sum())
    kayip_E = (E_h * w).reshape(g.omur, SAAT_YIL).sum(1)
    kayip_R = (R_h * w).reshape(g.omur, SAAT_YIL).sum(1)
    pot_E = E_h.reshape(g.omur, SAAT_YIL).sum(1) * g.pay.sum()
    A_E_yil = 1 - kayip_E / pot_E
    # --- giderler (yıllık ortalama)
    e = p["ekip"]
    sabit_ekip = ekip_sayisi(g.N, p) * e["kisi"] * e["yillik_saat"] * e["saat_ucreti_usd"]
    cms = g.N * p["durum_izleme"]["cms_usd_turbin_yil"] if g.strateji == "durum" else 0.0
    stok_tutma = sum(
        g.stok.get(ad, 0) * a["maliyet_eur"][2] * eur * p["stok"]["tutma_orani"] for ad, a in p["alt_sistemler"].items() if a["stok"]
    )
    gider = {
        "sabit_ekip": sabit_ekip,
        "duzeltici_malzeme": kayit["maliyet"]["duzeltici_malzeme"] / g.omur,
        "vinc": kayit["maliyet"]["vinc"] / g.omur,
        "onleyici_malzeme": kayit["maliyet"]["onleyici_malzeme"] / g.omur,
        "cms": cms,
        "stok_tutma": stok_tutma,
    }
    return {
        "A_zaman": 1 - dur_saat / (g.N * T),
        "A_enerji": float(1 - kayip_E.sum() / pot_E.sum()),
        "A_enerji_kisa": float(1 - (E_h * wk).sum() / pot_E.sum()),
        "A_enerji_yil": A_E_yil,
        "kayip_mwh_yil": float(kayip_E.mean()),
        "kayip_gelir_yil": float(kayip_R.mean()),
        "gider": gider,
        "sayac": sayac,
        "beklemeler": beklemeler,
    }


def simule(g: Girdi, R: int, tohum: int = 0) -> dict:
    """R tekrar; özet dağılımlar. Tohumlar tekrar no ile sabit (ortak rastgele sayılar: stratejiler aynı tohumları kullanır)."""
    sonuc = [tekrar(g, tohum + r) for r in range(R)]
    p = g.p
    gider = {k: np.array([s["gider"][k] for s in sonuc]) for k in sonuc[0]["gider"]}
    turbin_gider = sum(gider.values()) * p["genel_gider_carpani"]
    MW = g.N * g.P_mw
    opex = turbin_gider + p["diger_sabit_usd_mw_yil"] * MW
    sayac: dict = {}
    for s in sonuc:
        for k, v in s["sayac"].items():
            sayac[k] = sayac.get(k, 0) + v
    return {
        "A_zaman": np.array([s["A_zaman"] for s in sonuc]),
        "A_enerji": np.array([s["A_enerji"] for s in sonuc]),
        "A_enerji_kisa": np.array([s["A_enerji_kisa"] for s in sonuc]),
        "A_enerji_yil": np.vstack([s["A_enerji_yil"] for s in sonuc]),
        "kayip_mwh_yil": np.array([s["kayip_mwh_yil"] for s in sonuc]),
        "kayip_gelir_yil": np.array([s["kayip_gelir_yil"] for s in sonuc]),
        "gider": {k: float(v.mean()) for k, v in gider.items()},
        "turbin_om_usd_yil": turbin_gider,
        "opex_usd_yil": opex,
        "opex_usd_mw_yil": opex / MW,
        "ariza_orani": {f"{a}|{k}": v / (R * g.N * g.omur) for (a, k), v in sayac.items()},
        "beklemeler": [b for s in sonuc for b in s["beklemeler"]],
        "R": R,
    }
