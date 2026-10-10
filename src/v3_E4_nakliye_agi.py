"""
v3 E4 — Ağır nakliye ağı ve kaynaklardan en kısa rotalar (çevrimdışı).

Girdi: data/raw/osm_cikti/yollar.parquet (OSM), data/grid/egim_tr (rakım), data/atlas/tedarik_kaynaklari.csv.
Ağ: otoyol/devlet/il yolu (+ link) ve ikincil yol (+ link; maliyet × kosullu_yol_ceza). Yollar paylaşılan düğümlerde
bölünür (kavşaklar), kenar uzunluğu büyük daire mesafesi toplamı. Eğim: 250 m rakımdan ≥ 200 m'lik ardışık kesitlerin
eğimi %10'u aşarsa kenar × yokus_ceza (TAHMİN; kanat römorkları). En büyük bağlı bileşen tutulur.
Her doğrulanmış kaynak için Dijkstra (scipy.sparse.csgraph) → etkin mesafe ve öncül dizisi.
Çıktılar: data/grid/lojistik_tr/v1/ag.npz (düğüm koordinatları, mesafe [kaynak × düğüm], öncül), outputs/v3E/E4_ag_ozet.json
Çalıştırma: .venv/bin/python src/v3_E4_nakliye_agi.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from src.ayarlar import CIKTILAR, HAM_VERI, KOK, config_oku, deger
from src.cbs import katmanlar

KLASOR = KOK / "data" / "grid" / "lojistik_tr" / "v1"


def hav(e1, b1, e2, b2):
    p = np.pi / 180
    a = np.sin((e2 - e1) * p / 2) ** 2 + np.cos(e1 * p) * np.cos(e2 * p) * np.sin((b2 - b1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def main() -> None:
    t0 = time.time()
    cfg = config_oku()
    c = deger(cfg["v3"]["cbs"])
    siniflar = set(c["agir_yol_siniflari"]) | set(c["kosullu_yol_siniflari"])
    y = pd.read_parquet(HAM_VERI / "osm_cikti" / "yollar.parquet")
    y = y[y["sinif"].isin(siniflar)].reset_index(drop=True)
    # paylaşılan düğümler: birden çok yolda geçen ya da yol ucu olan düğümler kavşaktır
    say: dict[int, int] = {}
    for d in y["dugum"]:
        for n in d:
            say[n] = say.get(n, 0) + 1
        say[d[0]] = say.get(d[0], 0) + 1
        say[d[-1]] = say.get(d[-1], 0) + 1
    kod: dict[int, int] = {}
    e_lat, e_lon = [], []
    u, v, w_km, w_eff = [], [], [], []
    for r in y.itertuples():
        d, E, B = list(r.dugum), np.asarray(r.enlem), np.asarray(r.boylam)
        ceza = c["kosullu_yol_ceza"] if r.sinif in c["kosullu_yol_siniflari"] else 1.0
        seg = hav(E[:-1], B[:-1], E[1:], B[1:])
        z = katmanlar.degerler(E, B)
        rak = z["rakim"] if z is not None else np.zeros(len(E))
        bas = 0
        for k in range(1, len(d)):
            if say[d[k]] >= 2 or k == len(d) - 1:
                km = float(seg[bas:k].sum())
                if km > 0:
                    yokus = 1.0
                    if km >= 0.2 and np.isfinite(rak[bas]) and np.isfinite(rak[k]):
                        if abs(rak[k] - rak[bas]) / (km * 1000) > c["yokus_ceza"]["esik"]:
                            yokus = c["yokus_ceza"]["carpan"]
                    for n, e_, b_ in ((d[bas], E[bas], B[bas]), (d[k], E[k], B[k])):
                        if n not in kod:
                            kod[n] = len(e_lat)
                            e_lat.append(e_)
                            e_lon.append(b_)
                    u.append(kod[d[bas]])
                    v.append(kod[d[k]])
                    w_km.append(km)
                    w_eff.append(km * ceza * yokus)
                bas = k
    n = len(e_lat)
    G = coo_matrix((w_eff + w_eff, (u + v, v + u)), shape=(n, n)).tocsr()
    nc, lab = connected_components(G, directed=False)
    ana = np.argmax(np.bincount(lab))
    tut = np.where(lab == ana)[0]
    yeni = -np.ones(n, int)
    yeni[tut] = np.arange(len(tut))
    G = G[tut][:, tut]
    lat, lon = np.asarray(e_lat)[tut], np.asarray(e_lon)[tut]
    print(f"ağ: {n} düğüm, {len(u)} kenar, {nc} bileşen; ana bileşen {len(tut)} düğüm ({time.time() - t0:.0f} s)", flush=True)
    K = pd.read_csv(KOK / "data" / "atlas" / "tedarik_kaynaklari.csv")
    K = K[K["dogrulandi"]].reset_index(drop=True)
    agac = cKDTree(np.c_[lat, lon * np.cos(np.radians(39.0))])
    dd, idx = agac.query(np.c_[K["enlem"], K["boylam"] * np.cos(np.radians(39.0))])
    D, P = dijkstra(G, directed=False, indices=idx, return_predecessors=True)
    son = dd * 111.32 * deger(cfg["v3"]["lojistik"])["tasima"]["ag_disi_carpan"]
    D = D + son[:, None]
    KLASOR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        KLASOR / "ag.npz",
        enlem=lat.astype(np.float32),
        boylam=lon.astype(np.float32),
        mesafe=np.where(np.isfinite(D), D, 1e5).astype(np.float32),
        oncul=np.where(P < 0, -1, P).astype(np.int32),
        kaynak_ad=np.array(K["ad"].tolist()),
    )
    oz = {
        "dugum": int(len(tut)),
        "kenar": int(G.nnz // 2),
        "toplam_km": float(np.sum(w_km)),
        "kaynak": K["ad"].tolist(),
        "kaynak_aga_km": son.round(2).tolist(),
        "sure_s": time.time() - t0,
    }
    (CIKTILAR / "v3E").mkdir(parents=True, exist_ok=True)
    (CIKTILAR / "v3E" / "E4_ag_ozet.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1))
    print(json.dumps(oz, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
