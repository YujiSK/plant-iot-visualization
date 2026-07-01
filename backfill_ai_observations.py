#!/usr/bin/env python3
"""Backfill AI plant observations from historical Slack photo care logs."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from ai_observation import analyze_observation
from slack_observation_bot import (
    ImageIdentity,
    ObservationConfig,
    build_image_identity,
    fetch_slack_image_bytes,
    find_existing_plant_observation_identity,
    insert_plant_observation,
    slack_file_url,
    supabase_headers,
)


load_dotenv()

LOGGER = logging.getLogger("backfill_ai_observations")


@dataclass(frozen=True)
class BackfillCandidate:
    care_log_id: Any
    created_at: str | None
    note: str
    metadata: dict[str, str]
    sensor_log_id: Any = None

    @property
    def slack_ts(self) -> str | None:
        return self.metadata.get("slack_ts")

    @property
    def slack_file_id(self) -> str | None:
        return self.metadata.get("slack_file_id")

    @property
    def observed_at(self) -> datetime | None:
        return parse_observed_at(self.metadata.get("observed_at")) or parse_observed_at(
            self.created_at
        )


@dataclass
class BackfillStats:
    candidates_found: int = 0
    skipped_existing: int = 0
    skipped_duplicate_file_id: int = 0
    skipped_duplicate_sha256: int = 0
    processed_success: int = 0
    failed_download: int = 0
    failed_ai: int = 0
    failed_insert: int = 0
    plan: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates_found": self.candidates_found,
            "skipped_existing": self.skipped_existing,
            "skipped_duplicate_file_id": self.skipped_duplicate_file_id,
            "skipped_duplicate_sha256": self.skipped_duplicate_sha256,
            "processed_success": self.processed_success,
            "failed_download": self.failed_download,
            "failed_ai": self.failed_ai,
            "failed_insert": self.failed_insert,
        }


def parse_note_metadata(note: str | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if not note:
        return metadata
    for line in note.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            metadata[key] = value.strip()
    return metadata


def parse_observed_at(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith(" JST"):
        text = text[: -len(" JST")] + "+09:00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M%z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_backfill_candidate(row: dict[str, Any]) -> bool:
    note = row.get("note")
    metadata = parse_note_metadata(note)
    if not metadata.get("slack_file_id"):
        return False
    if metadata.get("ai_observation_json"):
        return False
    if metadata.get("ai_observation_error"):
        return True
    message = str(row.get("message") or "")
    return "Slack" in message or "写真" in message or "slack_ts" in metadata


def candidate_from_row(row: dict[str, Any]) -> BackfillCandidate:
    note = str(row.get("note") or "")
    return BackfillCandidate(
        care_log_id=row.get("id"),
        created_at=row.get("created_at"),
        note=note,
        metadata=parse_note_metadata(note),
        sensor_log_id=row.get("sensor_log_id"),
    )


def order_candidates(candidates: list[BackfillCandidate]) -> list[BackfillCandidate]:
    def sort_key(candidate: BackfillCandidate) -> tuple[datetime, str]:
        observed_at = candidate.observed_at or datetime.min.replace(tzinfo=timezone.utc)
        return observed_at.astimezone(timezone.utc), candidate.slack_ts or ""

    return sorted(candidates, key=sort_key)


def fetch_candidate_rows(
    config: ObservationConfig,
    http_client=requests,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    query = (
        "select=id,created_at,note,sensor_log_id,vitality_score,message"
        "&action_type=eq.checked"
        f"&note=ilike.{quote('*slack_file_id=*', safe='*=')}"
        "&order=created_at.asc"
        f"&limit={limit}"
    )
    response = http_client.get(
        f"{config.supabase_url}/rest/v1/care_logs?{query}",
        headers=supabase_headers(config),
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


def load_backfill_candidates(
    config: ObservationConfig,
    http_client=requests,
    limit: int | None = None,
) -> list[BackfillCandidate]:
    rows = fetch_candidate_rows(config, http_client=http_client)
    candidates = [candidate_from_row(row) for row in rows if is_backfill_candidate(row)]
    ordered = order_candidates(candidates)
    return ordered[:limit] if limit is not None else ordered


def slack_file_from_candidate(candidate: BackfillCandidate) -> dict[str, Any]:
    metadata = candidate.metadata
    return {
        "id": metadata.get("slack_file_id"),
        "name": metadata.get("slack_file_name"),
        "mimetype": metadata.get("slack_file_mimetype"),
        "url_private": metadata.get("slack_file_url"),
    }


def nearest_sensor_log_from_candidate(candidate: BackfillCandidate) -> dict[str, Any] | None:
    metadata = candidate.metadata
    if not any(key.startswith("nearest_") for key in metadata) and not candidate.sensor_log_id:
        return None
    return {
        "id": candidate.sensor_log_id,
        "created_at": metadata.get("nearest_sensor_log_time"),
        "vitality_score": _coerce_number(metadata.get("nearest_vitality_score")),
        "float_switch_state": metadata.get("nearest_float_switch_state"),
        "solution_temperature": _coerce_number(
            metadata.get("nearest_solution_temperature")
        ),
        "light_lux": _coerce_number(metadata.get("nearest_light_lux")),
    }


def existing_observation_for_candidate(
    candidate: BackfillCandidate,
    config: ObservationConfig,
    http_client=requests,
) -> str | None:
    if candidate.slack_file_id:
        reason = find_existing_plant_observation_identity(
            config=config,
            slack_file_id=candidate.slack_file_id,
            http_client=http_client,
            limit=1000,
        )
        if reason:
            return reason
    return None


def build_backfill_payload(
    *,
    candidate: BackfillCandidate,
    config: ObservationConfig,
    ai_observation: dict[str, Any],
    image_identity: ImageIdentity,
) -> dict[str, Any]:
    observed_at = candidate.observed_at
    if observed_at is None:
        raise ValueError("candidate missing observed_at")
    slack_file = slack_file_from_candidate(candidate)
    nearest_sensor_log = nearest_sensor_log_from_candidate(candidate)
    raw_ai_json = {
        **ai_observation,
        "backfilled": True,
        "provider": config.ai_vision_provider,
        "model": config.selected_ai_model,
        "slack_ts": candidate.slack_ts,
        "slack_file_id": slack_file.get("id"),
        "slack_file_name": slack_file.get("name"),
        "image_sha256": image_identity.sha256,
        "image_byte_size": image_identity.byte_size,
        "image_mime_type": image_identity.mime_type,
    }
    payload = {
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "sensor_log_id": candidate.sensor_log_id,
        "device_id": config.device_id,
        "location_id": config.location_id,
        "image_url": slack_file_url(slack_file),
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
        "raw_ai_json": raw_ai_json,
        "model": config.selected_ai_model,
    }
    if nearest_sensor_log and nearest_sensor_log.get("id") is not None:
        payload["sensor_log_id"] = nearest_sensor_log["id"]
    return {key: value for key, value in payload.items() if value is not None}


def plan_candidate(
    candidate: BackfillCandidate,
    config: ObservationConfig,
    http_client=requests,
    check_download: bool = False,
) -> dict[str, Any]:
    plan = {
        "care_log_id": candidate.care_log_id,
        "observed_at": candidate.observed_at.isoformat() if candidate.observed_at else None,
        "slack_ts": candidate.slack_ts,
        "slack_file_id": candidate.slack_file_id,
        "slack_file_name": candidate.metadata.get("slack_file_name"),
        "action": "process",
        "reason": None,
    }
    duplicate_reason = existing_observation_for_candidate(
        candidate, config, http_client=http_client
    )
    if duplicate_reason:
        plan["action"] = "skip"
        plan["reason"] = duplicate_reason
        return plan
    if check_download:
        image_bytes, image_mime_type = fetch_slack_image_bytes(
            slack_file_from_candidate(candidate), config, http_client=http_client
        )
        image_identity = build_image_identity(image_bytes, image_mime_type)
        if image_identity:
            plan.update(
                {
                    "image_sha256": image_identity.short_sha256,
                    "image_byte_size": image_identity.byte_size,
                    "image_mime_type": image_identity.mime_type,
                }
            )
    return plan


def run_backfill(
    *,
    config: ObservationConfig,
    dry_run: bool = False,
    check_download: bool = False,
    limit: int | None = None,
    http_client=requests,
) -> BackfillStats:
    stats = BackfillStats()
    candidates = load_backfill_candidates(config, http_client=http_client, limit=limit)
    stats.candidates_found = len(candidates)
    LOGGER.warning("backfill candidates found: %s", len(candidates))
    seen_slack_ts: set[str] = set()
    seen_slack_file_ids: set[str] = set()
    seen_image_sha256: set[str] = set()

    for candidate in candidates:
        in_run_duplicate_reason = in_run_duplicate_candidate_reason(
            candidate, seen_slack_ts, seen_slack_file_ids
        )
        if in_run_duplicate_reason:
            _count_skip(stats, in_run_duplicate_reason)
            plan = {
                "care_log_id": candidate.care_log_id,
                "observed_at": (
                    candidate.observed_at.isoformat() if candidate.observed_at else None
                ),
                "slack_ts": candidate.slack_ts,
                "slack_file_id": candidate.slack_file_id,
                "slack_file_name": candidate.metadata.get("slack_file_name"),
                "action": "skip",
                "reason": in_run_duplicate_reason,
            }
            if dry_run:
                stats.plan.append(plan)
            LOGGER.warning(
                "%s skipped in current backfill run: care_log_id=%s slack_ts=%s slack_file_id=%s",
                in_run_duplicate_reason,
                candidate.care_log_id,
                candidate.slack_ts,
                candidate.slack_file_id,
            )
            continue
        remember_candidate_identity(candidate, seen_slack_ts, seen_slack_file_ids)

        if dry_run:
            plan = plan_candidate(
                candidate,
                config,
                http_client=http_client,
                check_download=check_download,
            )
            stats.plan.append(plan)
            if plan["reason"] == "duplicate_slack_file_id":
                stats.skipped_duplicate_file_id += 1
            elif plan["reason"] == "duplicate_image_sha256":
                stats.skipped_duplicate_sha256 += 1
            elif plan["reason"]:
                stats.skipped_existing += 1
            continue

        duplicate_reason = existing_observation_for_candidate(
            candidate, config, http_client=http_client
        )
        if duplicate_reason:
            _count_skip(stats, duplicate_reason)
            LOGGER.warning(
                "%s skipped: care_log_id=%s slack_file_id=%s",
                duplicate_reason,
                candidate.care_log_id,
                candidate.slack_file_id,
            )
            continue

        try:
            image_bytes, image_mime_type = fetch_slack_image_bytes(
                slack_file_from_candidate(candidate), config, http_client=http_client
            )
            image_identity = build_image_identity(image_bytes, image_mime_type)
            if not image_identity:
                raise ValueError("downloaded image was empty")
            if image_identity.sha256 in seen_image_sha256:
                _count_skip(stats, "duplicate_image_sha256")
                LOGGER.warning(
                    "duplicate_image_sha256 skipped in current backfill run: care_log_id=%s slack_file_id=%s sha256=%s",
                    candidate.care_log_id,
                    candidate.slack_file_id,
                    image_identity.short_sha256,
                )
                continue
            seen_image_sha256.add(image_identity.sha256)
            LOGGER.warning(
                "backfill image identity: slack_file_id=%s sha256=%s bytes=%s mime_type=%s",
                candidate.slack_file_id,
                image_identity.short_sha256,
                image_identity.byte_size,
                image_identity.mime_type,
            )
        except Exception as exc:
            stats.failed_download += 1
            LOGGER.error(
                "backfill download failed: care_log_id=%s slack_file_id=%s error=%s: %s",
                candidate.care_log_id,
                candidate.slack_file_id,
                type(exc).__name__,
                exc,
            )
            continue

        duplicate_reason = find_existing_plant_observation_identity(
            config=config,
            image_sha256=image_identity.sha256,
            http_client=http_client,
            limit=1000,
        )
        if duplicate_reason:
            _count_skip(stats, duplicate_reason)
            LOGGER.warning(
                "%s skipped: care_log_id=%s slack_file_id=%s sha256=%s",
                duplicate_reason,
                candidate.care_log_id,
                candidate.slack_file_id,
                image_identity.short_sha256,
            )
            continue

        try:
            observed_at = candidate.observed_at
            ai_observation = analyze_observation(
                image_url=slack_file_url(slack_file_from_candidate(candidate)),
                image_bytes=image_bytes,
                image_mimetype=image_mime_type,
                nearest_sensor_log=nearest_sensor_log_from_candidate(candidate),
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
        except Exception as exc:
            stats.failed_ai += 1
            LOGGER.error(
                "backfill AI failed: care_log_id=%s slack_file_id=%s error=%s: %s",
                candidate.care_log_id,
                candidate.slack_file_id,
                type(exc).__name__,
                exc,
            )
            continue

        payload = build_backfill_payload(
            candidate=candidate,
            config=config,
            ai_observation=ai_observation,
            image_identity=image_identity,
        )
        if insert_plant_observation(payload, config, http_client=http_client):
            stats.processed_success += 1
            LOGGER.warning(
                "backfill insert success: care_log_id=%s slack_file_id=%s growth_stage=%s true_leaf_pair_count=%s",
                candidate.care_log_id,
                candidate.slack_file_id,
                payload.get("growth_stage"),
                payload.get("true_leaf_pair_count"),
            )
        else:
            stats.failed_insert += 1
    return stats


def print_dry_run_plan(stats: BackfillStats) -> None:
    for item in stats.plan:
        print(
            "candidate "
            f"care_log_id={item.get('care_log_id')} "
            f"observed_at={item.get('observed_at')} "
            f"slack_ts={item.get('slack_ts')} "
            f"slack_file_id={item.get('slack_file_id')} "
            f"file={item.get('slack_file_name')} "
            f"action={item.get('action')} "
            f"reason={item.get('reason')}"
        )
    print("summary=" + json.dumps(stats.as_dict(), sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-download", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    config = ObservationConfig.from_env()
    stats = run_backfill(
        config=config,
        dry_run=args.dry_run,
        check_download=args.check_download,
        limit=args.limit,
    )
    if args.dry_run:
        print_dry_run_plan(stats)
    else:
        print("summary=" + json.dumps(stats.as_dict(), sort_keys=True))
    return 0


def _coerce_number(value: str | None) -> int | float | None:
    if value in {None, "", "None"}:
        return None
    text = str(value)
    try:
        parsed = float(text)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _count_skip(stats: BackfillStats, reason: str) -> None:
    if reason == "duplicate_slack_file_id":
        stats.skipped_duplicate_file_id += 1
    elif reason == "duplicate_image_sha256":
        stats.skipped_duplicate_sha256 += 1
    else:
        stats.skipped_existing += 1


def in_run_duplicate_candidate_reason(
    candidate: BackfillCandidate,
    seen_slack_ts: set[str],
    seen_slack_file_ids: set[str],
) -> str | None:
    if candidate.slack_ts and candidate.slack_ts in seen_slack_ts:
        return "duplicate_slack_ts"
    if candidate.slack_file_id and candidate.slack_file_id in seen_slack_file_ids:
        return "duplicate_slack_file_id"
    return None


def remember_candidate_identity(
    candidate: BackfillCandidate,
    seen_slack_ts: set[str],
    seen_slack_file_ids: set[str],
) -> None:
    if candidate.slack_ts:
        seen_slack_ts.add(candidate.slack_ts)
    if candidate.slack_file_id:
        seen_slack_file_ids.add(candidate.slack_file_id)


if __name__ == "__main__":
    raise SystemExit(main())
