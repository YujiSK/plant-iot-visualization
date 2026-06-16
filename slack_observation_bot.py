#!/usr/bin/env python3
"""Record Slack photo posts as Plant IoT observation logs."""

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

try:
    from fastapi import FastAPI, Header, HTTPException, Request
except ImportError:
    FastAPI = None
    Header = None
    HTTPException = None
    Request = None


load_dotenv()

LOGGER = logging.getLogger("slack_observation")
JST = timezone(timedelta(hours=9), "JST")
SLACK_CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
NOTE_PREFIX = "Slackに植物観察写真が投稿されました。AI解析は未実施です。"


@dataclass(frozen=True)
class ObservationConfig:
    supabase_url: str
    supabase_key: str
    slack_bot_token: str
    signing_secret: str
    observation_channel_id: str
    device_id: str = "raspberrypi2"
    location_id: str = "location-b"

    @classmethod
    def from_env(cls) -> "ObservationConfig":
        env_names = {
            "supabase_url": "SUPABASE_URL",
            "supabase_key": "SUPABASE_KEY",
            "slack_bot_token": "SLACK_BOT_TOKEN",
            "signing_secret": "SLACK_SIGNING_SECRET",
            "observation_channel_id": "SLACK_OBSERVATION_CHANNEL_ID",
            "device_id": "DEVICE_ID",
            "location_id": "LOCATION_ID",
        }
        values = {
            "supabase_url": os.getenv("SUPABASE_URL", "").rstrip("/"),
            "supabase_key": os.getenv("SUPABASE_KEY", ""),
            "slack_bot_token": os.getenv("SLACK_BOT_TOKEN", ""),
            "signing_secret": os.getenv("SLACK_SIGNING_SECRET", ""),
            "observation_channel_id": os.getenv("SLACK_OBSERVATION_CHANNEL_ID", ""),
            "device_id": os.getenv("DEVICE_ID", "raspberrypi2"),
            "location_id": os.getenv("LOCATION_ID", "location-b"),
        }
        missing = [env_names[key] for key, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                "Slack observation bot disabled: missing " + ", ".join(missing)
            )
        return cls(**values)


def slack_ts_to_jst(slack_ts: str) -> datetime:
    return datetime.fromtimestamp(float(slack_ts), tz=timezone.utc).astimezone(JST)


def is_image_file(slack_file: dict[str, Any]) -> bool:
    mimetype = str(slack_file.get("mimetype") or "")
    return mimetype.startswith("image/")


def first_image_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    for slack_file in files:
        if is_image_file(slack_file):
            return slack_file
    return None


def extract_observation_photo(
    event: dict[str, Any], observation_channel_id: str
) -> dict[str, Any] | None:
    if event.get("type") != "message":
        return None
    if event.get("channel") != observation_channel_id:
        return None
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return None

    files = event.get("files") or []
    if not isinstance(files, list):
        return None

    image_file = first_image_file(files)
    if image_file is None:
        return None

    return {
        "channel": event.get("channel"),
        "user": event.get("user"),
        "ts": event.get("ts"),
        "file": image_file,
    }


