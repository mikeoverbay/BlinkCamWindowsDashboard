"""
Blink DVR Web Dashboard
Run: python web_app.py
Access: http://localhost:5000 (or http://<your-pc-ip>:5000 on LAN)
"""
import asyncio
import configparser
import json
import logging
import motion_tracker

from datetime import datetime
from pathlib import Path
from threading import Lock

from aiohttp import ClientSession
from flask import Flask, jsonify, render_template, send_from_directory, request
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

logging.getLogger("blinkpy").setLevel(logging.WARNING)

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "settings.ini"
CREDS_PATH = ROOT / "config" / "credentials.json"
THUMBS_DIR = ROOT / "static" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

config = configparser.ConfigParser()
config.read(CONFIG_PATH)
CLIPS_DIR = Path(config["download"]["output_dir"])

app = Flask(__name__)
blink_lock = Lock()


def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def with_blink(action_coro):
    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()
        return await action_coro(blink)


def thumb_filename(camera_name):
    """Map a camera name to a safe filename for its thumbnail."""
    safe = "".join(c if c.isalnum() else "_" for c in camera_name)
    return f"{safe}.jpg"


# --- Routes ---------------------------------------------------------------
@app.route("/api/active_motion")
def api_active_motion():
    """Return cameras currently in active motion state."""
    return jsonify(motion_tracker.get_active_cameras())

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/cameras")
def api_cameras():
    async def fetch(blink):
        sync_modules = getattr(blink, "sync", {}) or {}
        system_armed = any(sm.arm for sm in sync_modules.values())
        cams = []
        for name, cam in blink.cameras.items():
            cams.append({
                "name": name,
                "type": type(cam).__name__,
                "motion_enabled": cam.motion_enabled,
                "thumbnail_url": f"/static/thumbs/{thumb_filename(name)}",
            })
        return {"system_armed": system_armed, "cameras": cams}

    with blink_lock:
        return jsonify(run_async(with_blink(fetch)))


@app.route("/api/refresh_thumbnails", methods=["POST"])
def api_refresh_thumbnails():
    """Pull fresh thumbnails for every camera and save to static/thumbs/."""
    async def refresh(blink):
        results = {}
        for name, cam in blink.cameras.items():
            try:
                await cam.snap_picture()      # tell Blink to capture a fresh thumb
                await asyncio.sleep(2)         # give it a moment to upload
                await cam.get_thumbnail()      # pull the URL
                dest = THUMBS_DIR / thumb_filename(name)
                await cam.image_to_file(str(dest))
                results[name] = "ok"
            except Exception as e:
                results[name] = f"error: {e}"
        return results

    with blink_lock:
        return jsonify(run_async(with_blink(refresh)))


@app.route("/api/refresh_thumbnail/<path:name>", methods=["POST"])
def api_refresh_one_thumbnail(name):
    """Refresh a single camera's thumbnail. Faster than refreshing all."""
    async def refresh(blink):
        if name not in blink.cameras:
            return {"ok": False, "error": "Camera not found"}
        cam = blink.cameras[name]
        try:
            await cam.snap_picture()
            await asyncio.sleep(2)
            await cam.get_thumbnail()
            dest = THUMBS_DIR / thumb_filename(name)
            await cam.image_to_file(str(dest))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    with blink_lock:
        return jsonify(run_async(with_blink(refresh)))


@app.route("/api/arm", methods=["POST"])
def api_arm():
    state = request.json.get("armed", True)

    async def do_arm(blink):
        sync_modules = getattr(blink, "sync", {}) or {}
        for sm in sync_modules.values():
            try:
                await sm.async_arm(state)
            except Exception:
                pass
        return {"ok": True, "armed": state}

    with blink_lock:
        return jsonify(run_async(with_blink(do_arm)))


@app.route("/api/camera/motion", methods=["POST"])
def api_camera_motion():
    name = request.json.get("name")
    enable = request.json.get("enable", True)

    async def do_toggle(blink):
        if name not in blink.cameras:
            return {"ok": False, "error": f"Camera not found: {name}"}
        cam = blink.cameras[name]
        try:
            await cam.async_arm(enable)
        except Exception:
            pass
        return {"ok": True, "name": name, "enabled": enable}

    with blink_lock:
        return jsonify(run_async(with_blink(do_toggle)))


@app.route("/api/clips")
def api_clips():
    """List downloaded MP4s with metadata, newest first."""
    from metadata_helper import read_sidecar

    if not CLIPS_DIR.exists():
        return jsonify([])
    clips = []
    for mp4 in CLIPS_DIR.glob("*.mp4"):
        stat = mp4.stat()
        sidecar = read_sidecar(mp4)
        clip_data = {
            "filename": mp4.name,
            "size_mb": round(stat.st_size / 1_000_000, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "source": None,        # cv_motion / pir / snapshot
            "cv_detection": [],    # ['vehicle'], ['person'], etc.
        }
        if sidecar:
            clip_data["source"] = sidecar.get("source")
            clip_data["cv_detection"] = sidecar.get("cv_detection", [])
        clips.append(clip_data)
    clips.sort(key=lambda c: c["modified"], reverse=True)
    return jsonify(clips[:200])

@app.route("/clips/<path:filename>")
def serve_clip(filename):
    return send_from_directory(CLIPS_DIR, filename)


if __name__ == "__main__":
    print("Blink DVR Web starting on http://0.0.0.0:5000")
    print("Access from this PC: http://localhost:5000")
    print("Access from phones/tablets on same WiFi: http://<your-pc-ip>:5000")
    
    motion_tracker.start_background_thread()
    print("Motion tracker started (polls Blink every 10 sec)")
    
    
    app.run(host="0.0.0.0", port=5000, debug=False)
