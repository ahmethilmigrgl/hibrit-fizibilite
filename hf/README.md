---
license: cc-by-4.0
language: [tr, en]
pretty_name: Hibrit Fizibilite — Türkiye ERA5 nokta gridi ve GWA 250 m karoları
tags: [wind, solar, era5, global-wind-atlas, turkey, renewable-energy]
---

# Hibrit Fizibilite — Türkiye rüzgâr veri paketi (v1)

Bu veri deposu, "hibrit-fizibilite" web uygulamasının (Türkiye'de herhangi bir saha için hibrit GES/RES/batarya fizibilitesi)
çalışma zamanında indirdiği rüzgâr verilerini içerir. Uygulama yalnız gereken tek nokta dosyasını ve 1–4 karoyu indirir.

## İçerik

| Yol | İçerik | Biçim |
|---|---|---|
| `era5_tr/v1/manifest.json` | Nokta listesi, dosya boyutu, sha256 | JSON |
| `era5_tr/v1/noktalar/{enlem}_{boylam}.npz` | Türkiye karasına değen 1.464 ERA5 0,25° hücresi, 2014–2023 saatlik (UTC) | `v100`, `v10` uint16 cm/s; `t2m` uint16 K×50; `sp` uint16 Pa/2; `bas` ISO başlangıç |
| `gwa_tr/v1/karolar/{enlem0}_{boylam0}.npz` | Global Wind Atlas 3, 100 m ortalama hız, 250 m, 1° × 1° karolar | `ws` uint16 cm/s; `ust`, `sol`, `adim` |
| `gwa_tr/v1/gwa_tr_250m_ws100_cog.tif` | Aynı GWA verisi, Cloud Optimized GeoTIFF (EPSG:4326) | uint16 cm/s, deflate |

## Kaynaklar, lisanslar ve atıflar

- **ERA5** (`era5_tr/`): Hersbach et al., *ERA5 hourly time-series data on single levels from 1940 to present*, Copernicus Climate
  Change Service (C3S) Climate Data Store, DOI 10.24381/1cf1ad76. Lisans: CC-BY (C3S). Hız büyüklüğüne indirgenip kuantalandı.
  **Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is
  responsible for any use that may be made of the Copernicus information or data it contains.**
- **Global Wind Atlas 3.0** (`gwa_tr/`): CC BY 4.0. **Global Wind Atlas 3.0, a free, web-based application developed, owned and
  operated by the Technical University of Denmark (DTU). The Global Wind Atlas 3.0 is released in partnership with the World Bank
  Group, utilizing data provided by Vortex, using funding provided by the Energy Sector Management Assistance Program (ESMAP).
  For additional information: https://globalwindatlas.info.** Değişiklik: Türkiye kesiti, uint16 kuantalama, 1° karolar.

Bu deponun tamamı, yukarıdaki kaynak lisanslarına uygun olarak CC BY 4.0 ile paylaşılır.

## Sürümleme

Dosyalar sürüm klasöründe (`v1`) tutulur; uygulama `revision = "v1"` etiketiyle sabitlenir. Biçim değişirse `v2` klasörü ve yeni
etiket açılır; eski sürüm silinmez.
