# Unity VAWT Conversion

This folder is a Unity-ready scaffold for converting `viz9_dpcbf_sphere_3d.py` into a native Unity experience.

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

1. Create a new Unity `2022 LTS` project using `URP`.
2. Copy the `UnityVAWT/Assets` folder into that Unity project.
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
- The repo is not yet a full Unity project with generated metadata, scenes, or materials. This scaffold is designed to drop into a new URP project cleanly.
