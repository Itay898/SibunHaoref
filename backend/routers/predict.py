from fastapi import APIRouter, Query, HTTPException

from ..models import PredictResponse
from ..services.risk_engine import calculate_risk

router = APIRouter()


@router.get("/predict")
async def predict(
    location: str = Query(..., description="Pipe-delimited area names"),
    duration: int = Query(10, description="Shower duration in minutes"),
) -> PredictResponse:
    areas = [a.strip() for a in location.split("|") if a.strip()]
    if not areas:
        raise HTTPException(status_code=400, detail="At least one location is required")
    return calculate_risk(areas, duration)
