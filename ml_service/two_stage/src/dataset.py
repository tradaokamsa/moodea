from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd


POSITIVE_EVENT_WEIGHTS = {
    "like": 3.0,
    "continue": 1.0,
    "spotify_saved": 0.7,
    "spotify_top_track": 0.4,
    "recently_played": 0.4,
}
NEGATIVE_EVENT_WEIGHTS = {"skip": 1.0}


@dataclass(frozen=True)
class DatasetBuildResult:
    ranking_examples: pd.DataFrame
    retrieval_examples: pd.DataFrame
    report: dict[str, Any]


def read_event_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"event table not found: {path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    raise ValueError(f"unsupported event table format: {path.suffix}")


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _utc_column(frame: pd.DataFrame, column: str, name: str) -> None:
    frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    invalid = int(frame[column].isna().sum())
    if invalid:
        raise ValueError(f"{name}.{column} contains {invalid} invalid timestamps")


def _event_label(row: pd.Series) -> tuple[int | None, float | None]:
    event_type = str(row.get("interaction_type", ""))
    if event_type in POSITIVE_EVENT_WEIGHTS:
        sample_weight = row.get("sample_weight")
        weight = sample_weight if pd.notna(sample_weight) else POSITIVE_EVENT_WEIGHTS[event_type]
        return 1, float(weight)
    if event_type in NEGATIVE_EVENT_WEIGHTS:
        sample_weight = row.get("sample_weight")
        weight = sample_weight if pd.notna(sample_weight) else NEGATIVE_EVENT_WEIGHTS[event_type]
        return 0, float(weight)

    play_ms = row.get("play_ms")
    duration_ms = row.get("track_duration_ms")
    if pd.notna(play_ms) and pd.notna(duration_ms) and float(duration_ms) > 0:
        if float(play_ms) / float(duration_ms) >= 0.7:
            return 1, 0.7
    return None, None


