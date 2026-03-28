from __future__ import annotations

import shutil
from pathlib import Path

from pipeline_contracts import STREAMING_ASSETS_PATH, UNITY_INPUTS, resolve_source_path


def _is_up_to_date(source: Path, destination: Path) -> bool:
    if not destination.exists():
        return False
    return destination.stat().st_mtime >= source.stat().st_mtime and destination.stat().st_size == source.stat().st_size


def sync_to_unity() -> tuple[int, int]:
    if not STREAMING_ASSETS_PATH.exists():
        raise FileNotFoundError(
            f"Unity StreamingAssets path not found: {STREAMING_ASSETS_PATH}. "
            "Create the Unity project first or point the repo at an existing UnityVAWT project."
        )

    copied = 0
    skipped = 0
    for file_name in UNITY_INPUTS:
        source = resolve_source_path(file_name)
        if not source.exists():
            raise FileNotFoundError(f"Required pipeline file is missing: {source}")

        destination = STREAMING_ASSETS_PATH / Path(file_name).name
        if _is_up_to_date(source, destination):
            skipped += 1
            continue

        shutil.copy2(source, destination)
        copied += 1

    print(f"Synced {copied} files to Unity StreamingAssets. {skipped} skipped (up to date).")
    return copied, skipped


def main() -> None:
    sync_to_unity()


if __name__ == "__main__":
    main()
