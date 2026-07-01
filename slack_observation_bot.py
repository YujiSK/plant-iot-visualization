#!/usr/bin/env python3
"""Record Slack photo posts as Plant IoT observation logs."""

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from ai_observation import (
    analyze_observation,
    compare_observations,
    DEFAULT_AI_VISION_PROVIDER,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    extract_ai_observation_from_note,
    extract_observed_at_from_note,
    format_comparison_for_slack,
    format_observation_for_slack,
)

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
NOTE_PREFIX = (
    "Slackに植物観察写真が投稿されました。"
    "AI観察支援は画像AIによる非診断の観察支援です。"
)


@dataclass(frozen=True)
class ObservationConfig:
    supabase_url: str
    supabase_key: str
    slack_bot_token: str
    signing_secret: str
    observation_channel_id: str
    device_id: str = "raspberrypi2"
    location_id: str = "location-b"
    ai_vision_provider: str = DEFAULT_AI_VISION_PROVIDER
    openai_api_key: str = ""
    openai_vision_model: str = DEFAULT_OPENAI_MODEL
    gemini_api_key: str = ""
    gemini_vision_model: str = DEFAULT_GEMINI_MODEL

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
            "ai_vision_provider": os.getenv(
                "AI_VISION_PROVIDER", DEFAULT_AI_VISION_PROVIDER
            ),
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "openai_vision_model": os.getenv("OPENAI_VISION_MODEL", DEFAULT_OPENAI_MODEL),
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "gemini_vision_model": os.getenv("GEMINI_VISION_MODEL", DEFAULT_GEMINI_MODEL),
        }
        required_keys = [
            "supabase_url",
            "supabase_key",
            "slack_bot_token",
            "signing_secret",
            "observation_channel_id",
            "device_id",
            "location_id",
        ]
        missing = [env_names[key] for key in required_keys if not values[key]]
        if missing:
            raise RuntimeError(
                "Slack observation bot disabled: missing " + ", ".join(missing)
            )
        return cls(**values)

    @property
    def selected_ai_model(self) -> str:
        if self.ai_vision_provider.strip().lower() == "gemini":
            return self.gemini_vision_model
        return self.openai_vision_model


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


