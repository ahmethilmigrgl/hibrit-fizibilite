# Hybrid Wind + Solar + Battery Feasibility Model (Türkiye)

[![CI](https://github.com/KULLANICI/hibrit-fizibilite/actions/workflows/ci.yml/badge.svg)](https://github.com/KULLANICI/hibrit-fizibilite/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
[![License: MIT (code)](https://img.shields.io/badge/license-MIT%20(code)-green.svg)](LICENSE)

[Türkçe](README.tr.md) · **Live dashboard:** _link will be added after deployment_

**Documents (Turkish):** [Investment memo (PDF)](outputs/08/Yatirim_Memosu.pdf) · [Presentation (PDF)](outputs/08/Sunum.pdf) ·
[Full report (PDF)](outputs/RAPOR.pdf) · [Excel financial model](outputs/08/Ezine_Hibrit_Finansal_Model.xlsx)

**v2 (branch `v2-genel`, release candidate):** a **Türkiye-wide site screening and analysis app**. Pick any point on land and
get a quick scan in seconds or a full optimisation + Monte Carlo analysis in minutes; see [Türkiye-wide app](#türkiye-wide-app-v2).
The original Ezine study (v1.0.0) remains as a case study below.

The case study sizes solar (PV), wind and battery storage behind a **50 MW grid connection** at Çanakkale-Ezine, Türkiye, to
**maximise project NPV**. It then stress-tests that answer under uncertainty. The pipeline goes end to end:

- **Generation:** hourly profiles from satellite and reanalysis data, with wind calibrated against nearby operating wind farms.
- **Market:** 12 years of Turkish day-ahead and ancillary-service prices.
- **Finance:** a project-finance model in real USD.
- **Optimisation:** a capacity MILP in Pyomo + HiGHS.
- **Risk:** a 10,000-scenario Monte Carlo, including a stress test of how quickly batteries saturate the secondary-reserve market.

It is a portfolio project. Every assumption is sourced in `config.yaml`, and every optimisation model is written out
mathematically in `docs/`.

## Türkiye-wide app (v2)

Run locally with one command (after the environment and data packages are in place, see [How to run](#how-to-run)):

```bash
.venv/bin/streamlit run app.py          # → http://localhost:8501
```

- **Opening screen:** a pre-screening map of all 1,464 land cells (0.25°) of Türkiye. The default layer is the break-even
  price of the best standard design; wind/solar capacity factors and break-evens are selectable. Low-confidence cells are
  hatched, and calibrated wind farms form their own layer.
- **Site selection:** click the map, type coordinates, or choose a province/district to see its windiest candidate points.
  The selected point shows its GWA wind speed, confidence level and the calibrated wind farms it relies on.
- **Quick scan (seconds):** capacity factors with an uncertainty band, capture rates, LCOE, break-even price, the rank among
  Türkiye's cells, standard designs, a representative-day optimisation and a "worth a full analysis?" check.
- **Full analysis (1–6 min):** full-year capacity MILP, run-time dispatch tables, converging Monte Carlo, revenue structures
  (merchant / annual YEKDEM option / PPA), schedule by project stage, recommendation and triggers, and an HTML/PDF site report.
- **Sharing:** every result reopens from a share link (URL parameters + result cache).
- **Data:** the app reads only local, pre-built data packages through one data-access layer (`src/veri_katmani.py`): the ERA5
  grid, the PVGIS solar grid, Global Wind Atlas, the calibration atlas and the market package. It never calls external APIs
  or uses personal credentials at run time.
- **Docs:** [data infrastructure](docs/v2_A_veri_altyapisi.md), [analysis engine](docs/v2_B_analiz_motoru.md),
  [app](docs/v2_C_arayuz.md).

<p align="center"><img src="docs/img/v2/01_acilis_harita_masaustu.png" width="85%" alt="Pre-screening map"></p>

## Case study (v1.0.0): key findings

| # | Finding | Number |
|---|---|---|
| 1 | **Solar never enters the optimal design.** Turkish solar capture rates collapsed as installed PV reached 25 GW, and afternoon sea breezes make wind and solar peak together behind the shared connection. | Solar capture rate 1.21 (2016) → 0.71 (2026); 14–40% of added PV is curtailed |
| 2 | **Merchant wind alone is not investable** at today's price expectations. | NPV −1.6 M$, break-even 59 $/MWh, P(NPV > 0) 42% |
| 3 | **Battery value comes almost entirely from secondary-reserve (SFK) capacity payments**, not arbitrage. | 87% of battery revenue; NPV −1.6 → +26 M$ in the no-saturation case |
| 4 | **The saturation stress test changed the recommendation.** The SFK market needs ~1 GW against 28–33 GW of storage pre-licences. A supply–demand model calibrated on GB, Germany and Australia turns the battery into an *option*. | P(NPV > 0) for the 40 MW battery design: 97% → 59%; CVaR 5%: −2.5 → −30 M$ |
| 5 | **The valuable flexibility is deferring battery scale, not adding duration.** A 30 MW battery (the SFK entry threshold) with a conditional expansion beats both a 40 MW and a 4-hour battery. Waiting to learn costs more than the information is worth. | E[NPV] +6.3 M$ (staged) vs −0.4 M$ (4-hour); 1-year delay −2.1 M$ |
| 6 | **Real-world frictions and three consistency checks set the final answer.** Wind curtailment started in 2026; a CPM + Monte Carlo schedule puts COD at Nov 2029 for a ready-to-build project (May 2032 from a pre-licence). Under YEKDEM the battery cannot arbitrage. YEKDEM turned out to be an **annual option** (participation chosen each 30 Nov), not a 10-year lock-in. Option worth +0.5 M$ over merchant; 10-year fixed YEKDEM −12.3 M$ |
| 7 | **Reconciling deterministic and Monte Carlo values flipped the sign.** The deterministic base was −2.4 M$ but the Monte Carlo mean was +1.5 M$, even for pure merchant. The log-price process had been centred on 58 as its *median*; the lognormal skew lifted the simulated mean price to 61.8 $/MWh. Calibrated to an expected 58, the gap is explained component by component. | Base case +1.5 → **−1.7 M$**, P(NPV>0) 50% → 42% |

**Recommendation: shelve the acquisition and monitor triggers. No due-diligence budget and no offer for now.**

- **Final base case** (`config.yaml → nihai_baz_vaka`): COD Nov 2029, 58.8 MW wind + 30 MW / 60 MWh battery, YEKDEM
  annual option (nominal corridor) plus merchant.
- **Result:** expected NPV **−1.7 M$**, probability of profit **42%**, CVaR 5% −28.0 M$, maximum premium 0.
- **Sensitivity:** value is thin (break-even expected price ≈ 59 $/MWh). Indexed YEKDEM corridor +0.4 M$; pure merchant
  −2.1 M$; PPA −6.1 M$. Due-diligence items have zero value of information: even good news leaves E[NPV] negative.
- **Triggers to revisit:** YEKDEM corridor confirmed as indexed; long-term price expectations ≳ 60 $/MWh; turbine + EPC
  cost ≳ 2% below base; slow storage build-out (SFK prices hold in 2027).
  See the [report](docs/RAPOR.md#10-öneri).

<p align="center">
  <img src="outputs/05_risk/s_risk_getiri.png" width="85%"><br>
  <em>Risk–return before (hollow) and after (filled) modelling ancillary-service saturation. Labels in Turkish.</em>
</p>

<p align="center">
  <img src="outputs/02_piyasa/yakalanma_orani_trendi.png" width="85%"><br>
  <em>Solar cannibalisation in Türkiye: capture rates of solar vs wind, 2014–2026.</em>
</p>

<p align="center">
  <img src="outputs/05_risk/s_firsat_penceresi.png" width="85%"><br>
  <em>Opportunity window: NPV if secondary-reserve revenue lasts only N years.</em>
</p>

## Case-study dashboard (v1)

<p align="center"><img src="docs/img/dashboard.gif" width="85%" alt="Dashboard"></p>

| | |
|---|---|
| <img src="docs/img/dashboard_ozet.jpg" alt="Summary"> | <img src="docs/img/dashboard_gezgin.jpg" alt="Design explorer"> |
| <img src="docs/img/dashboard_risk.jpg" alt="Risk"> | <img src="docs/img/dashboard_piyasa.jpg" alt="Market"> |

*Summary, design explorer, risk and market tabs (Turkish UI; an English toggle is built in). The layout also works on a 390 px phone screen.*

## Method

```mermaid
flowchart LR
    A[Data<br/>PVGIS · ERA5 · EPİAŞ] --> B[Generation<br/>pvlib · windpowerlib<br/>month×hour wind calibration]
    B --> C[Market<br/>capture prices · cannibalisation<br/>ancillary services]
    C --> D[Finance<br/>real-USD cash flows · tax<br/>P90-sculpted debt]
    D --> E[Optimisation<br/>Pyomo + HiGHS<br/>dispatch LP · capacity MILP]
    E --> F[Risk<br/>Monte Carlo · EVPI<br/>saturation stress test]
    F --> G[Dashboard & report]
```

| Stage | What | Docs |
|---|---|---|
| 1 Site & generation | Four candidate sites screened; 10 years of hourly PV (PVGIS-SARAH3 + pvlib PVWatts) and wind (ERA5 + Enercon E-141 power curve, 120 m) profiles | [docs/01](docs/01_uretim_modeli.md) |
| 2 Market & calibration | EPİAŞ prices 2014–2026 (DST-safe UTC conversion), capture rates, duck curve. ERA5 wind calibrated with a month × hour speed factor against three wind farms (cross-validated; hourly-profile error ÷10) | [docs/02](docs/02_piyasa_analizi.md) |
| 3 Finance | Real-USD cash flows, TEİAŞ charges, imbalance, 25% tax with loss carry-forward, P90-sculpted debt, LCOE, tornado | [docs/03](docs/03_finansal_model.md) |
| 4 Optimisation | Battery arbitrage LP → hybrid dispatch LP with grid shadow prices → capacity MILP (integer turbines, binary build decision, full year 2 × 8,760 h, ~35 s); representative days vs full year; regret analysis | [docs/04](docs/04_optimizasyon.md) |
| 5 Revenue stack & risk | Ancillary services (binary participation ≥ 30 MW), PPA, storage licence. Monte Carlo with block-bootstrapped weather, mean-reverting log prices with crisis/price-cap events, Gaussian copula. Dispatch pre-computed on a grid + trilinear interpolation (error ~1%). EVPI/EVPPI, Sobol indices | [docs/05](docs/05_risk_ve_gelir_yigini.md) |
| 6 Stress test | SFK supply–demand saturation model (GB/DE/AU calibration), opportunity window, delay & wait-and-see, flexible battery designs, conservative debt | [docs/05 §9](docs/05_risk_ve_gelir_yigini.md#9-stres-testi-sfk-piyasasının-doyumu-aşama-6) |
| 7 Real-world frictions | System curtailment detected from EPİAŞ instructions + co-located wind farms; incentives (VAT); merchant vs PPA vs YEKDEM in one Monte Carlo; avoided CO2; CPM + Monte Carlo project schedule (COD P50/P80, criticality index); 20-item risk register | [docs/07](docs/07_tamamlayici_analizler.md) |
| 8 Decision package | Formula-driven Excel model (FAST-style; 48/48 scenarios reconciled to Python), 3-page investment-committee memo, 13-slide deck with a decision-journey chart | [outputs/08](outputs/08) |

## Model validation
Full write-up (Turkish): [docs/MODEL_DOGRULAMA.md](docs/MODEL_DOGRULAMA.md).

- **Validated:** PV model vs PVGIS (+4.0% annual yield); ERA5 wind calibrated against three wind farms (hourly
  correlation 0.76 → 0.85, month × hour RMSE 10.6 → 0.9 CF points; cross-validated 2.5–2.8); Excel model reconciles with
  Python in 48/48 scenarios; representative days vs full-year MILP (−0.7 M$ bias → headline results use the full year);
  Monte Carlo interpolation error ~1%; deterministic-vs-Monte Carlo gap decomposed component by component (this found
  the price-median bug).
- **Not validated (assumptions):** YEKDEM corridor indexation, curtailment compensation share, SFK saturation pace and
  battery eligibility, PPA discount, CAPEX distributions, ornithology costs; no on-site wind measurement.
- **Most sensitive to:** long-term price level (break-even ≈ 59 $/MWh vs 58 assumed), SFK saturation pace, CAPEX/WACC,
  and the schedule (COD after 2030 loses YEKDEM).

## Tech stack
Python 3.11 · Pyomo + HiGHS (`highspy`) · CPM / schedule Monte Carlo · pandas / NumPy / SciPy · pvlib · windpowerlib · xarray / ERA5 (cdsapi) ·
EPİAŞ Transparency API · matplotlib / Plotly · Streamlit · pytest

## How to run

```bash
# Environment (Python 3.11)
uv venv --python 3.11 .venv
uv pip install -r requirements.txt --python .venv/bin/python
cp .env.example .env              # CDS (ERA5) and EPİAŞ credentials — only needed to download raw data

.venv/bin/python calistir.py --listele          # list steps and which credentials each one needs
.venv/bin/python calistir.py --asama all        # full pipeline (first run ~3–4 h, mostly downloads)
.venv/bin/python calistir.py --asama 5 6        # re-run risk + packaging from cached data
.venv/bin/python -m pytest -q                   # tests: NPV/IRR/LCOE, battery SOC, DST conversion, capacity factors

# v2 app — no credentials needed at run time; needs the local data packages:
#   data/atlas (in the repo) + data/grid (built offline, not in the repo):
.venv/bin/python src/v2_O2_era5_grid.py       # ERA5 Türkiye grid (CDS key, offline, ~7 h)
.venv/bin/python src/v2_C1_pvgis_grid.py      # PVGIS solar grid (keyless, ~1 h)
.venv/bin/python src/v2_C1_rakim_grid.py      # elevation grid (keyless, ~10 s)
.venv/bin/python -c "from src.kaynaklar import gwa250; gwa250.karolari_hazirla()"   # GWA 250 m tiles
.venv/bin/python src/v2_C2_on_tarama.py       # pre-screening map (~10 min)
.venv/bin/streamlit run app.py                # → http://localhost:8501
```

Credentials are read only from `.env`. They are never printed or committed. Raw and processed data (`data/`) are not
in the repository; the dashboard and report use small aggregated files in `results/` (< 1 MB).

## Project structure

```
├── app.py                  v2 app entry point (pages: screening & analysis, Ezine case study, method; TR/EN)
├── uygulama/               v2 app pages and helpers (map, site selection, results; v1 dashboard as sayfa_vaka.py)
├── calistir.py             Single entry point for the whole pipeline
├── config.yaml             Every assumption with value, unit, source and note
├── src/
│   ├── 00–08_*.py          Stage scripts
│   ├── uretim/             Generation models (PV, wind, calibration)
│   ├── piyasa/             EPİAŞ client, market analysis
│   ├── finans/             Price scenarios, cash-flow model, debt
│   ├── optimizasyon/       Battery/hybrid LPs, representative days, capacity MILP
│   ├── risk/               Dispatch tables, vectorised valuation, Monte Carlo, saturation, design explorer
│   ├── motor/              v2 analysis engine: analiz_et(site, "hizli" | "tam", assumptions) + cache, queue, report
│   ├── atlas/, kaynaklar/  v2 calibration atlas, transfer rule, turbine proxies; data sources (ERA5/PVGIS grids, GWA, boundaries)
│   └── veri_katmani.py     v2 single data-access layer (local now; remote hosting later)
├── tests/                  pytest suite (CI: .github/workflows/ci.yml)
├── docs/                   Formulations per stage, RAPOR.md (report), MODEL_DOGRULAMA.md (validation)
├── outputs/                Figures and tables per stage, RAPOR.pdf; 08/: memo, deck, Excel model
├── results/                Small aggregated results for the dashboard
├── dashboard/              Streamlit Community Cloud entry point (light requirements)
├── DATA_SOURCES.md         Data sources, licences, attributions
└── CHANGELOG.md            Stages, revisions and the decision journey
```

## Limitations
- **Wind resource:** ERA5 calibrated on three plants; no on-site measurement; wake losses are a lump-sum loss factor.
- **Market estimates:** SFK prices, saturation pace, scenario probabilities and the PPA discount are estimates. No
  Turkish battery has participated in SFK at scale yet.
- **Dispatch:** perfect foresight (annual LP). Arbitrage revenue is overstated, but the impact is limited because most
  battery value is capacity payments.
- **FX and debt:** FX risk is not modelled separately (real USD). Debt is not restructured within simulations.
- **Design explorer:** uses one representative weather year plus interpolation (error vs full model ≈ 0.5–0.8 M$).

## Data sources and attribution
Details, licences and what each source is used for: [DATA_SOURCES.md](DATA_SOURCES.md).

- **ERA5:** Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor
  ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.
  Dataset: *ERA5 hourly time-series data on single levels from 1940 to present*, DOI [10.24381/1cf1ad76](https://doi.org/10.24381/1cf1ad76).
- **PVGIS:** PVGIS © European Communities, 2001-2026 (PVGIS-SARAH3 database).
- **Global Wind Atlas 3.0** (DTU, World Bank Group, Vortex, ESMAP; CC BY 4.0) — https://globalwindatlas.info
- **OpenStreetMap** wind-farm and turbine data © OpenStreetMap contributors (ODbL); boundaries: geoBoundaries (Runfola et al. 2020).
- **Copernicus DEM GLO-90** © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.
- **EPİAŞ:** Source: EPİAŞ Transparency Platform (seffaflik.epias.com.tr). Only derived and aggregated results are
  stored in this repository; raw hourly EPİAŞ data are not redistributed.

## License
The MIT licence ([LICENSE](LICENSE)) applies **to the code only**. The embedded data packages in `data/atlas/` carry their own licences (OSM-derived files ODbL 1.0, Global Wind Atlas derivatives CC BY 4.0, boundaries ODbL/CC BY-SA); see [data/atlas/README.md](data/atlas/README.md). Data and data-derived results remain subject to the
terms of their sources (Copernicus/C3S licence, PVGIS reuse conditions, EPİAŞ Transparency Platform terms); see
[DATA_SOURCES.md](DATA_SOURCES.md).
