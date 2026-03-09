from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GridLayout:
    x: np.ndarray
    y: np.ndarray

    @property
    def coordinates(self) -> np.ndarray:
        return np.column_stack([self.x, self.y])


def default_grid_layout() -> GridLayout:
    axis = np.array([-8.0, -4.0, 0.0, 4.0, 8.0], dtype=float)
    points = [(x, y) for y in axis for x in axis]
    return GridLayout(
        x=np.array([p[0] for p in points], dtype=float),
        y=np.array([p[1] for p in points], dtype=float),
    )


def exponential_covariance(coords: np.ndarray, correlation_length: float, epsilon: float = 1e-6) -> np.ndarray:
    deltas = coords[:, None, :] - coords[None, :, :]
    distances = np.sqrt(np.sum(deltas**2, axis=-1))
    covariance = np.exp(-distances / correlation_length)
    covariance += np.eye(len(coords)) * epsilon
    return covariance


def sample_correlated_standard_normals(rng: np.random.Generator, covariance: np.ndarray) -> np.ndarray:
    mean = np.zeros(covariance.shape[0], dtype=float)
    return rng.multivariate_normal(mean=mean, cov=covariance)


class CorrelatedTurbulenceGenerator:
    """
    Spatially correlated, temporally persistent turbulence perturbation model.

    This is a practical next-step model for visualization and early SIL forcing.
    It is not a validated replacement for IEC/Mann/Kaimal field synthesis or CFD.
    """

    def __init__(
        self,
        layout: GridLayout | None = None,
        spatial_corr_length: float = 5.0,
        temporal_persistence: float = 0.85,
        seed: int = 2026,
    ) -> None:
        self.layout = layout or default_grid_layout()
        self.spatial_corr_length = spatial_corr_length
        self.temporal_persistence = temporal_persistence
        self.rng = np.random.default_rng(seed)
        self.covariance = exponential_covariance(self.layout.coordinates, self.spatial_corr_length)
        self._speed_state = np.zeros(len(self.layout.x), dtype=float)
        self._direction_state = np.zeros(len(self.layout.x), dtype=float)

    def reset(self) -> None:
        self._speed_state[:] = 0.0
        self._direction_state[:] = 0.0

    def step(
        self,
        mean_speed: np.ndarray,
        mean_direction_deg: np.ndarray,
        ti: np.ndarray | float,
        direction_sigma_deg: float = 18.0,
    ) -> dict[str, np.ndarray]:
        mean_speed = np.asarray(mean_speed, dtype=float)
        mean_direction_deg = np.asarray(mean_direction_deg, dtype=float)
        ti = np.asarray(ti, dtype=float)
        if ti.ndim == 0:
            ti = np.full_like(mean_speed, float(ti))

        spatial_speed_noise = sample_correlated_standard_normals(self.rng, self.covariance)
        spatial_dir_noise = sample_correlated_standard_normals(self.rng, self.covariance)

        self._speed_state = self.temporal_persistence * self._speed_state + np.sqrt(1.0 - self.temporal_persistence**2) * spatial_speed_noise
        self._direction_state = self.temporal_persistence * self._direction_state + np.sqrt(1.0 - self.temporal_persistence**2) * spatial_dir_noise

        speed = np.clip(mean_speed * (1.0 + ti * self._speed_state), 0.1, None)
        direction = np.mod(mean_direction_deg + direction_sigma_deg * ti * self._direction_state, 360.0)

        radians = np.deg2rad(direction)
        u = speed * np.sin(radians)
        v = speed * np.cos(radians)

        return {
            "speed": speed,
            "direction_deg": direction,
            "u": u,
            "v": v,
        }
