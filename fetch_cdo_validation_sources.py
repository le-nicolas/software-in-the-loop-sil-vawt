from __future__ import annotations

import calendar
import csv
import io
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from CDO_project_constants import (
    ALPHA_CDO_CANONICAL,
    CDO_CENTER_WS15_MEAN,
    GRID_LATITUDES,
    GRID_LONGITUDES,
    OPENMETEO_ARCHIVE_URL,
)


UTC = timezone.utc
PH_TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent

NOAA_RAW_PATH = ROOT / "LUMBIA_ISD_2023_raw.csv"
OGIMET_RAW_PATH = ROOT / "OGIMET_SYNOP_2023_raw.csv"
OPENMETEO_RAW_PATH = ROOT / "OPENMETEO_ERA5_2023_raw.csv"

NOAA_STATION = "987470-99999"
NOAA_SERVICE_STATION = "98747099999"
OGIMET_PRIMARY = "98747"
OGIMET_ALT = "98743"
CDO_LAT = GRID_LATITUDES[2]
CDO_LON = GRID_LONGITUDES[2]


@dataclass
class Summary:
    source: str
    source_type: str
    rows: int
    missing_pct: float
    mean_ws10m: float | None
    mean_ws15m: float | None
    deviation_vs_merra2_pct: float | None
    deviation_vs_merra2_abs: float | None


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def parse_float(value: str | None) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if math.isnan(number):
        return None
    return number


def safe_mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return statistics.fmean(present)


def missing_pct(values: Iterable[float | None], total_rows: int) -> float:
    if total_rows == 0:
        return 100.0
    missing = sum(1 for value in values if value is None)
    return missing * 100.0 / total_rows


def temporal_resolution_label(datetimes: list[datetime]) -> str:
    if len(datetimes) < 2:
        return "insufficient rows"
    deltas = []
    for previous, current in zip(datetimes, datetimes[1:]):
        delta_hours = (current - previous).total_seconds() / 3600.0
        if delta_hours > 0:
            deltas.append(round(delta_hours, 3))
    if not deltas:
        return "non-increasing timestamps"
    counts = Counter(deltas)
    top_delta, top_count = counts.most_common(1)[0]
    coverage = top_count * 100.0 / len(deltas)
    if top_delta.is_integer():
        top_delta_text = f"{int(top_delta)}h"
    else:
        top_delta_text = f"{top_delta:g}h"
    if coverage >= 95:
        return top_delta_text
    return f"irregular, most common step {top_delta_text} ({coverage:.1f}% of gaps)"


def compare_to_merra2(mean_ws15m: float | None) -> tuple[float | None, float | None]:
    if mean_ws15m is None:
        return None, None
    abs_diff = mean_ws15m - CDO_CENTER_WS15_MEAN
    pct = abs_diff * 100.0 / CDO_CENTER_WS15_MEAN
    return abs_diff, pct


def parse_noaa_wnd(raw_wnd: str) -> tuple[float | None, float | None, str | None, str | None, bool]:
    # ISD WND convention is direction, direction_quality, type_code, speed, speed_quality.
    parts = (raw_wnd or "").split(",")
    if len(parts) != 5:
        return None, None, None, None, False
    direction_raw, direction_quality, type_code, speed_raw, speed_quality = parts
    suspect = direction_quality in {"2", "3", "6", "7"} or speed_quality in {"2", "3", "6", "7"}

    wind_speed_ms = None
    if speed_raw and speed_raw != "9999":
        wind_speed_ms = int(speed_raw) / 10.0

    wind_direction_deg = None
    if direction_raw and direction_raw != "999":
        wind_direction_deg = float(direction_raw)

    return wind_speed_ms, wind_direction_deg, speed_quality, direction_quality, suspect


