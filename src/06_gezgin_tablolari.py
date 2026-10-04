"""
Aşama 6 — Dashboard "Tasarım gezgini" için önceden hesaplanan işletme tabloları.

Izgara: türbin sayısı × GES [MW] × batarya gücü [MW] × batarya süresi [saat]. Her tasarım için
(şekil yılı S=2) × (güneş yakalanma hedefi H=2) × (RES çarpanı M=2) × (SFK çarpanı A=4) × (PPA açık/kapalı)
işletme durumu çözülür (bataryalı: 8.760 saatlik LP; bataryasız: kapalı form). Hız için tek bir temsilî hava yılı
(ortalama KF'ye ölçeklenmiş) kullanılır — yaklaşım hatası src/06_sonuclari_paketle.py'de ölçülür.

Çıktı: results/gezgin_tablolari.npz (~0,5 MB, float32)
Çalıştırma: .venv/bin/python src/06_gezgin_tablolari.py  (~15-30 dk, paralel)
"""

import importlib.util
import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.ayarlar import KOK
from src.risk.tasarim import Tasarim

TURBIN = [8, 11, 14, 17, 20]
GES = [0.0, 25.0, 50.0]
BESS_MW = [0.0, 15.0, 30.0, 45.0]
SURE = [1.0, 1.5, 2.0, 3.0, 4.0]   # 1,5-2 saat: SFK rezervi için E ≥ 2·h·r kırılması (r ≤ 30 MW)
A_IZGARA = [0.0, 0.05, 0.25, 1.0]
SFK_ASGARI = 30.0
_O = None


def _ortam():
    global _O
    if _O is None:
        spec = importlib.util.spec_from_file_location("gy", Path(__file__).parent / "05_gelir_yigini.py")
        gy = importlib.util.module_from_spec(spec); spec.loader.exec_module(gy)
        _O = gy.Ortam()
        _O.H2 = [0.60, round(_O.oran0, 4)]
        from src.risk.senaryo import birim_sekiller
        _O.sek2 = birim_sekiller(_O.cfg, _O.u, _O.H2)[0]
    return _O


def tasarim_tablosu(arg):
    from src.risk.isletme import tablo_uret
    nt, ges, p, sure = arg
    o = _ortam()
    t = Tasarim("gezgin", nt * 4.2, ges, p, p * sure, yan_hizmet=p >= SFK_ASGARI, dengesizlik_azaltim=True, yekg=True, ppa=True)
    M, PP = [0.90, 1.00], [0.0, o.c.ppa_pay]
    G, R = o.g[None], o.r[None]
    kw = dict(h_izgara=o.H2, m_izgara=M, ppa_izgara=PP, L_ref=58.0, a_ref=1.0, sabitler=o.sabit)
    if p >= SFK_ASGARI:
        sifir = tablo_uret(replace(t, yan_hizmet=False), G, R, o.sek2, o.yan, a_izgara=[0.0], **kw)["T"]
        ust = tablo_uret(t, G, R, o.sek2, o.yan, a_izgara=A_IZGARA[1:], **kw)["T"]
        T = np.concatenate([sifir, ust], axis=4)
    else:   # SFK'ya katılamaz: tüm A değerlerinde aynı işletme
        T = tablo_uret(replace(t, yan_hizmet=False), G, R, o.sek2, o.yan, a_izgara=[0.0], **kw)["T"]
        T = np.repeat(T, len(A_IZGARA), axis=4)
    return arg, T[0].astype(np.float32)          # (S, H, M, A, PP, alan)


def main():
    t0 = time.time()
    isler = [(nt, g_, p, s) for nt, g_, p, s in itertools.product(TURBIN, GES, BESS_MW, SURE) if not (p == 0 and s != SURE[0])]
    isler.sort(key=lambda x: -x[2])     # büyük bataryalar önce (en uzun işler)
    sonuc = {}
    # Önceki çalıştırmanın sonuçlarını yeniden kullan (ızgara genişletildiğinde yalnız yeni tasarımlar çözülür)
    eski_dosya = KOK / "results" / "gezgin_tablolari.npz"
    if eski_dosya.exists():
        z = np.load(eski_dosya)
        for (i, nt), (j, g_), (k, p), (l_, s) in itertools.product(enumerate(z["turbin"]), enumerate(z["ges"]),
                                                                   enumerate(z["bess_mw"]), enumerate(z["sure"])):
            arg = (int(nt), float(g_), float(p), float(s))
            if arg in isler:
                sonuc[arg] = z["T"][i, j, k, l_]
        isler = [a for a in isler if a not in sonuc]
        print(f"{len(sonuc)} tasarım önceki çalıştırmadan, {len(isler)} yeni", flush=True)
    with ProcessPoolExecutor(max_workers=7) as ex:
        for i, (arg, T) in enumerate(ex.map(tasarim_tablosu, isler, chunksize=1)):
            sonuc[arg] = T
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(isler)} tasarım ({(time.time() - t0) / 60:.1f} dk)", flush=True)
    ornek = next(iter(sonuc.values()))
    T = np.zeros((len(TURBIN), len(GES), len(BESS_MW), len(SURE)) + ornek.shape, np.float32)
    for (nt, g_, p, s), v in sonuc.items():
        i, j, k = TURBIN.index(nt), GES.index(g_), BESS_MW.index(p)
        if p == 0:
            T[i, j, k, :] = v
        else:
            T[i, j, k, SURE.index(s)] = v
    o = _ortam()
    hedef = KOK / "results"; hedef.mkdir(exist_ok=True)
    np.savez_compressed(hedef / "gezgin_tablolari.npz", T=T, turbin=np.array(TURBIN, float), ges=np.array(GES), bess_mw=np.array(BESS_MW),
                        sure=np.array(SURE), h=np.array(o.H2), m=np.array([0.90, 1.00]), a=np.array(A_IZGARA),
                        ppa=np.array([0.0, o.c.ppa_pay]), sfk_asgari=SFK_ASGARI)
    print(f"Kaydedildi: results/gezgin_tablolari.npz, şekil {T.shape}, {(time.time() - t0) / 60:.1f} dk")


if __name__ == "__main__":
    main()
