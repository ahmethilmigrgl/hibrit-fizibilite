"""
v3 E2 — Türkiye ön tarama haritasının v3 sürümü: hızlı taramadaki iz kaybı (tablo), kullanılabilirlik ve işletme modeli
(FSA), mesafeye bağlı şebeke bağlantısı ve sahaya göre lojistik maliyeti.

v2 ön tarama mantığı (src/v2_C2_on_tarama.py) aynen; fark: standart tasarımların RES profili hızlı tarama gibi
(1 − iz(N)) × A ile ölçeklenir, OPEX işletme modelinden, bağlantı ve lojistik CAPEX'i sahaya göre (motor.ortak.hazirla).
Kipler:
    tam      → data/atlas/on_tarama.parquet (uygulamanın haritası); v2 sürümü outputs/v3E/on_tarama_v2.parquet olarak saklanır
    altyapisiz (altyapı maliyetleri kapalı; yalnız etki ayrıştırması) → outputs/v3E/on_tarama_v3_altyapisiz.parquet
Çalıştırma: .venv/bin/python src/v3_E2_on_tarama.py [tam|altyapisiz] [--paralel 6]
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import multiprocessing as mp

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK
from src.kaynaklar import era5_grid, pvgis_grid

ATLAS = KOK / "data" / "atlas" / "on_tarama.parquet"
KIP = "tam"


def hucre_tara(h: tuple[float, float]) -> dict:
    from src.ayarlar import deger
    from src.finans.metrikler import basabas_fiyat
    from src.kaynaklar.adalar import ada_bilgisi
    from src.motor.hizli import _fiyat, standart_tasarimlar, uretim_ozeti
    from src.motor.ortak import hazirla
    from src.motor.v3 import hizli_hazirla, iz_hizli
    from src.motor.varsayimlar import KullaniciVarsayimlari

    e, b = h
    ne, nb = pvgis_grid.temsil_noktasi(e, b)
    kayit = {"hucre_enlem": e, "hucre_boylam": b, "enlem": round(ne, 4), "boylam": round(nb, 4)}
    kv = KullaniciVarsayimlari(altyapi_maliyetleri=(KIP == "tam"))
    try:
        hz = hazirla({"ad": f"hucre_{e:.2f}_{b:.2f}", "enlem": ne, "boylam": nb}, kv, profil_onbellegi=False)
        hz, v3b = hizli_hazirla(hz, kv)
        uo, _, _ = uretim_ozeti(hz)
        f, _ = _fiyat(hz, kv)
        tas = standart_tasarimlar(hz, f, iz_hizli)
        en_iyi = max(tas, key=lambda x: x["npv_musd"])

        def bb(ad: str) -> float:
            x = next((x for x in tas if x["tasarim"] == ad), None)
            try:
                return float(basabas_fiyat(x["_k"], hz.cfg, x["_u"], hz.v, kv.kanibalizasyon)) if x else np.nan
            except ValueError:
                return np.nan

        kal = hz.bilgi["kalibrasyon"]
        a = hz.cfg["_saha"].get("altyapi") or {}
        kayit.update(
            {
                "il": hz.saha.il,
                "ilce": hz.saha.ilce,
                "res_kf": uo["res_kf"],
                "ges_kf": uo["ges_kf"],
                "guven": hz.guven["seviye"],
                "komsu": "; ".join(kal.get("komsu", [])),
                "komsu_km": "; ".join(f"{x:.1f}" for x in kal.get("mesafe_km", [])),
                "gwa_100m": kal.get("gwa_hiz"),
                "turbin": hz.bilgi["turbin"],
                "basabas_res": bb("RES"),
                "basabas_ges": bb("GES"),
                "en_iyi_tasarim": en_iyi["tasarim"],
                "en_iyi_npv_musd": en_iyi["npv_musd"],
                "basabas_en_iyi": bb(en_iyi["tasarim"]),
                **{f"npv_{x['tasarim']}": x["npv_musd"] for x in tas},
                "sebeke_capex_usd_mw": float(deger(hz.cfg["teknoloji"]["sebeke"]["capex"])),
                "res_capex_usd_mw": float(deger(hz.cfg["teknoloji"]["res"]["capex"])),
                "om_usd_mw_yil": v3b["om_usd_mw_yil"],
                "kullanilabilirlik": v3b["kullanilabilirlik"],
                "goc_azami": (a.get("alan") or {}).get("goc_azami"),
                "uygun_oran": (a.get("alan") or {}).get("uygun_oran"),
                "ada": ada_bilgisi(ne, nb) is not None,
                "ust_sinir": bool(uo["res_kf"] >= deger(hz.cfg["v2"]["uygulama"])["ust_sinir_kf"]),
                "hata": "",
            }
        )
    except Exception as ex:
        kayit.update({"ada": False, "ust_sinir": False, "hata": f"{type(ex).__name__}: {str(ex)[:120]}"})
    return kayit


def _kip(k: str) -> None:
    global KIP
    KIP = k


def main() -> None:
    kip = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "tam"
    paralel = int(sys.argv[sys.argv.index("--paralel") + 1]) if "--paralel" in sys.argv else 6
    out = CIKTILAR / "v3E"
    out.mkdir(parents=True, exist_ok=True)
    if kip == "tam" and not (out / "on_tarama_v2.parquet").exists():
        shutil.copy(ATLAS, out / "on_tarama_v2.parquet")
    hucreler = era5_grid.kara_hucreleri()
    t0 = time.time()
    with mp.get_context("fork").Pool(paralel, initializer=_kip, initargs=(kip,)) as havuz:
        sonuc = []
        for i, r in enumerate(havuz.imap_unordered(hucre_tara, hucreler, chunksize=4), 1):
            sonuc.append(r)
            if i % 200 == 0:
                print(f"  {i}/{len(hucreler)} ({time.time() - t0:.0f} s)", flush=True)
    df = pd.DataFrame(sonuc).sort_values(["hucre_enlem", "hucre_boylam"]).reset_index(drop=True)
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    hedef = ATLAS if kip == "tam" else out / "on_tarama_v3_altyapisiz.parquet"
    df.to_parquet(hedef, index=False)
    ok = df[df["hata"] == ""]
    print(f"Tamam ({kip}): {len(ok)}/{len(df)} hücre, {time.time() - t0:.0f} s → {hedef}")
    print(df.loc[df["hata"] != "", "hata"].str.split(":").str[0].value_counts().to_string())
    print(ok[~ok["ada"]].nsmallest(10, "basabas_en_iyi")[["il", "ilce", "res_kf", "guven", "sebeke_capex_usd_mw", "basabas_en_iyi"]].to_string())


if __name__ == "__main__":
    main()
