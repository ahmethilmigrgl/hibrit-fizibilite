"""
Aşama 6 — docs/RAPOR.md → outputs/RAPOR.pdf

pandoc/LaTeX gerektirmeyen en basit yol: Markdown → HTML (python-markdown, baskı CSS'i) → Chrome/Chromium headless
"print to PDF". Görseller göreli yollarla (../outputs/...) gömülür. Chrome bulunamazsa HTML çıktısı bırakılır.

Çalıştırma: .venv/bin/python src/06_rapor_pdf.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import markdown

from src.ayarlar import KOK

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 10.2pt; line-height: 1.45; color: #1b1b1b; }
h1 { font-size: 20pt; margin: 0 0 4pt 0; color: #0b0b0b; }
h2 { font-size: 14pt; margin-top: 18pt; border-bottom: 1.5px solid #1baf7a; padding-bottom: 2pt; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 12pt; page-break-after: avoid; }
p, li { text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt 0; font-size: 8.8pt; page-break-inside: avoid; }
th { background: #f0efeb; text-align: left; }
th, td { border: 0.6pt solid #d0cfca; padding: 3pt 5pt; }
img { max-width: 100%; display: block; margin: 6pt auto; page-break-inside: avoid; }
blockquote { border-left: 3pt solid #1baf7a; margin: 8pt 0; padding: 4pt 10pt; background: #f5f9f6; }
code { font-size: 8.8pt; background: #f4f4f2; padding: 0 2pt; }
.sayfa-sonu { page-break-after: always; }
hr { border: none; border-top: 0.8pt solid #d0cfca; }
"""


def chrome_bul() -> str | None:
    for aday in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]:
        if Path(aday).exists() or shutil.which(aday):
            return aday
    return None


def md_pdf(kaynak: Path, pdf: Path, baslik: str, css_ek: str = "") -> None:
    """Markdown → HTML (kaynakla aynı klasörde, göreli görsel yolları korunur) → Chrome headless PDF."""
    govde = markdown.markdown(kaynak.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    html = f"<!doctype html><html lang='tr'><head><meta charset='utf-8'><title>{baslik}</title><style>{CSS}{css_ek}</style></head><body>{govde}</body></html>"
    html_yol = kaynak.with_suffix(".html")
    html_yol.write_text(html, encoding="utf-8")
    chrome = chrome_bul()
    if chrome is None:
        print(f"Chrome/Chromium bulunamadı; HTML bırakıldı: {html_yol} (tarayıcıda açıp PDF olarak yazdırabilirsiniz)")
        return
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html_yol.as_uri()],
        check=True,
        capture_output=True,
    )
    html_yol.unlink()
    print(f"Kaydedildi: {pdf.relative_to(KOK)} ({pdf.stat().st_size / 1e6:.1f} MB)")


def main():
    md_pdf(KOK / "docs" / "RAPOR.md", KOK / "outputs" / "RAPOR.pdf", "Hibrit Fizibilite Raporu")


if __name__ == "__main__":
    main()
