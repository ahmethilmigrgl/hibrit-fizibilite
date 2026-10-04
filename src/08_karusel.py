"""
Aşama 8 — LinkedIn karuseli: 8 sayfa, 1080 × 1080 kare PDF (docs/kariyer/linkedin_karusel.pdf; klasör git'e girmez).

Her sayfa: bir bulgu (başlık) + bir grafik. Karar yolculuğu grafiği dahil. Grafikler src/08_sunum_grafikleri.py'deki
fonksiyonlarla kare formatta yeniden çizilir; önceki aşamaların grafikleri kendi başlıkları kırpılarak kullanılır.

Çalıştırma: .venv/bin/python src/08_karusel.py
"""
import importlib
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

import src.gorsel as g
from src.ayarlar import CIKTILAR, KOK

gr = importlib.import_module("src.08_sunum_grafikleri")
CIKTI = KOK / "docs" / "kariyer" / "linkedin_karusel.pdf"
KARE = CIKTILAR / "08" / "grafikler" / "kare"


def kirp(yol: Path, kutu: tuple[float, float, float, float]) -> Path:
    """Görselin göreli kutusunu (sol, üst, sağ, alt; 0–1) kırpar; önceki aşama grafiklerinin başlığını atmak için."""
    im = Image.open(yol)
    w, h = im.size
    hedef = KARE / f"kirpik_{yol.stem}.png"
    im.crop((int(kutu[0] * w), int(kutu[1] * h), int(kutu[2] * w), int(kutu[3] * h))).save(hedef)
    return hedef


def sayfa(pdf, no: int, toplam: int, baslik: str, alt: str, gorsel: Path | None, kaynak: str = "", kapak: bool = False,
          sayilar: list | None = None):
    fig = plt.figure(figsize=(10.8, 10.8), dpi=100)
    fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0.06, 0.935), 0.09, 0.008, color=g.RENK_HIBRIT, transform=fig.transFigure))
    fig.text(0.94, 0.935, f"{no}/{toplam}", ha="right", va="center", fontsize=15, color=g.SOLUK)
    genislik = 26 if kapak else 34
    fig.text(0.06, 0.905, textwrap.fill(baslik, genislik), ha="left", va="top", fontsize=40 if kapak else 31,
             fontweight="bold", color=g.MUREKKEP, linespacing=1.15)
    satir = textwrap.fill(baslik, genislik).count("\n") + 1
    alt_y = 0.905 - satir * (0.062 if kapak else 0.05) - 0.025
    fig.text(0.06, alt_y, textwrap.fill(alt, 62 if not kapak else 48), ha="left", va="top",
             fontsize=19 if kapak else 16.5, color=g.IKINCIL, linespacing=1.35)
    if gorsel is not None:
        im = Image.open(gorsel)
        alt_satir = textwrap.fill(alt, 62).count("\n") + 1
        ust = alt_y - alt_satir * 0.03 - 0.03
        ax = fig.add_axes([0.05, 0.1, 0.9, ust - 0.1])
        ax.imshow(im, interpolation="lanczos")
        ax.set_anchor("N")
        ax.axis("off")
    for i, (deger_, etiket) in enumerate(sayilar or []):
        y0 = 0.47 - i * 0.12
        fig.text(0.06, y0, deger_, fontsize=46, fontweight="bold", color=[g.RENK_RES, g.RENK_RES, g.RENK_HIBRIT][i], va="center")
        fig.text(0.40, y0, etiket, fontsize=19, color=g.IKINCIL, va="center")
    fig.text(0.06, 0.045, "Ahmet Hilmi Görgülü · Hibrit RES + batarya fizibilite modeli", fontsize=13, color=g.IKINCIL)
    if kaynak:
        fig.text(0.06, 0.07, kaynak, fontsize=11, color=g.SOLUK)
    with plt.rc_context({"savefig.bbox": "standard"}):          # kare sayfa: gorsel.py'deki tight kırpmayı kapat
        pdf.savefig(fig, facecolor="white")
    plt.close(fig)


