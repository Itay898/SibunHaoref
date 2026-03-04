from fastapi import APIRouter

from ..models import CurrentAlertsResponse, StoredAlert
from ..services.alert_store import store

router = APIRouter()


@router.get("/alerts/current")
async def get_current_alerts() -> CurrentAlertsResponse:
    active_alerts = store.get_current_active()
    return CurrentAlertsResponse(
        active=len(active_alerts) > 0,
        alerts=[
            StoredAlert(
                id=a["id"],
                cat=a.get("cat", 0),
                title=a.get("title", ""),
                areas=a.get("areas", []),
                timestamp=a.get("timestamp", 0),
            )
            for a in active_alerts
        ],
        connected=store.is_connected(),
    )
