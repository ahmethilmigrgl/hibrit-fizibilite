# Hibrit GES + RES + BESS Fizibilite Modeli (Türkiye)

> 🚧 Geliştirme aşamasında — portföy projesi.

Türkiye'de seçilen bir saha için güneş (GES), rüzgâr (RES) ve batarya (BESS) kapasitelerini,
şebeke bağlantı kısıtı altında **NPV'yi en yüksek yapacak** şekilde boyutlandıran ve sonucu
**Monte Carlo** ile belirsizlik altında test eden fizibilite modeli.

## Yöntem (özet)
1. Saha seçimi ve çok yıllı saatlik üretim profilleri (PVGIS/pvlib, ERA5)
2. Piyasa analizi (EPİAŞ PTF, yakalanan fiyat, kanibalizasyon)
3. Finansal model (NPV, IRR, LCOE)
4. Kapasite + dispatch optimizasyonu (Pyomo + HiGHS, MILP)
5. Risk simülasyonu (Monte Carlo, P50/P90, tornado)
6. Streamlit dashboard

## Kurulum
```bash
uv venv --python 3.11 .venv
uv pip install -r requirements.txt --python .venv/bin/python
cp .env.example .env   # CDS ve EPİAŞ bilgilerini doldurun
.venv/bin/python src/00_kurulum_testi.py      # ısınma LP modeli
.venv/bin/python src/01_saha_taramasi.py      # Aşama 1: 4 saha taraması
.venv/bin/python src/01_uretim_profilleri.py  # Aşama 1: Ezine 10 yıllık profiller
.venv/bin/python src/02_piyasa_verisi.py      # Aşama 2: EPİAŞ verisi (önbellekli)
.venv/bin/python src/02_ruzgar_kalibrasyonu.py # Aşama 2: rüzgâr kalibrasyonu (öneri k)
.venv/bin/python src/02_piyasa_analizi.py     # Aşama 2: yakalanan fiyat, batarya göstergeleri
.venv/bin/python src/03_finansal_model.py     # Aşama 3: NPV/IRR/LCOE, borç, duyarlılık
```

## Klasör yapısı
| Klasör | İçerik |
|---|---|
| `src/` | Modüller ve scriptler |
| `notebooks/` | Analiz defterleri |
| `data/raw`, `data/processed` | Veri (git'e eklenmez) |
| `outputs/` | Grafikler ve sonuçlar |
| `docs/` | Matematiksel formülasyonlar ve açıklamalar |
| `config.yaml` | Tüm varsayımlar ve kaynakları |

## Sonuçlar

### Aşama 1 — Saha seçimi ve üretim modeli ✅
Dört aday saha (Çanakkale-Ezine, Balıkesir-Bandırma, İzmir-Aliağa, Konya-Karapınar) PVGIS ve ERA5
verisiyle tarandı. **Çanakkale-Ezine** seçildi: en yüksek rüzgâr kaynağı ve en güçlü GES–RES
tamamlayıcılığı.

| Ezine, 2014–2023 | 1 MW GES | 1 MW RES | 1+1 MW / 1 MW bağlantı |
|---|---|---|---|
| Ortalama kapasite faktörü | %20,6 | %37,7 | %52,6 (bağlantı kullanımı) |
| P50 [MWh/yıl] | 1.815 | 3.328 | 4.652 |
| P90 [MWh/yıl] (normal) | 1.741 | 3.057 | 4.390 |
| Yıllar arası değişkenlik katsayısı | %2,6 | %5,7 | %3,7 |
| Hibrit kesinti | — | — | %9,6 |

RES değerleri Aşama 2'de Ezine'deki gerçek santral üretimiyle kalibre edildi: ERA5'in kaçırdığı
öğleden sonraki deniz meltemi pikini düzelten ay × saat hız katsayısı matrisi, dönem bölmeli
çapraz doğrulamayla seçildi. Revizyonun etkisi: [docs/01, Revizyon](docs/01_uretim_modeli.md).

![Aylık kapasite faktörü](outputs/01_uretim_modeli/aylik_kapasite_faktoru.png)

Ayrıntılar, doğrulama ve sınırlamalar: [docs/01_uretim_modeli.md](docs/01_uretim_modeli.md)

### Aşama 2 — Piyasa analizi ve rüzgâr kalibrasyonu ✅
EPİAŞ Şeffaflık Platformu'ndan 2014–2026 saatlik PTF ve üretim verisi çekildi (yaz saati geçişleri
ele alınarak UTC'ye çevrildi).

| Yakalanma oranı (yakalanan / ortalama PTF, USD) | 2016 | 2023 | 2025 | 2026 (Oca–Eyl) |
|---|---|---|---|---|
| Ezine GES | 1,21 | 0,92 | 0,82* | 0,71* |
| Ezine RES | 1,01 | 0,96 | 0,94* | 1,00* |
| Ezine hibrit (1+1 MW / 1 MW) | 1,07 | 0,96 | 0,92* | 0,91* |
| Türkiye güneş şekli | — | 0,90 | 0,83 | 0,75 |

\* 2024 sonrası: 10 hava yılı × gerçek fiyat, eşzamanlılık düzeltmeli.

- **Güneş kanibalizasyonu:** Kurulu güneş 25 GW'a çıktıkça öğle fiyatları çöktü. Akşam/öğle fiyat oranı 2015'te 0,89, 2025'te 1,60, 2026'da 2,33.
- **Batarya göstergeleri:** 2026'da 10 $/MWh altındaki saat sayısı 1.564 ve günlük spread ortalama fiyatın 1,4 katı.
- **2022–2023 azami uzlaştırma fiyatı (AUF):** YEKDEM dışı yenilenebilir gelirlerini ~%44 kırptı.

![Yakalanma oranı trendi](outputs/02_piyasa/yakalanma_orani_trendi.png)

Ayrıntılar: [docs/02_piyasa_analizi.md](docs/02_piyasa_analizi.md)

### Aşama 3 — Finansal model ✅
Reel USD bazlı proje finansmanı modeli. Saatlik üretim × saatlik fiyat (3 seviye × 2 kanibalizasyon
senaryosu), Türkiye'ye özgü TEİAŞ bedelleri, dengesizlik ve vergi; P90'a göre borç boyutlandırma.

| 50 MW bağlantı, baz fiyat 58 $/MWh, kanibalizasyon devam | (a) RES 50 | (b) RES 50 + GES 25 | (c) RES 50 + GES 50 | (d) GES 50 |
|---|---|---|---|---|
| NPV [M$, %7 reel WACC] | −2,5 | −8,0 | −16,3 | −15,6 |
| Proje IRR (reel) | 6,5% | 5,8% | 4,8% | 1,0% |
| LCOE satılan enerji [$/MWh] | 50,5 | 50,1 | 52,1 | 51,3 |
| Yakalanan fiyat [$/MWh] | 54,5 | 51,0 | 49,5 | 35,5 |
| Kesinti | 0% | 2,2% | 8,1% | 0% |

- **En etkili değişkenler:** fiyat seviyesi, CAPEX ve WACC.
- **Ek GES'in değeri azalıyor:** İkinci 25 MW'ın enerjisinin %40'ı kesiliyor. Bu da batarya ve kapasite optimizasyonunu (Aşama 4) gerekli kılıyor.

![Konfigürasyon karşılaştırması](outputs/03_finans/konfigurasyon_karsilastirma.png)

Ayrıntılar: [docs/03_finansal_model.md](docs/03_finansal_model.md) · Excel: `outputs/03_finans/nakit_akisi_b.xlsx`
