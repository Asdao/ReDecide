"""Coordinate-to-region and coordinate-to-radar transforms for CS2 maps."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS


@dataclass(frozen=True, slots=True)
class NavArea:
    area_id: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    center_x: float
    center_y: float
    center_z: float


class NavRegionIndex:
    """Fast coarse index over Awpy nav-area bounding boxes.

    Awpy nav JSON preserves geometry and area IDs, but not human callout names.
    The returned labels therefore use ``nav_area_<id>`` and remain honest about
    what the data contains.
    """

    def __init__(self, areas: list[NavArea], *, cell_size: float = 512.0) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.areas = tuple(areas)
        self.cell_size = cell_size
        self._grid: dict[tuple[int, int], list[int]] = {}
        for index, area in enumerate(self.areas):
            min_cell_x = math.floor(area.min_x / cell_size)
            max_cell_x = math.floor(area.max_x / cell_size)
            min_cell_y = math.floor(area.min_y / cell_size)
            max_cell_y = math.floor(area.max_y / cell_size)
            for cell_x in range(min_cell_x, max_cell_x + 1):
                for cell_y in range(min_cell_y, max_cell_y + 1):
                    self._grid.setdefault((cell_x, cell_y), []).append(index)

    @classmethod
    def from_path(cls, path: Path, *, cell_size: float = 512.0) -> "NavRegionIndex":
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_areas = payload.get("areas") or {}
        areas: list[NavArea] = []
        for raw in raw_areas.values():
            corners = raw.get("corners") or []
            if not corners:
                continue
            xs = [float(point.get("x", 0.0)) for point in corners]
            ys = [float(point.get("y", 0.0)) for point in corners]
            zs = [float(point.get("z", 0.0)) for point in corners]
            areas.append(
                NavArea(
                    area_id=int(raw.get("area_id", len(areas))),
                    min_x=min(xs),
                    max_x=max(xs),
                    min_y=min(ys),
                    max_y=max(ys),
                    min_z=min(zs),
                    max_z=max(zs),
                    center_x=sum(xs) / len(xs),
                    center_y=sum(ys) / len(ys),
                    center_z=sum(zs) / len(zs),
                )
            )
        if not areas:
            raise ValueError(f"navigation mesh has no areas: {path}")
        return cls(areas, cell_size=cell_size)

    @classmethod
    def for_map(cls, map_name: str, map_root: Path = DATA_PATHS.public_maps) -> "NavRegionIndex | None":
        path = map_root / map_name / f"{map_name}.json"
        if not path.exists():
            return None
        return cls.from_path(path)

    def lookup(self, x: float, y: float, z: float = 0.0) -> str:
        cell = (math.floor(x / self.cell_size), math.floor(y / self.cell_size))
        candidate_indices = self._grid.get(cell, [])
        if not candidate_indices:
            candidate_indices = range(len(self.areas))
        containing: list[NavArea] = []
        for index in candidate_indices:
            area = self.areas[index]
            if area.min_x - 1.0 <= x <= area.max_x + 1.0 and area.min_y - 1.0 <= y <= area.max_y + 1.0:
                if area.min_z - 128.0 <= z <= area.max_z + 128.0:
                    containing.append(area)
        if containing:
            area = min(containing, key=lambda item: abs(item.center_z - z))
        else:
            area = min(
                (self.areas[index] for index in candidate_indices),
                key=lambda item: (item.center_x - x) ** 2 + (item.center_y - y) ** 2 + 0.25 * (item.center_z - z) ** 2,
            )
        return f"nav_area_{area.area_id}"


class RadarTransform:
    """Convert Hammer world positions into overview-image coordinates."""

    def __init__(self, map_data: dict[str, dict[str, Any]]) -> None:
        self.map_data = map_data

    @classmethod
    def from_path(cls, path: Path) -> "RadarTransform":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_root(cls, map_root: Path = DATA_PATHS.public_maps) -> "RadarTransform":
        return cls.from_path(map_root / "map-data.json")

    def world_to_radar(self, map_name: str, x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
        if map_name not in self.map_data:
            raise KeyError(f"no radar transform for map {map_name!r}")
        data = self.map_data[map_name]
        scale = float(data["scale"])
        if scale == 0:
            raise ValueError(f"invalid zero map scale for {map_name!r}")
        return (
            (float(x) - float(data["pos_x"])) / scale,
            (float(data["pos_y"]) - float(y)) / scale,
            float(z),
        )


def region_for_row(row: dict[str, Any], index: NavRegionIndex | None) -> str:
    """Return a nav-area label, falling back to a coarse grid if unavailable."""

    x = float(row.get("X") if row.get("X") is not None else row.get("x") or 0.0)
    y = float(row.get("Y") if row.get("Y") is not None else row.get("y") or 0.0)
    z = float(row.get("Z") if row.get("Z") is not None else row.get("z") or 0.0)
    if index is not None:
        return index.lookup(x, y, z)
    return f"grid:{math.floor(x / 1000.0)}:{math.floor(y / 1000.0)}"