def fetch_previous_ai_observation(
    config: ObservationConfig,
    http_client=requests,
    limit: int = 10,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        normalized_result = fetch_previous_plant_observation(
            config, http_client=http_client
        )
        if normalized_result[0] is not None:
            return normalized_result
    except Exception as exc:
        LOGGER.error(
            "plant_observations previous lookup failed: %s: %s",
            type(exc).__name__,
            exc,
        )

    scoped_result = _fetch_previous_ai_observation(
        config,
        http_client,
        limit,
        extra_note_filters=[
            f"device_id={config.device_id}",
            f"location_id={config.location_id}",
        ],
    )
    if scoped_result[0] is not None:
        return scoped_result
    return _fetch_previous_ai_observation(config, http_client, limit)


def fetch_previous_plant_observation(
    config: ObservationConfig,
    http_client=requests,
) -> tuple[dict[str, Any] | None, str | None]:
    select = "observed_at,raw_ai_json"
    query = (
        f"select={select}"
        f"&device_id=eq.{quote(config.device_id, safe='')}"
        f"&location_id=eq.{quote(config.location_id, safe='')}"
        "&order=observed_at.desc"
        "&limit=1"
    )
    response = http_client.get(
        f"{config.supabase_url}/rest/v1/plant_observations?{query}",
        headers=supabase_headers(config),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        return None, None

    row = rows[0]
    if not isinstance(row, dict):
        return None, None
    raw_ai_json = row.get("raw_ai_json")
    return raw_ai_json if isinstance(raw_ai_json, dict) else None, row.get("observed_at")


def _fetch_previous_ai_observation(
    config: ObservationConfig,
    http_client=requests,
    limit: int = 10,
    extra_note_filters: list[str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    note_filters = ["ai_observation_json="] + (extra_note_filters or [])
    query_parts = [
        "select=created_at,note",
        "action_type=eq.checked",
        *[f"note=ilike.{quote(f'*{item}*', safe='*')}" for item in note_filters],
        "order=created_at.desc",
        f"limit={limit}",
    ]
    query = "&".join(query_parts)
    response = http_client.get(
        f"{config.supabase_url}/rest/v1/care_logs?{query}",
        headers=supabase_headers(config),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        return None, None

    for row in rows:
        if not isinstance(row, dict):
            continue
        note = row.get("note")
        previous = extract_ai_observation_from_note(note)
        if previous is None:
            continue
        previous_observed_at = extract_observed_at_from_note(note) or row.get(
            "created_at"
        )
        return previous, previous_observed_at
    return None, None


def slack_file_url(slack_file: dict[str, Any]) -> str | None:
    return slack_file.get("url_private") or slack_file.get("permalink")


def fetch_slack_image_bytes(
    slack_file: dict[str, Any],
    config: ObservationConfig,
    http_client=requests,
) -> tuple[bytes | None, str | None]:
    url = slack_file.get("url_private_download") or slack_file.get("url_private")
    if not url:
        return None, None
    LOGGER.info("Slack image download start: file_id=%s", slack_file.get("id"))
    response = http_client.get(
        url,
        headers={"Authorization": f"Bearer {config.slack_bot_token}"},
        timeout=20,
    )
    LOGGER.info(
        "Slack image download result: status=%s bytes=%s mime_type=%s",
        getattr(response, "status_code", "unknown"),
        len(getattr(response, "content", b"") or b""),
        getattr(response, "headers", {}).get("Content-Type")
        if getattr(response, "headers", None)
        else slack_file.get("mimetype"),
    )
    response.raise_for_status()
    content_type = None
    headers = getattr(response, "headers", None)
    if headers:
        content_type = headers.get("Content-Type")
    return response.content, content_type or slack_file.get("mimetype")


def build_note(
    observation: dict[str, Any],
    observed_at: datetime,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str | None = None,
    location_id: str | None = None,
    ai_observation: dict[str, Any] | None = None,
    ai_observation_error: str | None = None,
    observation_comparison: dict[str, Any] | None = None,
    observation_comparison_error: str | None = None,
) -> str:
    slack_file = observation["file"]
    parts = [
        NOTE_PREFIX,
        f"observed_at={observed_at.strftime('%Y-%m-%d %H:%M:%S JST')}",
        f"device_id={device_id}" if device_id else None,
        f"location_id={location_id}" if location_id else None,
        f"slack_channel_id={observation.get('channel')}",
        f"slack_user_id={observation.get('user')}",
        f"slack_ts={observation.get('ts')}",
        f"slack_file_id={slack_file.get('id')}",
        f"slack_file_name={slack_file.get('name')}",
        f"slack_file_mimetype={slack_file.get('mimetype')}",
        f"slack_file_url={slack_file_url(slack_file)}",
    ]
    parts = [part for part in parts if part is not None]
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
    if ai_observation:
        parts.append(
            "ai_observation_json="
            + json.dumps(ai_observation, ensure_ascii=False, sort_keys=True)
        )
    if ai_observation_error:
        parts.append(f"ai_observation_error={ai_observation_error}")
    if observation_comparison:
        parts.append(
            "observation_comparison_json="
            + json.dumps(observation_comparison, ensure_ascii=False, sort_keys=True)
        )
    if observation_comparison_error:
        parts.append(f"observation_comparison_error={observation_comparison_error}")
    return "\n".join(parts)


def build_care_log_payload(
    observation: dict[str, Any],
    config: ObservationConfig,
    nearest_sensor_log: dict[str, Any] | None = None,
    ai_observation: dict[str, Any] | None = None,
    ai_observation_error: str | None = None,
    observation_comparison: dict[str, Any] | None = None,
    observation_comparison_error: str | None = None,
) -> dict[str, Any]:
    observed_at = slack_ts_to_jst(observation["ts"])
    payload = {
        "action_type": "checked",
        "note": build_note(
            observation,
            observed_at,
            nearest_sensor_log,
            config.device_id,
            config.location_id,
            ai_observation,
            ai_observation_error,
            observation_comparison,
            observation_comparison_error,
        ),
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


def build_plant_observation_payload(
    observation: dict[str, Any],
    config: ObservationConfig,
    nearest_sensor_log: dict[str, Any] | None,
    ai_observation: dict[str, Any],
) -> dict[str, Any]:
    observed_at = slack_ts_to_jst(observation["ts"])
    payload = {
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "sensor_log_id": (
            nearest_sensor_log.get("id") if nearest_sensor_log else None
        ),
        "device_id": config.device_id,
        "location_id": config.location_id,
        "image_url": slack_file_url(observation["file"]),
        "growth_stage": ai_observation.get("growth_stage"),
        "true_leaf_detected": ai_observation.get("true_leaf_detected"),
        "true_leaf_pair_count": ai_observation.get("true_leaf_pair_count"),
        "plant_count_estimate": ai_observation.get("plant_count_estimate"),
        "crowding": ai_observation.get("crowding"),
        "leaf_color": ai_observation.get("leaf_color"),
        "leaf_size": ai_observation.get("leaf_size"),
        "wilting": ai_observation.get("wilting"),
        "yellowing": ai_observation.get("yellowing"),
        "root_visibility": ai_observation.get("root_visibility"),
        "root_length_estimate": ai_observation.get("root_length_estimate"),
        "confidence": ai_observation.get("confidence"),
        "summary": ai_observation.get("summary"),
        "next_action": ai_observation.get("next_action"),
        "raw_ai_json": ai_observation,
        "model": config.selected_ai_model,
    }
    return {key: value for key, value in payload.items() if value is not None}


def insert_plant_observation(
    payload: dict[str, Any], config: ObservationConfig, http_client=requests
) -> bool:
    try:
        response = http_client.post(
            f"{config.supabase_url}/rest/v1/plant_observations",
            json=payload,
            headers=supabase_headers(config, prefer="return=minimal"),
            timeout=10,
        )
        if not response.ok:
            LOGGER.error(
                "plant_observations insert failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            return False
        return True
    except Exception as exc:
        LOGGER.error(
            "plant_observations insert failed: %s: %s", type(exc).__name__, exc
        )
        return False


def observation_already_recorded(
    observation: dict[str, Any],
    config: ObservationConfig,
    http_client=requests,
) -> bool:
    slack_ts = observation.get("ts")
    if not slack_ts:
        return False
    query = (
        "select=id"
        f"&action_type=eq.checked"
        f"&note=ilike.{quote(f'*slack_ts={slack_ts}*', safe='*=.')}"
        "&limit=1"
    )
    response = http_client.get(
        f"{config.supabase_url}/rest/v1/care_logs?{query}",
        headers=supabase_headers(config),
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    return isinstance(rows, list) and bool(rows)


def format_value(value: Any, suffix: str = "") -> str:
    return "取得不可" if value is None else f"{value}{suffix}"


def build_success_reply(
    observed_at: datetime,
    config: ObservationConfig,
    nearest_sensor_log: dict[str, Any] | None = None,
    ai_observation: dict[str, Any] | None = None,
    ai_observation_error: str | None = None,
    observation_comparison: dict[str, Any] | None = None,
    observation_comparison_error: str | None = None,
) -> str:
    message = (
        "🌱 観察写真を記録しました。\n\n"
        f"device: {config.device_id}\n"
        f"location: {config.location_id}\n"
        f"記録時刻: {observed_at.strftime('%Y-%m-%d %H:%M JST')}"
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
    if ai_observation:
        message += "\n\n" + format_observation_for_slack(ai_observation)
    elif ai_observation_error:
        message += "\n\nAI観察支援: 今回は取得できませんでした。"
    if observation_comparison:
        message += "\n\n" + format_comparison_for_slack(observation_comparison)
    elif observation_comparison_error:
        message += "\n\n前回との比較: 今回は取得できませんでした。"
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

    if observation_already_recorded(observation, config, http_client=http_client):
        LOGGER.info(
            "duplicate Slack observation skipped: slack_ts=%s file_id=%s",
            observation.get("ts"),
            observation["file"].get("id"),
        )
        return {"status": "duplicate", "care_log_created": False}

    observed_at = slack_ts_to_jst(observation["ts"])
    nearest_sensor_log = None
    try:
        nearest_sensor_log = fetch_nearest_sensor_log(
            observed_at, config, http_client=http_client
        )
    except Exception as exc:
        LOGGER.error("nearest sensor lookup failed: %s: %s", type(exc).__name__, exc)

    ai_observation = None
    ai_observation_error = None
    try:
        image_bytes, image_mimetype = fetch_slack_image_bytes(
            observation["file"], config, http_client=http_client
        )
        image_url = slack_file_url(observation["file"])
        LOGGER.info(
            "AI observation start: provider=%s model=%s image_bytes=%s",
            config.ai_vision_provider,
            config.selected_ai_model,
            len(image_bytes or b""),
        )
        ai_observation = analyze_observation(
            image_url=image_url,
            image_bytes=image_bytes,
            image_mimetype=image_mimetype,
            nearest_sensor_log=nearest_sensor_log,
            device_id=config.device_id,
            location_id=config.location_id,
            observed_at=observed_at,
            ai_vision_provider=config.ai_vision_provider,
            openai_api_key=config.openai_api_key,
            openai_model=config.openai_vision_model,
            gemini_api_key=config.gemini_api_key,
            gemini_model=config.gemini_vision_model,
            http_client=http_client,
        )
        LOGGER.info(
            "AI observation success: growth_stage=%s true_leaf_detected=%s true_leaf_pair_count=%s confidence=%s",
            ai_observation.get("growth_stage"),
            ai_observation.get("true_leaf_detected"),
            ai_observation.get("true_leaf_pair_count"),
            ai_observation.get("confidence"),
        )
    except Exception as exc:
        ai_observation_error = f"{type(exc).__name__}: {exc}"
        LOGGER.error("AI observation failed: %s", ai_observation_error)

    observation_comparison = None
    observation_comparison_error = None
    if ai_observation:
        try:
            previous_observation, previous_observed_at = fetch_previous_ai_observation(
                config, http_client=http_client
            )
            observation_comparison = compare_observations(
                ai_observation,
                previous_observation,
                previous_observed_at,
            )
        except Exception as exc:
            observation_comparison_error = f"{type(exc).__name__}: {exc}"
            LOGGER.error(
                "observation comparison failed: %s", observation_comparison_error
            )

    payload = build_care_log_payload(
        observation,
        config,
        nearest_sensor_log,
        ai_observation,
        ai_observation_error,
        observation_comparison,
        observation_comparison_error,
    )
    if not insert_care_log(payload, config, http_client=http_client):
        post_slack_reply(
            observation["channel"],
            observation["ts"],
            "⚠️ 観察写真の記録に失敗しました。\nログを確認してください。",
            config,
            http_client=http_client,
        )
        return {"status": "failed", "care_log_created": False}

    plant_observation_created = False
    if ai_observation:
        plant_payload = build_plant_observation_payload(
            observation,
            config,
            nearest_sensor_log,
            ai_observation,
        )
        LOGGER.info(
            "plant_observations insert start: growth_stage=%s true_leaf_detected=%s true_leaf_pair_count=%s model=%s",
            plant_payload.get("growth_stage"),
            plant_payload.get("true_leaf_detected"),
            plant_payload.get("true_leaf_pair_count"),
            plant_payload.get("model"),
        )
        plant_observation_created = insert_plant_observation(
            plant_payload, config, http_client=http_client
        )

    reply_sent = post_slack_reply(
        observation["channel"],
        observation["ts"],
        build_success_reply(
            observed_at,
            config,
            nearest_sensor_log,
            ai_observation,
            ai_observation_error,
            observation_comparison,
            observation_comparison_error,
        ),
        config,
        http_client=http_client,
    )
    return {
        "status": "recorded",
        "care_log_created": True,
        "nearest_sensor_log_found": nearest_sensor_log is not None,
        "ai_observation_created": ai_observation is not None,
        "plant_observation_created": plant_observation_created,
        "observation_comparison_created": observation_comparison is not None,
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
