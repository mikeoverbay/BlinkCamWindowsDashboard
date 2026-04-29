"""
Background poller that watches Blink's media-changed API for new motion events
and tracks which cameras have recently triggered.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

CREDS_PATH = Path("config/credentials.json")
POLL_INTERVAL = 10         # seconds between API checks         # seconds between API checks
MOTION_HOLD_SECONDS = 30   # how long a camera stays "active" after trigger

# Shared state, accessible to Flask via thread-safe lock
_state_lock = Lock()
_active_cameras = {}    # {camera_name: {"first_seen": ts, "last_event": ts, "source": str, "cv": [...]}}
_seen_event_ids = set()


def get_active_cameras():
    """Return dict of currently-active cameras (within MOTION_HOLD_SECONDS)."""
    now = time.time()
    with _state_lock:
        # Prune stale entries
        expired = [
            name for name, data in _active_cameras.items()
            if now - data["last_event"] > MOTION_HOLD_SECONDS
        ]
        for name in expired:
            del _active_cameras[name]
        # Return a copy
        return {
            name: {
                "since_seconds": round(now - data["first_seen"], 1),
                "source": data["source"],
                "cv_detection": data["cv"],
            }
            for name, data in _active_cameras.items()
        }


def _record_event(event):
    """Record a single event into active state."""
    cam = event.get("device_name")
    if not cam:
        return
    src = event.get("source", "")
    cv = []
    try:
        meta = json.loads(event.get("metadata") or "{}")
        cv = meta.get("cv_detection", []) or []
    except (json.JSONDecodeError, TypeError):
        pass

    now = time.time()
    with _state_lock:
        if cam not in _active_cameras:
            _active_cameras[cam] = {
                "first_seen": now,
                "last_event": now,
                "source": src,
                "cv": cv,
            }
        else:
            _active_cameras[cam]["last_event"] = now
            _active_cameras[cam]["source"] = src
            if cv:
                _active_cameras[cam]["cv"] = cv


async def _poll_loop():
    """Async loop that hits Blink's API and records new events."""
    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        # Skip events that exist BEFORE we start (don't replay history)
        first_pass = True

        while True:
            try:
                since = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime(
                    "%Y-%m-%dT%H:%M:%S+0000"
                )
                url = (
                    f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
                    f"/media/changed?since={since}&page=1"
                )
                resp = await blink.auth.query(
                    url=url, headers=blink.auth.header,
                    reqtype="get", json_resp=True
                )
                events = resp.get("media", []) if isinstance(resp, dict) else []

                for ev in events:
                    eid = ev.get("id")
                    if eid is None or eid in _seen_event_ids:
                        continue
                    _seen_event_ids.add(eid)
                    if first_pass:
                        continue
                    _record_event(ev)

                # Cap the seen-IDs set so it doesn't grow unbounded
                if len(_seen_event_ids) > 5000:
                    # Keep newest half
                    sorted_ids = sorted(_seen_event_ids)[-2500:]
                    _seen_event_ids.clear()
                    _seen_event_ids.update(sorted_ids)

                first_pass = False
            except Exception as e:
                print(f"[motion_tracker] poll error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


def start_background_thread():
    """Start the poll loop in a background thread (called once from web_app.py)."""
    import threading

    def runner():
        asyncio.new_event_loop().run_until_complete(_poll_loop())

    t = threading.Thread(target=runner, daemon=True, name="MotionTracker")
    t.start()
    return t