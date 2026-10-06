"""
v2 Faz C8 — Gerçek tarayıcıda (Playwright + yüklü Chrome) uçtan uca ölçüm ve ekran görüntüleri.

• Sunucu 2 çekirdek benzetimiyle başlatılır (MOTOR_CEKIRDEK=2, OMP/VECLIB tek iş parçacığı).
• Süreler: açılış soğuk (yeni sunucu, boş Streamlit önbelleği) ve sıcak (yeniden yükleme); hızlı tarama ve tam analiz
  (düğmeye basıştan sonuç görünene kadar; motor önbelleği temizlenmiş).
• Ekran görüntüleri: masaüstü 1366 × 900 ve mobil 390 × 844 → docs/img/v2/. Her ekranda yatay taşma (scrollWidth >
  clientWidth) ve görünüm alanından taşan öğeler kontrol edilir.
Çıktılar: outputs/v2C/C8_sure.csv, outputs/v2C/C8_tasma.csv, docs/img/v2/*.png

Çalıştırma: .venv/bin/python src/v2_C8_tarayici.py [--port 8601] [--saha 39.79,26.33]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import shutil
import subprocess
import time

import pandas as pd
from playwright.sync_api import sync_playwright

from src.ayarlar import CIKTILAR, KOK

IMG = KOK / "docs" / "img" / "v2"
_SURE: list = []
SURE_DOSYA = "C8_sure.csv"
GORUNUM = {"masaustu": {"width": 1366, "height": 900}, "mobil": {"width": 390, "height": 844}}
TASMA_JS = """() => {
  const W = document.documentElement.clientWidth;
  const tasan = [];
  for (const el of document.querySelectorAll('[data-testid="stMain"] *')) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > W + 1 || r.left < -1)) {
      const s = getComputedStyle(el);
      // görünmez öğeler (gizli sekme panelleri) ve kendi içinde kaydırılan sekme çubukları/tablolar sayılmaz
      if (el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) && s.position !== 'fixed' && s.overflowX !== 'auto'
          && !el.closest('[role="tablist"], [data-testid="stDataFrame"], .stDataFrame, [data-testid="stCode"], iframe, .js-plotly-plot')) {
        tasan.push((el.getAttribute('data-testid') || el.tagName) + ':' + Math.round(r.right));
      }
    }
  }
  return {scroll: document.documentElement.scrollWidth, client: W, tasan: tasan.slice(0, 8), adet: tasan.length};
}"""


def sunucu(port: int) -> subprocess.Popen:
    env = {**os.environ, "MOTOR_CEKIRDEK": "2", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    p = subprocess.Popen(
        [str(KOK / ".venv" / "bin" / "streamlit"), "run", str(KOK / "app.py"), "--server.headless", "true", "--server.port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    return p


def bekle_metin(sayfa, metin: str, zaman_s: float) -> None:
    sayfa.get_by_text(metin, exact=False).first.wait_for(state="visible", timeout=zaman_s * 1000)


def kaydet(sure: list, tas: list) -> None:
    (CIKTILAR / "v2C").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sure).to_csv(CIKTILAR / "v2C" / SURE_DOSYA, index=False, encoding="utf-8-sig", float_format="%.1f")
    pd.DataFrame(tas).to_csv(CIKTILAR / "v2C" / "C8_tasma.csv", index=False, encoding="utf-8-sig")


def tasma(sayfa, ad: str, gorunum: str, kayit: list) -> None:
    r = sayfa.evaluate(TASMA_JS)
    kayit.append({"ekran": ad, "gorunum": gorunum, "scroll_genislik": r["scroll"], "gorunum_genislik": r["client"],
                  "yatay_tasma": r["scroll"] > r["client"] + 1, "tasan_oge": r["adet"], "ornek": "; ".join(r["tasan"])})  # fmt: skip


def goruntu(sayfa, ad: str, gorunum: str, kayit: list, tam: bool = True, odak: str | None = None) -> None:
    """odak: ekran görüntüsünden önce bu metne kaydırılır (Streamlit'te kaydırma ana kapsayıcıda; tam sayfa çekimi inmez)."""
    sayfa.wait_for_timeout(1500)
    if odak:
        sayfa.get_by_text(odak, exact=False).first.scroll_into_view_if_needed()
        sayfa.wait_for_timeout(800)
        tam = False
    tasma(sayfa, ad, gorunum, kayit)
    sayfa.screenshot(path=str(IMG / f"{ad}_{gorunum}.png"), full_page=tam)
    kaydet(_SURE, kayit)


def main() -> None:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8601
    e, b = (float(x) for x in (sys.argv[sys.argv.index("--saha") + 1] if "--saha" in sys.argv else "39.79,26.33").split(","))
    IMG.mkdir(parents=True, exist_ok=True)
    sicak = "--sicak" in sys.argv  # yalnız ekran görüntüleri: önbellek korunur, süreler C8_sure_sicak.csv'ye
    if not sicak:
        for d in ("sonuc", "rapor", "tablolar", "profil"):  # motor önbelleği: süre ölçümü soğuk başlasın
            shutil.rmtree(KOK / "data" / "onbellek" / d, ignore_errors=True)
    global SURE_DOSYA
    SURE_DOSYA = "C8_sure_sicak.csv" if sicak else "C8_sure.csv"
    url = f"http://localhost:{port}"
    sure, tas = _SURE, []
    p = sunucu(port)
    try:
        with sync_playwright() as pw:
            tar = pw.chromium.launch(channel="chrome", headless=True)
            for gorunum, boyut in GORUNUM.items():
                s = tar.new_page(viewport=boyut)
                t0 = time.time()
                s.goto(url)
                bekle_metin(s, "Türkiye hibrit", 120)
                s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                sure.append({"olcum": f"açılış ({'soğuk' if gorunum == 'masaustu' else 'ılık'}, {gorunum})", "sure_s": time.time() - t0})
                goruntu(s, "01_acilis_harita", gorunum, tas, tam=False)
                t0 = time.time()
                s.reload()
                bekle_metin(s, "Türkiye hibrit", 120)
                s.frame_locator("iframe").first.locator(".leaflet-container").wait_for(timeout=120000)
                sure.append({"olcum": f"açılış (sıcak, yeniden yükleme, {gorunum})", "sure_s": time.time() - t0})
                # saha seçimi: paylaşım bağlantısıyla (koordinat)
                s.goto(f"{url}/?enlem={e:.3f}&boylam={b:.3f}")
                bekle_metin(s, "GWA 100 m (nokta)", 120)
                goruntu(s, "02_saha_karti", gorunum, tas, odak="GWA 100 m (nokta)")
                t0 = time.time()
                s.get_by_role("button", name="Hızlı tarama").click()
                bekle_metin(s, "Tam analize değer mi?", 300)
                sure.append({"olcum": f"hızlı tarama (arayüz, {gorunum})", "sure_s": time.time() - t0})
                goruntu(s, "03_hizli_tarama", gorunum, tas, odak="Tam analize değer mi?")
                if gorunum == "masaustu":
                    t0 = time.time()
                    s.get_by_role("button", name="Tam analiz (birkaç dakika)").click()
                    bekle_metin(s, "Öneri:", 900)
                    sure.append({"olcum": "tam analiz (arayüz, soğuk tablolar)", "sure_s": time.time() - t0})
                else:  # mobilde sonuç önbellekten (paylaşım bağlantısı)
                    s.goto(f"{url}/?enlem={e:.3f}&boylam={b:.3f}&mod=tam")
                    bekle_metin(s, "Öneri:", 120)
                goruntu(s, "04_tam_analiz", gorunum, tas, odak="Öneri:")
                s.goto(f"{url}/vaka")
                bekle_metin(s, "Karar yolculuğu", 120)
                goruntu(s, "05_vaka_calismasi", gorunum, tas, tam=False)
                s.goto(f"{url}/yontem")
                bekle_metin(s, "Veri kaynakları", 120)
                goruntu(s, "06_yontem", gorunum, tas, tam=False)
                s.close()
            tar.close()
    finally:
        p.terminate()
    kaydet(sure, tas)
    print(pd.DataFrame(sure).round(1).to_string(index=False))
    print(pd.DataFrame(tas).to_string(index=False))


if __name__ == "__main__":
    main()