def fetch_noaa_isd() -> tuple[Summary, list[dict[str, str]]]:
    window_start = "2022-12-31T16:00:00"
    window_end = "2023-12-31T15:59:59"
    rows_iterable: list[dict[str, str]] | None = None

    csv_params = {
        "dataset": "global-hourly",
        "stations": NOAA_SERVICE_STATION,
        "startDate": window_start,
        "endDate": window_end,
        "format": "csv",
        "includeStationName": "true",
        "includeStationLocation": "true",
        "units": "metric",
    }
    csv_url = f"https://www.ncei.noaa.gov/access/services/data/v1?{urlencode(csv_params)}"
    raw_csv = fetch_text(csv_url)
    csv_rows = list(csv.DictReader(io.StringIO(raw_csv)))
    if csv_rows:
        rows_iterable = csv_rows
    else:
        json_params = dict(csv_params)
        json_params["format"] = "json"
        json_url = f"https://www.ncei.noaa.gov/access/services/data/v1?{urlencode(json_params)}"
        json_rows = fetch_json(json_url)
        if isinstance(json_rows, list) and json_rows:
            rows_iterable = json_rows
        else:
            raise RuntimeError("NOAA access service returned no rows in CSV or JSON format.")

    rows = []
    for row in rows_iterable:
        dt_utc = datetime.fromisoformat(row["DATE"]).replace(tzinfo=UTC)
        dt_local = dt_utc.astimezone(PH_TZ)
        if not (datetime(2023, 1, 1, tzinfo=PH_TZ) <= dt_local < datetime(2024, 1, 1, tzinfo=PH_TZ)):
            continue

        wind_speed_ms, wind_direction_deg, speed_quality, direction_quality, suspect = parse_noaa_wnd(row.get("WND", ""))
        parsed = dict(row)
        parsed["datetime_utc"] = dt_utc.isoformat()
        parsed["datetime_ph"] = dt_local.isoformat()
        parsed["wind_speed_ms"] = "" if wind_speed_ms is None else f"{wind_speed_ms:.3f}"
        parsed["wind_direction_deg"] = "" if wind_direction_deg is None else f"{wind_direction_deg:.1f}"
        parsed["wind_speed_quality"] = speed_quality or ""
        parsed["wind_direction_quality"] = direction_quality or ""
        parsed["wind_suspect_flag"] = "1" if suspect else "0"
        rows.append(parsed)

    if not rows:
        raise RuntimeError("NOAA ISD returned zero rows after civil 2023 filtering.")

    fieldnames = list(rows[0].keys())
    with NOAA_RAW_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ws_values = [parse_float(row["wind_speed_ms"]) for row in rows]
    wd_values = [parse_float(row["wind_direction_deg"]) for row in rows]
    dt_values = [datetime.fromisoformat(row["datetime_ph"]) for row in rows]
    ws15_values = [
        None if ws is None else ws * ((15.0 / 10.0) ** ALPHA_CDO_CANONICAL)
        for ws in ws_values
    ]
    mean_ws15 = safe_mean(ws15_values)
    abs_diff, pct_diff = compare_to_merra2(mean_ws15)

    station_name = rows[0].get("STATION NAME", rows[0].get("NAME", ""))
    station_lat = rows[0].get("LATITUDE", "")
    station_lon = rows[0].get("LONGITUDE", "")

    print("FETCH 1 — NOAA ISD Lumbia Airport")
    print(f"Rows fetched: {len(rows)}")
    print(f"Date range (PH): {rows[0]['datetime_ph']} to {rows[-1]['datetime_ph']}")
    print(f"Missing wind speed %: {missing_pct(ws_values, len(rows)):.2f}")
    print(f"Missing wind direction %: {missing_pct(wd_values, len(rows)):.2f}")
    print(f"Mean wind speed (m/s): {safe_mean(ws_values):.6f}")
    print(f"Station: {station_name} ({station_lat}, {station_lon})")
    print(f"Temporal resolution: {temporal_resolution_label(dt_values)}")
    print()

    return (
        Summary(
            source="NOAA ISD Lumbia",
            source_type="Measured station",
            rows=len(rows),
            missing_pct=missing_pct(ws_values, len(rows)),
            mean_ws10m=safe_mean(ws_values),
            mean_ws15m=mean_ws15,
            deviation_vs_merra2_pct=pct_diff,
            deviation_vs_merra2_abs=abs_diff,
        ),
        rows,
    )


def parse_ogimet_line(line: str, station: str) -> dict[str, str] | None:
    parts = line.strip().split(",", 6)
    if len(parts) != 7:
        return None
    station_code, year, month, day, hour, minute, synop = parts
    if station_code != station:
        return None
    synop = synop.strip()
    if synop == "NIL":
        return {
            "station": station_code,
            "datetime_utc": f"{year}-{month}-{day}T{hour}:{minute}:00+00:00",
            "datetime_ph": (
                datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=UTC)
                .astimezone(PH_TZ)
                .isoformat()
            ),
            "synop_raw": synop,
            "wind_speed_ms": "",
            "wind_direction_deg": "",
            "wind_unit_code": "",
            "missing_wind_flag": "1",
        }

    groups = synop.replace("=", "").split()
    if len(groups) < 5 or groups[0] != "AAXX":
        return None

    yyggiw = groups[1]
    i_w = yyggiw[-1]
    station_token = groups[2]
    if station_token != station:
        return None
    nddff = groups[4]
    if len(nddff) != 5 or not nddff.isdigit():
        wind_direction = None
        wind_speed = None
    else:
        dd = nddff[1:3]
        ff = nddff[3:5]
        wind_direction = None if dd in {"//", "99"} else float(dd) * 10.0
        wind_speed = None if ff == "//" else float(ff)
        if i_w in {"3", "4"} and wind_speed is not None:
            wind_speed *= 0.514444

    dt_utc = datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=UTC)
    dt_local = dt_utc.astimezone(PH_TZ)

    return {
        "station": station_code,
        "datetime_utc": dt_utc.isoformat(),
        "datetime_ph": dt_local.isoformat(),
        "synop_raw": synop,
        "wind_speed_ms": "" if wind_speed is None else f"{wind_speed:.3f}",
        "wind_direction_deg": "" if wind_direction is None else f"{wind_direction:.1f}",
        "wind_unit_code": i_w,
        "missing_wind_flag": "1" if (wind_speed is None or wind_direction is None) else "0",
    }


