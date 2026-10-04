"""
v2 Faz A3-1 — Türkiye RES'lerinin OpenStreetMap konumlarıyla EPİAŞ santral listesinin eşleştirilmesi (çevrimdışı).

Kaynaklar: OSM Overpass (power=plant, plant:source=wind; ODbL, © OpenStreetMap katkıcıları), EPİAŞ santral listesi
(önbellek; kimlik bilgisi yalnız çevrimdışı). İsimler normalize edilir (RES/rüzgâr/enerji/santrali, Türkçe karakter,
noktalama), difflib benzerlik oranı + ortak anlamlı kelime ile puanlanır.
Sınıflar: otomatik (puan ≥ 0,90 ve tek aday) · kontrol (0,75–0,90 ya da birden çok aday) · eşleşmedi.
Kontrol listesi elle gözden geçirilip data/atlas/eslestirme_manuel.csv'ye (osm_id, epias_id, karar) yazılır.

Çalıştırma: .venv/bin/python src/v2_A3_santral_eslestirme.py
Çıktı: data/atlas/santral_eslestirme.csv, outputs/v2/A3_eslestirme_ozet.csv
"""

import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.ayarlar import CIKTILAR, HAM_VERI, KOK

ATLAS = KOK / "data" / "atlas"
GENEL = {
    "res",
    "ruzgar",
    "ruzgari",
    "enerji",
    "enerjisi",
    "santrali",
    "santral",
    "elektrik",
    "uretim",
    "tesisi",
    "ciftligi",
    "wind",
    "farm",
    "power",
    "plant",
    "ve",
    "as",
    "a",
    "s",
    "ltd",
    "sti",
    "tic",
    "san",
    "es",
    "spp",
}


def normalize(ad: str) -> str:
    ad = (ad if isinstance(ad, str) else "").upper().split("-40W")[0]
    ad = ad.replace("İ", "I").replace("I", "I").lower()
    ad = unicodedata.normalize("NFKD", ad).encode("ascii", "ignore").decode()
    ad = re.sub(r"[^a-z0-9 ]", " ", ad)
    return " ".join(k for k in ad.split() if k not in GENEL)


def kapasite(etiket: str | None) -> float | None:
    if not etiket:
        return None
    m = re.search(r"([\d.,]+)\s*(MW|kW|GW)?", etiket.replace(" ", ""), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    birim = (m.group(2) or "MW").upper()
    return v / 1000 if birim == "KW" else v * 1000 if birim == "GW" else v


def puan(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    oran = SequenceMatcher(None, a, b).ratio()
    ka, kb = set(a.split()), set(b.split())
    kelime = len(ka & kb) / max(len(ka), 1)
    return max(oran, 0.5 * oran + 0.5 * kelime)


def main() -> None:
    osm = json.load(open(HAM_VERI / "osm" / "res_tr_overpass.json"))["elements"]
    o = pd.DataFrame(
        [
            {
                "osm_id": f"{e['type'][0]}{e['id']}",
                "osm_ad": e["tags"].get("name") or e["tags"].get("operator"),
                "enlem": e.get("lat", e.get("center", {}).get("lat")),
                "boylam": e.get("lon", e.get("center", {}).get("lon")),
                "osm_mw": kapasite(e["tags"].get("plant:output:electricity")),
            }
            for e in osm
        ]
    )
    ep = json.load(open(next((HAM_VERI / "epias" / "santral_listesi").glob("*.json"))))
    ep = pd.DataFrame(ep["items"] if isinstance(ep, dict) else ep)
    ep = ep[ep["name"].str.upper().str.contains(r"\bRES\b|RÜZGAR|RUZGAR", regex=True)].copy()
    ep["n"] = ep["name"].map(normalize)
    o["n"] = o["osm_ad"].map(normalize)
    satir = []
    for _, r in o.iterrows():
        p = ep["n"].map(lambda x, ad=r["n"]: puan(ad, x))
        sira = p.sort_values(ascending=False)
        en, iki = sira.iloc[0], sira.iloc[1]
        e0 = ep.loc[sira.index[0]]
        sinif = "eşleşmedi" if en < 0.75 or not r["n"] else ("otomatik" if en >= 0.90 and en - iki >= 0.05 else "kontrol")
        satir.append(
            {
                **r.drop("n").to_dict(),
                "epias_id": int(e0["id"]) if sinif != "eşleşmedi" else None,
                "epias_ad": e0["name"].split("-40W")[0] if sinif != "eşleşmedi" else None,
                "puan": round(en, 3),
                "ikinci_aday": ep.loc[sira.index[1], "name"].split("-40W")[0],
                "ikinci_puan": round(iki, 3),
                "sinif": sinif,
            }
        )
    df = pd.DataFrame(satir)
    man = ATLAS / "eslestirme_manuel.csv"
    if man.exists():  # elle gözden geçirilmiş kontrol kararları: karar = kabul / ret / degistir (epias_id ile)
        m = pd.read_csv(man).set_index("osm_id")
        for oid, k in m.iterrows():
            i = df.index[df["osm_id"] == oid]
            if k["karar"] == "ret":
                df.loc[i, ["sinif", "epias_id", "epias_ad"]] = ["reddedildi", None, None]
            elif k["karar"] in ("kabul", "degistir"):
                if k["karar"] == "degistir":
                    df.loc[i, "epias_id"] = int(k["epias_id"])
                    df.loc[i, "epias_ad"] = ep.set_index("id").loc[int(k["epias_id"]), "name"].split("-40W")[0]
                df.loc[i, "sinif"] = "manuel kabul"
    # Güvenlik: aynı EPİAŞ santraline birden çok OSM kaydı kalırsa yalnız en yüksek puanlı tutulur, diğerleri işaretlenir
    kabul = df["epias_id"].notna()
    sira = df[kabul].sort_values("puan", ascending=False)
    yinelenen = sira.index[sira["epias_id"].duplicated()]
    df.loc[yinelenen, ["sinif", "epias_id", "epias_ad"]] = ["yinelenen", None, None]
    ATLAS.mkdir(parents=True, exist_ok=True)
    df.to_csv(ATLAS / "santral_eslestirme.csv", index=False, encoding="utf-8-sig")
    ozet = df["sinif"].value_counts().rename("santral sayısı")
    (CIKTILAR / "v2").mkdir(parents=True, exist_ok=True)
    ozet.to_csv(CIKTILAR / "v2" / "A3_eslestirme_ozet.csv", encoding="utf-8-sig")
    print(ozet.to_string())
    print("OSM kurulu güç toplamı [MW]:", round(df["osm_mw"].sum()))


if __name__ == "__main__":
    main()
