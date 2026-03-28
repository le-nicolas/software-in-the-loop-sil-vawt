# Unity VAWT Conversion

This folder is a Unity-ready scaffold for converting `viz9_dpcbf_sphere_3d.py` into a native Unity experience.

## Current Sync Status

This scaffold now mirrors the current research-side SIL assumptions more closely than the original Unity placeholder.

- lookup-table `Cp(TSR)` replaces the old parabola
- startup-to-MPPT handoff matches the current low-TSR SIL behavior
- overspeed braking is less trigger-happy and only acts as a real protection mode
- rated power is capped at `0.38 kW`, matching the present honest physics ceiling rather than the old unreachable `1.0 kW`
- HUD output now shows controller mode, electrical power, torque balance, and cap hits

The Unity side is still a research visualization layer, not a validated digital twin. It uses the center-series hourly wind data rather than the full ring-resolved SIL forcing stack.

## What Is Included

- `Assets/Scripts/Data`
  runtime CSV loading from `StreamingAssets`
- `Assets/Scripts/Physics`
  wind decomposition, rotor-state visualization, and CBF capture monitoring
- `Assets/Scripts/Scene`
  spheres, rotor geometry, particles, and wind arrow support
- `Assets/Scripts/UI`
  HUD graphs and directional capture histogram
- `Assets/Scripts/Camera`
  orbit camera and playback timeline
- `Assets/Scripts/Controls`
  real-time parameter slider bindings
- `Assets/StreamingAssets/CDO_wind_2023_hourly.csv`
  the runtime data source used by `WindDataLoader`

## Recommended Unity Setup

1. Open this folder directly as a Unity project. A minimal `Packages/` and `ProjectSettings/` baseline is now included.
2. The installed editor on this machine is `6000.3.5f1`, which should open the project directly.
3. Create a scene named `VAWTScene`.
4. Add a root GameObject named `VAWTSystem`.
5. Attach these scripts to the scene:
   `WindDataLoader`, `WindDecomposer`, `RotorPhysics`, `CBFMonitor`,
   `SphereZones`, `VAWTParticles`, `RotorMesh`, `HUDController`,
   `DirectionHistogram`, `OrbitCamera`, `TimelineSlider`, `ParameterPanel`
6. Create a Canvas with:
   - two `RawImage` slots for the HUD graphs
   - one `RawImage` slot for the directional histogram
   - text labels for status and alerts
   - sliders for timeline and parameters
7. Wire the script references in the Inspector.
8. Press play. The loader reads `StreamingAssets/CDO_wind_2023_hourly.csv` at runtime.

## Notes

- The scripts are written to be inspector-friendly and runtime-generated where possible.
- No third-party chart package is required; the HUD and polar summary are drawn into `Texture2D` surfaces.
- The repo now includes the minimum project files needed to open directly, but scenes, materials, prefabs, and `.meta` assets are still intentionally lightweight.