def _prepare_interactions(interactions: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    interactions = interactions.copy()
    _require_columns(
        interactions,
        {"event_id", "user_id", "track_id", "interaction_type", "event_timestamp"},
        "interactions",
    )
    if "request_id" not in interactions:
        interactions["request_id"] = pd.NA
    _utc_column(interactions, "event_timestamp", "interactions")
    interactions = interactions.sort_values("event_timestamp", kind="stable")
    before = len(interactions)
    interactions = interactions.drop_duplicates("event_id", keep="first").reset_index(drop=True)
    interactions["_label_weight"] = interactions.apply(_event_label, axis=1)
    interactions["_event_label"] = interactions["_label_weight"].map(lambda value: value[0])
    interactions["_event_weight"] = interactions["_label_weight"].map(lambda value: value[1])
    return interactions.drop(columns=["_label_weight"]), before - len(interactions)


def _history_index(interactions: pd.DataFrame) -> dict[str, tuple[list[pd.Timestamp], list[str]]]:
    positives = interactions[interactions["_event_label"] == 1].sort_values(
        ["user_id", "event_timestamp"], kind="stable"
    )
    result: dict[str, tuple[list[pd.Timestamp], list[str]]] = {}
    for user_id, rows in positives.groupby("user_id", sort=False):
        result[str(user_id)] = (
            rows["event_timestamp"].tolist(),
            rows["track_id"].astype(str).tolist(),
        )
    return result


def build_point_in_time_datasets(
    impressions: pd.DataFrame,
    interactions: pd.DataFrame,
    *,
    as_of: datetime | pd.Timestamp | None = None,
    attribution_window: timedelta = timedelta(hours=24),
    max_history: int = 20,
) -> DatasetBuildResult:
    if max_history < 1:
        raise ValueError("max_history must be positive")

    impressions = impressions.copy()
    _require_columns(
        impressions,
        {"request_id", "user_id", "track_id", "shown_at"},
        "impressions",
    )
    _utc_column(impressions, "shown_at", "impressions")
    interactions, duplicate_events = _prepare_interactions(interactions)
    source_impressions = len(impressions)
    source_interactions = len(interactions) + duplicate_events

    snapshot_time = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if snapshot_time.tzinfo is None:
        snapshot_time = snapshot_time.tz_localize("UTC")
    else:
        snapshot_time = snapshot_time.tz_convert("UTC")
    window = pd.Timedelta(attribution_window)

    interactions = interactions[interactions["event_timestamp"] <= snapshot_time].copy()
    impressions["label_available_at"] = impressions["shown_at"] + window
    impressions = impressions[impressions["label_available_at"] <= snapshot_time].copy()
    impressions = impressions.sort_values("shown_at", kind="stable").reset_index(drop=True)
    impressions["_row_id"] = impressions.index

    attributable = interactions[
        interactions["request_id"].notna() & interactions["_event_label"].notna()
    ].copy()
    matches = impressions[
        ["_row_id", "request_id", "user_id", "track_id", "shown_at", "label_available_at"]
    ].merge(
        attributable,
        on=["request_id", "user_id", "track_id"],
        how="inner",
        suffixes=("", "_event"),
    )
    matches = matches[
        (matches["event_timestamp"] >= matches["shown_at"])
        & (matches["event_timestamp"] <= matches["label_available_at"])
    ].copy()
    matches = matches.sort_values(
        ["_row_id", "_event_label", "_event_weight", "event_timestamp"],
        ascending=[True, False, False, True],
        kind="stable",
    ).drop_duplicates("_row_id", keep="first")

    attributed = matches[
        [
            "_row_id",
            "event_id",
            "interaction_type",
            "event_timestamp",
            "_event_label",
            "_event_weight",
        ]
    ].rename(columns={"_event_label": "label", "_event_weight": "sample_weight"})
    examples = impressions.merge(attributed, on="_row_id", how="left")
    examples["label"] = examples["label"].fillna(0).astype("int8")
    examples["sample_weight"] = examples["sample_weight"].fillna(0.1).astype("float32")
    examples["interaction_type"] = examples["interaction_type"].fillna("no_response")
    examples["feature_timestamp"] = examples["shown_at"]
    examples["label_timestamp"] = examples["event_timestamp"].fillna(
        examples["label_available_at"]
    )

    histories = _history_index(interactions)
    history_tracks: list[list[str]] = []
    history_timestamps: list[list[str]] = []
    for row in examples.itertuples(index=False):
        timestamps, tracks = histories.get(str(row.user_id), ([], []))
        cutoff = bisect_left(timestamps, row.shown_at)
        start = max(0, cutoff - max_history)
        history_tracks.append(tracks[start:cutoff])
        history_timestamps.append(
            [timestamp.isoformat() for timestamp in timestamps[start:cutoff]]
        )
    examples["history_track_ids"] = history_tracks
    examples["history_event_timestamps"] = history_timestamps
    examples["history_length"] = examples["history_track_ids"].map(len).astype("int16")

    leakage_violations = sum(
        any(pd.Timestamp(timestamp) >= shown_at for timestamp in timestamps)
        for shown_at, timestamps in zip(
            examples["shown_at"], examples["history_event_timestamps"]
        )
    )
    if leakage_violations:
        raise AssertionError(f"point-in-time leakage detected in {leakage_violations} rows")

    retrieval = examples[examples["label"] == 1].copy()
    retrieval = retrieval.rename(
        columns={"track_id": "positive_track_id", "label_timestamp": "target_timestamp"}
    )[
        [
            "request_id",
            "user_id",
            "positive_track_id",
            "feature_timestamp",
            "target_timestamp",
            "sample_weight",
            "history_track_ids",
            "history_event_timestamps",
        ]
    ]

    examples = examples.drop(columns=["_row_id"])
    report = {
        "as_of": snapshot_time.isoformat(),
        "attribution_window_hours": attribution_window.total_seconds() / 3600.0,
        "max_history": max_history,
        "source_impressions": source_impressions,
        "mature_impressions": len(examples),
        "source_interactions": source_interactions,
        "deduplicated_interactions": duplicate_events,
        "positive_examples": int((examples["label"] == 1).sum()),
        "negative_examples": int((examples["label"] == 0).sum()),
        "no_response_examples": int((examples["interaction_type"] == "no_response").sum()),
        "retrieval_examples": len(retrieval),
        "point_in_time_leakage_violations": leakage_violations,
    }
    return DatasetBuildResult(
        ranking_examples=examples.reset_index(drop=True),
        retrieval_examples=retrieval.reset_index(drop=True),
        report=report,
    )


def save_point_in_time_datasets(result: DatasetBuildResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.ranking_examples.to_parquet(output_dir / "ranking_examples.parquet", index=False)
    result.retrieval_examples.to_parquet(output_dir / "retrieval_examples.parquet", index=False)
    (output_dir / "dataset_report.json").write_text(
        json.dumps(result.report, indent=2, sort_keys=True), encoding="utf-8"
    )
