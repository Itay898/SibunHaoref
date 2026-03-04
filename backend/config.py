import os

# Oref API
OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HISTORY_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
OREF_POLL_INTERVAL_SEC = 3
OREF_TIMEOUT_SEC = 5

# Fallback community API
TZEVAADOM_HISTORY_URL = "https://api.tzevaadom.co.il/alerts-history"

# RocketAlert.live API (deep history)
ROCKETALERT_API_URL = "https://agg.rocketalert.live/api/v1/alerts"
ROCKETALERT_HISTORY_DAYS = 90  # How many days of history to fetch on startup

# Alert store
ALERT_HISTORY_WINDOW_HOURS = 48
MAX_HISTORY_RECORDS = 50000

# Risk engine weights (sum to 1.0)
WEIGHT_RECENCY = 0.28
WEIGHT_BURST = 0.20
WEIGHT_VOLUME = 0.12
WEIGHT_PATTERN = 0.10
WEIGHT_PROXIMITY = 0.08
WEIGHT_ESCALATION = 0.10
WEIGHT_CLUSTER = 0.07
WEIGHT_DAY_OF_WEEK = 0.05

# Risk level thresholds
LEVEL_GREEN_MAX = 0.20
LEVEL_YELLOW_MAX = 0.40
LEVEL_ORANGE_MAX = 0.60

# Dev mode
DEV_MODE = os.environ.get("DEV_MODE", "").lower() in ("true", "1", "yes")
