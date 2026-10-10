"""
v3 E6 — Faz E arayüzünün gerçek tarayıcıda ölçümü ve ekran görüntüleri (Playwright + yüklü Chrome, 2 çekirdek benzetimi).

• Açılış süresi (soğuk/sıcak; altyapı katmanları kapalıyken) — v2 C8 ile aynı ölçüt (outputs/v2C/C8_sure.csv ile karşılaştırılır).
• Altyapı katmanları açıkken harita (trafo, hat, ağır yol, tedarik, koruma, göç) ve saha kartı (bağlantı, lojistik, uyarılar).
• Tam analiz "Lojistik ve bağlantı" bölümü (Ezine; motor önbelleği).
• "Çok kriterli saha seçimi" sayfası.
Her ekran açık/koyu tema, masaüstü 1366 × 900 ve mobil 390 × 844; yatay taşma v2 C8 ölçütüyle denetlenir.
Çıktılar: docs/img/v3/E_*.png, outputs/v3E/E6_tarayici_sure.csv, outputs/v3E/E6_tasma.csv
Çalıştırma: .venv/bin/python src/v3_E6_tarayici.py [--port 8621]
"""

import importlib.util
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK
from src.motor import KullaniciVarsayimlari, analiz_et

IMG = KOK / "docs" / "img" / "v3"
E, B = 39.79, 26.33
KATMAN_ADLARI = ["Trafo merkezleri (≥154 kV)", "Ağır nakliye yolları", "Limanlar ve üreticiler", "Göç koridorları (yaklaşık)"]


def c8():
    sp = importlib.util.spec_from_file_location("c8", KOK / "src" / "v2_C8_tarayici.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def main() -> None:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8621
    IMG.mkdir(parents=True, exist_ok=True)
    analiz_et({"ad": "Çanakkale-Ezine", "enlem": E, "boylam": B}, "tam", KullaniciVarsayimlari())  # önbelleğe al
    m = c8()
    url = f"http://localhost:{port}"
    sure, tas = [], []

    def kayit_tasma(s, ad: str, tema: str, gorunum: str) -> None:
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
                    t0 = time.time()
                    s.goto(url)
                    m.bekle_metin(s, "Türkiye hibrit", 120)
                    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                    if tema == "acik":
                        sure.append(
                            {"olcum": f"açılış ({'soğuk' if gorunum == 'masaustu' else 'ılık'}, {gorunum})", "sure_s": time.time() - t0}
                        )
                        t0 = time.time()
                        s.reload()
                        m.bekle_metin(s, "Türkiye hibrit", 120)
                        s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                        sure.append({"olcum": f"açılış (sıcak, yeniden yükleme, {gorunum})", "sure_s": time.time() - t0})
                    # altyapı katmanları + saha kartı
                    s.goto(f"{url}/?enlem={E:.3f}&boylam={B:.3f}")
                    m.bekle_metin(s, "GWA 100 m (nokta)", 120)
                    t0 = time.time()
                    for ad in KATMAN_ADLARI:
                        s.get_by_role("button", name=ad).first.click()
                        s.wait_for_timeout(600)
                    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                    s.wait_for_timeout(2500)
                    if tema == "acik":
                        sure.append({"olcum": f"4 altyapı katmanı açma ({gorunum})", "sure_s": time.time() - t0})
                    s.frame_locator("iframe").first.locator(".leaflet-container").scroll_into_view_if_needed()
                    kayit_tasma(s, "E_altyapi_harita", tema, gorunum)
                    s.screenshot(path=str(IMG / f"E_altyapi_harita_{tema}_{gorunum}.png"))
                    k = s.get_by_text("Bağlantı maliyeti", exact=False).first
                    k.scroll_into_view_if_needed()
                    s.wait_for_timeout(800)
                    kayit_tasma(s, "E_saha_karti", tema, gorunum)
                    s.screenshot(path=str(IMG / f"E_saha_karti_{tema}_{gorunum}.png"))
                    # tam analiz: lojistik ve bağlantı
                    s.goto(f"{url}/?enlem={E:.3f}&boylam={B:.3f}&mod=tam")
                    m.bekle_metin(s, "Öneri:", 300)
                    h = s.locator(".esik-bolum h3", has_text="Lojistik ve bağlantı").first
                    h.wait_for(state="visible", timeout=60000)
                    h.scroll_into_view_if_needed()
                    s.wait_for_timeout(3000)
                    kayit_tasma(s, "E_lojistik", tema, gorunum)
                    s.screenshot(path=str(IMG / f"E_lojistik_{tema}_{gorunum}.png"))
                    # çok kriterli sayfa
                    t0 = time.time()
                    s.goto(f"{url}/cok-kriterli")
                    m.bekle_metin(s, "Tutarlılık oranı", 120)
                    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                    if tema == "acik":
                        sure.append({"olcum": f"çok kriterli sayfa ({gorunum})", "sure_s": time.time() - t0})
                    s.get_by_text("3. Uygunluk haritası", exact=False).first.scroll_into_view_if_needed()
                    s.wait_for_timeout(2000)
                    kayit_tasma(s, "E_cok_kriterli", tema, gorunum)
                    s.screenshot(path=str(IMG / f"E_cok_kriterli_{tema}_{gorunum}.png"))
                    s.get_by_text("4. Doğrulama", exact=False).first.scroll_into_view_if_needed()
                    s.wait_for_timeout(1200)
                    s.screenshot(path=str(IMG / f"E_dogrulama_{tema}_{gorunum}.png"))
                    ctx.close()
            tar.close()
    finally:
        p.terminate()
    (CIKTILAR / "v3E").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sure).to_csv(CIKTILAR / "v3E" / "E6_tarayici_sure.csv", index=False, encoding="utf-8-sig", float_format="%.2f")
    pd.DataFrame(tas).to_csv(CIKTILAR / "v3E" / "E6_tasma.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(sure).round(1).to_string(index=False))
    print(pd.DataFrame(tas).to_string(index=False))


if __name__ == "__main__":
    main()
