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
.venv/bin/python src/00_kurulum_testi.py
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
_Henüz yok._
