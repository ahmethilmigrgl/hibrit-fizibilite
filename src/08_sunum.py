"""
Aşama 8 — yatırım komitesi sunumu: outputs/08/Sunum.pptx (+ LibreOffice ile Sunum.pdf).

Her slaytın başlığı tek cümlelik ana mesajdır; gövde bir grafik ve az metin. Sayılar model çıktılarından okunur
(outputs/07/baz_vaka.csv, durum_tespiti_bilgi_degeri.csv); grafikler src/08_sunum_grafikleri.py ve önceki aşamalardan.

Çalıştırma: .venv/bin/python src/08_sunum.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

from src.ayarlar import CIKTILAR, KOK

CIKTI = CIKTILAR / "08"
GRAF = CIKTI / "grafikler"
SOFFICE = [Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
           Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")]

MUREKKEP, IKINCIL, SOLUK = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x52, 0x51, 0x4E), RGBColor(0x8A, 0x89, 0x84)
YESIL, MAVI, TURUNCU = RGBColor(0x1B, 0xAF, 0x7A), RGBColor(0x2A, 0x78, 0xD6), RGBColor(0xEB, 0x68, 0x34)
ZEMIN = RGBColor(0xF5, 0xF4, 0xF0)
G, Y = 13.333, 7.5            # slayt boyutu [inç], 16:9
KENAR = 0.55
YAZI_TIPI = "Arial"           # LibreOffice PDF dönüşümünde de bulunan yazı tipi


def tr(x: float, fmt: str = ".1f") -> str:
    return format(x, fmt).replace(".", ",").replace("-", "−")


class Sunum:
    def __init__(self):
        self.p = Presentation()
        self.p.slide_width, self.p.slide_height = Inches(G), Inches(Y)
        self.no = 0

    def yazi(self, s, x, y, w, h, metin, boyut=14, renk=MUREKKEP, kalin=False, hiza=PP_ALIGN.LEFT, dikey=MSO_ANCHOR.TOP):
        kutu = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = kutu.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = dikey
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        satirlar = metin if isinstance(metin, list) else [metin]
        for i, sat in enumerate(satirlar):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            par.alignment = hiza
            parcalar = sat if isinstance(sat, list) else [(sat, kalin)]
            for parca, k in parcalar:
                r = par.add_run()
                r.text = parca
                r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(boyut), k, renk, YAZI_TIPI
            par.space_after = Pt(boyut * 0.45)
        return kutu

    def slayt(self, baslik: str, alt: str | None = None, kaynak: str | None = None):
        s = self.p.slides.add_slide(self.p.slide_layouts[6])
        self.no += 1
        cubuk = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(KENAR), Inches(0.42), Inches(0.9), Inches(0.07))
        cubuk.fill.solid(); cubuk.fill.fore_color.rgb = YESIL; cubuk.line.fill.background(); cubuk.shadow.inherit = False
        self.yazi(s, KENAR, 0.6, G - 2 * KENAR, 1.0, baslik, boyut=24, kalin=True)
        if alt:
            self.yazi(s, KENAR, 1.55, G - 2 * KENAR, 0.4, alt, boyut=13, renk=IKINCIL)
        if kaynak:
            self.yazi(s, KENAR, Y - 0.42, G - 2 * KENAR - 1.0, 0.3, kaynak, boyut=9, renk=SOLUK)
        self.yazi(s, G - KENAR - 0.8, Y - 0.42, 0.8, 0.3, str(self.no), boyut=9, renk=SOLUK, hiza=PP_ALIGN.RIGHT)
        return s

    def gorsel(self, s, yol: Path, x=KENAR, y=2.1, w=G - 2 * KENAR, h=4.85):
        """Görseli kutuya en-boy oranını koruyarak sığdırır ve ortalar."""
        gw, gh = Image.open(yol).size
        olcek = min(w / gw, h / gh)
        ww, hh = gw * olcek, gh * olcek
        s.shapes.add_picture(str(yol), Inches(x + (w - ww) / 2), Inches(y + (h - hh) / 2), Inches(ww), Inches(hh))

    def kutu(self, s, x, y, w, h, ust, deger, alt=None, renk=MAVI, boyut=28):
        k = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        k.fill.solid(); k.fill.fore_color.rgb = ZEMIN; k.line.fill.background(); k.shadow.inherit = False
        serit = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(0.07), Inches(h))
        serit.fill.solid(); serit.fill.fore_color.rgb = renk; serit.line.fill.background(); serit.shadow.inherit = False
        self.yazi(s, x + 0.25, y + 0.18, w - 0.4, 0.3, ust, boyut=11, renk=IKINCIL)
        self.yazi(s, x + 0.25, y + 0.5, w - 0.4, 0.6, deger, boyut=boyut, kalin=True)
        if alt:
            self.yazi(s, x + 0.25, y + 1.15, w - 0.4, 0.4, alt, boyut=10, renk=IKINCIL)


def main():
    b = pd.read_csv(CIKTILAR / "07" / "baz_vaka.csv")
    baz = b[b["Baz vaka"]].iloc[0]
    end = b[b["Senaryo"].str.contains("endeksli")].iloc[0]
    sabit = b[b["Senaryo"].str.contains("sabit")].iloc[0]
    e, prim = baz["Beklenen NPV [M USD]"], baz["Azami edinim primi [M USD]"]
    if e > 0 and prim > 0:      # memo karar kuralı: (a) durum tespiti + sınırlı teklif; metinler (b) için yazıldı
        raise SystemExit("Baz vaka E[NPV] > 0: karar (a). Sunum metinleri (b) 'rafa kaldır' için yazıldı; önce güncelleyin.")
    tuc = b[b["Senaryo"] == "Tüccar"].iloc[0]
    KAYNAK = "Kaynak: kendi modelim (Pyomo + HiGHS, Monte Carlo 10.000 simülasyon). Reel 2026 USD, %7 reel WACC."
    S = Sunum()

    # 1 — Başlık
    s = S.slayt("Ezine RES + batarya: edinimi şimdilik rafa kaldırmayı ve tetikleyicileri izlemeyi öneriyoruz")
    S.yazi(s, KENAR, 2.3, 11, 0.5, "Hibrit güneş–rüzgâr–batarya fizibilitesi · Çanakkale-Ezine · 50 MW şebeke bağlantısı",
           boyut=16, renk=IKINCIL)
    S.yazi(s, KENAR, 2.85, 11, 0.5, "Yatırım komitesi sunumu · Ekim 2026 · Ahmet Hilmi Görgülü", boyut=14, renk=IKINCIL)
    S.kutu(s, KENAR, 4.3, 3.8, 1.6, "Baz vaka beklenen NPV", f"{tr(e)} M$", f"kâr olasılığı %{baz['P(NPV > 0) [%]']:.0f}", renk=TURUNCU)
    S.kutu(s, KENAR + 4.05, 4.3, 3.8, 1.6, "Talep edilen karar", "Rafa kaldır", "durum tespiti bütçesi ve teklif yok", renk=SOLUK)
    S.kutu(s, KENAR + 8.1, 4.3, 3.8, 1.6, "Yeniden değerlendirme", "5 tetikleyici", "YEKDEM endeksleme, fiyat, CAPEX, SFK, kesinti")

    # 2 — Yönetici özeti
    s = S.slayt(f"Değer marjinal olarak negatif ({tr(e)}\u00a0M$): edinimi rafa kaldır, gözlenebilir tetikleyicileri izle",
                "Nihai baz vaka: inşaata hazır proje, COD Kasım 2029; RES 58,8 MW + batarya 30 MW / 60 MWh; YEKDEM yıllık opsiyonu + tüccar",
                KAYNAK)
    w = (G - 2 * KENAR - 0.75) / 4
    for i, (u, d, a, r) in enumerate([("Beklenen NPV", f"{tr(e)} M$", f"endeksli YEKDEM'de {tr(end['Beklenen NPV [M USD]'], '+.1f')} M$", TURUNCU),
                                      ("Kâr olasılığı P(NPV>0)", f"%{baz['P(NPV > 0) [%]']:.0f}", f"saf tüccarda %{tuc['P(NPV > 0) [%]']:.0f}", MAVI),
                                      ("En kötü %5 ortalaması", f"{tr(baz['CVaR %5 [M USD]'])} M$", "CVaR %5", TURUNCU),
                                      ("Başabaş beklenen fiyat", "≈ 59 $/MWh", "baz varsayım 58 $/MWh", MAVI)]):
        S.kutu(s, KENAR + i * (w + 0.25), 2.2, w, 1.6, u, d, a, r)
    S.yazi(s, KENAR, 4.2, G - 2 * KENAR, 2.8, [
        [("GES elendi. ", True), ("Güneş kendi öğle fiyatını düşürüyor; hiçbir optimal tasarıma girmedi.", False)],
        [("Batarya SFK geliri için. ", True), ("30 MW, ikili SFK katılım eşiği; piyasa doyarsa kaybı küçük, yavaş doyumda kazancı büyük.", False)],
        [("YEKDEM bir taban. ", True), (f"Her yıl seçilebilen opsiyon olarak değerli; 10 yıl kilitlemek E[NPV]'yi {tr(sabit['Beklenen NPV [M USD]'])} M$'a düşürüyor.", False)],
        [("Önceki +1,5 M$ bir tutarsızlıktı. ", True), ("Monte Carlo'da 58 fiyatın medyanıydı; ortalama 61,8'e çıkıyordu. Düzeltilince −1,7 M$.", False)],
        [("Durum tespitinin bilgi değeri sıfır. ", True), ("Olumlu sonuçlar bile E[NPV]'yi pozitife çevirmiyor; tek istisna YEKDEM endekslemesi.", False)],
    ], boyut=15)

    # 3 — Problem ve yaklaşım
    s = S.slayt("50 MW bağlantıya ne kurulmalı sorusunu saatlik optimizasyon ve 10.000 senaryolu risk modeliyle yanıtladık",
                "Soru: güneş, rüzgâr ve batarya kapasitelerinin hangi bileşimi şebeke kısıtı altında proje değerini en yüksek yapar ve bu yatırım belirsizlik altında yapılmalı mı?")
    adimlar = [("Üretim", "PVGIS, ERA5 · 10 hava yılı\nEPİAŞ santral verisiyle kalibrasyon"),
               ("Piyasa", "EPİAŞ PTF 2014–2026\nyakalama oranı, kanibalizasyon"),
               ("Optimizasyon", "Pyomo + HiGHS MILP\n8760 saat · kapasite + dispatch"),
               ("Finans", "NPV, IRR, DSCR, LCOE\nExcel modeli ile 48/48 mutabık"),
               ("Risk", "Monte Carlo 10.000 · SFK doyumu\ntakvim (CPM), kesinti, YEKDEM")]
    w = (G - 2 * KENAR - 4 * 0.35) / 5
    for i, (bas_, ack) in enumerate(adimlar):
        x = KENAR + i * (w + 0.35)
        S.kutu(s, x, 2.7, w, 2.2, f"{i + 1}", bas_, None, [MAVI, MAVI, YESIL, YESIL, TURUNCU][i], boyut=17)
        S.yazi(s, x + 0.25, 3.6, w - 0.4, 1.2, ack.split("\n"), boyut=11, renk=IKINCIL)
        if i < 4:
            ok = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + w + 0.07), Inches(3.65), Inches(0.21), Inches(0.3))
            ok.fill.solid(); ok.fill.fore_color.rgb = SOLUK; ok.line.fill.background(); ok.shadow.inherit = False
    S.yazi(s, KENAR, 5.4, G - 2 * KENAR, 1.2, [
        "Tüm varsayımlar kaynaklarıyla config.yaml'da; her optimizasyon modelinin matematiksel formülasyonu docs/ altında.",
        "Karar ölçütü: beklenen NPV, kâr olasılığı ve kuyruk riski (CVaR) birlikte; değer pozitif ama inceyse kademeli karar."],
        boyut=13, renk=IKINCIL)

    # 4 — Saha ve üretim
    s = S.slayt("Ezine dört aday saha arasında en güçlü rüzgâra sahip; model EPİAŞ santral verisiyle kalibre edildi",
                "Sol: aday sahaların kapasite faktörü. Sağ: komşu RES'in gerçek üretimi ile modelin yıllık karşılaştırması (ay × saat hız katsayısı).",
                "Kaynak: PVGIS-SARAH3, ERA5, EPİAŞ Şeffaflık Platformu; kendi modelim (pvlib, windpowerlib).")
    S.gorsel(s, KOK / "outputs/01_saha_taramasi/kapasite_faktorleri.png", x=KENAR, w=5.6)
    S.gorsel(s, KOK / "outputs/02_piyasa/kalibrasyon_yillik.png", x=KENAR + 5.9, w=G - 2 * KENAR - 5.9)

    # 5 — Piyasa
    s = S.slayt("Güneş kendi fiyatını düşürüyor: yakalanma oranı 2016'da %120, 2026'da %70; rüzgâr ortalamada kalıyor",
                "Yakalanma oranı = üretim ağırlıklı fiyat / ortalama fiyat. Öğle saatlerinde fiyat çöküyor (ördek eğrisi), gece ve akşam rüzgârı değerli.",
                "Kaynak: EPİAŞ PTF; Ezine üretim profilleri kendi modelim.")
    S.gorsel(s, KOK / "outputs/02_piyasa/yakalanma_orani_trendi.png")

    # 6 — Tasarım optimizasyonu
    s = S.slayt("GES hiçbir optimal tasarıma girmedi: güneş eklemek her senaryoda NPV'yi düşürüyor",
                "RES 58,8 MW sabit, 50 MW bağlantı. Hücre: en iyi tasarıma göre NPV farkı. Güneş, rüzgârın zaten doldurduğu bağlantıyla da çakışıyor.",
                KAYNAK)
    S.gorsel(s, KOK / "outputs/04_optimizasyon/b4_ges_bess_npv_izgara.png")

    # 7 — Batarya ve SFK doyumu
    s = S.slayt("Bataryanın değeri SFK'dan geliyor; piyasa doyarsa avantaj kayboluyor ama kayıp küçük kalıyor",
                "28–33 GW'lık depolama boru hattı ~1 GW'lık SFK ihtiyacını doyurabilir. Seçilen tasarım (F2 ailesi) yavaş doyumda kazanıyor, hızlı doyumda az kaybediyor.",
                "Kaynak: kendi modelim; doyum kalibrasyonu İngiltere DC ve Almanya FCR deneyimi; Türkiye depolama: EPDK, ETKB.")
    S.gorsel(s, KOK / "outputs/05_risk/s_senaryo_npv.png")

    # 8 — Gelir yapıları
    s = S.slayt("YEKDEM'i her yıl seçilebilen bir taban olarak kullanmak en iyi yapı, ama nominal koridorda değer yine negatif",
                "YEK Yönetmeliği md. 4/2, 5/1: katılım her yıl 30 Kasım'a kadar ayrı karar. Opsiyon, fiyat düştüğü yıllarda koridora sığınma hakkı veriyor.",
                KAYNAK)
    S.gorsel(s, GRAF / "gelir_yapilari.png")

    # 9 — Takvim
    s = S.slayt("İnşaata hazır proje Kasım 2029'da devrede; geliştirmeden başlamak COD'u 2032'ye itip YEKDEM hakkını kaybettiriyor",
                "CPM + Monte Carlo (üçgen süreler). Kritik yol: devir → finansman → türbin tedariki (12–30 ay) → montaj → devreye alma.",
                "Kaynak: kendi modelim; süreler ÇED özetleri, EPDK mevzuatı ve sektör kaynakları (docs/07).")
    S.gorsel(s, GRAF / "cod_dagilimi.png")

    # 10 — Risk kaydı
    s = S.slayt("En büyük riskler fiyat seviyesi, SFK doyumu ve takvim; azaltımlar hepsini kırmızı bölgeden çıkarıyor",
                "20 maddelik risk kaydı (outputs/07/risk_kaydi.xlsx): olasılık × etki, azaltım öncesi ve sonrası.",
                "Kaynak: kendi değerlendirmem (puanlar uzman yargısı); sayısal etkiler model çıktılarından.")
    S.gorsel(s, KOK / "outputs/07/risk_isi_haritasi.png")

    # 11 — Karar yolculuğu
    s = S.slayt("Karar beş kez değişti: iyimser SFK, kötümser sabit YEKDEM ve iyimser fiyat ortalaması varsayımları düzeltildi",
                "Her nokta o aşamadaki önerinin beklenen NPV'si. Tutarlılık 2: YEKDEM yıllık opsiyonu, ortak batarya sürücüsü, inşaata hazır takvim. Nihai: 58 $/MWh medyan değil beklenen değer.",
                KAYNAK)
    S.gorsel(s, GRAF / "karar_yolculugu.png")

    # 12 — Öneri, karar ve tetikleyiciler
    s = S.slayt("Talep: edinimi rafa kaldır; değeri pozitif gösteren fark fiyat ortalamasındaki bir ayar hatasıydı",
                "Deterministik baz (−2,4 M$) ile Monte Carlo arasındaki fark bileşenlere ayrıldı. Çubuk: düzeltme sonrası; nokta: öncesi (58 = medyan).",
                KAYNAK)
    S.gorsel(s, GRAF / "kopru.png", x=KENAR, y=2.2, w=7.4, h=4.7)
    S.yazi(s, KENAR + 7.8, 2.25, G - 2 * KENAR - 7.8, 4.6, [
        [("Durum tespiti bütçesi ve teklif yok", True)],
        "TEİAŞ, teşvik ve ornitoloji kalemleri olumlu sonuçlansa bile E[NPV] < 0: bilgi değerleri sıfır.",
        [("Yeniden değerlendirme tetikleyicileri", True)],
        f"1. YEKDEM koridoru endeksli teyit edilir (E[NPV] {tr(end['Beklenen NPV [M USD]'], '+.1f')} M$)",
        "2. Uzun vadeli fiyat beklentisi ≳ 60 $/MWh",
        "3. Türbin + EPC maliyeti ≳ %2 düşer",
        "4. 2027'de depolama < ~1 GW, SFK fiyatı korunur",
        "5. RES'lere sistem kesintisi 2027'de < %5",
        [("Pencere: ", True), ("tetikleyici 2027 ortasından sonra gelirse YEKDEM'e erişim riski artar.", False)],
    ], boyut=13)

    # 13 — Ek: yöntem ve varsayımlar
    s = S.slayt("Ek: sonuçlar kaynaklı varsayımlara ve Excel ile birebir mutabık bir finansal modele dayanıyor",
                kaynak="Tüm değerler config.yaml'da kaynak ve notlarıyla; formülasyonlar docs/00–07; Excel: outputs/08/Ezine_Hibrit_Finansal_Model.xlsx.")
    satir = [("Para birimi, iskonto", "Reel 2026 USD; %7 reel WACC (Damodaran ülke riski primiyle aşağıdan yukarı)"),
             ("CAPEX", "RES 1,15 M$/MW; batarya 110 bin $/MWh + 90 bin $/MW; şebeke bağlantısı ayrı (toplam 82,9 M$)"),
             ("Fiyat", "Baz 58 $/MWh reel; AR(1) fiyat yolları; 2 gün içi şekil yılı × 10 hava yılı"),
             ("Borç", "Nominal %8, DSCR'a göre boyutlama, azami %75 borç oranı"),
             ("Vergi", "%25 kurumlar vergisi, 10 yıl doğrusal amortisman, 5 yıl zarar mahsubu; teşvik belgesiyle KDV istisnası"),
             ("Optimizasyon", "Pyomo + HiGHS: tamsayı türbin sayısı, ikili yatırım kararı, saatlik dispatch; 24 temsilî gün / tam yıl"),
             ("Risk", "10.000 simülasyon, ortak rastgele sayılar (tohum 42): fiyat, hava, CAPEX, SFK doyumu, kesinti, takvim"),
             ("Doğrulama", "Excel modeli 48 senaryoda Python ile birebir; 0 formül hatası; 18 birim testi")]
    tab = s.shapes.add_table(len(satir), 2, Inches(KENAR), Inches(1.75), Inches(G - 2 * KENAR), Inches(4.9)).table
    tab.columns[0].width, tab.columns[1].width = Inches(2.6), Inches(G - 2 * KENAR - 2.6)
    for i, (a, d) in enumerate(satir):
        for j, metin in enumerate((a, d)):
            h = tab.cell(i, j)
            h.text = metin
            h.fill.solid(); h.fill.fore_color.rgb = ZEMIN if i % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF)
            for par in h.text_frame.paragraphs:
                for r in par.runs:
                    r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(12.5), j == 0, MUREKKEP, YAZI_TIPI

    pptx = CIKTI / "Sunum.pptx"
    S.p.save(pptx)
    print(f"Kaydedildi: {pptx.relative_to(KOK)} ({S.no} slayt)")
    soffice = next((str(p) for p in SOFFICE if p.exists()), None)
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(CIKTI), str(pptx)],
                       check=True, capture_output=True)
        print(f"Kaydedildi: {(CIKTI / 'Sunum.pdf').relative_to(KOK)}")
    else:
        print("LibreOffice bulunamadı; PDF üretilmedi.")


if __name__ == "__main__":
    main()
