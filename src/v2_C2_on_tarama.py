"""
v2 Faz C2 — Türkiye ön tarama haritası (çevrimdışı; yalnız yerel ERA5 + PVGIS gridleri, atlas ve piyasa paketi).

Her kara hücresi (0,25°, 1.464) için hücrenin temsilî kara noktasında (merkeze en yakın kara pikseli) varsayılan kullanıcı
varsayımlarıyla (50 MW bağlantı, baz fiyat, türbin yerleşimi config varsayılanı) hızlı taramanın deterministik kısmı:
    RES ve GES KF'si, güven seviyesi ve komşu santraller, RES ve GES başabaş fiyatı, standart tasarımların NPV'si,
    en iyi standart tasarım (baz fiyatta en yüksek NPV) ve onun başabaş fiyatı.
Temsilî gün MILP'i ve Monte Carlo yok (harita bir ön elemedir).

Çıktı: data/atlas/on_tarama.parquet (küçük; uygulamanın açılış haritası) + outputs/v2C/C2_on_tarama_ozet.csv
Çalıştırma: .venv/bin/python src/v2_C2_on_tarama.py [--paralel 6]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK
from src.kaynaklar import era5_grid, pvgis_grid

CIKTI = KOK / "data" / "atlas" / "on_tarama.parquet"


def hucre_tara(h: tuple[float, float]) -> dict:
    from src.finans.metrikler import basabas_fiyat
    from src.motor.hizli import _fiyat, standart_tasarimlar, uretim_ozeti
    from src.motor.ortak import hazirla
    from src.motor.varsayimlar import KullaniciVarsayimlari

    e, b = h
    ne, nb = pvgis_grid.temsil_noktasi(e, b)
    kayit = {"hucre_enlem": e, "hucre_boylam": b, "enlem": round(ne, 4), "boylam": round(nb, 4)}
    kv = KullaniciVarsayimlari()
    try:
        hz = hazirla({"ad": f"hucre_{e:.2f}_{b:.2f}", "enlem": ne, "boylam": nb}, kv, profil_onbellegi=False)
        uo, _, _ = uretim_ozeti(hz)
        f, _ = _fiyat(hz, kv)
        tas = standart_tasarimlar(hz, f)
        en_iyi = max(tas, key=lambda x: x["npv_musd"])

        def bb(ad: str) -> float:
            k = next((x["_k"] for x in tas if x["tasarim"] == ad), None)
            try:
                return float(basabas_fiyat(k, hz.cfg, hz.u, hz.v, kv.kanibalizasyon)) if k else np.nan
            except ValueError:
                return np.nan

        kal = hz.bilgi["kalibrasyon"]
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
                "hata": "",
            }
        )
    except Exception as ex:  # hücre atlanır, nedeni kaydedilir
        kayit["hata"] = f"{type(ex).__name__}: {str(ex)[:120]}"
    return kayit


def main() -> None:
    paralel = int(sys.argv[sys.argv.index("--paralel") + 1]) if "--paralel" in sys.argv else 6
    hucreler = era5_grid.kara_hucreleri()
    t0 = time.time()
    with mp.get_context("fork").Pool(paralel) as havuz:
        sonuc = []
        for i, r in enumerate(havuz.imap_unordered(hucre_tara, hucreler, chunksize=4), 1):
            sonuc.append(r)
            if i % 100 == 0:
                print(f"  {i}/{len(hucreler)} ({time.time() - t0:.0f} s)", flush=True)
    df = pd.DataFrame(sonuc).sort_values(["hucre_enlem", "hucre_boylam"]).reset_index(drop=True)
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    df.to_parquet(CIKTI, index=False)
    ok = df[df["hata"] == ""]
    (CIKTILAR / "v2C").mkdir(parents=True, exist_ok=True)
    ozet = ok.describe(percentiles=[0.1, 0.5, 0.9]).T
    ozet.to_csv(CIKTILAR / "v2C" / "C2_on_tarama_ozet.csv", encoding="utf-8-sig", float_format="%.3f")
    print(f"Tamam: {len(ok)}/{len(df)} hücre, {time.time() - t0:.0f} s, {CIKTI.stat().st_size / 1e3:.0f} KB")
    print(df.loc[df["hata"] != "", "hata"].str.split(":").str[0].value_counts().to_string())
    print(
        ok.nsmallest(10, "basabas_en_iyi")[
            ["il", "ilce", "enlem", "boylam", "res_kf", "guven", "en_iyi_tasarim", "basabas_en_iyi"]
        ].to_string()
    )


if __name__ == "__main__":
    main()
