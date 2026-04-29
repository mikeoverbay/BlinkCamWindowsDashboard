"""
Helpers for fetching Blink event metadata and writing sidecar JSON files
next to each downloaded MP4.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def metadata_path_for(mp4_path: Path) -> Path:
    """Return the sidecar JSON path for a given MP4 file."""
    return mp4_path.with_suffix(".json")


def detection_summary(metadata_str: str) -> dict:
    """Parse the Blink 'metadata' field (a JSON string) into a clean summary."""
    if not metadata_str:
        return {"cv_detection": [], "pts_length_ms": None}
    try:
        meta = json.loads(metadata_str)
        return {
            "cv_detection": meta.get("cv_detection", []) or [],
            "pts_length_ms": meta.get("pts_length_ms"),
        }
    except (json.JSONDecodeError, TypeError):
        return {"cv_detection": [], "pts_length_ms": None}


def event_to_sidecar(event: dict) -> dict:
    """Convert a raw Blink media event into the data we want to store."""
    meta = detection_summary(event.get("metadata", ""))
    return {
        "id": event.get("id"),
        "device_name": event.get("device_name"),
        "device_type": event.get("device"),
        "created_at": event.get("created_at"),
        "source": event.get("source"),  # cv_motion / pir / snapshot
        "type": event.get("type"),
        "cv_detection": meta["cv_detection"],
        "duration_ms": meta["pts_length_ms"],
        "time_zone": event.get("time_zone"),
    }


def filename_to_timestamp(filename: str) -> Optional[datetime]:
    """
    Extract the timestamp from a blinkpy-style filename like:
      'outdoor-4-front-2026-04-27t10-55-50-00-00.mp4'
    Returns naive UTC datetime, or None if not parseable.
    """
    m = re.search(
        r"(\d{4})-(\d{2})-(\d{2})t(\d{2})-(\d{2})-(\d{2})",
        filename.lower(),
    )
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = map(int, m.groups())
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def event_timestamp(event: dict) -> Optional[datetime]:
    """Parse the created_at field of a Blink event into a naive UTC datetime."""
    created = event.get("created_at", "")
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("+00:00", "")).replace(
            microsecond=0
        )
    except ValueError:
        return None


def match_event_to_file(event: dict, mp4_files: list) -> Optional[Path]:
    """
    Given a Blink event and a list of MP4 file paths, return the MP4 whose
    filename timestamp is within 60 seconds of the event's created_at AND
    whose filename contains the device name.
    """
    event_dt = event_timestamp(event)
    if event_dt is None:
        return None

    device_name = event.get("device_name", "")
    if not device_name:
        return None

    # Normalize the camera name to match blinkpy's lowercase-with-dashes
    device_slug = (
        device_name.lower()
        .replace(" - ", "-")
        .replace(" ", "-")
    )

    best_match = None
    best_delta = None
    for mp4 in mp4_files:
        if device_slug not in mp4.name.lower():
            continue
        file_dt = filename_to_timestamp(mp4.name)
        if file_dt is None:
            continue
        delta = abs((file_dt - event_dt).total_seconds())
        if delta < 60 and (best_delta is None or delta < best_delta):
            best_match = mp4
            best_delta = delta
    return best_match


def write_sidecar(mp4_path: Path, event: dict) -> None:
    """Write the sidecar JSON file for a given MP4."""
    sidecar = metadata_path_for(mp4_path)
    sidecar.write_text(json.dumps(event_to_sidecar(event), indent=2))


def read_sidecar(mp4_path: Path) -> Optional[dict]:
    """Read the sidecar JSON for a given MP4. Returns None if missing."""
    sidecar = metadata_path_for(mp4_path)
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text())
    except (json.JSONDecodeError, OSError):
        return None