"""
v3 D3 — Yeni arayüz bölümlerinin ("Türbin yerleşimi", "İşletme ve bakım") gerçek tarayıcıda görüntüsü ve taşma kontrolü.

Ezine tam analizi motorla önbelleğe alınır, uygulama paylaşım bağlantısıyla (mod=tam) açılır; iki bölüm masaüstü
(1366 × 900) ve mobilde (390 × 844), açık ve koyu temada çekilir. Yatay taşma v2 C8 ölçütüyle denetlenir.
Çıktılar: docs/img/v3/*.png, outputs/v3D/D3_tasma.csv
Çalıştırma: .venv/bin/python src/v3_D3_tarayici.py [--port 8611]
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK
from src.motor import KullaniciVarsayimlari, analiz_et

IMG = KOK / "docs" / "img" / "v3"
E, B = 39.79, 26.33


def c8():
    sp = importlib.util.spec_from_file_location("c8", KOK / "src" / "v2_C8_tarayici.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def main() -> None:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8611
    IMG.mkdir(parents=True, exist_ok=True)
    analiz_et({"ad": "Çanakkale-Ezine", "enlem": E, "boylam": B}, "tam", KullaniciVarsayimlari())  # önbelleğe al
    m = c8()
    kayit = []
    p = m.sunucu(port)
    try:
        with sync_playwright() as pw:
            tar = pw.chromium.launch(channel="chrome", headless=True)
            for tema in ("acik", "koyu"):
                for gorunum, boyut in m.GORUNUM.items():
                    ctx = tar.new_context(viewport=boyut, color_scheme="dark" if tema == "koyu" else "light")
                    ctx.add_cookies([{"name": "esik_tema", "value": tema, "url": f"http://localhost:{port}"}])
                    s = ctx.new_page()
                    s.goto(f"http://localhost:{port}/?enlem={E:.3f}&boylam={B:.3f}&mod=tam")
                    m.bekle_metin(s, "Öneri:", 300)
                    for ad, metin in (("yerlesim", "Türbin yerleşimi"), ("bakim", "İşletme ve bakım")):
                        h = s.locator(".esik-bolum h3", has_text=metin).first
                        h.wait_for(state="visible", timeout=60000)
                        h.scroll_into_view_if_needed()
                        s.wait_for_timeout(2500)
                        r = s.evaluate(m.TASMA_JS)
                        kayit.append(
                            {
                                "ekran": ad,
                                "tema": tema,
                                "gorunum": gorunum,
                                "yatay_tasma": r["scroll"] > r["client"] + 1,
                                "tasan_oge": r["adet"],
                                "ornek": "; ".join(r["tasan"]),
                            }
                        )
                        s.screenshot(path=str(IMG / f"{ad}_{tema}_{gorunum}.png"))
                    ctx.close()
            tar.close()
    finally:
        p.terminate()
    d = pd.DataFrame(kayit)
    (CIKTILAR / "v3D").mkdir(parents=True, exist_ok=True)
    d.to_csv(CIKTILAR / "v3D" / "D3_tasma.csv", index=False, encoding="utf-8-sig")
    print(d.to_string(index=False))


if __name__ == "__main__":
    main()