def fetch_ogimet_month(station: str, month: int) -> list[dict[str, str]]:
    year = 2023
    last_day = calendar.monthrange(year, month)[1]
    begin = f"{year}{month:02d}010000"
    end = f"{year}{month:02d}{last_day:02d}2300"
    urls = [
        f"https://www.ogimet.com/cgi-bin/getsynop?block={station[:3]}&begin={begin}&end={end}",
        f"https://www.ogimet.com/cgi-bin/getsynop?block={station}&begin={begin}&end={end}",
    ]
    for url in urls:
        try:
            content = fetch_text(url)
        except HTTPError:
            continue
        rows = []
        for line in content.splitlines():
            parsed = parse_ogimet_line(line, station)
            if parsed is not None:
                rows.append(parsed)
        if rows:
            return rows
    return []


def fetch_ogimet() -> Summary:
    test_rows = fetch_ogimet_month(OGIMET_PRIMARY, 1)
    station = OGIMET_PRIMARY
    if not test_rows:
        test_rows = fetch_ogimet_month(OGIMET_ALT, 1)
        station = OGIMET_ALT
    if not test_rows:
        raise RuntimeError("OGIMET returned no January 2023 data for stations 98747 and 98743.")

    print("FETCH 2 — OGIMET SYNOP")
    print("First 5 parsed observations:")
    for row in test_rows[:5]:
        print(
            f"{row['datetime_utc']} UTC | ws={row['wind_speed_ms'] or 'NaN'} m/s | "
            f"wd={row['wind_direction_deg'] or 'NaN'} deg"
        )
    print()

    all_rows: list[dict[str, str]] = []
    for month in range(1, 13):
        monthly_rows = fetch_ogimet_month(station, month)
        all_rows.extend(monthly_rows)

    if not all_rows:
        raise RuntimeError("OGIMET full-year fetch returned zero rows.")

    with OGIMET_RAW_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    dt_values = [datetime.fromisoformat(row["datetime_ph"]) for row in all_rows]
    ws_values = [parse_float(row["wind_speed_ms"]) for row in all_rows]
    ws15_values = [
        None if ws is None else ws * ((15.0 / 10.0) ** ALPHA_CDO_CANONICAL)
        for ws in ws_values
    ]
    mean_ws15 = safe_mean(ws15_values)
    abs_diff, pct_diff = compare_to_merra2(mean_ws15)

    print(f"Total observations: {len(all_rows)}")
    print(f"Temporal resolution: {temporal_resolution_label(dt_values)}")
    print(f"Missing wind %: {missing_pct(ws_values, len(all_rows)):.2f}")
    print(f"Mean wind speed (m/s): {safe_mean(ws_values):.6f}")
    print()

    return Summary(
        source=f"OGIMET SYNOP {station}",
        source_type="Measured SYNOP",
        rows=len(all_rows),
        missing_pct=missing_pct(ws_values, len(all_rows)),
        mean_ws10m=safe_mean(ws_values),
        mean_ws15m=mean_ws15,
        deviation_vs_merra2_pct=pct_diff,
        deviation_vs_merra2_abs=abs_diff,
    )


