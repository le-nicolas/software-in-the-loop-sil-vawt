# CDO Wind Data 2023

Hourly wind dataset and visualization pipeline for Cagayan de Oro, Philippines, prepared for engineering simulation and interactive analysis.

## Overview

This project contains:

- A validated hourly master CSV for civil Philippines time (`UTC+8`) for calendar year 2023
- Derived wind-speed columns for multiple hub heights
- Per-hour wind shear exponent reference (`alpha_actual`)
- Plotly-based interactive visualizations
- Scripts for updating derived columns and rebuilding outputs

## Location

- Location: `Cagayan de Oro, Misamis Oriental, Philippines`
- Latitude: `8.482`
- Longitude: `124.647`

## Master Dataset

Primary dataset:

- [CDO_wind_2023_hourly.csv](/c:/Users/User/VAWT/CDO_wind_2023_hourly.csv)

Permanent schema:

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

Expected shape:

- `8760` rows
- `19` columns

## Time Basis

NASA POWER hourly timestamps are returned in Local Solar Time (`LST`), not civil Philippine time.

This project uses:

1. `LST_offset = longitude / 15`
2. `UTC = LST - LST_offset`
3. `Civil_PH = UTC + 8 hours`
4. Round to nearest whole hour
5. Filter to civil year `2023-01-01 00:00:00` through `2023-12-31 23:00:00`

All downstream analysis uses civil `UTC+8`.

## Derived Fields

### Height-adjusted wind speeds

Derived from `wind_speed_10m_ms` using the power law:

`V_h = WS10M * (h / 10)^alpha`

Where:

- `alpha_actual` is computed hourly from raw NASA `WS10M` and `WS50M`
- Derived hub-height columns use the median `alpha_actual` across valid hours

### Air density

`air_density_kgm3 = 1.225 * (273.15 / (273.15 + air_temp_c))`

Standard pressure is assumed.

### Outlier flag

- `outlier_flag = 1` when wind speed exceeds `40 m/s`
- Flagged rows are retained

## Validation Rules

Validation expectations:

- No dropped rows
- No silent zero-filling of missing wind values
- `hour_of_year` remains continuous from `1` to `8760`
- Numeric values preserved after CSV rewrites within `rtol=1e-9`
- Non-numeric columns preserved exactly

Validation note:

CSV floating-point reserialization may change text representation without changing the numeric value. Post-write validation must use tolerant numeric comparison, not strict string or binary equality for floats.

## Project Files

- [CDO_project_constants.py](/c:/Users/User/VAWT/CDO_project_constants.py)
  Permanent schema and validation constants
- [fetch_cdo_wind_2023.py](/c:/Users/User/VAWT/fetch_cdo_wind_2023.py)
  NASA POWER fetch and validation workflow
- [add_wind_height_columns.py](/c:/Users/User/VAWT/add_wind_height_columns.py)
  Recomputes `alpha_actual` and derived height columns
- [build_visualizations.py](/c:/Users/User/VAWT/build_visualizations.py)
  Builds all visualization outputs
- [viz_common.py](/c:/Users/User/VAWT/viz_common.py)
  Shared validation and plotting utilities
- [viz1_vector_field.py](/c:/Users/User/VAWT/viz1_vector_field.py)
- [viz2_wind_rose_3d.py](/c:/Users/User/VAWT/viz2_wind_rose_3d.py)
- [viz3_interactive_slider.py](/c:/Users/User/VAWT/viz3_interactive_slider.py)
- [viz4_weibull_surface.py](/c:/Users/User/VAWT/viz4_weibull_surface.py)
- [viz5_energy_heatmap.py](/c:/Users/User/VAWT/viz5_energy_heatmap.py)

## Visualization Outputs

Output folder:

- [CDO_wind_visualizations_2023](/c:/Users/User/VAWT/CDO_wind_visualizations_2023)

Generated files:

- `CDO_wind_2023_hourly.csv`
- `viz1_vector_field.html`
- `viz2_wind_rose_3d.html`
- `viz3_interactive_slider.html`
- `viz4_weibull_surface.html`
- `viz5_energy_heatmap.html`
- `viz_summary.txt`

## Environment

Python dependencies:

- `pandas`
- `numpy`
- `plotly`
- `scipy`

## Rebuild Commands

Recompute derived columns:

```bash
python add_wind_height_columns.py
```

Rebuild visualizations:

```bash
python build_visualizations.py
```

## Project Rules

- The master CSV schema is fixed at `(8760, 19)`
- Future derived columns must go into separate analysis files, not the master CSV
- All wind speeds are in `m/s`
- All timestamps are civil `UTC+8`
- `hour_of_year` is the universal alignment key for all downstream tools
