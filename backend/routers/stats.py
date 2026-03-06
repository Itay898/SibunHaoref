from fastapi import APIRouter, Query

from ..services.alert_store import store
from .locations import _load_coords

router = APIRouter()


@router.get("/stats")
async def get_stats(
    location: str = Query(..., description="Pipe-delimited area names"),
    window_days: int = Query(30, ge=1, le=90, description="History window in days"),
):
    """Return alert count, shelter time, and city ranking for given areas."""
    areas = [a.strip() for a in location.split("|") if a.strip()]
    stats = store.get_stats_for_areas(areas, window_days)

    coords = _load_coords()
    migun_time = 90
    for area in areas:
        if area in coords:
            migun_time = coords[area].get("migun_time", 90)
            break

    stats["shelter_time_sec"] = stats["alert_count"] * migun_time
    return stats
