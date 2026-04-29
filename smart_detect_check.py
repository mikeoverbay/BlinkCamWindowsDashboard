"""
Catalog all unique cv_detection values across recent events.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter
from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

CREDS_PATH = Path("config/credentials.json")


async def main():
    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:%M:%S+0000"
        )

        all_media = []
        for page in range(1, 6):  # up to 5 pages
            url = f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}/media/changed?since={since}&page={page}"
            response = await blink.auth.query(
                url=url, headers=blink.auth.header, reqtype="get", json_resp=True
            )
            page_media = response.get("media", []) if isinstance(response, dict) else []
            if not page_media:
                break
            all_media.extend(page_media)

        print(f"Total events fetched: {len(all_media)}\n")

        sources = Counter()
        detections = Counter()
        per_camera = {}

        for event in all_media:
            sources[event.get("source", "?")] += 1
            cam = event.get("device_name", "?")
            per_camera.setdefault(cam, Counter())

            meta_str = event.get("metadata", "")
            if meta_str:
                try:
                    meta = json.loads(meta_str)
                    cv = meta.get("cv_detection", [])
                    if cv:
                        tag = ",".join(sorted(cv))
                        detections[tag] += 1
                        per_camera[cam][tag] += 1
                    else:
                        detections["(empty)"] += 1
                        per_camera[cam]["(empty)"] += 1
                except json.JSONDecodeError:
                    detections["(parse error)"] += 1
            else:
                detections["(no metadata)"] += 1
                per_camera[cam]["(no metadata)"] += 1

        print("=== source field distribution ===")
        for k, v in sources.most_common():
            print(f"  {v:5d}  {k}")

        print("\n=== cv_detection values ===")
        for k, v in detections.most_common():
            print(f"  {v:5d}  {k}")

        print("\n=== per camera ===")
        for cam, counts in per_camera.items():
            print(f"\n  {cam}:")
            for k, v in counts.most_common():
                print(f"    {v:5d}  {k}")


asyncio.run(main())