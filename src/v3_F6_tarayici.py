"""
v3 F6 — Portföy ve Performans izleme sayfalarının gerçek tarayıcıda süre ölçümü ve ekran görüntüleri (Playwright + Chrome,
2 çekirdek benzetimi). Süre bütçeleri: portföy optimizasyonu ≤ 30 s, performans sayfası ≤ 2 s.
Her ekran açık/koyu tema, masaüstü 1366 × 900 ve mobil 390 × 844; yatay taşma v2 C8 ölçütüyle denetlenir.
Çıktılar: docs/img/v3/F_*.png, outputs/v3F/F6_tarayici_sure.csv, outputs/v3F/F6_tasma.csv
Çalıştırma: .venv/bin/python src/v3_F6_tarayici.py [--port 8631]
"""

import importlib.util
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK

IMG = KOK / "docs" / "img" / "v3"


def c8():
    sp = importlib.util.spec_from_file_location("c8", KOK / "src" / "v2_C8_tarayici.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def main() -> None:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8631
    IMG.mkdir(parents=True, exist_ok=True)
    m = c8()
    url = f"http://localhost:{port}"
    sure, tas = [], []

    def kayit(s, ad, tema, gorunum):
        r = s.evaluate(m.TASMA_JS)
        tas.append(
            {
                "ekran": ad,
                "tema": tema,
                "gorunum": gorunum,
                "yatay_tasma": r["scroll"] > r["client"] + 1,
                "tasan_oge": r["adet"],
                "ornek": "; ".join(r["tasan"]),
            }
        )

    p = m.sunucu(port)
    try:
        with sync_playwright() as pw:
            tar = pw.chromium.launch(channel="chrome", headless=True)
            for tema in ("acik", "koyu"):
                for gorunum, boyut in m.GORUNUM.items():
                    ctx = tar.new_context(viewport=boyut, color_scheme="dark" if tema == "koyu" else "light")
                    ctx.add_cookies([{"name": "esik_tema", "value": tema, "url": url}])
                    s = ctx.new_page()
                    # performans izleme
                    t0 = time.time()
                    s.goto(f"{url}/performans")
                    m.bekle_metin(s, "Kontrol kartları", 120)
                    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                    if tema == "acik":
                        sure.append({"olcum": f"performans sayfası ({gorunum})", "sure_s": time.time() - t0})
                    s.wait_for_timeout(1500)
                    kayit(s, "F_performans_harita", tema, gorunum)
                    s.screenshot(path=str(IMG / f"F_performans_harita_{tema}_{gorunum}.png"))
                    s.get_by_text("2. Kontrol kartları", exact=False).first.scroll_into_view_if_needed()
                    s.wait_for_timeout(1500)
                    kayit(s, "F_performans_kart", tema, gorunum)
                    s.screenshot(path=str(IMG / f"F_performans_kart_{tema}_{gorunum}.png"))
                    # portföy: λ = 0,2 ile çözüm süresi (kaydırıcı klavyeyle)
                    t0 = time.time()
                    s.goto(f"{url}/portfoy")
                    m.bekle_metin(s, "Seçilen portföy", 180)
                    if tema == "acik":
                        sure.append({"olcum": f"portföy sayfası, λ = 0 ({gorunum})", "sure_s": time.time() - t0})
                        sl = s.get_by_role("slider").nth(1)
                        sl.focus()
                        t0 = time.time()
                        for _ in range(4):
                            sl.press("ArrowRight")
                        s.wait_for_timeout(500)
                        s.wait_for_timeout(1500)
                        s.get_by_text("Portföy optimize ediliyor", exact=False).first.wait_for(state="hidden", timeout=180000)
                        sure.append({"olcum": f"portföy optimizasyonu, λ = 0,2 ({gorunum})", "sure_s": time.time() - t0})
                    s.get_by_text("Portföy optimize ediliyor", exact=False).first.wait_for(state="hidden", timeout=180000)
                    s.wait_for_timeout(1500)
                    kayit(s, "F_portfoy", tema, gorunum)
                    s.get_by_text("2. Seçilen portföy", exact=False).first.scroll_into_view_if_needed()
                    s.wait_for_timeout(1500)
                    s.screenshot(path=str(IMG / f"F_portfoy_{tema}_{gorunum}.png"))
                    s.get_by_text("4. Değer ayrıştırması", exact=False).first.scroll_into_view_if_needed()
                    s.wait_for_timeout(1500)
                    kayit(s, "F_portfoy_ayristirma", tema, gorunum)
                    s.screenshot(path=str(IMG / f"F_portfoy_ayristirma_{tema}_{gorunum}.png"))
                    ctx.close()
            tar.close()
    finally:
        p.terminate()
    (CIKTILAR / "v3F").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sure).to_csv(CIKTILAR / "v3F" / "F6_tarayici_sure.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    pd.DataFrame(tas).to_csv(CIKTILAR / "v3F" / "F6_tasma.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(sure).round(1).to_string(index=False))
    print(pd.DataFrame(tas).to_string(index=False))


if __name__ == "__main__":
    main()
