"""Call request_camera_liveview directly and dump whatever comes back."""
import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy import api

CREDS_PATH = Path("config/credentials.json")


async def main():
    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        for name in ["Mini - white", "Outdoor 4 - front"]:
            if name not in blink.cameras:
                continue
            cam = blink.cameras[name]
            print(f"\n=== {name} ({type(cam).__name__}) ===")
            print(f"camera_type: {cam.camera_type!r}")
            print(f"network_id: {cam.network_id}, camera_id: {cam.camera_id}")
            try:
                resp = await api.request_camera_liveview(
                    blink,
                    cam.network_id,
                    cam.camera_id,
                    camera_type=cam.camera_type,
                )
                print(f"Response type: {type(resp).__name__}")
                print(json.dumps(resp, indent=2, default=str))
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")


asyncio.run(main())