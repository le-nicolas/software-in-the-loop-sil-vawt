# Software-in-the-Loop VAWT

![Status](https://img.shields.io/badge/status-active_research-0f766e)
![Stage](https://img.shields.io/badge/stage-honest_SIL_%2B_geometry_lock-1d4ed8)
![Location](https://img.shields.io/badge/site-Cagayan_de_Oro,_PH-475569)

Transparent wind-resource analysis, spatial wind-field modeling, visualization, DPCBF-inspired capture diagnostics, MATLAB design-foundation benchmarking, and adaptive software-in-the-loop work for a vertical-axis wind turbine feasibility study in Cagayan de Oro, Philippines.

## Research Status

This repository is under active research and remains a working engineering notebook as well as a codebase.

- active status as of 2026-03-28: the hybrid SIL loop now uses a DMST-derived lookup-table `Cp(TSR)` model, startup/MPPT hysteresis, a more conservative overspeed brake trigger, and an honest `0.38 kW` rated-power ceiling; geometry is narrowed around `c/R=0.11`, `e/d=0.15`, and `R_s/R_d=0.50`, while fabrication details, generator matching, and structural signoff remain open
- stable foundation: hourly 2023 CDO wind dataset, derived height columns, spatial analysis utilities, reproducible plots, `viz9` and `viz10` DPCBF diagnostics, exported sphere metrics, Fusion360 load benchmarks, a MATLAB design-foundation workflow, and an adaptive SIL loop with lookup-table Cp(TSR), corrected power accounting, and improved startup-to-MPPT handoff
- still in-progress: controller fidelity, plant physics, terrain correction quality, validation depth, uncertainty tightening, and the Unity scene integration layer
- not yet claimed: bankable resource assessment, final micrositing accuracy, or full digital-twin realism

If you are viewing this from GitHub, the intended repo description is:

`Active research: transparent wind-resource, DPCBF capture diagnostics, MATLAB design-foundation numbers, and adaptive SIL modeling for a CDO VAWT study`

## What This Repo Contains

- `CDO_wind_2023_hourly.csv`: the main hourly wind dataset for 2023
- height-derived wind columns and atmospheric metrics
- spatial wind-field builders using hybrid and refined workflows
- interactive Plotly and Dash visualizations
- DPCBF-inspired 3D and blade-azimuth capture viewers for Savonius vs Darrieus regime insight
- exported sphere, azimuth, particle, and Fusion360-oriented design benchmark tables
- a MATLAB benchmark script with toolbox-aware design-foundation outputs for CAD and Simulink follow-on work
- early software-in-the-loop controller and plant scaffolding
- a Unity-ready runtime scaffold for native 3D exploration
- validation-source fetches and supporting raw reference files

## Transparency Notes

This project is intentionally transparent about what each dataset or model can and cannot support.

- NASA POWER is the base hourly series for the master dataset
- Open-Meteo ERA5-Seamless is used for refined spatial-pattern exploration
- some files are evidence-building validation inputs, not final truth sources
- current SIL controller and plant dynamics are still research models, but they now include adaptive Cp feedback, a literature-anchored lookup-table Cp(TSR), ring-resolved inflow preservation, startup-zone controller tuning, and explicit hourly energy accounting
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

## Pipeline

Three tools. One data flow. File-based.

1. Python SIL is the source of truth. It writes `CDO_sil_run_2023_hourly.csv`, `CDO_sil_run_2023_summary.txt`, `yield_uncertainty_results.json`, and `validation_report.txt`.
2. MATLAB reads those Python outputs, validates the batch model branch, and writes `matlab_validation_summary.csv`, `matlab_cp_tsr_comparison.csv`, and `matlab_sil_summary.mat`.
3. Unity reads the Python and MATLAB outputs from `UnityVAWT/Assets/StreamingAssets/` for runtime visualization.
4. `run_pipeline.py` is the master entry point that executes the full file-based flow and syncs the outputs into Unity.

## New In This Repo State

- `viz9_dpcbf_sphere_3d.py` adds a 3D wind-particle capture sphere with CBF-inspired alert logic
- `viz10_blade_azimuth_dpcbf.py` extends the model to explicit blade-azimuth relative velocity and particle-side DPCBF logging
- exported sphere and particle CSVs now make the capture logic inspectable outside the HTML viewers
- `build_fusion360_design_benchmark.py` and `design_benchmarks/` turn the simulation outputs into first-pass CAD load cases
- `matlab_design_foundation_benchmark.m` converts the benchmark stack into MATLAB-native tables, figures, workspace data, and toolbox-aware follow-on artifacts
- `build_cdo_vawt_models.m` now generates repo-native Simulink and Simscape baseline models aligned to the current hybrid SIL assumptions
- `run_cdo_vawt_matlab_pipeline.m` now rebuilds the MATLAB benchmark, regenerates the models, and exports MATLAB SIL results for the 2023 CDO dataset
- `sil_controller.py`, `sil_plant_model.py`, and `run_sil_simulation.py` now preserve Cp feedback, use a lookup-table Cp(TSR) model, keep ring-resolved inflow structure, lower the startup-to-MPPT handoff threshold, review overspeed braking more conservatively, and separate hourly energy from mean power
- `pipeline_contracts.py`, `run_pipeline.py`, and `sync_to_unity.py` now define the canonical file contracts and connect Python SIL, MATLAB validation, and Unity StreamingAssets with a file-based flow
- `dmst_model.py` derives the current DMST-inspired Cp(TSR) lookup, `yield_uncertainty.py` quantifies annual-yield spread, and `validate_against_literature.py` checks the fitted curve against published hybrid Cp traces
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
- `viz10_blade_azimuth_dpcbf.py`
- `build_fusion360_design_benchmark.py`
- `validate_sphere_benchmark_outputs.py`

Primary interactive apps:

- `viz7_spatial_field_slider.py`
- `viz8_wpd_spatial_slider.py`
- `viz9_dpcbf_sphere_3d.py`
- `viz10_blade_azimuth_dpcbf.py`

### Design benchmark outputs

- `design_benchmarks/fusion360_design_parameters.csv`: CAD-facing baseline geometry, rpm, torque, and sector numbers
- `design_benchmarks/fusion360_load_cases.csv`: named operating and structural load cases for design studies
- `design_benchmarks/fusion360_design_summary.txt`: compact text interpretation of the benchmark outputs

### MATLAB foundation workflow

- `matlab_design_foundation_benchmark.m`: MATLAB-native benchmark builder using repo CSV outputs plus optional toolboxes when available
- `matlab_vawt_constants.m`: MATLAB copy of the current hybrid SIL constants and lookup-table Cp(TSR) baseline
- `matlab_vawt_sil_hour_step.m`: one-hour MATLAB SIL step that mirrors the present controller and plant assumptions
- `matlab_vawt_sil_hour_step_vector.m`: Simulink wrapper used by the generated SIL model
- `build_cdo_vawt_models.m`: programmatic Simulink and Simscape model builder
- `run_cdo_vawt_matlab_pipeline.m`: full MATLAB pipeline runner for model build plus validation
- `matlab_models/cdo_vawt_sil.slx`: generated Simulink hourly SIL model
- `matlab_models/cdo_vawt_simscape_plant.slx`: generated Simscape rotational plant baseline
- `matlab_design_outputs/matlab_foundation_parameters.csv`: MATLAB-exported foundation numbers for design work
- `matlab_design_outputs/matlab_foundation_load_cases.csv`: MATLAB-exported load cases
- `matlab_design_outputs/matlab_seasonal_summary.csv`: seasonal operating summary
- `matlab_design_outputs/matlab_foundation_summary.txt`: plain-text design summary
- `matlab_design_outputs/matlab_foundation_dashboard.png`: MATLAB dashboard image
- `matlab_design_outputs/matlab_foundation_workspace.mat`: saved MATLAB workspace for follow-on analysis
- `matlab_design_outputs/matlab_sil_hourly.csv`: MATLAB / Simulink hourly SIL export
- `matlab_design_outputs/matlab_sil_summary.txt`: MATLAB / Simulink / Simscape validation summary

### Current MATLAB foundation numbers

- current conservative hybrid assumptions: `CP_GENERIC=0.33`, `TSR_OPT=2.5`, `TSR_SPREAD=1.85`, with a lookup-table Cp(TSR) shape anchored to low-wind hybrid Savonius-Darrieus literature
- rotor radius: `0.750 m`
- rotor diameter: `1.500 m`
- swept-area-equivalent rotor height: `2.667 m`
- operating hours in 2023: `6739`
- operating wind `P50`: `3.957 m/s`
- operating wind `P90`: `6.038 m/s`
- rotor speed `P50`: `120.63 rpm`
- rotor speed `P90`: `220 rpm`
- aero torque `P90`: `7.301 N*m`
- aero torque `P95`: `9.314 N*m`
- capture fraction `P50`: `1.000`
- dominant peak sector: `210 deg`

### Current MATLAB / Simulink snapshot

- latest MATLAB / Simulink annual yield: `299.797 kWh/year`
- MATLAB / Simulink daily average: `821 Wh/day`
- MATLAB SIL mode counts: `idle=1983`, `startup=20`, `adaptive_mppt=6725`, `brake=32`
- peak hourly MATLAB SIL electrical power: `0.380 kW`
- Simscape demo final shaft speed: `15.935 rad/s`

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

- `sil_controller.py`: adaptive TSR-tracking torque control using plant Cp and aerodynamic-torque feedback, with an earlier startup-to-MPPT handoff and a less trigger-happy brake condition
- `sil_plant_model.py`: VAWT plant model with DMST-inspired lookup-table Cp(TSR), startup torque support, damping, and optional ring-resolved inflow asymmetry
- `run_sil_simulation.py`: year-scale closed-loop simulation using blended spatial forcing with preserved ring-level inflow structure, explicit hourly energy accounting, and mode-transition logging
- `dmst_model.py`: DMST-style Cp/TSR surrogate builder for the current hybrid geometry lock
- `yield_uncertainty.py`: Monte Carlo yield spread analysis for wind, Cp, and density uncertainty
- `validate_against_literature.py`: comparison of the fitted Cp(TSR) curve against published hybrid VAWT data

## Current SIL Loop

1. Spatial wind forcing is assembled from center-series magnitude, refined spatial ratios and direction deltas, plus turbulence.
2. The disturbed 25-point field is reconstructed into a ring-resolved rotor inflow instead of collapsing direction immediately to one scalar.
3. The controller reads simulated wind, rotor speed, previous Cp, previous TSR, and previous aerodynamic torque.
4. The controller issues adaptive generator torque and brake commands with startup/MPPT hysteresis and logged mode transitions.
5. The plant advances rotor state using a lookup-table Cp(TSR) model and optional azimuthal inflow asymmetry.
6. Hourly outputs log both mean power and hourly energy, along with upwind/downwind face statistics.

### Current SIL Snapshot

- latest 2023 closed-loop run with the honest rated-power cap: `289.312 kWh/year`
- average daily yield from the current SIL run: `793 Wh/day`
- hours generating: `5779`
- mean effective wind speed: `3.724 m/s`
- mean rotor RPM: `116.64 rpm`
- peak modeled electrical power: `0.380 kW` at the current rated-power cap
- working-range hours (`2.5-7.0 m/s`) with zero electrical output: `273`
- the model still touches the rated cap during a small number of high-wind hours, so annual yield should be treated as an honest research estimate rather than a final hardware claim

Interpretation:

- the lookup-table Cp(TSR) and controller retune materially reduced startup-zone under-harvesting
- the remaining gap is no longer dominated by a zero-Cp startup model, but is still sensitive to controller details and the present rated-power ceiling
- the present SIL result should still be treated as a research output, not a bankable yield claim

### Current Design Direction

- hybrid type: low-wind Savonius-Darrieus VAWT for Cagayan de Oro
- current geometry lock: `CHORD_TO_RADIUS=0.11`, `OVERLAP_RATIO=0.15`, `RADIUS_RATIO=0.50`
- current material direction: `NACA 4412` Darrieus blades in `GFRP`, inner Savonius buckets in `5052-H32` marine aluminum
- next engineering gates: blade thickness and spar sizing, shaft and bearing selection, generator match, and fabrication-ready drawings

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

Run the explicit blade-azimuth DPCBF viewer and benchmark exports:

```bash
python viz10_blade_azimuth_dpcbf.py
python build_fusion360_design_benchmark.py
python validate_sphere_benchmark_outputs.py
```

Run the MATLAB design-foundation workflow:

```matlab
matlab_design_foundation_benchmark
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
- exported benchmark CSV and summary artifacts used for downstream design work
- Unity conversion scaffold source
- raw validation-reference inputs used for transparency and reproducibility

Ignored:

- generated visualization HTML
- generated spatial CSVs
- generated SIL output CSVs

## What Comes Next

- validate and refine the new lookup-table Cp(TSR) representation against more primary-source hybrid curves
- deepen controller logic and state handling beyond the current startup and overspeed retune
- add sensor models and fault scenarios
- tighten validation against local or nearby measurements
- improve terrain, roughness, and coastline corrections
- replace heuristic DPCBF particle terms with a paper-matched calibrated form once the preferred reference formulation is locked
- turn the Unity scaffold into a fully wired Unity project scene with materials, prefabs, and UI assets
- mature the workflow from early SIL scaffold toward a stronger research test harness
- carry the MATLAB foundation numbers into Simulink, Simscape, and Fusion360 iterations
