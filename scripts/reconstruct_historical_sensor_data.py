#!/usr/bin/env python3
"""Export sensor logs with reversible historical offset reconstruction.

The source SQLite database is opened read-only and is never modified. Original
columns are preserved in the CSV. Reconstructed columns represent the sensor
outputs before the historical fixed offsets, not calibrated ambient values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


JST = timezone(timedelta(hours=9), name="JST")
UTC = timezone.utc
SCRIPT_VERSION = "1"


@dataclass(frozen=True)
class ReconstructionPeriod:
    name: str
    start_jst: datetime | None
    end_jst: datetime | None
    measurement_system: str
    temperature_offset: float | None
    humidity_offset: float | None
    confidence: str
    evidence: str

    def contains(self, recorded_at_jst: datetime) -> bool:
        if self.start_jst is not None and recorded_at_jst < self.start_jst:
            return False
        if self.end_jst is not None and recorded_at_jst > self.end_jst:
            return False
        return True


def jst(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=JST)


PERIODS = (
    ReconstructionPeriod(
        name="sense_hat_no_offset",
        start_jst=None,
        end_jst=jst("2026-05-14 00:32:17"),
        measurement_system="sense_hat",
        temperature_offset=0.0,
        humidity_offset=0.0,
        confidence="confirmed",
        evidence="Stored before the fixed offsets were active.",
    ),
    ReconstructionPeriod(
        name="sense_hat_temp_minus_8",
        start_jst=jst("2026-05-15 08:23:25"),
        end_jst=jst("2026-05-18 09:32:35"),
        measurement_system="sense_hat",
        temperature_offset=-8.0,
        humidity_offset=0.0,
        confidence="high_confidence",
        evidence=(
            "Inferred from the database gap, value discontinuity, historical "
            "code, and the contemporaneous .env setting."
        ),
    ),
    ReconstructionPeriod(
        name="sense_hat_temp_minus_8_humidity_plus_15",
        start_jst=jst("2026-05-18 09:32:39"),
        end_jst=jst("2026-05-18 09:37:41"),
        measurement_system="sense_hat",
        temperature_offset=-8.0,
        humidity_offset=15.0,
        confidence="confirmed",
        evidence="Historical code, project log, and database transition.",
    ),
    ReconstructionPeriod(
        name="sense_hat_temp_minus_15_humidity_plus_15",
        start_jst=jst("2026-05-18 09:38:33"),
        end_jst=jst("2026-05-25 21:42:39"),
        measurement_system="sense_hat",
        temperature_offset=-15.0,
        humidity_offset=15.0,
        confidence="confirmed",
        evidence=(
            "Codex session logs preserve raw and corrected pairs; database "
            "rows confirm the transition."
        ),
    ),
    ReconstructionPeriod(
        name="dht11_no_offset",
        start_jst=jst("2026-06-02 04:12:03"),
        end_jst=None,
        measurement_system="dht11",
        temperature_offset=0.0,
        humidity_offset=0.0,
        confidence="confirmed",
        evidence="DHT11 runtime intentionally records unadjusted readings.",
    ),
)


ADDED_COLUMNS = (
    "recorded_at_utc",
    "recorded_at_jst",
    "reconstruction_period",
    "measurement_system",
    "temperature_offset_applied",
    "humidity_offset_applied",
    "reconstructed_sensor_temperature",
    "reconstructed_sensor_humidity",
    "reconstruction_confidence",
    "reconstruction_evidence",
    "reconstruction_note",
)


def parse_sqlite_timestamp(value: Any) -> datetime:
    if value is None:
        raise ValueError("created_at is NULL")
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def period_for(recorded_at_jst: datetime) -> ReconstructionPeriod | None:
    for period in PERIODS:
        if period.contains(recorded_at_jst):
            return period
    return None


def undo_offset(value: Any, offset: float | None) -> float | None:
    if value is None or offset is None:
        return None
    return round(float(value) - offset, 2)


def reconstruct_row(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    try:
        recorded_at_utc = parse_sqlite_timestamp(row.get("created_at"))
    except (TypeError, ValueError) as exc:
        output.update(
            {
                "recorded_at_utc": "",
                "recorded_at_jst": "",
                "reconstruction_period": "unknown",
                "measurement_system": "unknown",
                "temperature_offset_applied": "",
                "humidity_offset_applied": "",
                "reconstructed_sensor_temperature": "",
                "reconstructed_sensor_humidity": "",
                "reconstruction_confidence": "unknown",
                "reconstruction_evidence": "",
                "reconstruction_note": f"Not reconstructed: {exc}",
            }
        )
        return output

    recorded_at_jst = recorded_at_utc.astimezone(JST)
    period = period_for(recorded_at_jst)
    if period is None:
        output.update(
            {
                "recorded_at_utc": recorded_at_utc.isoformat(),
                "recorded_at_jst": recorded_at_jst.isoformat(),
                "reconstruction_period": "unknown",
                "measurement_system": "unknown",
                "temperature_offset_applied": "",
                "humidity_offset_applied": "",
                "reconstructed_sensor_temperature": "",
                "reconstructed_sensor_humidity": "",
                "reconstruction_confidence": "unknown",
                "reconstruction_evidence": "",
                "reconstruction_note": (
                    "No row is expected in this known data gap. Values were "
                    "left unchanged and were not guessed."
                ),
            }
        )
        return output

    output.update(
        {
            "recorded_at_utc": recorded_at_utc.isoformat(),
            "recorded_at_jst": recorded_at_jst.isoformat(),
            "reconstruction_period": period.name,
            "measurement_system": period.measurement_system,
            "temperature_offset_applied": period.temperature_offset,
            "humidity_offset_applied": period.humidity_offset,
            "reconstructed_sensor_temperature": undo_offset(
                row.get("temperature"), period.temperature_offset
            ),
            "reconstructed_sensor_humidity": undo_offset(
                row.get("humidity"), period.humidity_offset
            ),
            "reconstruction_confidence": period.confidence,
            "reconstruction_evidence": period.evidence,
            "reconstruction_note": (
                "Reconstructed values are pre-offset sensor outputs, not "
                "calibrated ambient measurements."
            ),
        }
    )
    return output


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(db_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    uri = f"file:{quote(str(db_path.resolve()), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'sensor_logs'"
        ).fetchone()
        if table is None:
            raise RuntimeError("sensor_logs table was not found")
        columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(sensor_logs)"
            ).fetchall()
        ]
        required = {"created_at", "temperature", "humidity"}
        missing = sorted(required.difference(columns))
        if missing:
            raise RuntimeError(
                "sensor_logs is missing required columns: " + ", ".join(missing)
            )
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM sensor_logs ORDER BY created_at, id"
            ).fetchall()
        ]
    return columns, rows


def metadata_period(period: ReconstructionPeriod) -> dict[str, Any]:
    data = asdict(period)
    data["start_jst"] = (
        period.start_jst.isoformat() if period.start_jst is not None else None
    )
    data["end_jst"] = (
        period.end_jst.isoformat() if period.end_jst is not None else None
    )
    return data


def export(db_path: Path, output_path: Path) -> dict[str, Any]:
    hash_before = sha256_file(db_path)
    original_columns, rows = read_rows(db_path)
    reconstructed = [reconstruct_row(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = original_columns + list(ADDED_COLUMNS)
    with output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reconstructed)
    hash_after = sha256_file(db_path)

    unknown_count = sum(
        row["reconstruction_period"] == "unknown" for row in reconstructed
    )
    metadata = {
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_database": str(db_path.resolve()),
        "source_sha256_before": hash_before,
        "source_sha256_after": hash_after,
        "source_changed_during_export": hash_before != hash_after,
        "output_csv": str(output_path.resolve()),
        "row_count": len(reconstructed),
        "unknown_reconstruction_count": unknown_count,
        "first_recorded_at": rows[0].get("created_at") if rows else None,
        "last_recorded_at": rows[-1].get("created_at") if rows else None,
        "periods": [metadata_period(period) for period in PERIODS],
        "interpretation": (
            "Reconstructed values are the outputs before historical fixed "
            "offsets. Sense HAT board heat remains present."
        ),
    }
    metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export sensor_logs without changing the database and reconstruct "
            "pre-offset historical sensor outputs."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data.db"),
        help="Source SQLite database (default: data.db)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("exports/sensor_logs_reconstructed.csv"),
        help="Destination CSV path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.is_file():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 1
    try:
        metadata = export(args.db, args.output)
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1
    print(f"exported {metadata['row_count']} rows: {args.output}")
    print(
        "metadata: "
        + str(args.output.with_suffix(args.output.suffix + ".metadata.json"))
    )
    if metadata["source_changed_during_export"]:
        print(
            "warning: the source database changed during export; rerun during "
            "a quiet interval for matching before/after hashes",
            file=sys.stderr,
        )
    if metadata["unknown_reconstruction_count"]:
        print(
            "warning: "
            f"{metadata['unknown_reconstruction_count']} rows were left unknown",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
