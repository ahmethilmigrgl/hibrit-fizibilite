"""
Aday sahalar ve ortak senaryolarla değerleme (Faz F1, çevrimdışı).

Aday seçimi: ön tarama hücrelerinden dışlananlar (koruma, uygun alan, ada) çıkarılır; ekonomik sıra (başabaş) ile çok
kriterli sıra (dengeli profil, TOPSIS) ortalamasına göre sıralanır; açgözlü seçimle hücreler arası ≥ asgari mesafe ve il
başına en çok il_azami aday (coğrafi yayılım).

Değerleme: her aday için tam analiz motorunun adımları (hazırlık → iz verimi eğrisi → MILP tasarımı) ve 2–4 ayrık tasarım
seçeneği (MILP, bataryasız, küçük, büyük). Her seçenek için yerleşim + bakım (tam_sonra) ve işletme tabloları, sonra
Monte Carlo SABİT senaryo sayısıyla ve TÜM ADAYLARDA AYNI tohumla:
    ortak (tohum)       : fiyat yolu, hava yılı (her sahada aynı ERA5 takvim yılı → sahalar arası rüzgâr korelasyonu),
                          SFK/doyum senaryosu ve batarya yayılımı, CAPEX/OPEX çarpanları, kesinti, YEKDEM koridoru
    sahaya özgü (tohum_saha): RES model hatası (atlas aktarım hatası), bağlantı mesafesi oranı, COD (proje takvimi)
Saklanan: tasarım × senaryo NPV matrisi (en iyi gelir yapısıyla), CAPEX, türbin sayısı, kurulu güç, işletme gider
kalemleri (sinerji hesabı), lojistik birim maliyetleri.
"""

from __future__ import annotations

import time
import zlib

import numpy as np
import pandas as pd

from src.ayarlar import KOK, config_oku, deger

BOLGE = {  # coğrafi bölge (bölge kapasite kısıtı ve özetler için)
    "Marmara": "Balıkesir Bilecik Bursa Çanakkale Edirne İstanbul Kırklareli Kocaeli Sakarya Tekirdağ Yalova",
    "Ege": "Afyonkarahisar Aydın Denizli İzmir Kütahya Manisa Muğla Uşak",
    "Akdeniz": "Adana Antalya Burdur Hatay Isparta Kahramanmaraş Mersin Osmaniye",
    "İç Anadolu": "Aksaray Ankara Çankırı Eskişehir Karaman Kayseri Kırıkkale Kırşehir Konya Nevşehir Niğde Sivas Yozgat",
    "Karadeniz": "Amasya Artvin Bartın Bayburt Bolu Çorum Düzce Giresun Gümüşhane Karabük Kastamonu Ordu Rize Samsun Sinop Tokat Trabzon Zonguldak",
    "Doğu Anadolu": "Ağrı Ardahan Bingöl Bitlis Elazığ Erzincan Erzurum Hakkari Iğdır Kars Malatya Muş Tunceli Van",
    "Güneydoğu Anadolu": "Adıyaman Batman Diyarbakır Gaziantep Kilis Mardin Siirt Şanlıurfa Şırnak",
}
IL_BOLGE = {il: b for b, s in BOLGE.items() for il in s.split()}


def ayar(cfg: dict | None = None) -> dict:
    return deger((cfg or config_oku())["v3"]["portfoy"])


