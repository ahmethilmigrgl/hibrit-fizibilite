"""
v3 F ön adım Ö1 — v1 nihai baz vakasında sigorta + arazi kirası çift sayımının etkisi.

v1 RES O&M'i 35.000 $/MW-yıl (Lazard LCOE+ 2025 "her şey dahil" sabit O&M bandı) iken finansal model ayrıca RES arazi kirası
(1.500 $/MW-yıl) ve RES CAPEX'i üzerinden sigorta (%0,35/yıl) ekliyordu. Düzeltilmiş senaryo: bu iki RES kalemi düşülür
(batarya, şebeke ve GES sigortası kalır). v1 kodu ve çıktıları değişmez: düzeltme ortam değişkeniyle (V1_CIFT_SAYIM=1)
açılır, Aşama 7 Monte Carlo'su (src/07_gelir_yapilari.py, yalnız G* seçenekleri, aynı tohum) ayrı klasöre yeniden koşar ve
baz vaka metrikleri src/07_baz_vaka.py'nin fonksiyonlarıyla hesaplanır.

Çıktılar: outputs/07/v1_cift_sayim/ (Monte Carlo), outputs/v3F/O1_v1_duzeltme.csv, O1_v1_duzeltme.json,
          outputs/v3F/O1_kalem_kontrol.csv (deterministik kalem kontrolü)
Çalıştırma: .venv/bin/python src/v3_O1_v1_duzeltme.py [--mc-atla]
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.ayarlar import CIKTILAR, KOK, config_oku, deger

HEDEF = CIKTILAR / "07" / "v1_cift_sayim"
CIKTI = CIKTILAR / "v3F"


def modul(ad: str, dosya: str):
    sp = importlib.util.spec_from_file_location(ad, KOK / "src" / dosya)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def kalem_kontrol(cfg: dict) -> pd.DataFrame:
    """Baz vaka tasarımında yıllık çift sayılan tutar ve bugünkü değeri (vergi kalkanı öncesi/sonrası, COD 2028)."""
    t = cfg["teknoloji"]
    b = deger(cfg["nihai_baz_vaka"])["tasarim"]
    res_mw = b["res_mw"]
    arazi = deger(t["res"]["arazi"]) * res_mw
    sigorta = deger(t["ortak"]["sigorta"]) * deger(t["res"]["capex"]) * res_mw
    r = deger(cfg["finans"]["wacc_reel"])
    vergi = deger(cfg["finans"]["kurumlar_vergisi"])
    N = deger(cfg["proje"]["omur"])
    ins = deger(cfg["proje"]["insaat_suresi"])
    df = (1 + r) ** -(ins + np.arange(1, N + 1))
    pv = df.sum()
    return pd.DataFrame(
        [
            {
                "kalem": "RES arazi kirası",
                "yillik_usd": arazi,
                "bd_vergi_oncesi_musd": arazi * pv / 1e6,
                "bd_vergi_sonrasi_musd": arazi * pv * (1 - vergi) / 1e6,
            },
            {
                "kalem": "RES sigortası (%0,35 × RES CAPEX)",
                "yillik_usd": sigorta,
                "bd_vergi_oncesi_musd": sigorta * pv / 1e6,
                "bd_vergi_sonrasi_musd": sigorta * pv * (1 - vergi) / 1e6,
            },
            {
                "kalem": "Toplam",
                "yillik_usd": arazi + sigorta,
                "bd_vergi_oncesi_musd": (arazi + sigorta) * pv / 1e6,
                "bd_vergi_sonrasi_musd": (arazi + sigorta) * pv * (1 - vergi) / 1e6,
            },
        ]
    )


def metrikler(bv, z, k: float, prim: float) -> dict:
    out = {}
    for anahtar, (kod, ad) in bv.YAPILAR.items():
        x = bv.dagilim(z, kod, k)
        out[anahtar] = {"ad": ad, **{kk: float(v) for kk, v in bv.metrik(x, prim).items()}}
    return out


def main() -> None:
    CIKTI.mkdir(parents=True, exist_ok=True)
    cfg = config_oku()
    if "--mc-atla" not in sys.argv:
        os.environ["V1_CIFT_SAYIM"] = "1"
        os.environ["SADECE_G"] = "1"
        gy7 = modul("gy7", "07_gelir_yapilari.py")
        gy7.CIKTI = HEDEF
        HEDEF.mkdir(parents=True, exist_ok=True)
        gy7.main()
        os.environ.pop("V1_CIFT_SAYIM")
    bv = modul("bv", "07_baz_vaka.py")
    # Baz vaka betiğinin tamamı (bilgi değeri, DD bütçesi) düzeltilmiş dağılımla: girdiler kopyalanır, results/ yerine HEDEF/results
    import shutil

    for f in ("takvim_ozet.csv", "takvim_ozet_duzeltme_oncesi.csv", "takvim_cod_ornekleri.npz"):
        shutil.copy(CIKTILAR / "07" / f, HEDEF / f)
    (HEDEF / "ortak_surucu_kapali").mkdir(exist_ok=True)
    shutil.copy(
        CIKTILAR / "07" / "ortak_surucu_kapali" / "gelir_yapilari_npv_erteleme.npz",
        HEDEF / "ortak_surucu_kapali" / "gelir_yapilari_npv_erteleme.npz",
    )
    bv.CIKTI, bv.KOK = HEDEF, HEDEF
    bv.main()
    k, cod = bv.gecikme(CIKTILAR / "07" / "takvim_ozet.csv")
    prim = float(deger(cfg["nihai_baz_vaka"])["edinim_primi_musd"])
    once = metrikler(bv, np.load(CIKTILAR / "07" / "gelir_yapilari_npv_erteleme.npz"), k, prim)
    sonra = metrikler(bv, np.load(HEDEF / "gelir_yapilari_npv_erteleme.npz"), k, prim)
    satir = []
    for a in once:
        for kip, m in (("v1 (çift sayımlı)", once[a]), ("düzeltilmiş", sonra[a])):
            satir.append({"gelir_yapisi": a, "senaryo": m["ad"], "kip": kip, **{kk: v for kk, v in m.items() if kk != "ad"}})
    d = pd.DataFrame(satir)
    d.to_csv(CIKTI / "O1_v1_duzeltme.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    kk = kalem_kontrol(cfg)
    kk.to_csv(CIKTI / "O1_kalem_kontrol.csv", index=False, encoding="utf-8-sig", float_format="%.3f")
    baz = deger(cfg["nihai_baz_vaka"])["gelir_yapisi"]
    e1 = sonra[baz]["Beklenen NPV [M USD]"]
    oz = {
        "baz_gelir_yapisi": baz,
        "cod": cod,
        "once": once[baz],
        "sonra": sonra[baz],
        "fark_enpv_musd": e1 - once[baz]["Beklenen NPV [M USD]"],
        "karar_once": "a" if once[baz]["Beklenen NPV [M USD]"] > 0 else "b",
        "karar_sonra": "a" if e1 > 0 else "b",
        "karar_kurali": "baz vakada E[NPV] > 0 ve azami prim > 0 ise (a) durum tespiti + teklif, aksi halde (b) rafa kaldır (docs/07 §Güncelleme 3)",
        "kalem_kontrol": kk.to_dict(orient="records"),
        "durum_tespiti_once": pd.read_csv(CIKTILAR / "07" / "durum_tespiti_bilgi_degeri.csv", index_col=0)["değer"].to_dict(),
        "durum_tespiti_sonra": pd.read_csv(HEDEF / "durum_tespiti_bilgi_degeri.csv", index_col=0)["değer"].to_dict(),
    }
    (CIKTI / "O1_v1_duzeltme.json").write_text(json.dumps(oz, ensure_ascii=False, indent=1, default=float))
    print(d.round(3).to_string(index=False))
    print(kk.round(3).to_string(index=False))
    print(json.dumps({k_: v for k_, v in oz.items() if k_ != "kalem_kontrol"}, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
