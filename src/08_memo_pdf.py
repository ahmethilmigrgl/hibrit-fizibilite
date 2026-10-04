"""
Aşama 8 — Yatırım komitesi memosu: outputs/08/Yatirim_Memosu.md → outputs/08/Yatirim_Memosu.pdf (2–3 sayfa).
Rapor PDF'iyle aynı yol (src/06_rapor_pdf.py → md_pdf), daha sıkı baskı CSS'i.

Çalıştırma: .venv/bin/python src/08_memo_pdf.py
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ayarlar import KOK

md_pdf = importlib.import_module("src.06_rapor_pdf").md_pdf

CSS_MEMO = """
@page { size: A4; margin: 13mm 14mm 13mm 14mm; }
body { font-size: 9.3pt; line-height: 1.36; }
h1 { font-size: 16pt; }
h2 { font-size: 11.5pt; margin-top: 10pt; margin-bottom: 4pt; }
p { margin: 3pt 0; }
ul, ol { margin: 3pt 0; padding-left: 16pt; }
table { font-size: 8.3pt; margin: 4pt 0 6pt 0; }
th, td { padding: 2pt 4pt; }
"""


def main():
    d = KOK / "outputs" / "08"
    md_pdf(d / "Yatirim_Memosu.md", d / "Yatirim_Memosu.pdf", "Yatırım Komitesi Memosu — Ezine RES + Batarya", CSS_MEMO)


if __name__ == "__main__":
    main()