def supabase_headers(config: ObservationConfig, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": config.supabase_key,
        "Authorization": f"Bearer {config.supabase_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def fetch_nearest_sensor_log(
    observed_at: datetime,
    config: ObservationConfig,
    http_client=requests,
    window_minutes: int = 10,
) -> dict[str, Any] | None:
    start = (observed_at - timedelta(minutes=window_minutes)).astimezone(timezone.utc)
    end = (observed_at + timedelta(minutes=window_minutes)).astimezone(timezone.utc)
    select = ",".join(
        [
            "id",
            "created_at",
            "vitality_score",
            "float_switch_state",
            "solution_temperature",
            "light_lux",
            "message",
        ]
    )
    query = (
        f"select={select}"
        f"&device_id=eq.{quote(config.device_id, safe='')}"
        f"&created_at=gte.{quote(start.isoformat(), safe='')}"
        f"&created_at=lte.{quote(end.isoformat(), safe='')}"
        "&order=created_at.asc"
    )
    response = http_client.get(
        f"{config.supabase_url}/rest/v1/sensor_logs?{query}",
        headers=supabase_headers(config),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None

    def distance(row: dict[str, Any]) -> float:
        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        return abs((created_at - observed_at.astimezone(timezone.utc)).total_seconds())

    return min(rows, key=distance)


def slack_file_url(slack_file: dict[str, Any]) -> str | None:
    return slack_file.get("url_private") or slack_file.get("permalink")


def build_note(
    observation: dict[str, Any],
    observed_at: datetime,
    nearest_sensor_log: dict[str, Any] | None,
) -> str:
    slack_file = observation["file"]
    parts = [
        NOTE_PREFIX,
        f"observed_at={observed_at.strftime('%Y-%m-%d %H:%M:%S JST')}",
        f"slack_channel_id={observation.get('channel')}",
        f"slack_user_id={observation.get('user')}",
        f"slack_ts={observation.get('ts')}",
        f"slack_file_id={slack_file.get('id')}",
        f"slack_file_name={slack_file.get('name')}",
        f"slack_file_mimetype={slack_file.get('mimetype')}",
        f"slack_file_url={slack_file_url(slack_file)}",
    ]
    if nearest_sensor_log:
        parts.extend(
            [
                f"nearest_sensor_log_time={nearest_sensor_log.get('created_at')}",
                f"nearest_vitality_score={nearest_sensor_log.get('vitality_score')}",
                "nearest_float_switch_state="
                f"{nearest_sensor_log.get('float_switch_state')}",
                "nearest_solution_temperature="
                f"{nearest_sensor_log.get('solution_temperature')}",
                f"nearest_light_lux={nearest_sensor_log.get('light_lux')}",
            ]
        )
    return "\n".join(parts)


def build_care_log_payload(
    observation: dict[str, Any],
    config: ObservationConfig,
    nearest_sensor_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed_at = slack_ts_to_jst(observation["ts"])
    payload = {
        "action_type": "checked",
        "note": build_note(observation, observed_at, nearest_sensor_log),
        "vitality_score": (
            nearest_sensor_log.get("vitality_score") if nearest_sensor_log else None
        ),
        "message": "Slack写真投稿による観察記録",
    }
    if nearest_sensor_log and nearest_sensor_log.get("id") is not None:
        payload["sensor_log_id"] = nearest_sensor_log["id"]
    return payload


def insert_care_log(
    payload: dict[str, Any], config: ObservationConfig, http_client=requests
) -> bool:
    try:
        response = http_client.post(
            f"{config.supabase_url}/rest/v1/care_logs",
            json=payload,
            headers=supabase_headers(config, prefer="return=minimal"),
            timeout=10,
        )
        if not response.ok:
            LOGGER.error(
                "care_logs insert failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            return False
        return True
    except Exception as exc:
        LOGGER.error("care_logs insert failed: %s: %s", type(exc).__name__, exc)
        return False


def format_value(value: Any, suffix: str = "") -> str:
    return "取得不可" if value is None else f"{value}{suffix}"


def build_success_reply(
    observed_at: datetime,
    config: ObservationConfig,
    nearest_sensor_log: dict[str, Any] | None = None,
) -> str:
    message = (
        "🌱 観察写真を記録しました。\n\n"
        f"device: {config.device_id}\n"
        f"location: {config.location_id}\n"
        f"記録時刻: {observed_at.strftime('%Y-%m-%d %H:%M JST')}\n\n"
        "この段階ではAI解析は行っていません。\n"
        "次の段階で、発芽・子葉・本葉・水位確認などの観察支援を追加予定です。"
    )
    if nearest_sensor_log:
        message += (
            "\n\n最寄りセンサー:\n"
            f"vitality: {format_value(nearest_sensor_log.get('vitality_score'))}\n"
            f"水位: {format_value(nearest_sensor_log.get('float_switch_state'))}\n"
            "養液温度: "
            f"{format_value(nearest_sensor_log.get('solution_temperature'), '℃')}\n"
            f"照度: {format_value(nearest_sensor_log.get('light_lux'), ' lx')}"
        )
    return message


def post_slack_reply(
    channel: str,
    thread_ts: str,
    text: str,
    config: ObservationConfig,
    http_client=requests,
) -> bool:
    try:
        response = http_client.post(
            SLACK_CHAT_POST_MESSAGE_URL,
            json={"channel": channel, "thread_ts": thread_ts, "text": text},
            headers={
                "Authorization": f"Bearer {config.slack_bot_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            LOGGER.error("Slack reply failed: %s", body)
            return False
        return True
    except Exception as exc:
        LOGGER.error("Slack reply failed: %s: %s", type(exc).__name__, exc)
        return False


def process_slack_event(
    event: dict[str, Any], config: ObservationConfig, http_client=requests
) -> dict[str, Any]:
    observation = extract_observation_photo(event, config.observation_channel_id)
    if observation is None:
        return {"status": "ignored"}

    observed_at = slack_ts_to_jst(observation["ts"])
    nearest_sensor_log = None
    try:
        nearest_sensor_log = fetch_nearest_sensor_log(
            observed_at, config, http_client=http_client
        )
    except Exception as exc:
        LOGGER.error("nearest sensor lookup failed: %s: %s", type(exc).__name__, exc)

    payload = build_care_log_payload(observation, config, nearest_sensor_log)
    if not insert_care_log(payload, config, http_client=http_client):
        post_slack_reply(
            observation["channel"],
            observation["ts"],
            "⚠️ 観察写真の記録に失敗しました。\nログを確認してください。",
            config,
            http_client=http_client,
        )
        return {"status": "failed", "care_log_created": False}

    reply_sent = post_slack_reply(
        observation["channel"],
        observation["ts"],
        build_success_reply(observed_at, config, nearest_sensor_log),
        config,
        http_client=http_client,
    )
    return {
        "status": "recorded",
        "care_log_created": True,
        "nearest_sensor_log_found": nearest_sensor_log is not None,
        "reply_sent": reply_sent,
    }


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(now - request_time) > 60 * 5:
        return False

    basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
    digest = hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256)
    expected = "v0=" + digest.hexdigest()
    return hmac.compare_digest(expected, signature)


if FastAPI is not None:
    app = FastAPI(title="Plant IoT Slack Observation Bot")

    @app.post("/slack/events")
    async def slack_events(
        request: Request,
        x_slack_request_timestamp: str = Header(default=""),
        x_slack_signature: str = Header(default=""),
    ):
        try:
            config = ObservationConfig.from_env()
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        body = await request.body()
        if not verify_slack_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            config.signing_secret,
        ):
            raise HTTPException(status_code=401, detail="invalid Slack signature")

        payload = await request.json()
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        if payload.get("type") != "event_callback":
            return {"ok": True, "status": "ignored"}

        result = process_slack_event(payload.get("event", {}), config)
        return {"ok": True, **result}
else:
    app = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        ObservationConfig.from_env()
        print("[slack-observation] enabled", flush=True)
    except RuntimeError as exc:
        print(f"[slack-observation] {exc}", flush=True)
