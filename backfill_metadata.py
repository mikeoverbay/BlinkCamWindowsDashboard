"""
Backfill .json sidecar metadata files for all existing MP4 clips.
Run once to catch up. Idempotent — re-running is safe and skips clips
that already have sidecars.
"""
import asyncio
import configparser
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

from metadata_helper import (
    metadata_path_for,
    write_sidecar,
    match_event_to_file,
)

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "settings.ini"
CREDS_PATH = ROOT / "config" / "credentials.json"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)
CLIPS_DIR = Path(config["download"]["output_dir"])


async def fetch_all_events(blink, days_back: int = 90) -> list:
    """Fetch as many event records as possible from the media-changed API."""
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%S+0000"
    )
    all_events = []
    for page in range(1, 50):  # safety cap
        url = (
            f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
            f"/media/changed?since={since}&page={page}"
        )
        response = await blink.auth.query(
            url=url, headers=blink.auth.header, reqtype="get", json_resp=True
        )
        if not isinstance(response, dict):
            break
        page_events = response.get("media", [])
        if not page_events:
            break
        all_events.extend(page_events)
        print(f"  Page {page}: +{len(page_events)} events (total {len(all_events)})")
    return all_events


async def main():
    print(f"Reading clips from: {CLIPS_DIR}")
    if not CLIPS_DIR.exists():
        print("Clip directory does not exist.")
        return

    # Find all MP4s that don't have sidecars yet
    all_mp4s = list(CLIPS_DIR.glob("*.mp4"))
    needs_sidecar = [m for m in all_mp4s if not metadata_path_for(m).exists()]
    print(f"Found {len(all_mp4s)} MP4s; {len(needs_sidecar)} need sidecars.")

    if not needs_sidecar:
        print("Nothing to do.")
        return

    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        print("\nFetching event history from Blink...")
        events = await fetch_all_events(blink, days_back=90)
        print(f"Got {len(events)} total events from server.\n")

        print("Matching events to local clips...")
        matched = 0
        for event in events:
            mp4 = match_event_to_file(event, needs_sidecar)
            if mp4:
                write_sidecar(mp4, event)
                matched += 1

        print(f"\nDone. Wrote {matched} sidecar files.")
        unmatched = len(needs_sidecar) - matched
        if unmatched:
            print(
                f"({unmatched} clips had no matching event — likely older "
                f"than 90 days or naming mismatch.)"
            )


if __name__ == "__main__":
    asyncio.run(main())