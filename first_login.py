"""
One-time interactive login for blinkpy 0.26+ (OAuth flow).
"""
import asyncio
import getpass
import json
from pathlib import Path
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth, BlinkTwoFARequiredError

CREDS_PATH = Path("config/credentials.json")

async def main():
    username = input("Blink email: ").strip()
    password = getpass.getpass("Blink password: ")

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(
            {"username": username, "password": password},
            no_prompt=True,
            session=session,
        )

        try:
            await blink.start()
        except BlinkTwoFARequiredError:
            print("\n2FA required. Check your email/phone for a code from Blink.")
            code = input("Enter 2FA code: ").strip()
            await blink.auth.complete_2fa_login(code)
            # Now retry start() to finish camera discovery, etc.
            await blink.start()

        CREDS_PATH.parent.mkdir(exist_ok=True)
        with open(CREDS_PATH, "w") as f:
            json.dump(blink.auth.login_attributes, f, indent=2)

        print(f"\n{'='*60}")
        print(f"SUCCESS! Saved credentials to {CREDS_PATH}")
        print(f"Found {len(blink.cameras)} cameras:")
        for name in blink.cameras:
            print(f"  - {name}")
        print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())