from __future__ import annotations


SPATIAL_FIELD_LABEL = (
    "Spatial field: MERRA-2 single-point time series with terrain-informed "
    "multipliers. Not independently measured spatial data. Replace multipliers "
    "with Global Wind Atlas values for higher accuracy."
)

SPATIAL_METHOD = "MERRA2_center * terrain_multiplier"
DATA_SOURCE = "MERRA2_hybrid"

SPATIAL_MULTIPLIERS = {
    "R4C0": 1.08,
    "R4C1": 1.10,
    "R4C2": 1.12,
    "R4C3": 1.09,
    "R4C4": 1.07,
    "R3C0": 1.04,
    "R3C1": 1.06,
    "R3C2": 1.05,
    "R3C3": 1.03,
    "R3C4": 1.02,
    "R2C0": 1.00,
    "R2C1": 1.01,
    "R2C2": 1.00,
    "R2C3": 0.98,
    "R2C4": 0.97,
    "R1C0": 0.96,
    "R1C1": 0.97,
    "R1C2": 0.95,
    "R1C3": 0.93,
    "R1C4": 0.92,
    "R0C0": 0.88,
    "R0C1": 0.89,
    "R0C2": 0.87,
    "R0C3": 0.85,
    "R0C4": 0.84,
}
