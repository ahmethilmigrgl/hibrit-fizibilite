"""
Arayüz tasarımı — açılış ve hızlı tarama sürelerinin önce/sonra ölçümü (Playwright + yüklü Chrome).

Aynı protokol her iki sürüme uygulanır (masaüstü 1440 × 900):
- açılış (soğuk): sunucu yeni başlatılır, ilk sayfa yüklemesinden harita (Leaflet) görünene kadar; 3 tekrar (her biri yeni sunucu)
- açılış (sıcak): aynı sunucuda yeniden yükleme; 5 tekrar
- hızlı tarama: sonuç önbelleğindeki hızlı tarama kayıtları silinir, Ezine koordinatı bağlantıyla seçilir, düğmeye basıştan
  "Tam analize değer mi?" görünene kadar; --tekrar (varsayılan 3) (profil önbelleği sıcak: belgelerdeki "~2 s" koşulu)

- hızlı tarama (ince): Playwright'ın bekleme yoklaması süreleri ~0,5 s'lik basamaklara yuvarladığından, aynı olay tarayıcı
  içinde MutationObserver ile ms çözünürlükte de ölçülür (ilerleme çubuğunun görünmesi, sonucun DOM'a gelmesi); sunucu
  süresi sonuç ekranındaki "Süre" notundan

Çalıştırma: .venv/bin/python src/v2_tasarim_sure.py --kok <uygulama klasörü> --etiket once|sonra [--port 8502]
Çıktı: outputs/v2_tasarim/sure_olcum.csv (etiket başına satırlar eklenir/yenilenir)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import pickle
import statistics
import subprocess
import time

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR

SAHA = "enlem=39.790&boylam=26.330"


def arg(ad: str, vars_: str) -> str:
    return sys.argv[sys.argv.index(ad) + 1] if ad in sys.argv else vars_


def sunucu(kok: Path, port: int) -> subprocess.Popen:
    p = subprocess.Popen(
        [str(kok / ".venv" / "bin" / "streamlit"), "run", str(kok / "app.py"), "--server.headless", "true", "--server.port", str(port)],
        cwd=kok,
        env={**os.environ},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import urllib.request

    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    return p


def hizli_kayitlarini_sil(kok: Path) -> None:
    for f in (kok / "data" / "onbellek" / "sonuc").glob("*.pkl"):
        try:
            if pickle.loads(f.read_bytes()).mod == "hizli":
                f.unlink()
        except Exception:
            continue


INCE_JS = """() => new Promise(res => { const t0 = performance.now(); const z = {};
  const ob = new MutationObserver(() => {
    if (!z.ilerleme && document.querySelector('[data-testid=stProgress]')) z.ilerleme = performance.now() - t0;
    if (!z.sonuc && document.body.textContent.includes('Tam analize değer mi?')) { z.sonuc = performance.now() - t0; ob.disconnect(); res(z); }
  });
  ob.observe(document.body, {childList: true, subtree: true, characterData: true});
  for (const b of document.querySelectorAll('button')) if (b.textContent.trim().endsWith('Hızlı tarama')) { b.click(); break; }
  setTimeout(() => res(z), 60000); })"""


def harita_bekle(s) -> None:
    s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)


def main() -> None:
    kok = Path(arg("--kok", str(Path(__file__).resolve().parents[1]))).resolve()
    etiket, port = arg("--etiket", "sonra"), int(arg("--port", "8502"))
    url = f"http://localhost:{port}"
    olc: dict[str, list[float]] = {
        "açılış (soğuk)": [],
        "açılış (sıcak, yeniden yükleme)": [],
        "hızlı tarama": [],
        "hızlı tarama (ince): ilerleme görünür": [],
        "hızlı tarama (ince): sonuç DOM'da": [],
        "hızlı tarama: sunucu süresi": [],
    }
    with sync_playwright() as pw:
        tar = pw.chromium.launch(channel="chrome", headless=True)
        for tekrar in range(3):
            p = sunucu(kok, port)
            try:
                s = tar.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light").new_page()
                t0 = time.time()
                s.goto(url)
                harita_bekle(s)
                olc["açılış (soğuk)"].append(time.time() - t0)
                if tekrar == 0:
                    for _ in range(5):
                        t0 = time.time()
                        s.reload()
                        harita_bekle(s)
                        olc["açılış (sıcak, yeniden yükleme)"].append(time.time() - t0)
                    for _ in range(int(arg("--tekrar", "3"))):
                        hizli_kayitlarini_sil(kok)
                        s.goto(f"{url}/?{SAHA}")
                        harita_bekle(s)
                        s.get_by_text("GWA 100 m (nokta)").first.wait_for(timeout=120000)
                        t0 = time.time()
                        s.get_by_role("button", name="Hızlı tarama").first.click()
                        s.get_by_text("Tam analize değer mi?").first.wait_for(timeout=300000)
                        olc["hızlı tarama"].append(time.time() - t0)
                    for _ in range(int(arg("--tekrar", "3"))):
                        hizli_kayitlarini_sil(kok)
                        s.goto(f"{url}/?{SAHA}")
                        harita_bekle(s)
                        s.get_by_text("GWA 100 m (nokta)").first.wait_for(timeout=120000)
                        s.wait_for_timeout(1000)
                        z = s.evaluate(INCE_JS)
                        olc["hızlı tarama (ince): ilerleme görünür"].append(z.get("ilerleme", float("nan")) / 1000)
                        olc["hızlı tarama (ince): sonuç DOM'da"].append(z.get("sonuc", float("nan")) / 1000)
                        s.wait_for_timeout(800)
                        for c in s.locator('[data-testid="stCaptionContainer"]').all_inner_texts():
                            if c.startswith("Süre:"):
                                olc["hızlı tarama: sunucu süresi"].append(float(c.split()[1].replace(",", ".")))
                s.context.close()
            finally:
                p.terminate()
                p.wait(timeout=20)
        tar.close()
    satir = [
        {"etiket": etiket, "olcum": k, "n": len(v), "medyan_s": statistics.median(v), "min_s": min(v), "maks_s": max(v)}
        for k, v in olc.items()
    ]
    hedef = CIKTILAR / "v2_tasarim" / "sure_olcum.csv"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    eski = pd.read_csv(hedef) if hedef.exists() else pd.DataFrame()
    if len(eski):
        eski = eski[eski["etiket"] != etiket]
    pd.concat([eski, pd.DataFrame(satir)]).to_csv(hedef, index=False, float_format="%.2f")
    print(pd.DataFrame(satir).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
