---
license: other
license_name: mixed-cc-by-4.0-odbl-1.0
language: [tr, en]
pretty_name: Hibrit Fizibilite — Türkiye rüzgâr, güneş ve CBS veri paketi
tags: [wind, solar, era5, pvgis, global-wind-atlas, openstreetmap, turkey, renewable-energy]
---

# Hibrit Fizibilite — Türkiye veri paketi (v1)

Bu veri deposu, "hibrit-fizibilite" web uygulamasının (Türkiye'de herhangi bir saha için hibrit GES/RES/batarya
fizibilitesi; kaynak kod: https://github.com/ahmethilmigrgl/hibrit-fizibilite) çalışma anında indirdiği grid verilerini içerir.
Uygulama yalnız seçilen sahanın hücre dosyalarını indirir. Düzen, uygulamanın `data/` klasörüyle birebir aynıdır.

## İçerik ve lisanslar

| Yol | İçerik | Kaynak | Lisans |
|---|---|---|---|
| `grid/era5_tr/v1/{enlem}_{boylam}.npz` (+ `manifest.json`) | Türkiye karasına değen 1.464 ERA5 0,25° hücresi, 2014–2023 saatlik 100 m / 10 m rüzgâr hızı, sıcaklık, basınç (uint16) | ERA5, Copernicus C3S | CC BY 4.0 |
| `grid/era5_yon_tr/v1/...` | Aynı hücreler için 100 m rüzgâr yönü (16 sektör) | ERA5, Copernicus C3S | CC BY 4.0 |
| `grid/pvgis_tr/v1/...` (+ `manifest.json`) | Hücre başına saatlik GES kapasite faktörü (PVGIS-SARAH3 ışınımı + pvlib) | PVGIS © European Communities | CC BY 4.0 (atıflı) |
| `grid/gwa_tr/v1/karolar/...`, `gwa_tr_250m_ws100_cog.tif` | Global Wind Atlas 3, 100 m ortalama hız, 250 m | DTU / Dünya Bankası (GWA 3.0) | CC BY 4.0 |
| `grid/rakim_tr/v1/rakim_002.npz` | Rakım ızgarası | Copernicus DEM GLO-90 | Copernicus DEM lisansı (atıflı, ücretsiz) |
| `grid/egim_tr/v1/...` | Eğim ızgarası (1° karolar) | Copernicus DEM GLO-90 türevi | Copernicus DEM lisansı |
| `grid/cbs_tr/v1/...` | Dışlama katmanları (yerleşim, yol, hat, koruma alanı mesafeleri; 1° karolar) | OpenStreetMap türevi | **ODbL 1.0** |
| `grid/lojistik_tr/v1/ag.npz` | Ağır nakliye yol ağı (düğüm/kenar) | OpenStreetMap türevi | **ODbL 1.0** |

## Atıflar

- **Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is
  responsible for any use that may be made of the Copernicus information or data it contains.** (ERA5: Hersbach et al.,
  DOI 10.24381/1cf1ad76.)
- PVGIS © European Communities, 2001–2026 (PVGIS-SARAH3).
- **Global Wind Atlas 3.0, a free, web-based application developed, owned and operated by the Technical University of Denmark
  (DTU). The Global Wind Atlas 3.0 is released in partnership with the World Bank Group, utilizing data provided by Vortex,
  using funding provided by the Energy Sector Management Assistance Program (ESMAP). For additional information:
  https://globalwindatlas.info.**
- Copernicus DEM GLO-90 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the
  European Union and ESA; all rights reserved.
- © OpenStreetMap katkıcıları. ODbL 1.0 ile işaretli dosyalar Open Database License ile paylaşılır
  (https://opendatacommons.org/licenses/odbl/1-0/); kullanan ya da değiştiren aynı lisansla paylaşmalıdır.

Değişiklikler: Türkiye kesiti, birim dönüşümü ve uint16 kuantalama, hücre/karo bölme. Ayrıntılı kaynak listesi:
`DATA_SOURCES.md` (GitHub reposu).

## Sürümleme

Dosyalar sürüm klasöründe (`v1`) tutulur; uygulama `v1` etiketine sabitlenir. Biçim değişirse yeni klasör ve etiket açılır.
