import asyncio
import json
import logging
import random
import time

import httpx

from config import (
    OREF_ALERTS_URL, OREF_HISTORY_URL, OREF_HEADERS,
    OREF_POLL_INTERVAL_SEC, OREF_TIMEOUT_SEC,
    TZEVAADOM_HISTORY_URL, DEV_MODE,
    ROCKETALERT_API_URL, ROCKETALERT_HISTORY_DAYS,
)
from services.alert_store import store
from routers.locations import _load_areas

logger = logging.getLogger(__name__)


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _parse_oref_alerts(text: str) -> list[dict]:
    text = _strip_bom(text).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Oref JSON response")
        return []
    if isinstance(data, dict):
        data = [data]
    return data


def _parse_rocketalert_timestamp(ts_str: str) -> float:
    """Parse rocketalert.live timestamp like '2026-02-28 10:10:19' (Israel time)."""
    from datetime import datetime, timezone, timedelta
    israel_tz = timezone(timedelta(hours=2))
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=israel_tz)
        return dt.timestamp()
    except (ValueError, TypeError):
        return time.time()


async def _seed_from_rocketalert(client: httpx.AsyncClient) -> bool:
    """Seed history from rocketalert.live API (deep history with rich data)."""
    from datetime import datetime, timedelta
    today = datetime.now()
    from_date = (today - timedelta(days=ROCKETALERT_HISTORY_DAYS)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    url = f"{ROCKETALERT_API_URL}/details?from={from_date}&to={to_date}"

    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if not data.get("success"):
            return False

        payload = data.get("payload", [])
        total = 0
        for day_entry in payload:
            for alert in day_entry.get("alerts", []):
                ts = _parse_rocketalert_timestamp(alert.get("timeStamp", ""))
                # Include both city name and Oref area name for matching
                city_name = alert.get("name", "")
                area_he = alert.get("areaNameHe")
                areas = [city_name]
                if area_he and area_he not in areas:
                    areas.append(area_he)
                if city_name and area_he:
                    store.register_region(city_name, area_he)
                transformed = {
                    "id": f"ra_{alert.get('taCityId', '')}_{alert.get('timeStamp', '')}",
                    "cat": alert.get("alertTypeId", 1),
                    "title": "",
                    "data": areas,
                }
                await store.add_alert(transformed, ts)
                total += 1
        logger.info(f"Seeded {total} alerts from rocketalert.live ({ROCKETALERT_HISTORY_DAYS} days)")
        return True
    except Exception as e:
        logger.warning(f"Failed to seed from rocketalert.live: {e}")
        return False


async def _seed_from_oref(client: httpx.AsyncClient) -> bool:
    """Seed from Oref history API (recent alerts only)."""
    try:
        resp = await client.get(OREF_HISTORY_URL, headers=OREF_HEADERS)
        if resp.status_code == 200:
            alerts = _parse_oref_alerts(resp.text)
            for alert in alerts:
                ts = alert.get("alertDate", time.time())
                if isinstance(ts, str):
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts = dt.timestamp()
                    except (ValueError, TypeError):
                        ts = time.time()
                await store.add_alert(alert, ts)
            logger.info(f"Seeded {len(alerts)} alerts from Oref history")
            return True
    except Exception as e:
        logger.warning(f"Failed to seed from Oref history: {e}")
    return False


async def _seed_from_tzevaadom(client: httpx.AsyncClient) -> bool:
    """Seed from tzevaadom API (fallback)."""
    try:
        resp = await client.get(TZEVAADOM_HISTORY_URL, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            alerts = data if isinstance(data, list) else []
            for alert in alerts[:500]:
                ts = time.time()
                if "alertDate" in alert:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(str(alert["alertDate"]).replace("Z", "+00:00"))
                        ts = dt.timestamp()
                    except (ValueError, TypeError):
                        pass
                transformed = {
                    "id": str(alert.get("rid", "")),
                    "cat": alert.get("cat", 1),
                    "title": alert.get("title", ""),
                    "data": [alert.get("name", "")] if isinstance(alert.get("name"), str) else alert.get("cities", []),
                }
                await store.add_alert(transformed, ts)
            logger.info(f"Seeded {min(len(alerts), 500)} alerts from tzevaadom")
            return True
    except Exception as e:
        logger.warning(f"Failed to seed from tzevaadom: {e}")
    return False


async def _fetch_rocketalert_realtime(client: httpx.AsyncClient, seen_ra_ids: set[str]) -> set[str]:
    """Fetch recent alerts from rocketalert real-time/cached endpoint to fill gaps."""
    try:
        resp = await client.get(f"{ROCKETALERT_API_URL}/real-time/cached", timeout=15)
        if resp.status_code != 200:
            return seen_ra_ids
        data = resp.json()
        if not data.get("success"):
            return seen_ra_ids

        payload = data.get("payload", [])
        added = 0
        new_seen = set(seen_ra_ids)
        for alert in payload:
            ts_str = alert.get("timeStamp", "")
            name = alert.get("name", "")
            ra_id = f"ra_rt_{name}_{ts_str}"
            if ra_id in new_seen:
                continue
            new_seen.add(ra_id)
            ts = _parse_rocketalert_timestamp(ts_str)
            areas = [name]
            area_he = alert.get("areaNameHe")
            if area_he and area_he not in areas:
                areas.append(area_he)
            if name and area_he:
                store.register_region(name, area_he)
            transformed = {
                "id": ra_id,
                "cat": alert.get("alertTypeId", 1),
                "title": "",
                "data": areas,
            }
            await store.add_alert(transformed, ts)
            added += 1
        if added:
            logger.info(f"Added {added} alerts from rocketalert real-time")
        return new_seen
    except Exception as e:
        logger.warning(f"Rocketalert real-time fetch failed: {e}")
        return seen_ra_ids


async def _seed_history(client: httpx.AsyncClient) -> set[str]:
    """Fetch alert history on startup. Returns seen RT IDs."""
    # Try rocketalert first (deep history + real-time for recent gap)
    ra_ok = await _seed_from_rocketalert(client)
    seen_rt = set()
    if ra_ok:
        # Fill gap between /details and now with real-time cache
        seen_rt = await _fetch_rocketalert_realtime(client, set())
    else:
        # Fallback: Oref history > tzevaadom
        if not await _seed_from_oref(client):
            await _seed_from_tzevaadom(client)
    count = len(store._history)
    logger.info(f"History seeding complete: {count} total alerts")
    return seen_rt


async def _poll_oref(client: httpx.AsyncClient, last_seen_ids: set[str]) -> tuple[set[str], bool]:
    """Poll Oref for current alerts. Returns (new_seen_ids, success)."""
    try:
        resp = await client.get(OREF_ALERTS_URL, headers=OREF_HEADERS)
        if resp.status_code == 200:
            alerts = _parse_oref_alerts(resp.text)
            if alerts:
                new_ids = set()
                active_alerts = []
                for alert in alerts:
                    aid = str(alert.get("id", ""))
                    new_ids.add(aid)
                    active_alerts.append({
                        "id": aid,
                        "areas": alert.get("data", []),
                        "title": alert.get("title", ""),
                        "cat": alert.get("cat", 0),
                        "timestamp": time.time(),
                    })
                    if aid not in last_seen_ids:
                        await store.add_alert(alert, time.time())
                        logger.info(f"New alert: {alert.get('title', '')} in {alert.get('data', [])}")
                store.set_current_active(active_alerts)
                return new_ids, True
            else:
                store.set_current_active([])
                return set(), True
        return last_seen_ids, False
    except Exception as e:
        logger.warning(f"Oref poll failed: {e}")
        return last_seen_ids, False


async def _poll_tzevaadom_fallback(client: httpx.AsyncClient, last_seen_ids: set[str]) -> tuple[set[str], bool]:
    """Fallback poll using tzevaadom API."""
    try:
        resp = await client.get(TZEVAADOM_HISTORY_URL, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            alerts = data if isinstance(data, list) else []
            if alerts:
                latest = alerts[0]
                rid = str(latest.get("rid", ""))
                if rid and rid not in last_seen_ids:
                    transformed = {
                        "id": rid,
                        "cat": latest.get("cat", 1),
                        "title": latest.get("title", ""),
                        "data": [latest.get("name", "")] if isinstance(latest.get("name"), str) else latest.get("cities", []),
                    }
                    await store.add_alert(transformed, time.time())
                    logger.info(f"New alert (tzevaadom): {transformed['title']} in {transformed['data']}")
                return {rid} if rid else set(), True
            return set(), True
        return last_seen_ids, False
    except Exception as e:
        logger.warning(f"Tzevaadom poll failed: {e}")
        return last_seen_ids, False


async def _dev_mode_loop():
    """Generate synthetic alerts at random intervals for development."""
    areas = _load_areas()
    logger.info("DEV MODE: Generating synthetic alerts")
    while True:
        await asyncio.sleep(random.uniform(30, 120))
        fake_areas = random.sample(areas, min(3, len(areas)))
        alert = {
            "id": f"dev_{int(time.time())}",
            "cat": 1,
            "title": "ירי רקטות וטילים",
            "data": fake_areas,
        }
        await store.add_alert(alert, time.time())
        store.set_current_active([{
            "id": alert["id"],
            "areas": fake_areas,
            "title": alert["title"],
            "cat": 1,
            "timestamp": time.time(),
        }])
        store.set_connected(True)
        logger.info(f"DEV: Synthetic alert in {fake_areas}")
        await asyncio.sleep(15)
        store.set_current_active([])


async def poll_loop():
    """Main polling loop."""
    if DEV_MODE:
        await _dev_mode_loop()
        return

    async with httpx.AsyncClient(timeout=OREF_TIMEOUT_SEC, verify=False) as client:
        seen_ra_rt_ids = await _seed_history(client)

        last_seen_ids: set[str] = set()
        oref_available = True
        consecutive_oref_failures = 0
        poll_counter = 0

        while True:
            if oref_available:
                new_ids, success = await _poll_oref(client, last_seen_ids)
                if success:
                    last_seen_ids = new_ids
                    store.set_connected(True)
                    consecutive_oref_failures = 0
                else:
                    consecutive_oref_failures += 1
                    if consecutive_oref_failures >= 5:
                        logger.warning("Oref unavailable, switching to tzevaadom fallback")
                        oref_available = False
            else:
                new_ids, success = await _poll_tzevaadom_fallback(client, last_seen_ids)
                if success:
                    last_seen_ids = new_ids
                    store.set_connected(True)
                else:
                    store.set_connected(False)
                # Periodically retry Oref
                if poll_counter % 100 == 0:
                    oref_available = True
                    consecutive_oref_failures = 0

            poll_counter += 1

            # Every ~2 min: fetch rocketalert real-time to catch alerts we missed
            if poll_counter % 40 == 0:
                seen_ra_rt_ids = await _fetch_rocketalert_realtime(client, seen_ra_rt_ids)

            # Every ~30 min: prune old data
            if poll_counter % 600 == 0:
                await store.prune_old()

            await asyncio.sleep(OREF_POLL_INTERVAL_SEC)
