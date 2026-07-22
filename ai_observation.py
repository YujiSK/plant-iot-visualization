"""AI observation support for Slack plant photos.

This module extracts structured, non-diagnostic plant observations from photos.
It uses OpenAI vision when configured and keeps a conservative fallback for
local tests and degraded operation.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from datetime import datetime
from typing import Any

import requests


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_GENERATE_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_OPENAI_MODEL = "gpt-4.1"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_FALLBACK_MODELS = ("gemini-3.1-flash-lite",)
AI_VISION_TIMEOUT_SECONDS = 90
DEFAULT_AI_VISION_PROVIDER = "openai"
LOGGER = logging.getLogger("ai_observation")

GROWTH_STAGE_VALUES = [
    "seed",
    "germination",
    "cotyledon",
    "true_leaf_1",
    "true_leaf_2",
    "vegetative",
]

GROWTH_STAGE_LABELS = {
    "seed": "播種直後",
    "germination": "発芽期",
    "cotyledon": "子葉期",
    "true_leaf_1": "本葉1対",
    "true_leaf_2": "本葉2対",
    "vegetative": "栄養成長期",
    # Backward-compatible label for older notes.
    "true_leaf": "本葉期",
}

CROWDING_LABELS = {
    "low": "低い",
    "medium": "中程度",
    "high": "高い",
    "unknown": "未判定",
}

LEAF_COLOR_LABELS = {
    "green": "緑",
    "pale": "薄い緑",
    "yellowing": "黄化あり",
    "mixed": "混在",
    "unknown": "未判定",
}

LEAF_SIZE_LABELS = {
    "small": "小さい",
    "medium": "中程度",
    "large": "大きい",
    "unknown": "未判定",
}


AI_OBSERVATION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "growth_stage",
        "true_leaf_detected",
        "true_leaf_pair_count",
        "cotyledon_visible",
        "plant_count_estimate",
        "crowding",
        "leaf_color",
        "leaf_size",
        "wilting",
        "yellowing",
        "root_visibility",
        "root_length_estimate",
        "confidence",
        "summary",
        "next_action",
    ],
    "properties": {
        "growth_stage": {"type": "string", "enum": GROWTH_STAGE_VALUES},
        "true_leaf_detected": {"type": "boolean"},
        "true_leaf_pair_count": {"type": ["integer", "null"], "minimum": 0},
        "cotyledon_visible": {"type": "boolean"},
        "plant_count_estimate": {"type": ["integer", "null"], "minimum": 0},
        "crowding": {
            "type": "string",
            "enum": ["low", "medium", "high", "unknown"],
        },
        "leaf_color": {
            "type": "string",
            "enum": ["green", "pale", "yellowing", "mixed", "unknown"],
        },
        "leaf_size": {
            "type": "string",
            "enum": ["small", "medium", "large", "unknown"],
        },
        "wilting": {"type": "boolean"},
        "yellowing": {"type": "boolean"},
        "root_visibility": {"type": "boolean"},
        "root_length_estimate": {"type": ["number", "null"], "minimum": 0},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
        "next_action": {"type": "string"},
    },
}


def _light_lux(nearest_sensor_log: dict[str, Any] | None) -> float | None:
    if not nearest_sensor_log:
        return None
    value = nearest_sensor_log.get("light_lux")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_state(nearest_sensor_log: dict[str, Any] | None) -> str:
    if not nearest_sensor_log:
        return "unknown"
    return str(nearest_sensor_log.get("float_switch_state") or "unknown")


def _next_action(nearest_sensor_log: dict[str, Any] | None) -> str:
    if _float_state(nearest_sensor_log) == "low_water":
        return "水位とフェルト表面の湿りを確認してください"

    light_lux = _light_lux(nearest_sensor_log)
    if light_lux is not None and light_lux < 100:
        return "明るい時間帯に本葉の出現を確認してください"

    return "本葉の枚数、黄化、萎れを同じ角度で確認してください"


def fallback_observation(
    nearest_sensor_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    has_sensor_context = nearest_sensor_log is not None
    return {
        "growth_stage": "cotyledon",
        "true_leaf_detected": False,
        "true_leaf_pair_count": 0,
        "cotyledon_visible": True,
        "plant_count_estimate": 20,
        "crowding": "medium",
        "leaf_color": "green",
        "leaf_size": "small",
        "wilting": False,
        "yellowing": False,
        "root_visibility": False,
        "root_length_estimate": None,
        "confidence": 0.55 if has_sensor_context else 0.35,
        "summary": "画像AIが未設定のため、センサー文脈に基づく保守的な観察支援です。",
        "next_action": _next_action(nearest_sensor_log),
    }


def analyze_observation(
    *,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
    image_mimetype: str | None = None,
    nearest_sensor_log: dict[str, Any] | None = None,
    device_id: str = "",
    location_id: str = "",
    observed_at: datetime | None = None,
    user_note: str | None = None,
    ai_vision_provider: str | None = None,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    model: str | None = None,
    http_client=requests,
) -> dict[str, Any]:
    """Return structured observation support for a plant photo."""

    provider = (
        ai_vision_provider
        if ai_vision_provider is not None
        else os.getenv("AI_VISION_PROVIDER", DEFAULT_AI_VISION_PROVIDER)
    ).strip().lower()
    if provider not in {"openai", "gemini"}:
        raise ValueError(f"Unsupported AI_VISION_PROVIDER: {provider}")

    resolved_image_url = image_url
    if image_bytes is not None and provider == "openai":
        resolved_image_url = data_url_from_image_bytes(image_bytes, image_mimetype)
    if image_bytes is None and not resolved_image_url:
        return fallback_observation(nearest_sensor_log)

    if provider == "openai":
        api_key = (
            openai_api_key
            if openai_api_key is not None
            else os.getenv("OPENAI_API_KEY", "")
        )
        if not api_key:
            return fallback_observation(nearest_sensor_log)
        resolved_model = (
            model
            or openai_model
            or os.getenv("OPENAI_VISION_MODEL")
            or DEFAULT_OPENAI_MODEL
        )
        LOGGER.info("AI vision provider=openai model=%s", resolved_model)
        observation = analyze_with_openai(
            image_url=resolved_image_url,
            nearest_sensor_log=nearest_sensor_log,
            device_id=device_id,
            location_id=location_id,
            observed_at=observed_at,
            user_note=user_note,
            api_key=api_key,
            model=resolved_model,
            http_client=http_client,
        )
        normalized = validate_observation(observation)
        normalized["provider"] = "openai"
        normalized["model"] = resolved_model
        return normalized

    api_key = (
        gemini_api_key
        if gemini_api_key is not None
        else os.getenv("GEMINI_API_KEY", "")
    )
    if not api_key:
        return fallback_observation(nearest_sensor_log)
    resolved_model = gemini_model or os.getenv("GEMINI_VISION_MODEL") or DEFAULT_GEMINI_MODEL
    last_error: Exception | None = None
    for model_candidate in gemini_model_candidates(resolved_model):
        LOGGER.info("AI vision provider=gemini model=%s", model_candidate)
        try:
            observation = analyze_with_gemini(
                image_url=resolved_image_url,
                image_bytes=image_bytes,
                image_mimetype=image_mimetype,
                nearest_sensor_log=nearest_sensor_log,
                device_id=device_id,
                location_id=location_id,
                observed_at=observed_at,
                user_note=user_note,
                api_key=api_key,
                model=model_candidate,
                http_client=http_client,
            )
            normalized = validate_observation(observation)
            normalized["provider"] = "gemini"
            normalized["model"] = model_candidate
            return normalized
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if not is_retryable_gemini_error(exc):
                raise
            LOGGER.warning(
                "Gemini vision retrying with fallback after model=%s error=%s",
                model_candidate,
                exc.__class__.__name__,
            )
    if last_error is not None:
        raise last_error
    return fallback_observation(nearest_sensor_log)


def gemini_model_candidates(primary_model: str) -> list[str]:
    fallback_models = os.getenv("GEMINI_VISION_FALLBACK_MODELS")
    models = [primary_model]
    if fallback_models:
        models.extend(model.strip() for model in fallback_models.split(","))
    else:
        models.extend(DEFAULT_GEMINI_FALLBACK_MODELS)
    return list(dict.fromkeys(model for model in models if model))


def is_retryable_gemini_error(exc: requests.exceptions.RequestException) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code in {429, 500, 502, 503, 504}


def analyze_with_openai(
    *,
    image_url: str | None,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    user_note: str | None,
    api_key: str,
    model: str,
    http_client=requests,
) -> dict[str, Any]:
    if not image_url:
        return fallback_observation(nearest_sensor_log)
    payload = build_openai_observation_payload(
        image_url=image_url,
        nearest_sensor_log=nearest_sensor_log,
        device_id=device_id,
        location_id=location_id,
        observed_at=observed_at,
        user_note=user_note,
        model=model,
    )
    response = http_client.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=AI_VISION_TIMEOUT_SECONDS,
    )
    if not response.ok:
        LOGGER.error(
            "OpenAI vision failed: status=%s body=%s",
            response.status_code,
            _truncate_text(getattr(response, "text", "")),
        )
        response.raise_for_status()
    observation = parse_openai_observation_response(response.json())
    LOGGER.warning("OpenAI vision parsed JSON keys=%s", sorted(observation.keys()))
    return observation


def analyze_with_gemini(
    *,
    image_url: str | None,
    image_bytes: bytes | None,
    image_mimetype: str | None,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    user_note: str | None,
    api_key: str,
    model: str,
    http_client=requests,
) -> dict[str, Any]:
    if image_bytes is None and image_url and image_url.startswith("data:"):
        image_mimetype, image_bytes = image_bytes_from_data_url(image_url)
    if image_bytes is None:
        return fallback_observation(nearest_sensor_log)

    LOGGER.warning(
        "Gemini vision image_bytes=%s mime_type=%s",
        len(image_bytes),
        image_mimetype or "image/jpeg",
    )
    payload = build_gemini_generate_content_payload(
        image_bytes=image_bytes,
        image_mimetype=image_mimetype,
        nearest_sensor_log=nearest_sensor_log,
        device_id=device_id,
        location_id=location_id,
        observed_at=observed_at,
        user_note=user_note,
    )
    response = http_client.post(
        GEMINI_GENERATE_CONTENT_URL_TEMPLATE.format(model=model),
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=AI_VISION_TIMEOUT_SECONDS,
    )
    if not response.ok:
        LOGGER.error(
            "Gemini vision failed: status=%s body=%s",
            response.status_code,
            _truncate_text(getattr(response, "text", "")),
        )
        response.raise_for_status()
    response_body = response.json()
    observation = parse_gemini_observation_response(response_body)
    LOGGER.warning("Gemini vision parsed JSON keys=%s", sorted(observation.keys()))
    return observation


def data_url_from_image_bytes(image_bytes: bytes, mimetype: str | None = None) -> str:
    media_type = mimetype or "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def image_bytes_from_data_url(data_url: str) -> tuple[str | None, bytes]:
    header, encoded = data_url.split(",", 1)
    mimetype = None
    if header.startswith("data:") and ";base64" in header:
        mimetype = header[len("data:") : header.index(";base64")]
    return mimetype, base64.b64decode(encoded)


def build_openai_observation_payload(
    *,
    image_url: str,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    user_note: str | None = None,
    model: str,
) -> dict[str, Any]:
    prompt = build_vision_prompt(
        nearest_sensor_log=nearest_sensor_log,
        device_id=device_id,
        location_id=location_id,
        observed_at=observed_at,
        user_note=user_note,
    )
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "plant_observation",
                "strict": True,
                "schema": AI_OBSERVATION_JSON_SCHEMA,
            }
        },
    }


def build_gemini_generate_content_payload(
    *,
    image_bytes: bytes,
    image_mimetype: str | None,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    user_note: str | None = None,
) -> dict[str, Any]:
    prompt = build_vision_prompt(
        nearest_sensor_log=nearest_sensor_log,
        device_id=device_id,
        location_id=location_id,
        observed_at=observed_at,
        user_note=user_note,
    )
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": image_mimetype or "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": AI_OBSERVATION_JSON_SCHEMA,
            "temperature": 0.2,
            "maxOutputTokens": 1000,
        },
    }

def build_gemini_observation_payload(
    *,
    image_bytes: bytes,
    image_mimetype: str | None,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    model: str,
    user_note: str | None = None,
) -> dict[str, Any]:
    prompt = build_vision_prompt(
        nearest_sensor_log=nearest_sensor_log,
        device_id=device_id,
        location_id=location_id,
        observed_at=observed_at,
        user_note=user_note,
    )
    return {
        "model": model,
        "input": [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "mime_type": image_mimetype or "image/jpeg",
            },
        ],
        "generation_config": {"thinking_level": "low"},
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": AI_OBSERVATION_JSON_SCHEMA,
        },
    }


def build_vision_prompt(
    *,
    nearest_sensor_log: dict[str, Any] | None,
    device_id: str,
    location_id: str,
    observed_at: datetime | None,
    user_note: str | None = None,
) -> str:
    sensor_context = json.dumps(nearest_sensor_log or {}, ensure_ascii=False, sort_keys=True)
    observed_at_text = observed_at.isoformat() if observed_at else "unknown"
    note_text = (user_note or "").strip()
    note_context = json.dumps(note_text, ensure_ascii=False) if note_text else "null"
    return "\n".join(
        [
            "You are helping record hydroponic basil growth from a Slack photo.",
            "This is observation support, not disease diagnosis.",
            "Return only the JSON object required by the schema.",
            "Use these growth_stage values only: seed, germination, cotyledon, true_leaf_1, true_leaf_2, vegetative.",
            "Set true_leaf_detected true only when true leaves are clearly visible beyond cotyledons.",
            "Estimate true_leaf_pair_count as 0, 1, 2, or more when visible; use null if impossible.",
            "Use root_visibility true only when roots are visible in the image.",
            "If the image is ambiguous, choose conservative values and lower confidence.",
            f"device_id={device_id}",
            f"location_id={location_id}",
            f"observed_at={observed_at_text}",
            f"slack_user_note={note_context}",
            f"nearest_sensor_log={sensor_context}",
        ]
    )


def parse_openai_observation_response(response_body: dict[str, Any]) -> dict[str, Any]:
    output_text = response_body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        parsed = json.loads(output_text)
        if isinstance(parsed, dict):
            return parsed

    for output_item in response_body.get("output", []) or []:
        for content in output_item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
    raise ValueError("OpenAI response did not contain observation JSON")


def parse_gemini_observation_response(response_body: dict[str, Any]) -> dict[str, Any]:
    output_text = response_body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        parsed = json.loads(output_text)
        if isinstance(parsed, dict):
            return parsed

    for output_item in response_body.get("output", []) or []:
        text = output_item.get("text")
        if isinstance(text, str) and text.strip():
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    for candidate in response_body.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
    for step in response_body.get("steps", []) or []:
        for content in step.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
    LOGGER.error(
        "Gemini response did not contain parseable observation JSON: body=%s",
        _truncate_text(json.dumps(response_body, ensure_ascii=False, sort_keys=True)),
    )
    raise ValueError("Gemini response did not contain observation JSON")


def validate_observation(observation: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_observation(observation)
    missing = [key for key in AI_OBSERVATION_JSON_SCHEMA["required"] if key not in normalized]
    if missing:
        raise ValueError("AI observation missing required keys: " + ", ".join(missing))
    return normalized


def normalize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    normalized = fallback_observation(None)
    normalized.update({key: observation.get(key) for key in normalized})
    if normalized["growth_stage"] not in GROWTH_STAGE_VALUES:
        normalized["growth_stage"] = "cotyledon"
    if normalized["crowding"] not in CROWDING_LABELS:
        normalized["crowding"] = "unknown"
    if normalized["leaf_color"] not in LEAF_COLOR_LABELS:
        normalized["leaf_color"] = "unknown"
    if normalized["leaf_size"] not in LEAF_SIZE_LABELS:
        normalized["leaf_size"] = "unknown"
    normalized["confidence"] = _clamp_float(normalized.get("confidence"), 0, 1, 0.3)
    for key in [
        "true_leaf_detected",
        "cotyledon_visible",
        "wilting",
        "yellowing",
        "root_visibility",
    ]:
        normalized[key] = bool(normalized.get(key))
    normalized["true_leaf_pair_count"] = _nullable_int(
        normalized.get("true_leaf_pair_count")
    )
    normalized["plant_count_estimate"] = _nullable_int(
        normalized.get("plant_count_estimate")
    )
    normalized["root_length_estimate"] = _nullable_float(
        normalized.get("root_length_estimate")
    )
    normalized["summary"] = str(normalized.get("summary") or "")
    normalized["next_action"] = str(normalized.get("next_action") or "")
    return normalized


def format_observation_for_slack(observation: dict[str, Any]) -> str:
    """Format an observation JSON object for a Slack thread reply."""

    growth_stage = GROWTH_STAGE_LABELS.get(
        str(observation.get("growth_stage")), str(observation.get("growth_stage"))
    )
    crowding = CROWDING_LABELS.get(
        str(observation.get("crowding")), str(observation.get("crowding"))
    )
    leaf_color = LEAF_COLOR_LABELS.get(
        str(observation.get("leaf_color")), str(observation.get("leaf_color"))
    )
    leaf_size = LEAF_SIZE_LABELS.get(
        str(observation.get("leaf_size")), str(observation.get("leaf_size"))
    )
    plant_count = observation.get("plant_count_estimate")
    plant_count_text = "取得不可" if plant_count is None else f"約{plant_count}"
    true_leaf = "あり" if observation.get("true_leaf_detected") else "なし"
    true_leaf_pairs = observation.get("true_leaf_pair_count")
    true_leaf_pairs_text = "取得不可" if true_leaf_pairs is None else str(true_leaf_pairs)
    cotyledon = "あり" if observation.get("cotyledon_visible") else "なし"
    yellowing = "あり" if observation.get("yellowing") else "なし"
    wilting = "あり" if observation.get("wilting") else "なし"
    root_visibility = "あり" if observation.get("root_visibility") else "なし"
    confidence = observation.get("confidence")
    confidence_text = "取得不可" if confidence is None else f"{float(confidence):.2f}"
    summary = observation.get("summary") or "観察メモなし"
    next_action = observation.get("next_action") or "次回も同じ条件で観察してください"

    return "\n".join(
        [
            "AI観察支援:",
            f"・生育段階: {growth_stage}",
            f"・本葉検出: {true_leaf}",
            f"・本葉対数: {true_leaf_pairs_text}",
            f"・子葉: {cotyledon}",
            f"・推定株数: {plant_count_text}",
            f"・密集: {crowding}",
            f"・葉色: {leaf_color}",
            f"・葉サイズ: {leaf_size}",
            f"・黄化: {yellowing}",
            f"・萎れ: {wilting}",
            f"・根の視認: {root_visibility}",
            f"・信頼度: {confidence_text}",
            f"・要約: {summary}",
            f"・次の確認: {next_action}",
        ]
    )


def extract_ai_observation_from_note(note: str | None) -> dict[str, Any] | None:
    """Extract the first ai_observation_json line from a care_logs note."""

    if not note:
        return None
    prefix = "ai_observation_json="
    for line in note.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            parsed = json.loads(line[len(prefix) :])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def extract_observed_at_from_note(note: str | None) -> str | None:
    if not note:
        return None
    prefix = "observed_at="
    for line in note.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def compare_observations(
    current_observation: dict[str, Any],
    previous_observation: dict[str, Any] | None,
    previous_observed_at: str | None = None,
) -> dict[str, Any]:
    """Compare the current observation with a previous observation JSON."""

    if not previous_observation:
        return {
            "has_previous": False,
            "summary": "比較できる前回観察記録はまだありません。",
        }

    current_stage = current_observation.get("growth_stage")
    previous_stage = previous_observation.get("growth_stage")
    current_count = current_observation.get("plant_count_estimate")
    previous_count = previous_observation.get("plant_count_estimate")
    current_true_leaf_pairs = current_observation.get("true_leaf_pair_count")
    previous_true_leaf_pairs = previous_observation.get("true_leaf_pair_count")
    current_crowding = current_observation.get("crowding")
    previous_crowding = previous_observation.get("crowding")
    next_action = (
        current_observation.get("next_action") or "次回も同じ条件で観察してください"
    )

    summary = "大きな変化は未確認です。次回も同じ角度で観察してください。"
    if current_stage != previous_stage:
        summary = "生育段階に変化があります。次回も同じ角度で観察してください。"
    elif _as_int(current_true_leaf_pairs) != _as_int(previous_true_leaf_pairs):
        summary = "本葉の対数に変化があります。葉の枚数を目視で確認してください。"
    elif _as_int(current_count) != _as_int(previous_count):
        summary = "推定株数に変化があります。発芽株数を目視で確認してください。"
    elif current_crowding != previous_crowding:
        summary = "密集度に変化があります。葉の重なりを確認してください。"
    elif next_action:
        summary = next_action

    return {
        "has_previous": True,
        "previous_observed_at": previous_observed_at,
        "growth_stage_change": f"{previous_stage} -> {current_stage}",
        "true_leaf_pair_count_change": (
            f"{previous_true_leaf_pairs} -> {current_true_leaf_pairs}"
        ),
        "plant_count_change": f"{previous_count} -> {current_count}",
        "crowding_change": f"{previous_crowding} -> {current_crowding}",
        "summary": summary,
    }


def format_comparison_for_slack(comparison: dict[str, Any]) -> str:
    """Format an observation comparison JSON object for Slack."""

    if not comparison.get("has_previous"):
        return "\n".join(
            [
                "前回との比較:",
                f"・変化メモ: {comparison.get('summary')}",
            ]
        )

    growth_change = _format_labeled_change(
        comparison.get("growth_stage_change"), GROWTH_STAGE_LABELS
    )
    crowding_change = _format_labeled_change(
        comparison.get("crowding_change"), CROWDING_LABELS
    )
    plant_count_change = _format_count_change(comparison.get("plant_count_change"))
    true_leaf_pair_change = _format_plain_change(
        comparison.get("true_leaf_pair_count_change")
    )

    return "\n".join(
        [
            "前回との比較:",
            f"・前回観察: {comparison.get('previous_observed_at') or '取得不可'}",
            f"・生育段階: {growth_change}",
            f"・本葉対数: {true_leaf_pair_change}",
            f"・推定株数: {plant_count_change}",
            f"・密集: {crowding_change}",
            f"・変化メモ: {comparison.get('summary')}",
        ]
    )


def guess_mimetype_from_url(url: str | None) -> str | None:
    if not url:
        return None
    mimetype, _ = mimetypes.guess_type(url)
    return mimetype


def _truncate_text(value: Any, limit: int = 1000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nullable_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    parsed = _nullable_float(value)
    if parsed is None:
        return default
    return min(max(parsed, minimum), maximum)


def _format_labeled_change(value: Any, labels: dict[str, str]) -> str:
    previous, current = _split_change(value)
    return f"{labels.get(previous, previous)} → {labels.get(current, current)}"


def _format_count_change(value: Any) -> str:
    previous, current = _split_change(value)
    return f"{_format_count(previous)} → {_format_count(current)}"


def _format_plain_change(value: Any) -> str:
    previous, current = _split_change(value)
    return f"{_format_plain(previous)} → {_format_plain(current)}"


def _split_change(value: Any) -> tuple[str, str]:
    text = str(value or "unknown -> unknown")
    if " -> " not in text:
        return text, text
    previous, current = text.split(" -> ", 1)
    return previous, current


def _format_count(value: str) -> str:
    return "取得不可" if value in {"None", "unknown", ""} else f"約{value}"


def _format_plain(value: str) -> str:
    return "取得不可" if value in {"None", "unknown", ""} else value
