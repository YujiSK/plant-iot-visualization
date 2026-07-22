#!/usr/bin/env python3
"""Process the latest image message from the configured Slack observation channel."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

import requests

from slack_observation_bot import ObservationConfig, first_image_file, process_slack_event


SLACK_HISTORY_URL = "https://slack.com/api/conversations.history"


def fetch_latest_image_event(config: ObservationConfig, limit: int) -> dict[str, Any]:
    response = requests.get(
        SLACK_HISTORY_URL,
        headers={"Authorization": f"Bearer {config.slack_bot_token}"},
        params={"channel": config.observation_channel_id, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Slack history failed: {body.get('error')}")

    for message in body.get("messages", []):
        files = message.get("files") or []
        if not isinstance(files, list):
            continue
        image_file = first_image_file(files)
        if image_file is None:
            continue
        return {
            "type": "message",
            "channel": message.get("channel") or config.observation_channel_id,
            "user": message.get("user"),
            "ts": message.get("ts"),
            "text": message.get("text") or "",
            "files": [image_file],
        }
    raise RuntimeError(f"No image message found in latest {limit} Slack messages")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    config = ObservationConfig.from_env()
    event = fetch_latest_image_event(config, args.limit)
    file_info = (event.get("files") or [{}])[0]
    print(
        "latest_image="
        + json.dumps(
            {
                "channel": event.get("channel"),
                "ts": event.get("ts"),
                "file_id": file_info.get("id"),
                "file_name": file_info.get("name"),
                "mimetype": file_info.get("mimetype"),
                "text": event.get("text") or "",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if args.dry_run:
        return 0

    result = process_slack_event(event, config)
    print("result=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