def main():
    KARE.mkdir(parents=True, exist_ok=True)
    gr.CIKTI = KARE                                           # kare sürümler ayrı klasöre
    gr.karar_yolculugu(boyut=(10, 8.2), ad="karar_yolculugu.png", yazi=1.35, kisa=True)
    gr.gelir_yapilari(boyut=(10, 6.4), ad="gelir_yapilari.png", yazi=1.3)
    gr.cod_dagilimi(boyut=(10, 6.6), ad="cod_dagilimi.png", yazi=1.3)
    gr.bilgi_degeri(boyut=(10, 6.4), ad="dd_bilgi_degeri.png", yazi=1.35)
    gr.selale(boyut=(10, 6.6), ad="baz_vaka_selale.png", yazi=1.15)
    yakalanma = kirp(KOK / "outputs/02_piyasa/yakalanma_orani_trendi.png", (0, 0.17, 0.52, 1))
    doyum = kirp(KOK / "outputs/05_risk/s_senaryo_npv.png", (0, 0.14, 1, 1))

    b = pd.read_csv(CIKTILAR / "07" / "baz_vaka.csv")
    baz = b[b["Baz vaka"]].iloc[0]
    e = gr.tr(baz["Beklenen NPV [M USD]"], ".1f")
    MODEL = "Kaynak: kendi modelim (Pyomo + HiGHS, Monte Carlo 10.000 simülasyon), reel 2026 USD."
    sayfalar = [
        ("50 MW şebeke bağlantısına ne kurulmalı? Kararım altı adımda dört kez değişti.",
         "Çanakkale-Ezine için güneş, rüzgâr ve batarya fizibilitesi: saatlik optimizasyon, proje finansmanı ve "
         "10.000 senaryolu risk analizi. Sonuç: yatırım değil, durum tespiti ve sınırlı bir teklif.", None, "", True),
        ("Güneş elendi: kendi fiyatını düşürüyor.",
         "Güneşin yakaladığı fiyat 2016'da ortalamanın %20 üstündeydi, 2026'da %30 altında. Rüzgâr ortalamada kalıyor.",
         yakalanma, "Kaynak: EPİAŞ PTF; Ezine üretim profilleri kendi modelim.", False),
        ("Batarya yan hizmet için var; piyasa doyarsa avantajı kayboluyor.",
         "Yeşil: yavaş doyum, gri: TEİAŞ bataryayı kabul etmezse. ~1 GW SFK ihtiyacına karşı 28–33 GW depolama ön lisansı var.",
         doyum, "Kaynak: kendi modelim; doyum kalibrasyonu İngiltere ve Almanya deneyimi.", False),
        ("Takvim kararın yarısı: geliştirmeden başlarsanız YEKDEM'i kaçırırsınız.",
         "İnşaata hazır proje Kasım 2029'da devrede (P50). Ön lisanstan başlamak COD'u 2032'ye itiyor.",
         KARE / "cod_dagilimi.png", "Kaynak: kendi modelim (CPM + Monte Carlo).", False),
        ("YEKDEM bir sözleşme değil, her yıl yenilenen bir opsiyon.",
         "Yönetmeliğe göre katılım her yıl ayrı karar. Opsiyon olarak modellenince değer, 10 yıl kilitlemeye göre 12 M$ arttı.",
         KARE / "gelir_yapilari.png", MODEL, False),
        ("Karar dört kez değişti; her seferinde bir varsayımı düzelttim.",
         "Önce iyimser SFK geliri, sonra kötümser sabit YEKDEM varsayımı. Her nokta o andaki önerinin beklenen NPV'si.",
         KARE / "karar_yolculugu.png", MODEL, False),
        (f"Sonuç: beklenen değer +{e} M$, kâr olasılığı %{baz['P(NPV > 0) [%]']:.0f}. Değer ince.",
         "Önceki baz vakadan bugüne: üç tutarlılık düzeltmesi (YEKDEM opsiyonu, ortak batarya sürücüsü, takvim).",
         KARE / "baz_vaka_selale.png", MODEL, False),
        ("Önerim: 0,5 M$ durum tespiti ve en fazla 1,5 M$ primle bağlayıcı olmayan teklif.",
         "Bütçe, belirsizliği çözmenin değeriyle (EVPPI) sınırlı. En büyük ders: en güvendiğim sonuç, en az sorguladığım varsayıma dayanıyordu.",
         KARE / "dd_bilgi_degeri.png", "Kod, rapor, Excel modeli ve memo: GitHub · Dashboard: Streamlit", False),
    ]
    kapak_sayilari = [(f"+{e} M$", "beklenen NPV (10.000 senaryo)"), (f"%{baz['P(NPV > 0) [%]']:.0f}", "kâr olasılığı"),
                      ("0,5 M$", "önerilen durum tespiti bütçesi")]
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(CIKTI) as pdf:
        for i, (bas, alt, gorsel, kaynak, kapak) in enumerate(sayfalar, start=1):
            sayfa(pdf, i, len(sayfalar), bas, alt, gorsel, kaynak, kapak, sayilar=kapak_sayilari if kapak else None)
    print(f"Kaydedildi: {CIKTI.relative_to(KOK)} ({len(sayfalar)} sayfa, 1080 × 1080)")


if __name__ == "__main__":
    main()
