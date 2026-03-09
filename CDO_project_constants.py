from __future__ import annotations


# Validation note:
# CSV floating point reserialization
# changes string representation but
# preserves numeric values within 1e-9
# relative tolerance. Use numeric
# comparison for post-write checks,
# not string/binary comparison.

FINAL_CSV_SCHEMA = [
    "hour_of_year",
    "datetime",
    "month",
    "hour_of_day",
    "season",
    "wind_speed_10m_ms",
    "wind_direction_10m_deg",
    "wind_speed_50m_ms",
    "wind_speed_15m_ms",
    "wind_speed_20m_ms",
    "wind_speed_25m_ms",
    "wind_speed_30m_ms",
    "wind_speed_40m_ms",
    "air_temp_c",
    "relative_humidity_pct",
    "air_density_kgm3",
    "outlier_flag",
    "wind_speed_50m_ms_derived",
    "alpha_actual",
]

FINAL_CSV_SHAPE = (8760, 19)

# Wind speed reference values
# Updated after alpha recalibration
CDO_CENTER_WS15_MEAN = 3.643344
# m/s — current master CSV mean
# derived using ALPHA_CDO_CANONICAL
# replaces earlier estimate of 3.688513
# which used ALPHA_TEXTBOOK = 0.18

# Wind shear exponent
# Empirically derived from NASA MERRA-2
# WS10M vs WS50M cross-check
# CDO 2023 — median of hourly calculations
ALPHA_CDO_CANONICAL = 0.149612

# For reference only — do not use in calcs:
ALPHA_TEXTBOOK = 0.18
# standard urban terrain Class II
# overestimates CDO wind at height

# All derived wind speed columns
# in this project use ALPHA_CDO_CANONICAL.
# ALPHA_TEXTBOOK is retained for
# comparison only.

# Turbine placeholders
SWEPT_AREA_M2 = 4.0
# PLACEHOLDER — update when design locked

CP_GENERIC = 0.35
# PLACEHOLDER — update when design locked

TURBINE_RATED_KW = 1.0
# PLACEHOLDER — update when design locked
# 1kW medium VAWT — base case
# matches feasibility PDF base case
# update when physical design is locked

# SIL plant placeholders
ROTOR_RADIUS_M = 0.75
# PLACEHOLDER — update when design locked

ROTOR_INERTIA_KGM2 = 12.0
# PLACEHOLDER — update when design locked

DRIVETRAIN_DAMPING_NMS = 0.08
# PLACEHOLDER — update when design locked

GENERATOR_EFFICIENCY = 0.9
# PLACEHOLDER — update when design locked

BRAKE_TORQUE_NM = 18.0
# PLACEHOLDER — update when design locked

TSR_OPT = 2.2
# PLACEHOLDER — update when design locked

TSR_SPREAD = 1.6
# PLACEHOLDER — update when design locked

CUT_IN_MS = 2.5
# PLACEHOLDER — update when design locked

CUT_OUT_MS = 25.0
# PLACEHOLDER — update when design locked

MAX_ROTOR_RPM = 220.0
# PLACEHOLDER — update when design locked

STARTUP_TORQUE_COEFF = 0.12
# PLACEHOLDER — update when design locked

STANDARD_AIR_DENSITY = 1.225

# CDO spatial grid
GRID_LATITUDES = [8.282, 8.382, 8.482, 8.582, 8.682]
GRID_LONGITUDES = [124.447, 124.547, 124.647, 124.747, 124.847]
GRID_IDS_ROW_MAJOR = [f"R{row}C{col}" for row in range(5) for col in range(5)]

# Refined spatial data sources
OPENMETEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPENMETEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
OPENMETEO_REFINED_DATA_SOURCE = "OpenMeteo_ERA5_Seamless"
OPENMETEO_REFINED_SPATIAL_METHOD = (
    "Open-Meteo Historical Weather API per-point ERA5-Seamless "
    "winds and direction with per-point DEM elevation"
)
OPENMETEO_REFINED_SPATIAL_LABEL = (
    "Spatial field: Open-Meteo Historical Weather API using ERA5-Seamless "
    "per-point wind speed and direction, with per-point DEM elevation. "
    "This improves direction and speed variation over the heuristic hybrid "
    "field, but is still reanalysis-scale data rather than mast, LiDAR, "
    "or CFD-validated micrositing data."
)

# Spatial multipliers
# Hybrid spatial field limitation:
# Wind DIRECTION is identical across
# all 25 grid points per hour.
# Only wind SPEED varies spatially
# via terrain multipliers.
# True spatial direction variation
# requires ERA5 or Global Wind Atlas
# per-point direction data.
# This is a known limitation —
# documented in data_source column
# of CDO_grid_wind_2023_long.csv
