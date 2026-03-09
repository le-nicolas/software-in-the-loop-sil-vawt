# Software-in-the-Loop (SIL) VAWT

Wind-data, spatial-field, visualization, and early SIL scaffolding for a vertical-axis wind turbine feasibility project in Cagayan de Oro, Philippines.

## What This Repo Is

This project started as a validated hourly wind-resource dataset and has been extended into an early Software-in-the-Loop pipeline:

- single-point 2023 wind resource data for CDO
- derived hub-height wind columns and validation utilities
- gradient and turbulence proxy analysis
- interactive 3D Plotly/Dash visualizations
- spatial wind-field builders
- a first closed-loop SIL scaffold:
  wind forcing -> controller -> plant model -> simulated outputs

It is not yet a full turbine digital twin. The plant and controller are still placeholder engineering models.

## Core Data

### Master dataset

- `CDO_wind_2023_hourly.csv`

Authoritative shape and schema:

- `8760 x 19`
- civil Philippines time `UTC+8`
- `hour_of_year` is the universal alignment key

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

### Location

- `Cagayan de Oro, Misamis Oriental, Philippines`
- latitude: `8.482`
- longitude: `124.647`

## Data Sources

### 1. NASA POWER master series

The master hourly series is built from NASA POWER hourly data and converted from Local Solar Time to civil `UTC+8`.

### 2. Hybrid spatial field

The first spatial-field approach uses:

- the master center time series
- terrain-informed speed multipliers

Important limitation:

- wind direction is identical across all 25 grid points for any given hour
- only wind speed varies spatially

This is useful for early visualization, but not true spatial wind measurement.

### 3. Refined Open-Meteo spatial field

The repo also includes a direct refined spatial-grid fetch from Open-Meteo Historical Weather API using `ERA5-Seamless`:

- per-point `10m` wind speed
- per-point `10m` wind direction
- per-point `100m` wind speed
- per-point `100m` wind direction
- per-point temperature and humidity
- per-point DEM elevation

This is a real per-point spatial source and gives direction variation across the grid. It is still reanalysis-scale data, not micrositing-grade measurement.

## Current Accuracy Position

Reasonable for:

- feasibility-level resource exploration
- controller/plant prototyping
- early SIL forcing development
- comparative spatial scenario work

Not sufficient for:

- bankable energy estimates
- final micrositing
- CFD-grade building/terrain flow distortion
- design signoff without measurement calibration

## Main Scripts

### Data building

- `fetch_cdo_wind_2023.py`
  NASA POWER fetch and base dataset build
- `add_wind_height_columns.py`
  derived height columns and `alpha_actual`
- `build_gradients_analysis.py`
  gradients, turbulence proxies, WPD, density anomaly, Beaufort, and related analysis

### Spatial field

- `build_hybrid_spatial_field.py`
  center-series plus terrain-multiplier spatial field
- `fetch_openmeteo_refined_grid.py`
  direct 25-point refined spatial grid from Open-Meteo `ERA5-Seamless`
- `create_gwa_manual_template.py`
  template for manually entered Global Wind Atlas corrections
- `build_refined_spatial_field.py`
  builds a refined grid from the manual GWA template once populated
- `CDO_spatial_multipliers.py`
  current hybrid spatial multiplier map
- `spatial_turbulence_model.py`
  correlated turbulence model for spatial forcing and early SIL work

### Visualization

- `viz1_vector_field.py`
- `viz2_wind_rose_3d.py`
- `viz3_interactive_slider.py`
- `viz4_weibull_surface.py`
- `viz5_energy_heatmap.py`
- `viz6_quiver_field.py`
- `viz7_dash_spatial.py`
- `viz7_spatial_field_slider.py`
- `build_visualizations.py`

Primary live app:

- `viz7_spatial_field_slider.py`

### Early SIL scaffold

- `sil_controller.py`
  minimal controller scaffold with startup, MPPT-style torque command, and overspeed brake behavior
- `sil_plant_model.py`
  minimal dynamic VAWT plant model with inertia, aero torque, damping, and electrical output
- `run_sil_simulation.py`
  full-year closed-loop simulation using blended spatial forcing

## Current SIL Architecture

Current loop:

1. spatial wind forcing is built from:
   - NASA master center magnitude
   - Open-Meteo refined per-point speed ratios
   - Open-Meteo refined per-point direction deltas
   - correlated turbulence
2. the wind field is disk-averaged to an effective inflow
3. controller reads simulated wind and rotor speed
4. controller issues generator torque / brake commands
5. plant advances rotor state and electrical output
6. hourly outputs are logged

Generated SIL outputs are rebuildable and therefore ignored in git by default.

## Validation Rules

Project-wide data rules:

- no silent zero-fill of missing wind values
- no dropped rows from the master hourly series
- master schema fixed at `8760 x 19`
- future derived data goes into separate analysis files, not the master CSV
- floating-point CSV rewrites are validated numerically, not by exact float string match

## Key Constants

See `CDO_project_constants.py`.

Important values include:

- `ALPHA_CDO_CANONICAL`
- `CDO_CENTER_WS15_MEAN`
- `SWEPT_AREA_M2`
- `CP_GENERIC`
- `TURBINE_RATED_KW`

The turbine geometry and SIL plant constants are still placeholders and are explicitly marked that way in code.

## Commands

Rebuild derived master-analysis columns:

```bash
python add_wind_height_columns.py
python build_gradients_analysis.py
```

Rebuild hybrid spatial field:

```bash
python build_hybrid_spatial_field.py
```

Fetch refined Open-Meteo spatial field:

```bash
python fetch_openmeteo_refined_grid.py
```

Build manual-GWA refined field after populating the template:

```bash
python create_gwa_manual_template.py
python build_refined_spatial_field.py
```

Run the main Dash spatial app:

```bash
python viz7_spatial_field_slider.py
```

Run the first-pass SIL simulation:

```bash
python run_sil_simulation.py
```

## Generated Artifacts Policy

Tracked:

- source code
- constants
- master dataset
- lightweight documentation and template inputs

Ignored:

- generated visualization HTML files
- large generated spatial CSVs
- generated SIL result CSVs

This keeps the repo clonable while allowing every heavy artifact to be rebuilt locally.

## What Comes Next

The highest-value next upgrades are:

- replace placeholder plant aerodynamics with a VAWT performance map
- add richer controller logic
- add explicit sensor models and faults
- calibrate forcing against local measurements
- integrate better terrain/roughness/coastline corrections
- move from early SIL scaffold toward a true plant-controller test harness
