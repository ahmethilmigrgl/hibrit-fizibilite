"""
v2 Faz C1 — ERA5 ve PVGIS gridlerinin bütünlük kontrolü.

Her kara hücresi için: dosya var mı, açılıyor mu, saat sayısı (2014–2023: 87.648), başlangıç zamanı, eksik/aralık dışı değer
(v100, v10 0–60 m/s; t2m 220–330 K; sp 50–110 kPa; GES KF 0–1), manifest sha256 eşleşmesi, komşulara göre aykırı ortalama
(hücre ortalama hızı, 8 komşunun medyanından > %40 sapma → işaret, hata değil).
Çıktı: outputs/v2C/C1_grid_butunluk.csv (hücre bazında sorunlar) ve ekrana özet.
Çalıştırma: .venv/bin/python src/v2_C1_grid_butunluk.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import json

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR
from src.kaynaklar import era5_grid, pvgis_grid

SAAT = 87648
ARALIK = {"v100": (0, 6000), "v10": (0, 6000), "t2m": (220 * 50, 330 * 50), "sp": (25000, 55000), "kf": (0, 10000)}


def manifest(klasor: Path) -> dict:
    p = klasor / "manifest.json"
    return {d["dosya"]: d["sha256"] for d in json.loads(p.read_text())["dosyalar"]} if p.exists() else {}


def kontrol(ad: str, klasor: Path, dosya_adi, alanlar: list[str]) -> pd.DataFrame:
    man = manifest(klasor)
    satir = []
    for e, b in era5_grid.kara_hucreleri():
        f = klasor / dosya_adi(e, b)
        r = {"grid": ad, "hucre": f.name, "enlem": e, "boylam": b, "sorun": ""}
        if not f.exists():
            r["sorun"] = "eksik"
            satir.append(r)
            continue
        try:
            z = np.load(f)
            sorun = []
            for a in alanlar:
                x = z[a]
                if len(x) != SAAT:
                    sorun.append(f"{a} uzunluk {len(x)}")
                alt, ust = ARALIK[a]
                if ((x < alt) | (x > ust)).any():
                    sorun.append(f"{a} aralık dışı {int(((x < alt) | (x > ust)).sum())}")
            if str(z["bas"]) != "2014-01-01 00:00:00":
                sorun.append(f"başlangıç {z['bas']}")
            r["ortalama"] = float(z[alanlar[0]].mean()) / (100 if ad == "era5" else 1e4)
            if man and man.get(f.name) != hashlib.sha256(f.read_bytes()).hexdigest():
                sorun.append("sha256 uyuşmuyor" if f.name in man else "manifestte yok")
            r["sorun"] = "; ".join(sorun)
        except Exception as ex:  # bozuk dosya
            r["sorun"] = f"açılamadı: {type(ex).__name__}"
        satir.append(r)
    df = pd.DataFrame(satir)
    # komşu aykırılığı (işaret)
    ort = df.set_index(["enlem", "boylam"])["ortalama"].to_dict() if "ortalama" in df else {}
    isaret = []
    for r in df.itertuples():
        k = [ort.get((r.enlem + de, r.boylam + db)) for de in (-0.25, 0, 0.25) for db in (-0.25, 0, 0.25) if (de, db) != (0, 0)]
        k = [x for x in k if x is not None and np.isfinite(x)]
        v = getattr(r, "ortalama", np.nan)
        isaret.append(bool(len(k) >= 3 and np.isfinite(v) and abs(v / np.median(k) - 1) > 0.4))
    df["komsu_aykiri"] = isaret
    return df


def main() -> None:
    sonuc = pd.concat(
        [
            kontrol("era5", era5_grid.KLASOR, era5_grid.dosya_adi, ["v100", "v10", "t2m", "sp"]),
            kontrol("pvgis", pvgis_grid.KLASOR, pvgis_grid.dosya_adi, ["kf"]),
        ]
    )
    (CIKTILAR / "v2C").mkdir(parents=True, exist_ok=True)
    sonuc[(sonuc["sorun"] != "") | sonuc["komsu_aykiri"]].to_csv(
        CIKTILAR / "v2C" / "C1_grid_butunluk.csv", index=False, encoding="utf-8-sig"
    )
    for g, d in sonuc.groupby("grid"):
        print(
            f"{g}: {len(d)} hücre beklenen; eksik {int((d['sorun'] == 'eksik').sum())}; "
            f"bozuk/aralık dışı {int(((d['sorun'] != '') & (d['sorun'] != 'eksik')).sum())}; komşuya göre aykırı {int(d['komsu_aykiri'].sum())}; "
            f"ortalama {d['ortalama'].mean():.3f} (min {d['ortalama'].min():.3f}, maks {d['ortalama'].max():.3f})"
        )
        sorunlu = d[d["sorun"] != ""]
        if len(sorunlu):
            print(sorunlu[["hucre", "sorun"]].head(10).to_string(index=False))
        ayk = d[d["komsu_aykiri"]]
        if len(ayk):
            print("  aykırı:", ", ".join(f"{h} ({o:.2f})" for h, o in zip(ayk["hucre"], ayk["ortalama"], strict=True)))


if __name__ == "__main__":
    main()
