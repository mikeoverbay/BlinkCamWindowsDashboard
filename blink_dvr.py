"""
Blink DVR - polls your Blink account for new motion clips and downloads
them to local folders organized by camera name.
"""
import asyncio
import configparser
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "settings.ini"
CREDS_PATH = ROOT / "config" / "credentials.json"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

OUTPUT_DIR = Path(config["download"]["output_dir"])
POLL_INTERVAL = int(config["download"]["poll_interval_seconds"])
DELETE_AFTER_DAYS = int(config["download"]["delete_after_days"])
LOG_DIR = Path(config["logging"]["log_dir"])

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

log_handler = RotatingFileHandler(
    LOG_DIR / "blink_dvr.log", maxBytes=5_000_000, backupCount=5
)
logging.basicConfig(
    level=config["logging"]["level"],
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[log_handler, logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("blink_dvr")


def load_creds():
    if CREDS_PATH.exists():
        with open(CREDS_PATH, "r") as f:
            return json.load(f)
    return None


def save_creds(data):
    with open(CREDS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def sanitize(name):
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()


async def setup_blink(session):
    saved = load_creds()
    if not saved:
        log.error("No credentials.json found. Run first_login.py first.")
        sys.exit(1)

    log.info("Loading saved credentials")
    blink = Blink(session=session)
    blink.auth = Auth(saved, no_prompt=True, session=session)

    try:
        await blink.start()
    except BlinkTwoFARequiredError:
        log.error("Saved token expired - re-run first_login.py to renew")
        sys.exit(1)

    return blink


async def download_new_clips(blink):
    from datetime import datetime, timedelta, timezone
    from metadata_helper import (
        metadata_path_for,
        write_sidecar,
        match_event_to_file,
    )

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y/%m/%d %H:%M:%S"
    )
    log.info(f"Polling for clips since {since} UTC")

    await blink.get_videos_metadata()

    before = set(OUTPUT_DIR.rglob("*.mp4"))

    await blink.download_videos(
        path=str(OUTPUT_DIR),
        since=since,
        camera="all",
        stop=10,
        delay=1,
    )

    after = set(OUTPUT_DIR.rglob("*.mp4"))
    new_files = list(after - before)

    # If we got new clips, fetch their metadata and write sidecars
    if new_files:
        log.info(f"Downloaded {len(new_files)} new clip(s); fetching metadata")
        try:
            api_since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
                "%Y-%m-%dT%H:%M:%S+0000"
            )
            url = (
                f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
                f"/media/changed?since={api_since}&page=1"
            )
            resp = await blink.auth.query(
                url=url, headers=blink.auth.header, reqtype="get", json_resp=True
            )
            events = resp.get("media", []) if isinstance(resp, dict) else []

            sidecar_count = 0
            for event in events:
                matched = match_event_to_file(event, new_files)
                if matched and not metadata_path_for(matched).exists():
                    write_sidecar(matched, event)
                    sidecar_count += 1
            if sidecar_count:
                log.info(f"Wrote {sidecar_count} metadata sidecar(s)")
        except Exception as e:
            log.warning(f"Metadata fetch failed (clips still saved): {e}")

    return len(new_files)

def cleanup_old_clips():
    from metadata_helper import metadata_path_for

    if DELETE_AFTER_DAYS <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=DELETE_AFTER_DAYS)
    count = 0
    for mp4 in OUTPUT_DIR.rglob("*.mp4"):
        if datetime.fromtimestamp(mp4.stat().st_mtime) < cutoff:
            sidecar = metadata_path_for(mp4)
            mp4.unlink()
            if sidecar.exists():
                sidecar.unlink()
            count += 1
    if count:
        log.info(f"Cleaned up {count} old clips")
    return count

async def main():
    log.info("Blink DVR starting")
    async with ClientSession() as session:
        blink = await setup_blink(session)
        log.info(f"Connected. Found {len(blink.cameras)} cameras: {list(blink.cameras.keys())}")

        while True:
            try:
                downloaded = await download_new_clips(blink)
                if downloaded:
                    log.info(f"Downloaded {downloaded} new clip(s)")
                cleanup_old_clips()
            except Exception as e:
                log.exception(f"Error in poll cycle: {e}")

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("Blink DVR starting up...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down")