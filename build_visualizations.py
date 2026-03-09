from __future__ import annotations

from pathlib import Path

from viz1_vector_field import build_viz1_vector_field
from viz2_wind_rose_3d import build_viz2_wind_rose
from viz3_interactive_slider import build_viz3_interactive_slider
from viz4_weibull_surface import build_viz4_weibull_surface
from viz5_energy_heatmap import build_viz5_energy_heatmap
from viz_common import copy_csv_to_output, ensure_output_dir, load_and_validate_csv


def write_summary(
    output_path: Path,
    weibull_params: dict,
    peak_month: int,
    peak_hour: int,
    dominant_direction: str,
    annual_kwh: float,
    cut_in_pct: float,
    warnings: list[str],
) -> None:
    lines = ["Weibull Parameters:"]
    for season, params in weibull_params.items():
        lines.append(f"{season}: k={params['k']:.6f}, c={params['c']:.6f}")
    lines.append("")
    lines.append(f"Peak energy month: {peak_month}")
    lines.append(f"Peak energy hour_of_day: {peak_hour}")
    lines.append(f"Dominant wind direction: {dominant_direction}")
    lines.append(f"Total annual kWh estimate: {annual_kwh:.6f}")
    lines.append(f"Hours above cut-in percentage: {cut_in_pct:.6f}%")
    lines.append("Warnings:")
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("None")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {output_path.resolve()}")


def main() -> None:
    output_dir = ensure_output_dir()
    df, warnings = load_and_validate_csv()
    copy_csv_to_output()

    build_viz1_vector_field(df)
    _, rose_summary, dominant_direction = build_viz2_wind_rose(df)
    _, annual_kwh, file_size_mb = build_viz3_interactive_slider(df, allow_exceed_threshold=True)
    _, weibull_params = build_viz4_weibull_surface(df)
    _, peak_month, peak_hour = build_viz5_energy_heatmap(df)

    print(f"Visualization 3 HTML file size: {file_size_mb:.2f} MB")
    cut_in_pct = float((df["wind_speed_15m_ms"] >= 2.5).mean() * 100.0)
    write_summary(
        output_dir / "viz_summary.txt",
        weibull_params=weibull_params,
        peak_month=peak_month,
        peak_hour=peak_hour,
        dominant_direction=dominant_direction,
        annual_kwh=annual_kwh,
        cut_in_pct=cut_in_pct,
        warnings=warnings,
    )


if __name__ == "__main__":
    main()
