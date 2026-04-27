import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth


async def main():
    saved = json.loads(Path("config/credentials.json").read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        for name, cam in blink.cameras.items():
            print(f"{name}:")
            print(f"  type={type(cam).__name__}")
            print(f"  network_id={cam.network_id}")
            print(f"  motion_enabled={cam.motion_enabled}")
            print(f"  video_from_cache={cam.video_from_cache}")
            print(f"  thumbnail={getattr(cam, 'thumbnail', '?')}")
            print()


asyncio.run(main())