def _km(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def aday_listesi(cfg: dict | None = None) -> pd.DataFrame:
    from src.cbs import cok_kriterli as CK
    from src.cbs import kriterler as KR

    a = ayar(cfg)
    d = KR.tablo().copy()
    d = d[KR.dislanan(d) == ""].reset_index(drop=True)
    X, f = KR.matris(d, list(KR.KRITERLER))
    d["mcda"] = CK.topsis(X, CK.ahp(KR.profil_matrisi("dengeli"))["agirlik"], f, KR.vektor())
    d["sira_eko"] = d["basabas_en_iyi"].rank()
    d["sira_mcda"] = d["mcda"].rank(ascending=False)
    d["sira"] = (d["sira_eko"] + d["sira_mcda"]) / 2
    d = d[d["basabas_en_iyi"] <= a["aday_basabas_ust"]].sort_values("sira").reset_index(drop=True)
    sec: list[int] = []
    il_say: dict[str, int] = {}
    for i, r in d.iterrows():
        if il_say.get(r.il, 0) >= a["il_azami"]:
            continue
        if sec and _km(r.enlem, r.boylam, d.loc[sec, "enlem"].to_numpy(), d.loc[sec, "boylam"].to_numpy()).min() < a["aday_min_km"]:
            continue
        sec.append(i)
        il_say[r.il] = il_say.get(r.il, 0) + 1
        if len(sec) >= a["aday_sayisi"]:
            break
    s = d.loc[sec].reset_index(drop=True)
    s["bolge"] = s["il"].map(IL_BOLGE).fillna("?")
    s["kod"] = [f"A{i + 1:02d}" for i in range(len(s))]
    return s[
        ["kod", "il", "ilce", "bolge", "hucre_enlem", "hucre_boylam", "enlem", "boylam", "res_kf", "ges_kf", "guven", "basabas_en_iyi",
         "mcda", "sira_eko", "sira_mcda", "trafo_ad", "trafo_km"]
    ]  # fmt: skip


def tohum_saha(kod: str, tohum: int) -> int:
    return tohum + 1000 + zlib.crc32(kod.encode()) % 100_000


def _varyantlar(d0: dict, n_star: int, n_sigan: int, tg: float, a: dict) -> list[dict]:
    """MILP tasarımından 2–4 ayrık seçenek: MILP, bataryasız, küçük (~%60 türbin), büyük (~%140, alana sığdığı kadar)."""
    v = [{"ad": "MILP", **d0, "N": n_star}]
    if d0["bess_mw"] > 0.5:
        v.append({"ad": "Bataryasız", **d0, "bess_mw": 0.0, "bess_mwh": 0.0, "N": n_star})
    nk = max(a["varyant_asgari_turbin"], round(a["varyant_kucuk"] * n_star))
    if n_star - nk >= 2:
        v.append({"ad": "Küçük", **d0, "res_mw": nk * tg, "N": nk})
    nb = min(n_sigan, round(a["varyant_buyuk"] * n_star))
    if nb - n_star >= 2:
        v.append({"ad": "Büyük", **d0, "res_mw": nb * tg, "N": nb})
    return v


def degerle(aday: dict, cfg: dict | None = None) -> dict:
    """Bir adayı tüm tasarım seçenekleriyle ortak senaryolarda değerler (çevrimdışı; ~2–4 dk)."""
    from src.motor import mc as MC
    from src.motor import tablolar
    from src.motor.ortak import hazirla, ortam
    from src.motor.tam import ASAMA_ANAHTAR, _fiyat, tasarim_sec
    from src.motor.v3 import tam_once, tam_sonra
    from src.motor.varsayimlar import KullaniciVarsayimlari
    from src.risk.tasarim import Tasarim

    a = ayar(cfg)
    t0 = time.perf_counter()
    kv = KullaniciVarsayimlari(baglanti_mw=a["baglanti_mw"])
    h = hazirla({"ad": aday["kod"], "enlem": aday["enlem"], "boylam": aday["boylam"], "baglanti_mw": a["baglanti_mw"]}, kv)
    f, seviye = _fiyat(h, kv)
    on = tam_once(h, kv)
    o = ortam(on["hA"])
    o.opt["iz_verim"] = on["verim"]
    _t_milp, tas = tasarim_sec(on["hA"], o, kv, seviye if isinstance(seviye, str) else float(seviye), f)
    tg = float(deger(h.cfg["optimizasyon"]["turbin_gucu"]))
    d0 = {k: float(tas[k]) for k in ("res_mw", "ges_mw", "bess_mw", "bess_mwh")}
    n_star = round(d0["res_mw"] / tg)
    DF = o.DF
    p8760 = ((f.fiyatlar * DF[:, None, None]).sum(0) / DF.sum()).mean(0)
    sigma = MC.res_sigma(h.guven)
    ts = tohum_saha(aday["kod"], a["tohum"])
    cod_k = np.load(KOK / "results" / "takvim_cod_ornekleri.npz")[ASAMA_ANAHTAR[kv.proje_asamasi]].astype(float)
    lj = (h.cfg["_saha"].get("altyapi") or {}).get("lojistik") or {}
    cod = np.random.default_rng(ts + 99).choice(cod_k, a["n_mc"], replace=True) + float(lj.get("gecikme_ay") or 0.0)
    asgari_sfk = deger(h.cfg["gelir_yigini"]["yan_hizmet"]["asgari_guc"])
    out_tas, npv = [], []
    ortak = None
    for v in _varyantlar(d0, n_star, on["n_sigan"], tg, a) if n_star > 0 else [{"ad": "MILP", **d0, "N": 0}]:
        s3 = tam_sonra(h, kv, on, v["N"], p8760) if v["N"] > 0 else {"h": on["hA"], "yerlesim": None, "bakim": None}
        hv = s3["h"]
        ov = ortam(hv)
        t = Tasarim(
            v["ad"], v["res_mw"], v["ges_mw"], v["bess_mw"], v["bess_mwh"], sebeke_mw=a["baglanti_mw"],
            yan_hizmet=v["bess_mw"] >= asgari_sfk - 1e-6, dengesizlik_azaltim=True, yekg=True,
        )  # fmt: skip
        tb_T = tablolar.tablo(ov, t, "hafif", sigma=sigma or 0.06)
        tb_Y = tablolar.tablo(ov, t, "hafif", yekdem=True, sigma=sigma or 0.06)
        r = MC.mc_calistir(ov, t, tb_T, tb_Y, ["tuccar", "yekdem_opsiyon"], cod, a["n_mc"], a["tohum"], sigma, True, tohum_saha=ts)
        en = max(r["npv"], key=lambda y: r["npv"][y].mean())
        x = r["npv"][en].astype(np.float32)
        isl = s3.get("isletme") or {}
        bk = s3.get("bakim") or {}
        out_tas.append(
            {
                "kod": aday["kod"],
                "tasarim": v["ad"],
                "res_mw": v["res_mw"],
                "ges_mw": v["ges_mw"],
                "bess_mw": v["bess_mw"],
                "bess_mwh": v["bess_mwh"],
                "N": int(min(v["N"], on["n_sigan"])),
                "capex_musd": float(r["ek"][en]["capex_musd"]),
                "gelir_yapisi": en,
                "e_npv": float(x.mean()),
                "p_pozitif": float((x > 0).mean()),
                "cvar5": float(np.sort(x)[: int(0.05 * len(x))].mean()),
                "om_usd_mw_yil": float(deger(hv.cfg["teknoloji"]["res"]["opex_sabit"])),
                "isletme_model": isl.get("model"),
                "kullanilabilirlik": float(s3.get("kullanilabilirlik") or np.nan),
                "kendi_kullanilabilirlik": float(np.mean(bk["A_enerji_ornek"])) if bk.get("A_enerji_ornek") is not None else np.nan,
            }
        )
        npv.append(x)
        ortak = r["ortak"] if ortak is None else ortak
    altyapi = h.cfg["_saha"].get("altyapi") or {}
    bg = altyapi.get("baglanti") or {}
    return {
        "aday": {
            **aday,
            "trafo_ad": (bg.get("hedef_trafo") or {}).get("ad"),
            "trafo_kv": (bg.get("hedef_trafo") or {}).get("kv"),
            "turbin": h.cfg["_saha"]["turbin"],
            "turbin_mw": tg,
            "n_sigan": int(on["n_sigan"]),
            "sure_s": time.perf_counter() - t0,
        },
        "tasarimlar": out_tas,
        "npv": np.vstack(npv),
        "ortak": ortak,
        "lojistik": (altyapi.get("lojistik") or {}).get("alternatifler"),
    }
