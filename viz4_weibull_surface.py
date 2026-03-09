from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from scipy.stats import weibull_min

from viz_common import SEASON_COLORS, dropna_for_plot, ensure_output_dir, save_figure


SEASON_ORDER = ["Amihan", "Transition_DryDown", "Habagat", "Transition_Rampup"]


def build_viz4_weibull_surface(df):
    plot_df = dropna_for_plot(df, ["season", "wind_speed_15m_ms"], "Visualization 4")
    x = np.linspace(0.0, 20.0, 240)
    fig = go.Figure()
    params = {}

    for idx, season in enumerate(SEASON_ORDER):
        season_df = plot_df.loc[plot_df["season"] == season, "wind_speed_15m_ms"]
        if season_df.empty:
            raise ValueError(f"No data for season {season}")
        shape_k, loc, scale_c = weibull_min.fit(season_df.to_numpy(), floc=0)
        params[season] = {"k": float(shape_k), "c": float(scale_c)}
        print(f"Weibull fit {season}: k={shape_k:.6f}, c={scale_c:.6f}")

        pdf = weibull_min.pdf(x, shape_k, loc=loc, scale=scale_c)
        y = np.full_like(x, idx, dtype=float)
        z = np.tile(pdf, (2, 1))
        y_grid = np.vstack([y - 0.28, y + 0.28])
        x_grid = np.vstack([x, x])
        fig.add_trace(
            go.Surface(
                x=x_grid,
                y=y_grid,
                z=z,
                colorscale="Viridis",
                showscale=idx == 0,
                opacity=0.95,
                name=season,
                customdata=np.full_like(x_grid, season, dtype=object),
                hovertemplate=(
                    "Season: %{customdata}<br>"
                    "Wind speed: %{x:.2f} m/s<br>"
                    "PDF: %{z:.5f}<extra></extra>"
                ),
            )
        )

    max_pdf = max(
        weibull_min.pdf(x, params[season]["k"], scale=params[season]["c"]).max()
        for season in SEASON_ORDER
    )
    for x_ref, color, name in [(2.5, "red", "Cut-in"), (12.0, "green", "Rated")]:
        fig.add_trace(
            go.Surface(
                x=np.full((2, 2), x_ref),
                y=np.array([[-0.5, len(SEASON_ORDER) - 0.5], [-0.5, len(SEASON_ORDER) - 0.5]]),
                z=np.array([[0.0, 0.0], [max_pdf, max_pdf]]),
                showscale=False,
                opacity=0.25,
                colorscale=[[0, color], [1, color]],
                name=name,
                hoverinfo="skip",
            )
        )

    fig.update_layout(
        title="CDO Wind Speed Distribution by Season — Weibull Fit 2023",
        scene={
            "xaxis_title": "Wind speed (m/s)",
            "yaxis_title": "Season",
            "zaxis_title": "Probability density",
            "yaxis": {
                "tickvals": list(range(len(SEASON_ORDER))),
                "ticktext": SEASON_ORDER,
            },
        },
        showlegend=False,
    )

    output_path = ensure_output_dir() / "viz4_weibull_surface.html"
    save_figure(fig, output_path)
    return output_path, params
