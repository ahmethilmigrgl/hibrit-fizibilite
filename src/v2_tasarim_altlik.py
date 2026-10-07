"""
Arayüz tasarımı — karo gerektirmeyen sade harita altlığı (çevrimdışı bir kez çalıştırılır).

Ön tarama haritası varsayılan olarak üçüncü taraf karo sunucusu kullanmaz: il sınırları (geoBoundaries ADM1, sadeleştirilmiş)
ve bölge kıyı çizgileri (Natural Earth 1:10m, Türkiye çevresine kırpılmış) uygulamanın kendi renkleriyle çizilir. Böylece
harita açık/koyu temaya uyar, API anahtarı ya da karo kullanım politikası gerektirmez (CARTO karoları artık anahtar istiyor;
OSM karoları yalnız isteğe bağlı "ayrıntılı" katman).

Girdi: data/raw/sinirlar/tr_ADM1.geojson, data/raw/natural_earth/ne_10m_coastline.geojson
Çıktı: data/atlas/altlik_tr.geojson (lisans: il sınırları CC BY-SA 2.0 geoBoundaries/OSM; kıyılar Natural Earth, kamu malı)
Çalıştırma: .venv/bin/python src/v2_tasarim_altlik.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from shapely.geometry import box, mapping, shape
from shapely.ops import linemerge, unary_union

from src.ayarlar import KOK

TOLERANS = 0.008  # derece (~800 m): 0,25° hücre ızgarası ve il ölçeği için yeterli
KUTU = box(24.5, 34.3, 45.8, 43.2)


def main() -> None:
    il = json.loads((KOK / "data" / "raw" / "sinirlar" / "tr_ADM1.geojson").read_text())
    kiyi = json.loads((KOK / "data" / "raw" / "natural_earth" / "ne_10m_coastline.geojson").read_text())
    # Boyut için: kara dolgusu tek ülke çokgeni, il sınırları ortak kenarları bir kez çizen çizgiler (her yeniden çalıştırmada
    # haritayla tarayıcıya gönderilir)
    iller = [shape(f["geometry"]).buffer(0) for f in il["features"]]
    ulke = unary_union(iller)
    sinirlar = linemerge(unary_union([g.boundary for g in iller]))
    oz = [
        {"type": "Feature", "properties": {"tur": "ulke"}, "geometry": mapping(ulke.simplify(TOLERANS, preserve_topology=True))},
        {"type": "Feature", "properties": {"tur": "il"}, "geometry": mapping(sinirlar.simplify(TOLERANS, preserve_topology=False))},
    ]
    for f in kiyi["features"]:
        g = shape(f["geometry"])
        if not g.intersects(KUTU):
            continue
        g = g.intersection(KUTU).simplify(1.5 * TOLERANS, preserve_topology=False)  # komşu kıyılar: yalnız bağlam
        if g.is_empty or g.length < 0.05:
            continue
        oz.append({"type": "Feature", "properties": {"tur": "kiyi"}, "geometry": mapping(g)})

    def yuvarla(o):
        if isinstance(o, float):
            return round(o, 3)  # ~100 m
        if isinstance(o, (list, tuple)):
            return [yuvarla(x) for x in o]
        if isinstance(o, dict):
            return {k: yuvarla(v) for k, v in o.items()}
        return o

    cikti = KOK / "data" / "atlas" / "altlik_tr.geojson"
    cikti.write_text(json.dumps(yuvarla({"type": "FeatureCollection", "features": oz}), ensure_ascii=False, separators=(",", ":")))
    print(f"{cikti.name}: {len(oz)} öğe, {cikti.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
