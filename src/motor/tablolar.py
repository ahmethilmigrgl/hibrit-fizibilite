"""
Çalışma anında işletme (dispatch) tabloları — v1 önceden hesaplanmış tablo yaklaşımının yeni sahalar için genellemesi.

v1 (Ezine): bataryalı tasarımda kanibalizasyon 4 × model çarpanı 3 × yan hizmet 7 (doyum) × PPA payı noktası, 10 hava yılı × 2
şekil yılı → ~1.700 LP (YEKDEM tablosuyla ~3.400), diskte önbellekli.
v2 ızgaraları (config yok; burada sabit, docs/v2_B_analiz_motoru.md'de doğruluk ölçümü):
    "v1"    : v1 ile aynı ızgara (regresyon)
    "hafif" : H = {0,55; oran0}, M = {1 − 2σ; 1; 1 + 2σ} (σ: sahanın RES model belirsizliği), A = {0; 0,05; 0,25; 1,0}, 10 hava yılı
    "hizli" : "hafif" + 5 hava yılı (temsilî: yıllık RES KF sırasına göre eşit aralıklı)
Hava yılları iki sürece (2 çekirdek) bölünür; sonuç (profil, tasarım, ızgara, sabitler) anahtarıyla diskte önbelleklenir.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace

import numpy as np

from src.ayarlar import KOK
from src.risk.isletme import IsletmeLP, IsletmeLPHizli, tablo_uret
from src.risk.senaryo import birim_sekiller
from src.risk.tasarim import Tasarim
from src.risk.yekdem_tablo import A_DUSUK, YEKDEM_PP, YEKDEM_SABIT

KLASOR = KOK / "data" / "onbellek" / "tablolar"
CEKIRDEK = int(os.environ.get("MOTOR_CEKIRDEK", "2"))


def izgara(seviye: str, o, sigma: float = 0.125) -> dict:
    """sigma: RES model çarpanının göreli belirsizliği (güven seviyesinden); M ızgarası 1 ± 2σ ([0,5; 1,5])."""
    if seviye == "v1":
        return {"H": [0.55, 0.62, 0.70, round(o.oran0, 4)], "M": [0.80, 0.94, 1.08], "A": [0.0, *A_DUSUK, 0.25, 0.6, 1.0], "W": None}
    if seviye == "kucuk":  # yalnız testler (MOTOR_KUCUK=1)
        return {"H": [0.55, round(o.oran0, 4)], "M": [0.9, 1.1], "A": [0.0, 1.0], "W": 3}
    H = [0.55, round(o.oran0, 4)]
    W = None if seviye == "hafif" else 5
    d = float(min(0.5, max(0.2, 2 * sigma)))
    return {"H": H, "M": [round(1 - d, 3), 1.0, round(1 + d, 3)], "A": [0.0, 0.05, 0.25, 1.0], "W": W}


def _isci(args):
    t, ges, res, sek, yan, H, M, A, pp, sabit = args
    # highspy doğrudan LP (IsletmeLP ile birebir aynı sonuç, ~4× hızlı; src/risk/isletme.py)
    lp = IsletmeLP if os.environ.get("MOTOR_LP") == "pyomo" else IsletmeLPHizli  # karşılaştırma için eski sürüm
    return tablo_uret(t, ges, res, sek, yan, H, M, A, pp, 58.0, 1.0, sabit, lp_sinifi=lp)["T"]


def hava_alt_kumesi(o, W: int | None) -> np.ndarray:
    n = o.u.res.shape[0]
    if W is None or W >= n:
        return np.arange(n)
    sira = np.argsort(o.u.res.mean(1))
    return np.sort(sira[np.round(np.linspace(0, n - 1, W)).astype(int)])


def tablo(o, t: Tasarim, seviye: str = "hafif", yekdem: bool = False, sigma: float = 0.125) -> dict:
    """Tasarım için işletme tablosu (yan hizmet ızgarası 0 dahil). yekdem=True: φ ∈ {0, 1}, deşarj sözleşmeli fiyattan."""
    iz = izgara(seviye, o, sigma)
    yw = hava_alt_kumesi(o, iz["W"])
    t = replace(t, ppa=True) if yekdem else t
    pp = YEKDEM_PP if yekdem else ([0.0, o.c.ppa_pay] if t.ppa else [0.0])
    sabit = {**o.sabit, **(YEKDEM_SABIT if yekdem else {})}
    pil = t.bess_mw > 0.5
    anahtar = hashlib.md5(
        json.dumps([o.profil_imza or "v1", asdict(t), iz, yw.tolist(), pp, sabit, o.baglanti], default=float).encode()
    ).hexdigest()[:16]
    yol = KLASOR / f"{anahtar}.pkl"
    if yol.exists():
        return pickle.loads(yol.read_bytes())
    sek = birim_sekiller(o.cfg, o.u, iz["H"])[0]
    ges, res = o.u.ges[yw], o.u.res[yw]
    parca = np.array_split(np.arange(len(yw)), max(1, min(CEKIRDEK, len(yw))))

    def calistir(tt: Tasarim, A: list[float]) -> np.ndarray:
        isler = [(tt, ges[p], res[p], sek, o.yan, iz["H"], iz["M"], A, pp, sabit) for p in parca]
        if CEKIRDEK > 1 and pil:
            # fork: alt süreç ana modülü yeniden içe aktarmaz (Streamlit ve betikler için güvenli; Linux varsayılanı)
            with ProcessPoolExecutor(max_workers=len(isler), mp_context=mp.get_context("fork")) as hv:
                return np.concatenate(list(hv.map(_isci, isler)), axis=0)
        return np.concatenate([_isci(a) for a in isler], axis=0)

    A = iz["A"]
    if yekdem:
        # φ = 0 dilimi tüccar tablosuyla aynı (sözleşmeli deşarj yalnız φ > 0'da etkili; v1 tablolarında göreli fark 2e-9):
        # tüccar tablosu yeniden kullanılır, yalnız φ = 1 hesaplanır (LP sayısı üçte bir azalır)
        tuccar = tablo(o, replace(t, ppa=False), seviye, yekdem=False, sigma=sigma)
        pp = [1.0]
    if pil and t.yan_hizmet:
        T = np.concatenate([calistir(replace(t, yan_hizmet=False), [1.0]), calistir(t, [a for a in A if a > 0])], axis=4)
    else:
        T = np.repeat(calistir(t, [1.0]), len(A), axis=4)
    if yekdem:
        T = np.concatenate([tuccar["T"], T], axis=5)
        pp = [0.0, 1.0]
    sonuc = {"T": T, "h": np.array(iz["H"]), "m": np.array(iz["M"]), "a": np.array(A), "ppa": np.array(pp), "hava_yillari": yw}
    KLASOR.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(pickle.dumps(sonuc))
    return sonuc
