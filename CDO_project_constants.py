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
