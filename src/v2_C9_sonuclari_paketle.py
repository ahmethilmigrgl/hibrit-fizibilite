"""
v2 Faz C9 — Yöntem sayfası için doğrulama özetleri → results/v2_dogrulama.json (küçük; uygulama yalnız bunu okur).

Kaynaklar: data/atlas/guven_seviyeleri.csv, outputs/v2/A4_ozet.csv (GWA modu × yöntem), outputs/v2C/C0_ezine_kontrol.csv,
outputs/v2B/B5_regresyon.csv, B5_tutarlilik.csv, B5_bes_saha.csv, outputs/v2C/C8_sure.csv (varsa).
Çalıştırma: .venv/bin/python src/v2_C9_sonuclari_paketle.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import pandas as pd

from src.ayarlar import CIKTILAR, KOK


def oku(p: Path, **kw) -> pd.DataFrame | None:
    return pd.read_csv(p, encoding="utf-8-sig", **kw) if p.exists() else None


def main() -> None:
    d = {}
    g = oku(KOK / "data" / "atlas" / "guven_seviyeleri.csv")
    if g is not None:
        d["guven"] = g.round(3).to_dict("records")
    cv = oku(CIKTILAR / "v2" / "A4_ozet.csv", header=[0], index_col=[0, 1, 2])
    if cv is not None:
        cv = cv.reset_index()
        cv.columns = ["_", "gmod", "yontem", *cv.columns[3:]]
        cv = cv[cv["yontem"] == "gwa_olcekli"][["gmod", "rmse", "mutlak_medyan", "mutlak_p90", "ort_hata"]]
        cv["gmod"] = cv["gmod"].map(
            {
                "nokta250": "nokta (250 m)",
                "yerlesim": "türbin yerleşimi 2 km (varsayılan)",
                "turbin_konumu": "gerçek türbin konumları (kâhin)",
            }
        )
        d["cv"] = (
            cv.round(2)
            .rename(
                columns={"gmod": "saha GWA modu", "mutlak_medyan": "medyan |hata|", "mutlak_p90": "P90 |hata|", "ort_hata": "ort. hata"}
            )
            .to_dict("records")
        )
    for ad, p in [
        ("ezine", CIKTILAR / "v2C" / "C0_ezine_kontrol.csv"),
        ("regresyon", CIKTILAR / "v2B" / "B5_regresyon.csv"),
        ("tutarlilik", CIKTILAR / "v2B" / "B5_tutarlilik.csv"),
        ("bes_saha", CIKTILAR / "v2B" / "B5_bes_saha.csv"),
        ("sure", CIKTILAR / "v2C" / "C8_sure.csv"),
    ]:
        x = oku(p)
        if x is not None:
            d[ad] = x.round(2).astype(object).where(x.notna(), None).to_dict("records")
    yol = KOK / "results" / "v2_dogrulama.json"
    yol.write_text(json.dumps(d, ensure_ascii=False, indent=0, default=str), encoding="utf-8")
    print(yol, round(yol.stat().st_size / 1e3, 1), "KB;", list(d))


if __name__ == "__main__":
    main()
