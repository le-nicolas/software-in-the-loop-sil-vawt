from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from viz_common import dropna_for_plot, energy_density_wm2, ensure_output_dir, month_label_map, save_figure


def build_viz5_energy_heatmap(df):
    plot_df = dropna_for_plot(
        df,
        ["month", "hour_of_day", "wind_speed_15m_ms", "air_density_kgm3"],
        "Visualization 5",
    )
    plot_df["energy_density"] = energy_density_wm2(plot_df)
    grid = (
        plot_df.groupby(["hour_of_day", "month"], sort=True)["energy_density"]
        .mean()
        .unstack("month")
        .reindex(index=range(24), columns=range(1, 13))
    )
    x = np.array(grid.columns.tolist())
    y = np.array(grid.index.tolist())
    z = grid.to_numpy()

    fig = go.Figure(
        data=[
            go.Surface(
                x=x,
                y=y,
                z=z,
                colorscale="Viridis",
                contours={
                    "z": {"show": True, "usecolormap": True, "project_z": True}
                },
                hovertemplate=(
                    "Month: %{x}<br>"
                    "Hour of day: %{y}<br>"
                    "Mean energy density: %{z:.3f} W/m²<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        title="CDO Wind Energy Density by Month and Hour of Day 2023",
        scene={
            "xaxis_title": "Month",
            "yaxis_title": "Hour of day",
            "zaxis_title": "Mean energy density (W/m²)",
            "xaxis": {
                "tickvals": list(range(1, 13)),
                "ticktext": [month_label_map()[m] for m in range(1, 13)],
            },
        },
    )

    peak_idx = np.unravel_index(np.nanargmax(z), z.shape)
    peak_hour = int(y[peak_idx[0]])
    peak_month = int(x[peak_idx[1]])

    output_path = ensure_output_dir() / "viz5_energy_heatmap.html"
    save_figure(fig, output_path)
    return output_path, peak_month, peak_hour
