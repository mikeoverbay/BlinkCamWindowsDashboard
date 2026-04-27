"""
Arm/disarm Blink system or toggle individual cameras.
Usage:
  python arm_control.py arm                          (arms the whole system)
  python arm_control.py disarm                       (disarms the whole system)
  python arm_control.py status                       (shows current state)
  python arm_control.py enable "Camera Name"         (enable motion on one camera)
  python arm_control.py disable "Camera Name"        (disable motion on one camera)
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

# Suppress blinkpy's noisy completion-poll error logging
logging.getLogger("blinkpy").setLevel(logging.CRITICAL)

CREDS_PATH = Path("config/credentials.json")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()

    if not CREDS_PATH.exists():
        print(f"No credentials found at {CREDS_PATH}. Run first_login.py first.")
        sys.exit(1)

    with open(CREDS_PATH) as f:
        saved = json.load(f)

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        sync_modules = getattr(blink, "sync", {}) or {}

        if action == "status":
            print("\n=== Sync Modules ===")
            for sm_name, sm in sync_modules.items():
                print(f"  '{sm_name}': armed={sm.arm}, online={sm.online}")
            print("\n=== Cameras ===")
            for cam_name, camera in blink.cameras.items():
                cam_type = type(camera).__name__
                print(f"  '{cam_name}' ({cam_type}): "
                      f"motion_enabled={camera.motion_enabled}")
            print()

        elif action == "arm":
            for sm_name, sm in sync_modules.items():
                try:
                    await sm.async_arm(True)
                    print(f"Armed sync module: {sm_name}")
                except AttributeError:
                    print(f"Armed {sm_name} (command sent; verify in app)")

        elif action == "disarm":
            for sm_name, sm in sync_modules.items():
                try:
                    await sm.async_arm(False)
                    print(f"Disarmed sync module: {sm_name}")
                except AttributeError:
                    print(f"Disarmed {sm_name} (command sent; verify in app)")

        elif action in ("enable", "disable"):
            if len(sys.argv) < 3:
                print("Specify camera name in quotes")
                print(f"Available cameras: {list(blink.cameras.keys())}")
                sys.exit(1)
            cam_name = sys.argv[2]
            if cam_name not in blink.cameras:
                print(f"Camera '{cam_name}' not found.")
                print(f"Available: {list(blink.cameras.keys())}")
                sys.exit(1)
            camera = blink.cameras[cam_name]
            enable = (action == "enable")
            try:
                await camera.async_arm(enable)
                print(f"{action.capitalize()}d motion on '{cam_name}'")
            except AttributeError:
                print(f"{action.capitalize()}d motion on '{cam_name}' "
                      f"(command sent; verify in app)")

        else:
            print(f"Unknown action: {action}")
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())