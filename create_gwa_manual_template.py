from __future__ import annotations

from pathlib import Path

import pandas as pd

from CDO_spatial_multipliers import SPATIAL_MULTIPLIERS


OUTPUT_CSV = Path("CDO_gwa_manual_template.csv")
LATITUDES = [8.282, 8.382, 8.482, 8.582, 8.682]
LONGITUDES = [124.447, 124.547, 124.647, 124.747, 124.847]


def main() -> None:
    rows = []
    for row, lat in enumerate(LATITUDES):
        for col, lon in enumerate(LONGITUDES):
            grid_id = f"R{row}C{col}"
            rows.append(
                {
                    "grid_id": grid_id,
                    "grid_row": row,
                    "grid_col": col,
                    "latitude": lat,
                    "longitude": lon,
                    "speed_multiplier": SPATIAL_MULTIPLIERS[grid_id],
                    "direction_offset_deg": 0.0,
                    "source_type": "placeholder_terrain_multiplier",
                    "source_note": "Replace with manual Global Wind Atlas derived adjustment.",
                    "ready_for_refined_build": 0,
                }
            )
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    print(f"Saved manual GWA template to {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
