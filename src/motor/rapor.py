"""Tam analiz için otomatik saha raporu: HTML (grafikler gömülü) ve PDF (Chrome/Chromium headless)."""

from __future__ import annotations

import base64
import html
import io
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import src.gorsel as g
from src.ayarlar import KOK

KLASOR = KOK / "data" / "onbellek" / "rapor"
ATIFLAR = [
    "ERA5: Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.",
    "Weather data by Open-Meteo.com (CC BY 4.0), when used as fallback.",
    "PVGIS © European Communities, 2001-2026 (PVGIS-SARAH3).",
    "Global Wind Atlas 3.0 (DTU, World Bank Group, Vortex, ESMAP) — CC BY 4.0.",
    "Kaynak: EPİAŞ Şeffaflık Platformu (seffaflik.epias.com.tr).",
    "Santral konumları ve sınırlar © OpenStreetMap katkıcıları (ODbL); geoBoundaries (Runfola et al. 2020).",
]
SINIRLAMALAR = [
    "Rüzgâr: saha ölçümü yok; ERA5 + GWA + kalibrasyon atlası aktarımı. Hata dağılımı güven seviyesinden Monte Carlo'ya taşınır.",
    "Türbin yerleşimi basit: iz kayıpları toplu kayıp oranıyla; erişim, eğim, arazi kullanımı, koruma alanı ve izinler modellenmez.",
    "Dispatch mükemmel öngörülü (yıllık LP); işletme tabloları azaltılmış ızgarayla çalışma anında üretilir (Ezine'de E[NPV] farkı ~0,01 M$).",
    "Piyasa parametreleri (SFK doyumu, kesinti tazmini, YEKDEM endekslemesi, PPA iskontosu) tahmindir; v1 docs/MODEL_DOGRULAMA.md.",
    "Takvim dağılımı v1 CPM örneklerinden (Türkiye geneli için ortak); sahaya özgü izin süreleri modellenmez.",
]


def _png(fig) -> str:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(b.getvalue()).decode()


def grafikler(s) -> dict[str, str]:
    gr = s.grafikler
    out = {}
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.4))
    d = gr["gunici"]
    axs[0].plot(d["saat"], np.array(d["res"]) * 100, color=g.RENK_RES, lw=2, label="RES")
    axs[0].plot(d["saat"], np.array(d["ges"]) * 100, color=g.RENK_GES, lw=2, label="GES")
    axs[0].set_title("Gün içi kapasite faktörü (TSİ)", loc="left")
    axs[0].set_xlabel("Saat")
    axs[0].set_ylabel("%")
    axs[0].legend()
    d = gr["aylik"]
    axs[1].plot(d["ay"], np.array(d["res"]) * 100, color=g.RENK_RES, lw=2, marker="o", label="RES")
    axs[1].plot(d["ay"], np.array(d["ges"]) * 100, color=g.RENK_GES, lw=2, marker="o", label="GES")
    axs[1].set_title("Aylık kapasite faktörü", loc="left")
    axs[1].set_xlabel("Ay")
    for a in axs:
        g.eksen_sade(a)
    out["profil"] = _png(fig)
    if "npv_histogram" in gr:
        fig, ax = plt.subplots(figsize=(10, 3.4))
        renk = {"tuccar": g.RENK_RES, "yekdem_opsiyon": "#7f6bd1", "ppa": g.RENK_HIBRIT}
        for y, say in gr["npv_histogram"]["sayi"].items():
            k = np.array(gr["npv_histogram"]["kenar"][y])
            ax.step((k[:-1] + k[1:]) / 2, np.array(say) / max(1, sum(say)), where="mid", color=renk.get(y, g.SOLUK), lw=2, label=y)
        ax.axvline(0, color=g.MUREKKEP, lw=0.8)
        ax.set_title("NPV dağılımı (Monte Carlo)", loc="left")
        ax.set_xlabel("NPV [M USD]")
        ax.set_ylabel("Pay")
        ax.legend()
        g.eksen_sade(ax)
        out["npv"] = _png(fig)
    return out


