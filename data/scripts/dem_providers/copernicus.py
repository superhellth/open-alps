"""Stub - real implementation lands in Task 2."""

from pathlib import Path


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raise NotImplementedError


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    raise NotImplementedError
