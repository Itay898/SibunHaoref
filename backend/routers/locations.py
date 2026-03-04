import json
import math
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

_areas_cache: list[str] | None = None
_coords_cache: dict[str, dict] | None = None


def _load_areas() -> list[str]:
    global _areas_cache
    if _areas_cache is None:
        areas_path = Path(__file__).parent.parent / "data" / "areas.json"
        with open(areas_path, encoding="utf-8") as f:
            _areas_cache = json.load(f)
    return _areas_cache


def _load_coords() -> dict[str, dict]:
    global _coords_cache
    if _coords_cache is None:
        coords_path = Path(__file__).parent.parent / "data" / "area_coords.json"
        if coords_path.exists():
            with open(coords_path, encoding="utf-8") as f:
                _coords_cache = json.load(f)
        else:
            _coords_cache = {}
    return _coords_cache


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/locations")
async def get_locations() -> list[str]:
    return _load_areas()


@router.get("/locate")
async def locate_nearest(
    lat: float = Query(..., description="User latitude"),
    lon: float = Query(..., description="User longitude"),
    radius: float = Query(5.0, description="Search radius in km"),
):
    """Find the nearest alert areas to the user's GPS location."""
    coords = _load_coords()
    distances = []
    for name, c in coords.items():
        d = _haversine_km(lat, lon, c["lat"], c["lon"])
        if d <= radius:
            distances.append({"name": name, "distance_km": round(d, 2), "migun_time": c.get("migun_time", 90)})

    distances.sort(key=lambda x: x["distance_km"])

    # If nothing within radius, return closest 3
    if not distances:
        all_dists = [
            {"name": name, "distance_km": round(_haversine_km(lat, lon, c["lat"], c["lon"]), 2), "migun_time": c.get("migun_time", 90)}
            for name, c in coords.items()
        ]
        all_dists.sort(key=lambda x: x["distance_km"])
        distances = all_dists[:3]

    nearest = distances[0] if distances else None
    migun_time = nearest["migun_time"] if nearest else 90

    return {
        "areas": [d["name"] for d in distances[:10]],
        "nearest": nearest,
        "migun_time": migun_time,
        "details": distances[:10],
    }