def html_uret(s) -> str:
    o, sa = s.ozet, s.saha
    k = o["karar"]
    gr = grafikler(s)
    e = lambda x: html.escape(str(x))
    sat = lambda x, d=1: "—" if x is None else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    gy = s.tablolar["gelir_yapilari"].reset_index()
    tablo_gy = "".join(
        f"<tr><td>{e(r.ad_tr)}</td><td>{sat(r.e_npv, 2)}</td><td>±{sat(r.se, 2)}</td><td>%{sat(100 * r.p_pozitif, 0)}</td>"
        f"<td>{sat(r.cvar5)}</td><td>{sat(r.p10)} / {sat(r.p90)}</td><td>{r.n}</td></tr>"
        for r in gy.itertuples()
    )
    t = o["tasarim"]
    gv = o["guven"]
    tetik = "".join("<li>" + e(x["tr"]) + "</li>" for x in o["tetikleyiciler"])
    varsay = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in s.varsayimlar.items() if a not in ("ekstra",))
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>Saha raporu — {e(sa["ad"])}</title>
<style>body{{font-family:Arial,Helvetica,sans-serif;font-size:10pt;color:#1b1b1b;max-width:900px;margin:24px auto;line-height:1.4}}
h1{{font-size:18pt;margin:0}} h2{{font-size:12.5pt;border-bottom:1.5px solid #1baf7a;padding-bottom:2px;margin-top:18px}}
table{{border-collapse:collapse;width:100%;font-size:9pt;margin:6px 0}} th,td{{border:0.6pt solid #d0cfca;padding:3px 5px;text-align:left}}
th{{background:#f0efeb}} .kutu{{background:#f5f9f6;border-left:3pt solid #1baf7a;padding:8px 12px;margin:8px 0}} img{{max-width:100%}}
.kucuk{{font-size:8pt;color:#666}}</style></head><body>
<h1>Saha raporu — {e(sa["ad"])}</h1>
<p class="kucuk">{e(sa.get("il"))} / {e(sa.get("ilce"))} · {sa["enlem"]:.4f}, {sa["boylam"]:.4f} · bağlantı {sat(sa["baglanti_mw"], 0)} MW · TEİAŞ tarife bölgesi {e(sa["tarife_bolgesi"])} ·
türbin {e(sa["turbin"]["turbin"])} @{e(sa["turbin"]["gobek"])} m · veri sürümü {e(s.veri_surumu)}</p>
<div class="kutu"><b>Öneri: {e(k["tr"])}</b><br>En iyi gelir yapısı: {e(dict(zip(gy["yapi"], gy["ad_tr"])).get(o["en_iyi_yapi"], o["en_iyi_yapi"]))} — beklenen NPV {sat(o["baz"]["e_npv"], 1)} M$
(±{sat(o["baz"]["se"], 2)} standart hata), kâr olasılığı %{sat(100 * o["baz"]["p_pozitif"], 0)}, CVaR %5 {sat(o["baz"]["cvar5"])} M$,
azami edinim primi {sat(k["azami_prim"], 1)} M$.</div>
<h2>1. Tasarım ve üretim</h2>
<p>Tasarım: RES {sat(t["res_mw"])} MW, GES {sat(t["ges_mw"], 0)} MW, batarya {sat(t["bess_mw"], 0)} MW / {sat(t["bess_mwh"], 0)} MWh
(SFK katılımı: {"evet" if o["sfk_katilimi"] else "hayır"}). RES kapasite faktörü %{sat(100 * o["res_kf"])} (güven bandı %{sat(100 * o["res_kf_bandi_medyan"][0])}–%{sat(100 * o["res_kf_bandi_medyan"][1])},
%90: %{sat(100 * o["res_kf_bandi_p90"][0])}–%{sat(100 * o["res_kf_bandi_p90"][1])}); GES %{sat(100 * o["ges_kf"])}.</p>
<img src="data:image/png;base64,{gr["profil"]}">
<h2>2. Rüzgâr tahmininin güven seviyesi</h2>
<p><b>{e(gv["seviye"])}</b> — tipik kapasite faktörü hatası ±{sat(gv["medyan_puan"])} puan (medyan), %90'da ±{sat(gv["p90_puan"])} puan.
Komşu kalibre santraller: {e(", ".join(gv.get("komsu") or []) or "yok")}. Monte Carlo'da RES model belirsizliği σ = %{sat(100 * (o["res_sigma"] or 0))}.</p>
<h2>3. Gelir yapıları (Monte Carlo)</h2>
<table><tr><th>Yapı</th><th>E[NPV] [M$]</th><th>Std. hata</th><th>P(NPV&gt;0)</th><th>CVaR %5</th><th>P10 / P90</th><th>n</th></tr>{tablo_gy}</table>
{'<img src="data:image/png;base64,' + gr["npv"] + '">' if "npv" in gr else ""}
<p>Takvim ({e(o["takvim"]["proje_asamasi"])}): COD P50 {e(o["takvim"]["cod_p50"])}, P80 {e(o["takvim"]["cod_p80"])};
YEKDEM için COD ≤ 2030 olasılığı %{sat(100 * o["takvim"]["p_cod_2030_oncesi"], 0)}. Başabaş beklenen fiyat ≈ {sat(o["basabas_fiyat"], 0)} $/MWh
(senaryo {sat(o["fiyat_seviyesi"], 0)}).</p>
<h2>4. Tetikleyiciler</h2><ul>{tetik}</ul>
<h2>5. Varsayımlar</h2><table>{varsay}</table>
<h2>6. Sınırlamalar</h2><ul>{"".join(f"<li>{e(x)}</li>" for x in SINIRLAMALAR)}</ul>
<h2>7. Veri atıfları</h2><ul class="kucuk">{"".join(f"<li>{e(x)}</li>" for x in ATIFLAR)}</ul>
<p class="kucuk">Otomatik üretilmiştir (hibrit-fizibilite v2 analiz motoru). Yatırım tavsiyesi değildir.</p></body></html>"""


def uret(s, anahtar: str) -> dict:
    """HTML ve (Chrome bulunursa) PDF; yolları döndürür."""
    from importlib import import_module

    klasor = KLASOR / f"{s.saha['kod']}_{anahtar[:10]}"
    klasor.mkdir(parents=True, exist_ok=True)
    h = klasor / "rapor.html"
    h.write_text(html_uret(s), encoding="utf-8")
    out = {"html": str(h)}
    chrome = import_module("src.06_rapor_pdf").chrome_bul()
    if chrome:
        pdf = klasor / "rapor.pdf"
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", h.as_uri()],
            check=False,
            capture_output=True,
            timeout=120,
        )
        if pdf.exists():
            out["pdf"] = str(pdf)
    return out
