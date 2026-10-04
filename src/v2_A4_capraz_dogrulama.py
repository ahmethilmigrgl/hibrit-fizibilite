"""
v2 Faz A4 — Kalibrasyon aktarım kuralının "birini dışarıda bırak" çapraz doğrulaması ve güven seviyeleri.

Atlasın her kullanılabilir santrali sırayla yokmuş gibi, komşularından ve/veya GWA'dan tahmin edilir; tahmini matrisle
santralin kendi ERA5 hücresinden (vekil türbin) üretilen KF, gözlenen KF ile karşılaştırılır.
Metrikler: ortalama KF hatası (puan), gün içi profil RMSE (puan), saatlik korelasyon.
Güven seviyesi (kuralın kendisinden: yüksek ≤ 30 km benzer santral, orta ≤ 80 km, düşük = yalnız GWA) başına tipik hata
→ data/atlas/guven_seviyeleri.csv (Monte Carlo'da RES model belirsizliği olarak kullanılacak).

Çalıştırma: .venv/bin/python src/v2_A4_capraz_dogrulama.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.atlas import aktarim
from src.atlas import kalibrasyon as K
from src.ayarlar import CIKTILAR, KOK, config_oku
from src.kaynaklar import era5_cds
from src.piyasa import veri
from src.piyasa.epias import EpiasIstemcisi
from src.uretim import kalibrasyon as kal

YONTEMLER = ["yok", "gwa", "dogrudan", "gwa_olcekli"]


def main() -> None:
    cfg = config_oku()
    cr = cfg["uretim"]["ruzgar"]
    df, _ = aktarim.atlas()
    ist = EpiasIstemcisi()
    satir = []
    for r in df.itertuples():
        u = veri.uretim_cek(ist, "2014-01-01", "2026-09-30", santral_id=int(r.epias_id))
        era5 = era5_cds.indir(r.enlem, r.boylam)
        mw = u["toplam"].loc[:"2025-12-31 23:00"].astype(float)
        m = kal.referans_model(era5, cr, K.VEKIL_TURBIN, K.VEKIL_GOBEK)
        g = K.V1.degisken_kapasiteli_kf(mw).reindex(m.indeks).clip(upper=1.05).to_numpy()
        ok = ~np.isnan(g)
        gun_g = pd.Series(g[ok]).groupby(m.saat[ok]).mean()
        tan = {"rakim_m": r.rakim_m, "karmasiklik": r.karmasiklik, "kiyi_km": r.kiyi_km}
        komsu = aktarim.komsular(r.enlem, r.boylam, tan, cfg, haric=int(r.epias_id))
        for y in YONTEMLER:
            Km, bilgi = aktarim.tahmin(r.enlem, r.boylam, r.era5_100m, y, cfg, haric=int(r.epias_id), tan=tan)
            kf = m.kf_matris(Km)
            gun_m = pd.Series(kf[ok]).groupby(m.saat[ok]).mean()
            satir.append(
                {
                    "epias_id": r.epias_id,
                    "ad": r.ad,
                    "yontem": y,
                    "guven": bilgi["guven"],
                    "en_yakin_benzer_km": float(komsu["mesafe_km"].iloc[0]) if len(komsu) else np.nan,
                    "komsu_sayisi": len(komsu),
                    "kiyi": r.kiyi_km < 20,
                    "karmasiklik": r.karmasiklik,
                    "rakim_m": r.rakim_m,
                    "gozlenen_kf": float(g[ok].mean()),
                    "kf_hatasi_puan": 100 * float(kf[ok].mean() - g[ok].mean()),
                    "gunici_rmse_puan": 100 * float(np.sqrt(((gun_m - gun_g) ** 2).mean())),
                    "korelasyon": float(np.corrcoef(kf[ok], g[ok])[0, 1]),
                }
            )
    cv = pd.DataFrame(satir)
    cikti = CIKTILAR / "v2"
    cikti.mkdir(parents=True, exist_ok=True)
    cv.to_csv(cikti / "A4_capraz_dogrulama.csv", index=False, encoding="utf-8-sig", float_format="%.4f")

    def ozet(x):
        e = x["kf_hatasi_puan"]
        return pd.Series(
            {
                "santral": len(x),
                "ort_hata": e.mean(),
                "mutlak_medyan": e.abs().median(),
                "rmse": np.sqrt((e**2).mean()),
                "mutlak_p90": e.abs().quantile(0.9),
                "gunici_rmse_medyan": x["gunici_rmse_puan"].median(),
                "korelasyon_medyan": x["korelasyon"].median(),
            }
        )

    pd.set_option("display.width", 220)
    yontem = cv.groupby("yontem").apply(ozet, include_groups=False).loc[YONTEMLER]
    print("Yöntem karşılaştırması (tüm santraller):\n", yontem.round(2).to_string())
    kural = cv[cv["yontem"] == "gwa_olcekli"].copy()
    guven = kural.groupby("guven").apply(ozet, include_groups=False).reindex(["yüksek", "orta", "düşük"])
    gozlenen = kural["gozlenen_kf"].mean()
    guven["goreli_rmse_%"] = 100 * guven["rmse"] / (100 * gozlenen)
    print("\nKural (gwa_olcekli) — güven seviyeleri:\n", guven.round(2).to_string())
    kural["mesafe_sinifi"] = pd.cut(kural["en_yakin_benzer_km"], [0, 15, 30, 50, 80], labels=["0–15", "15–30", "30–50", "50–80"])
    kural["arazi"] = pd.qcut(kural["karmasiklik"], 3, labels=["düşük", "orta", "yüksek"])
    mesafe = kural.groupby("mesafe_sinifi", observed=True).apply(ozet, include_groups=False)
    arazi = kural.groupby("arazi", observed=True).apply(ozet, include_groups=False)
    gwa_arazi = (
        cv[cv["yontem"] == "gwa"].assign(arazi=kural["arazi"].to_numpy()).groupby("arazi", observed=True).apply(ozet, include_groups=False)
    )
    print("\nMesafeye göre (kural):\n", mesafe.round(2).to_string())
    print("\nArazi karmaşıklığına göre (kural):\n", arazi.round(2).to_string())
    print("\nArazi karmaşıklığına göre (yalnız GWA):\n", gwa_arazi.round(2).to_string())
    pd.concat({"yontem": yontem, "guven": guven, "mesafe": mesafe, "arazi_kural": arazi, "arazi_gwa": gwa_arazi}).to_csv(
        cikti / "A4_ozet.csv", encoding="utf-8-sig", float_format="%.3f"
    )
    guven[["santral", "rmse", "mutlak_medyan", "mutlak_p90", "goreli_rmse_%", "gunici_rmse_medyan"]].to_csv(
        KOK / "data" / "atlas" / "guven_seviyeleri.csv", encoding="utf-8-sig", float_format="%.3f"
    )


if __name__ == "__main__":
    main()
