# Software-in-the-Loop VAWT

![Status](https://img.shields.io/badge/status-active_research-0f766e)
![Stage](https://img.shields.io/badge/stage-viz9_%2B_Unity_scaffold-1d4ed8)
![Location](https://img.shields.io/badge/site-Cagayan_de_Oro,_PH-475569)

Transparent wind-resource analysis, spatial wind-field modeling, visualization, DPCBF-inspired capture diagnostics, and early software-in-the-loop work for a vertical-axis wind turbine feasibility study in Cagayan de Oro, Philippines.

## Research Status

This repository is under active research and remains a working engineering notebook as well as a codebase.

- stable foundation: hourly 2023 CDO wind dataset, derived height columns, spatial analysis utilities, reproducible plots, `viz9` capture-sphere diagnostics, and an early SIL loop
- still in-progress: controller fidelity, plant physics, terrain correction quality, validation depth, and the Unity scene integration layer
- not yet claimed: bankable resource assessment, final micrositing accuracy, or full digital-twin realism

If you are viewing this from GitHub, the intended repo description is:

`Active research: transparent wind-resource, spatial-field, and early SIL modeling for a CDO VAWT study`

## What This Repo Contains

- `CDO_wind_2023_hourly.csv`: the main hourly wind dataset for 2023
- height-derived wind columns and atmospheric metrics
- spatial wind-field builders using hybrid and refined workflows
- interactive Plotly and Dash visualizations
- a DPCBF-inspired 3D capture-sphere viewer for Savonius vs Darrieus regime insight
- early software-in-the-loop controller and plant scaffolding
- a Unity-ready runtime scaffold for native 3D exploration
- validation-source fetches and supporting raw reference files

## Transparency Notes

This project is intentionally transparent about what each dataset or model can and cannot support.

- NASA POWER is the base hourly series for the master dataset
- Open-Meteo ERA5-Seamless is used for refined spatial-pattern exploration
- some files are evidence-building validation inputs, not final truth sources
- current SIL controller and plant dynamics are placeholders for research iteration
- the Unity folder is a scaffold, not yet a fully generated Unity project with scenes and materials committed
- rebuildable outputs are separated from the master dataset so the core source stays clean

## Core Dataset

Primary file:

- `CDO_wind_2023_hourly.csv`

Authoritative shape and schema:

- `8760 x 19`
- local civil time in the Philippines: `UTC+8`
- `hour_of_year` is the alignment key across downstream processing

Permanent master schema:

1. `hour_of_year`
2. `datetime`
3. `month`
4. `hour_of_day`
5. `season`
6. `wind_speed_10m_ms`
7. `wind_direction_10m_deg`
8. `wind_speed_50m_ms`
9. `wind_speed_15m_ms`
10. `wind_speed_20m_ms`
11. `wind_speed_25m_ms`
12. `wind_speed_30m_ms`
13. `wind_speed_40m_ms`
14. `air_temp_c`
15. `relative_humidity_pct`
16. `air_density_kgm3`
17. `outlier_flag`
18. `wind_speed_50m_ms_derived`
19. `alpha_actual`

Location:

- Cagayan de Oro, Misamis Oriental, Philippines
- latitude: `8.482`
- longitude: `124.647`

## Data and Modeling Layers

### 1. Master hourly series

Built from NASA POWER hourly data and converted from Local Solar Time into civil `UTC+8`.

### 2. Hybrid spatial field

Uses the CDO center series plus terrain-informed speed multipliers.

Current limitation:

- wind direction is shared across the grid for a given hour
- speed varies spatially, but directional structure is simplified

### 3. Refined spatial field

Uses Open-Meteo Historical Weather API with `ERA5-Seamless` across the 25-point grid.

Available refined variables include:

- per-point wind speed and direction
- temperature and humidity
- DEM elevation

Interpretation rule:

- refined spatial patterns are treated as candidate evidence
- they are not treated as proof until backed by local measurements or higher-fidelity modeling

## Accuracy Position

Reasonable for:

- feasibility-stage wind-resource exploration
- forcing development for early controller and plant experiments
- comparative spatial scenario analysis
- research visualization and workflow prototyping

Not sufficient for:

- bankable yield assessment
- final micrositing
- CFD-grade local flow distortion conclusions
- design signoff without calibration against measurements

## New In This Repo State

- `viz9_dpcbf_sphere_3d.py` adds a 3D wind-particle capture sphere with CBF-inspired alert logic
- the new viewer compares inner Savonius drag behavior against outer Darrieus lift behavior
- `UnityVAWT/` adds a 12-script Unity scaffold using `StreamingAssets` runtime CSV loading and URP-oriented scene structure
- the Unity scaffold is designed to reproduce the engineering meaning of `viz9`, not just its appearance

## Main Files

### Data build and analysis

- `fetch_cdo_wind_2023.py`: build the base NASA POWER dataset
- `add_wind_height_columns.py`: derive additional wind-height columns and `alpha_actual`
- `build_gradients_analysis.py`: derive gradients, turbulence proxies, WPD, Beaufort, and related metrics
- `fetch_cdo_validation_sources.py`: pull and organize supporting validation sources

### Spatial field

- `build_hybrid_spatial_field.py`: terrain-multiplier grid from the center time series
- `fetch_openmeteo_refined_grid.py`: direct refined 25-point Open-Meteo fetch
- `create_gwa_manual_template.py`: template for manual Global Wind Atlas inputs
- `build_refined_spatial_field.py`: construct a refined field from populated manual inputs
- `CDO_spatial_multipliers.py`: current multiplier map
- `spatial_turbulence_model.py`: correlated turbulence model for spatial forcing

### Visualization

- `build_visualizations.py`
- `viz1_vector_field.py`
- `viz2_wind_rose_3d.py`
- `viz3_interactive_slider.py`
- `viz4_weibull_surface.py`
- `viz5_energy_heatmap.py`
- `viz6_quiver_field.py`
- `viz7_dash_spatial.py`
- `viz7_spatial_field_slider.py`
- `viz8_wpd_spatial_slider.py`
- `viz9_dpcbf_sphere_3d.py`

Primary interactive apps:

- `viz7_spatial_field_slider.py`
- `viz8_wpd_spatial_slider.py`
- `viz9_dpcbf_sphere_3d.py`

### Unity conversion scaffold

- `UnityVAWT/README.md`: setup notes for a fresh Unity `2022 LTS` `URP` project
- `UnityVAWT/Assets/StreamingAssets/CDO_wind_2023_hourly.csv`: runtime CSV source for Unity
- `UnityVAWT/Assets/Scripts/Data/WindDataLoader.cs`: `UnityWebRequest` CSV loading
- `UnityVAWT/Assets/Scripts/Physics/`: decomposition, rotor state, and CBF monitoring
- `UnityVAWT/Assets/Scripts/Scene/`: sphere zones, particles, and rotor mesh
- `UnityVAWT/Assets/Scripts/UI/`: HUD graphs and directional histogram
- `UnityVAWT/Assets/Scripts/Camera/`: orbit camera and timeline playback
- `UnityVAWT/Assets/Scripts/Controls/`: live parameter slider bindings

### Early SIL scaffold

- `sil_controller.py`: startup logic, MPPT-style torque command, and overspeed braking scaffold
- `sil_plant_model.py`: simple VAWT plant model with inertia, aero torque, damping, and electrical output
- `run_sil_simulation.py`: year-scale closed-loop simulation using blended spatial forcing

## Current SIL Loop

1. Spatial wind forcing is assembled from center-series magnitude, refined spatial ratios and direction deltas, plus turbulence.
2. The wind field is disk-averaged to an effective inflow.
3. The controller reads simulated wind and rotor speed.
4. The controller issues torque and brake commands.
5. The plant advances rotor state and electrical output.
6. Hourly outputs are logged for analysis.

## Project Rules

- no silent zero-fill of missing wind values
- no row-dropping from the master hourly series
- master schema remains fixed at `8760 x 19`
- new derived outputs belong in separate analysis files, not inside the master CSV
- floating-point rewrites are validated numerically, not by exact string equality

## Quick Start

```bash
python add_wind_height_columns.py
python build_gradients_analysis.py
python build_hybrid_spatial_field.py
python fetch_openmeteo_refined_grid.py
python run_sil_simulation.py
```

Launch the main spatial viewers:

```bash
python viz7_spatial_field_slider.py
python viz8_wpd_spatial_slider.py
```

Run the DPCBF-inspired capture-sphere viewer:

```bash
python viz9_dpcbf_sphere_3d.py
```

For Unity work:

```bash
see UnityVAWT/README.md
```

## Tracked vs Generated

Tracked:

- source code
- constants
- master dataset
- lightweight templates
- Unity conversion scaffold source
- raw validation-reference inputs used for transparency and reproducibility

Ignored:

- generated visualization HTML
- generated spatial CSVs
- generated SIL output CSVs

## What Comes Next

- replace placeholder aerodynamics with a better VAWT performance representation
- deepen controller logic and state handling
- add sensor models and fault scenarios
- tighten validation against local or nearby measurements
- improve terrain, roughness, and coastline corrections
- turn the Unity scaffold into a fully wired Unity project scene with materials, prefabs, and UI assets
- mature the workflow from early SIL scaffold toward a stronger research test harness
