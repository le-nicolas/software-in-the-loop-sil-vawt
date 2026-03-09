from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


LONG_CSV = Path("CDO_grid_wind_2023_long_openmeteo.csv")
SUMMARY_TXT = Path("CDO_refined_spatial_analysis.txt")


def circular_mean_deg(frame: pd.DataFrame, value_col: str, group_cols: list[str]) -> pd.Series:
    radians = np.deg2rad(frame[value_col].to_numpy(dtype=float))
    temp = frame[group_cols].copy()
    temp["_sin"] = np.sin(radians)
    temp["_cos"] = np.cos(radians)
    grouped = temp.groupby(group_cols, sort=True)[["_sin", "_cos"]].mean()
    return np.mod(np.degrees(np.arctan2(grouped["_sin"], grouped["_cos"])), 360.0)


def is_ne_sector(direction_deg: pd.Series) -> pd.Series:
    return (direction_deg <= 90.0) | (direction_deg >= 315.0)


def contiguous_events(hours: list[int]) -> list[tuple[int, int]]:
    if not hours:
        return []
    events: list[tuple[int, int]] = []
    start = hours[0]
    prev = hours[0]
    for hour in hours[1:]:
        if hour == prev + 1:
            prev = hour
            continue
        events.append((start, prev))
        start = hour
        prev = hour
    events.append((start, prev))
    return events


def hour_to_datetime_map(df: pd.DataFrame) -> pd.Series:
    return df.drop_duplicates("hour_of_year").set_index("hour_of_year")["datetime"]


def main() -> None:
    df = pd.read_csv(LONG_CSV)
    if len(df) != 219000 or df["grid_id"].nunique() != 25:
        raise ValueError("Expected refined 25-point long file with 219000 rows")
    if set(df["data_source"].unique()) != {"OpenMeteo_ERA5_Seamless"}:
        raise ValueError("Unexpected data_source in refined long file")

    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")

    row_speed = (
        df.groupby(["hour_of_year", "grid_row"], sort=True)["wind_speed_15m_ms"]
        .mean()
        .unstack("grid_row")
        .sort_index()
    )
    row_direction = circular_mean_deg(df, "wind_direction_15m_deg", ["hour_of_year", "grid_row"]).unstack("grid_row").sort_index()
    hour_to_dt = hour_to_datetime_map(df)

    north_speed = row_speed[4]
    south_speed = row_speed[0]
    north_dir = row_direction[4]
    south_dir = row_direction[0]

    nov_hours = df.loc[df["month"] == 11, "hour_of_year"].drop_duplicates().sort_values().to_numpy()
    nov_index = pd.Index(nov_hours)

    # Candidate "north-first Amihan arrival" hours:
    # north row already in NE sector, south row not yet in NE sector, and north row also faster.
    candidate = (
        is_ne_sector(north_dir)
        & ~is_ne_sector(south_dir)
        & (north_speed > south_speed)
    )
    nov_candidate_hours = [int(hour) for hour in nov_index if bool(candidate.loc[hour])]
    nov_events = [event for event in contiguous_events(nov_candidate_hours) if (event[1] - event[0] + 1) >= 3]

    afternoon = df[df["hour_of_day"].between(12, 17)]
    afternoon_row_mean = (
        afternoon.groupby("grid_row", sort=True)["wind_speed_15m_ms"]
        .mean()
        .sort_index(ascending=False)
    )
    afternoon_north_vs_south_pct = float(
        (
            afternoon.loc[afternoon["grid_row"] == 4].groupby("hour_of_year")["wind_speed_15m_ms"].mean()
            >
            afternoon.loc[afternoon["grid_row"] == 0].groupby("hour_of_year")["wind_speed_15m_ms"].mean()
        ).mean()
        * 100.0
    )

    overall_row_mean = (
        df.groupby("grid_row", sort=True)["wind_speed_15m_ms"]
        .mean()
        .sort_index(ascending=False)
    )

    df["wpd_15"] = 0.5 * df["air_density_kgm3"] * np.power(df["wind_speed_15m_ms"], 3)
    hotspot = (
        df.groupby(["grid_id", "grid_row", "grid_col"], sort=True)["wpd_15"]
        .mean()
        .reset_index()
        .sort_values("wpd_15", ascending=False)
    )

    summary_lines = [
        "CDO Refined Spatial Field Analysis",
        f"Source file: {LONG_CSV.name}",
        "",
        "Afternoon north-to-south row mean ws15 (12:00-17:59):",
    ]
    for row, value in afternoon_row_mean.items():
        summary_lines.append(f"- R{int(row)} mean ws15: {value:.6f} m/s")
    summary_lines.extend(
        [
            f"- Afternoon hours with north row faster than south row: {afternoon_north_vs_south_pct:.2f}%",
            "",
            "Overall north-to-south row mean ws15:",
        ]
    )
    for row, value in overall_row_mean.items():
        summary_lines.append(f"- R{int(row)} mean ws15: {value:.6f} m/s")

    summary_lines.extend(
        [
            "",
            "November north-first Amihan reanalysis candidate events:",
            "- Interpretation note: these are reanalysis-supported candidate events, not measurement proof of front arrival.",
            (
                f"- Candidate hours: {len(nov_candidate_hours)}"
            ),
            (
                f"- Contiguous events >= 3 hours: {len(nov_events)}"
            ),
        ]
    )
    if nov_events:
        for start, end in nov_events[:10]:
            duration = end - start + 1
            summary_lines.append(
                f"- {hour_to_dt.loc[start]} to {hour_to_dt.loc[end]} "
                f"({duration} h): north dir {north_dir.loc[start]:.1f} deg, "
                f"south dir {south_dir.loc[start]:.1f} deg, "
                f"north ws15 {north_speed.loc[start]:.3f}, south ws15 {south_speed.loc[start]:.3f}"
            )
    else:
        summary_lines.append("- No November events met the >= 3 hour threshold.")

    summary_lines.extend(
        [
            "",
            "Top 5 mean WPD hotspots at 15 m:",
        ]
    )
    for row in hotspot.head(5).itertuples(index=False):
        summary_lines.append(
            f"- {row.grid_id}: {row.wpd_15:.6f} W/m^2 (row={row.grid_row}, col={row.grid_col})"
        )

    summary_lines.extend(
        [
            "",
            "Bottom 5 mean WPD cells at 15 m:",
        ]
    )
    for row in hotspot.tail(5).sort_values("wpd_15", ascending=True).itertuples(index=False):
        summary_lines.append(
            f"- {row.grid_id}: {row.wpd_15:.6f} W/m^2 (row={row.grid_row}, col={row.grid_col})"
        )

    SUMMARY_TXT.write_text("\n".join(summary_lines) + "\n", encoding="ascii")

    print("\n".join(summary_lines))
    print(f"\nSaved {SUMMARY_TXT.resolve()}")


if __name__ == "__main__":
    main()
