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
| Ortalama kapasite faktörü | %20,6 | %34,5 | %52,1 (bağlantı kullanımı) |
| P50 [MWh/yıl] | 1.815 | 3.060 | 4.620 |
| P90 [MWh/yıl] (normal) | 1.741 | 2.766 | 4.316 |
| Yıllar arası değişkenlik katsayısı | %2,6 | %6,6 | %4,2 |

![Aylık kapasite faktörü](outputs/01_uretim_modeli/aylik_kapasite_faktoru.png)

Ayrıntılar, doğrulama ve sınırlamalar: [docs/01_uretim_modeli.md](docs/01_uretim_modeli.md)
