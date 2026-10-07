"""
Arayüz tasarımı — ana ekranların ekran görüntüleri (Playwright + yüklü Chrome). Hesaplamaya dokunmaz.

Ekranlar: açılış, saha kartı, hata durumu (kara dışı nokta), hızlı tarama (yükleniyor + sonuç), tam analiz, vaka çalışması,
yöntem; masaüstü 1440 px ve mobil 390 px; isteğe bağlı koyu mod (prefers-color-scheme: dark → uygulama sistem temasını izler).
Streamlit'te sayfa iç kapsayıcıda kaydığından "tam sayfa" çekim için görünüm alanı içerik yüksekliğine büyütülür. Her
ekranda yatay taşma (scrollWidth > clientWidth) denetlenir. Tam analiz sonucu önbellekte olmalıdır (uygulamada bir kez
çalıştırın); hızlı tarama "yükleniyor" çekimi için hızlı tarama kayıtları silinir.

Çalıştırma (sunucu 8502'de açık olmalı):
  .venv/bin/python src/v2_tasarim_ekran.py --etiket sonra [--koyu] [--ekranlar acilis,saha,hata,hizli,tam,vaka,yontem]
Çıktılar: docs/img/tasarim/<etiket>/<no>_<ekran>_<gorunum>[_koyu].jpg, outputs/v2_tasarim/tasma_<etiket>[_koyu].csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pickle

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK

GORUNUM = {"masaustu": {"width": 1440, "height": 900}, "mobil": {"width": 390, "height": 844}}
SAHA = "enlem=39.790&boylam=26.330"
DENIZ = "enlem=40.200&boylam=25.600"  # Ege denizi: kara dışı hata durumu
YUKSEKLIK_JS = """() => {
  const m = document.querySelector('[data-testid="stMain"]') || document.scrollingElement;
  return Math.max(m.scrollHeight, document.documentElement.scrollHeight);
}"""
TASMA_JS = "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"


def arg(ad: str, vars_: str) -> str:
    return sys.argv[sys.argv.index(ad) + 1] if ad in sys.argv else vars_


def bekle(s, metin: str, zaman_s: float = 180) -> None:
    s.get_by_text(metin, exact=False).first.wait_for(state="visible", timeout=zaman_s * 1000)


def harita_bekle(s) -> None:
    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)


def cek(s, yol: Path, tam: bool, boyut: dict, azami: int = 8000, bekleme_ms: int = 1800) -> dict:
    s.wait_for_timeout(bekleme_ms)
    sw, cw = s.evaluate(TASMA_JS)
    if tam:
        h = min(int(s.evaluate(YUKSEKLIK_JS)) + 40, azami)
        s.set_viewport_size({"width": boyut["width"], "height": h})
        s.wait_for_timeout(1200)
    s.screenshot(path=str(yol), type="jpeg", quality=72)
    if tam:
        s.set_viewport_size(boyut)
    return {"dosya": yol.name, "yatay_tasma": sw > cw + 1, "scroll": sw, "genislik": cw}


def hizli_kayitlarini_sil() -> None:
    for f in (KOK / "data" / "onbellek" / "sonuc").glob("*.pkl"):
        try:
            if pickle.loads(f.read_bytes()).mod == "hizli":
                f.unlink()
        except Exception:
            continue


def main() -> None:
    etiket, port = arg("--etiket", "sonra"), int(arg("--port", "8502"))
    koyu = "--koyu" in sys.argv
    ekranlar = arg("--ekranlar", "acilis,saha,hata,hizli,tam,vaka,yontem").split(",")
    hedef = KOK / "docs" / "img" / "tasarim" / etiket
    hedef.mkdir(parents=True, exist_ok=True)
    url = f"http://localhost:{port}"
    ek = "_koyu" if koyu else ""
    tasma = []
    with sync_playwright() as pw:
        tar = pw.chromium.launch(channel="chrome", headless=True)
        for gor in arg("--gorunum", "masaustu,mobil").split(","):
            boyut = GORUNUM[gor]
            bag = tar.new_context(viewport=boyut, color_scheme="dark" if koyu else "light")
            s = bag.new_page()
            if "acilis" in ekranlar:
                s.goto(url)
                harita_bekle(s)
                tasma.append(cek(s, hedef / f"01_acilis_{gor}{ek}.jpg", False, boyut, bekleme_ms=3000))
                tasma.append(cek(s, hedef / f"01_acilis_tam_{gor}{ek}.jpg", True, boyut))
            if "saha" in ekranlar:
                s.goto(f"{url}/?{SAHA}")
                harita_bekle(s)
                bekle(s, "GWA 100 m (nokta)")
                tasma.append(cek(s, hedef / f"02_saha_{gor}{ek}.jpg", True, boyut))
            if "hata" in ekranlar:
                s.goto(f"{url}/?{DENIZ}")
                harita_bekle(s)
                bekle(s, "Türkiye karası dışında")
                tasma.append(cek(s, hedef / f"02b_hata_{gor}{ek}.jpg", False, boyut))
            if "hizli" in ekranlar:
                hizli_kayitlarini_sil()
                s.goto(f"{url}/?{SAHA}")
                harita_bekle(s)
                bekle(s, "GWA 100 m (nokta)")
                s.get_by_role("button", name="Hızlı tarama").first.click()
                try:  # yükleniyor durumu (ilerleme çubuğu + iskelet); profil önbellekteyse birkaç saniye görünür
                    s.locator('[data-testid="stProgress"]').first.wait_for(timeout=15000)
                    s.locator('[data-testid="stProgress"]').first.scroll_into_view_if_needed()
                    s.wait_for_timeout(200)
                    s.screenshot(path=str(hedef / f"03b_yukleniyor_{gor}{ek}.jpg"), type="jpeg", quality=72)
                except Exception:
                    print("yükleniyor durumu yakalanamadı", gor)
                bekle(s, "Tam analize değer mi?", 300)
                tasma.append(cek(s, hedef / f"03_hizli_{gor}{ek}.jpg", True, boyut))
            if "tam" in ekranlar:
                s.goto(f"{url}/?{SAHA}&mod=tam")
                s.locator('[data-testid="stMetricLabel"]', has_text="E[NPV]").first.wait_for(timeout=120000)
                tasma.append(cek(s, hedef / f"04_tam_{gor}{ek}.jpg", True, boyut))
            if "vaka" in ekranlar:
                s.goto(f"{url}/vaka")
                bekle(s, "Ezine", 120)
                tasma.append(cek(s, hedef / f"05_vaka_{gor}{ek}.jpg", True, boyut, azami=6000))
            if "yontem" in ekranlar:
                s.goto(f"{url}/yontem")
                bekle(s, "Veri kaynakları", 120)
                tasma.append(cek(s, hedef / f"06_yontem_{gor}{ek}.jpg", True, boyut, azami=6000))
            bag.close()
        tar.close()
    (CIKTILAR / "v2_tasarim").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(tasma).to_csv(CIKTILAR / "v2_tasarim" / f"tasma_{etiket}{ek}.csv", index=False)
    print(pd.DataFrame(tasma).to_string(index=False))


if __name__ == "__main__":
    main()