def fetch_openmeteo() -> Summary:
    params = {
        "latitude": f"{CDO_LAT}",
        "longitude": f"{CDO_LON}",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "hourly": "windspeed_10m,winddirection_10m,windspeed_100m",
        "wind_speed_unit": "ms",
        "timezone": "Asia/Manila",
    }
    url = f"{OPENMETEO_ARCHIVE_URL}?{urlencode(params)}"
    payload = fetch_json(url)
    hourly = payload["hourly"]
    times = hourly["time"]
    ws10 = hourly["windspeed_10m"]
    wd10 = hourly["winddirection_10m"]
    ws100 = hourly["windspeed_100m"]
    rows = []
    ws15_values: list[float | None] = []
    for timestamp, speed10, dir10, speed100 in zip(times, ws10, wd10, ws100):
        speed10_value = parse_float(str(speed10))
        ws15 = None if speed10_value is None else speed10_value * ((15.0 / 10.0) ** ALPHA_CDO_CANONICAL)
        ws15_values.append(ws15)
        rows.append(
            {
                "datetime_ph": timestamp,
                "wind_speed_10m_ms": "" if speed10_value is None else f"{speed10_value:.6f}",
                "wind_direction_10m_deg": "" if dir10 is None else f"{float(dir10):.6f}",
                "wind_speed_100m_ms": "" if speed100 is None else f"{float(speed100):.6f}",
                "wind_speed_15m_ms": "" if ws15 is None else f"{ws15:.6f}",
            }
        )

    with OPENMETEO_RAW_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    dt_values = [datetime.fromisoformat(row["datetime_ph"]) for row in rows]
    ws10_values = [parse_float(row["wind_speed_10m_ms"]) for row in rows]
    mean_ws10 = safe_mean(ws10_values)
    mean_ws15 = safe_mean(ws15_values)
    abs_diff, pct_diff = compare_to_merra2(mean_ws15)

    print("FETCH 3 — Open-Meteo ERA5")
    print(f"Total rows: {len(rows)}")
    print(f"Date range: {rows[0]['datetime_ph']} to {rows[-1]['datetime_ph']}")
    print(f"Missing wind_speed_10m_ms: {missing_pct(ws10_values, len(rows)):.2f}%")
    print(
        "Missing wind_direction_10m_deg: "
        f"{missing_pct((parse_float(row['wind_direction_10m_deg']) for row in rows), len(rows)):.2f}%"
    )
    print(
        "Missing wind_speed_100m_ms: "
        f"{missing_pct((parse_float(row['wind_speed_100m_ms']) for row in rows), len(rows)):.2f}%"
    )
    print(f"Mean wind_speed_10m_ms: {mean_ws10:.6f}")
    print(f"Mean wind_speed_15m_ms: {mean_ws15:.6f}")
    print(
        f"vs MERRA-2 mean {CDO_CENTER_WS15_MEAN:.6f} m/s: "
        f"{abs_diff:+.6f} m/s ({pct_diff:+.2f}%)"
    )
    print()

    return Summary(
        source="Open-Meteo ERA5",
        source_type="Reanalysis model",
        rows=len(rows),
        missing_pct=missing_pct(ws10_values, len(rows)),
        mean_ws10m=mean_ws10,
        mean_ws15m=mean_ws15,
        deviation_vs_merra2_pct=pct_diff,
        deviation_vs_merra2_abs=abs_diff,
    )


def print_summary_table(summaries: list[Summary]) -> None:
    print("COMPARISON SUMMARY")
    print("Source | Type | Rows | Missing% | Mean WS10m | Mean WS15m | vs MERRA-2 deviation")
    for summary in summaries:
        mean_ws10m = "NaN" if summary.mean_ws10m is None else f"{summary.mean_ws10m:.6f}"
        mean_ws15m = "NaN" if summary.mean_ws15m is None else f"{summary.mean_ws15m:.6f}"
        deviation = (
            "NaN"
            if summary.deviation_vs_merra2_abs is None
            else f"{summary.deviation_vs_merra2_abs:+.6f} m/s ({summary.deviation_vs_merra2_pct:+.2f}%)"
        )
        print(
            f"{summary.source} | {summary.source_type} | {summary.rows} | "
            f"{summary.missing_pct:.2f} | {mean_ws10m} | {mean_ws15m} | {deviation}"
        )
    print()


def print_assessment(summaries: list[Summary]) -> None:
    most_complete = min(summaries, key=lambda item: item.missing_pct)
    comparable = [item for item in summaries if item.deviation_vs_merra2_abs is not None]
    closest = min(comparable, key=lambda item: abs(item.deviation_vs_merra2_abs))
    isd = next(item for item in summaries if item.source == "NOAA ISD Lumbia")
    if isd.mean_ws15m is None:
        merra_assessment = "Lumbia ISD did not provide enough wind data to compare against MERRA-2."
    elif isd.mean_ws15m > CDO_CENTER_WS15_MEAN:
        merra_assessment = "Lumbia ISD suggests the MERRA-2 baseline was conservative for CDO wind speed."
    elif isd.mean_ws15m < CDO_CENTER_WS15_MEAN:
        merra_assessment = "Lumbia ISD suggests the MERRA-2 baseline was optimistic for CDO wind speed."
    else:
        merra_assessment = "Lumbia ISD matches the MERRA-2 baseline exactly within the computed precision."

    print("ASSESSMENT")
    print(f"Most complete data: {most_complete.source}")
    print(f"Closest mean to MERRA-2 baseline: {closest.source}")
    print(merra_assessment)


def main() -> None:
    summaries: list[Summary] = []
    summaries.append(fetch_noaa_isd()[0])
    summaries.append(fetch_ogimet())
    summaries.append(fetch_openmeteo())
    print_summary_table(summaries)
    print_assessment(summaries)


if __name__ == "__main__":
    main()
