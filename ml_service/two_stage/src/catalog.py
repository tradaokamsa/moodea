from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


AUDIO_COLUMNS = [
    "danceability",
    "energy",
    "loudness",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
]

MODEL_NUMERIC_COLUMNS = ["duration_log", *AUDIO_COLUMNS]
MOOD_NAMES = ["sad", "happy", "energetic", "calm"]
TRACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{22}$")


@dataclass
class Catalog:
    frame: pd.DataFrame
    features: np.ndarray
    feature_mean: np.ndarray
    feature_std: np.ndarray

    @property
    def track_ids(self) -> list[str]:
        return self.frame["track_id"].astype(str).tolist()

    @property
    def feature_dim(self) -> int:
        return int(self.features.shape[1])


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quality_report(frame: pd.DataFrame) -> dict[str, Any]:
    normalized_columns = [
        "danceability",
        "energy",
        "speechiness",
        "acousticness",
        "instrumentalness",
        "liveness",
        "valence",
    ]
    invalid_ranges: dict[str, int] = {}
    for column in normalized_columns:
        invalid_ranges[column] = int((~frame[column].between(0.0, 1.0)).sum())
    invalid_ranges["loudness"] = int((~frame["loudness"].between(-60.0, 5.0)).sum())
    invalid_ranges["tempo"] = int((~frame["tempo"].between(0.0, 250.0)).sum())
    invalid_ranges["duration_ms"] = int((frame["duration_ms"] <= 0).sum())
    return {
        "row_count": int(len(frame)),
        "unique_track_ids": int(frame["track_id"].nunique()),
        "duplicate_track_ids": int(frame["track_id"].duplicated().sum()),
        "missing_values": int(frame.isna().sum().sum()),
        "invalid_track_ids": int(
            (~frame["track_id"].astype(str).map(lambda value: bool(TRACK_ID_PATTERN.fullmatch(value)))).sum()
        ),
        "invalid_ranges": invalid_ranges,
        "mood_distribution": {
            str(key): int(value)
            for key, value in frame["mood_label"].value_counts().sort_index().items()
        },
    }


def load_seed_catalog(csv_path: Path, max_tracks: int = 0, seed: int = 42) -> Catalog:
    if not csv_path.exists():
        raise FileNotFoundError(f"catalog CSV not found: {csv_path}")

    frame = pd.read_csv(csv_path)
    drop_columns = [column for column in frame.columns if not column or column.startswith("Unnamed:")]
    frame = frame.drop(columns=drop_columns, errors="ignore")
    frame = frame.drop(columns=["spec_rate"], errors="ignore")
    frame = frame.rename(columns={"duration (ms)": "duration_ms", "labels": "mood_label"})

    required = {"duration_ms", "mood_label", "uri", *AUDIO_COLUMNS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"catalog is missing required columns: {missing}")

    frame["track_id"] = frame["uri"].astype(str).str.removeprefix("spotify:track:")
    frame = frame.drop_duplicates(subset=["track_id"], keep="first")
    frame["duration_ms"] = pd.to_numeric(frame["duration_ms"], errors="raise").astype("int32")
    frame["mood_label"] = pd.to_numeric(frame["mood_label"], errors="raise").astype("int8")
    for column in AUDIO_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("float32")

    if max_tracks and len(frame) > max_tracks:
        selected, _ = train_test_split(
            frame,
            train_size=max_tracks,
            stratify=frame["mood_label"],
            random_state=seed,
        )
        frame = selected

    frame = frame.sort_values("track_id").reset_index(drop=True)
    frame["track_index"] = np.arange(1, len(frame) + 1, dtype=np.int32)
    frame["duration_log"] = np.log1p(frame["duration_ms"].to_numpy(dtype=np.float32))
    frame["source"] = "278k_labelled_uri"
    frame["feature_version"] = "item-features-v1"
    frame["eligible_for_recommendation"] = True

    report = _quality_report(frame)
    invalid_count = (
        report["duplicate_track_ids"]
        + report["missing_values"]
        + report["invalid_track_ids"]
        + sum(report["invalid_ranges"].values())
    )
    if invalid_count:
        raise ValueError(f"catalog quality validation failed: {json.dumps(report, sort_keys=True)}")
    if not frame["mood_label"].isin(range(4)).all():
        raise ValueError("mood_label must be one of 0, 1, 2, 3")

    numeric = frame[MODEL_NUMERIC_COLUMNS].to_numpy(dtype=np.float32)
    feature_mean = numeric.mean(axis=0, dtype=np.float64).astype(np.float32)
    feature_std = numeric.std(axis=0, dtype=np.float64).astype(np.float32)
    feature_std = np.where(feature_std < 1e-6, 1.0, feature_std).astype(np.float32)
    normalized = (numeric - feature_mean) / feature_std
    moods = np.eye(4, dtype=np.float32)[frame["mood_label"].to_numpy(dtype=np.int64)]
    features = np.concatenate([normalized, moods], axis=1).astype(np.float32)

    return Catalog(
        frame=frame,
        features=features,
        feature_mean=feature_mean,
        feature_std=feature_std,
    )


def save_catalog(catalog: Catalog, artifact_dir: Path, source_path: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    catalog.frame.to_parquet(artifact_dir / "catalog.parquet", index=False)
    np.savez_compressed(
        artifact_dir / "catalog.npz",
        track_ids=np.asarray(catalog.track_ids),
        features=catalog.features,
        feature_mean=catalog.feature_mean,
        feature_std=catalog.feature_std,
        duration_ms=catalog.frame["duration_ms"].to_numpy(dtype=np.int32),
        mood_label=catalog.frame["mood_label"].to_numpy(dtype=np.int8),
        **{
            column: catalog.frame[column].to_numpy(dtype=np.float32)
            for column in AUDIO_COLUMNS
        },
    )
    report = _quality_report(catalog.frame)
    (artifact_dir / "quality_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest = {
        "catalog_version": "tracks-v1",
        "feature_version": "item-features-v1",
        "row_count": len(catalog.frame),
        "feature_dim": catalog.feature_dim,
        "feature_order": [*MODEL_NUMERIC_COLUMNS, *[f"mood_{name}" for name in MOOD_NAMES]],
        "source": source_path.name,
        "source_sha256": _file_sha256(source_path),
    }
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def load_catalog_artifacts(artifact_dir: Path) -> Catalog:
    arrays = np.load(artifact_dir / "catalog.npz", allow_pickle=False)
    frame = pd.DataFrame(
        {
            "track_id": arrays["track_ids"].astype(str),
            "duration_ms": arrays["duration_ms"].astype(np.int32),
            "mood_label": arrays["mood_label"].astype(np.int8),
            **{column: arrays[column].astype(np.float32) for column in AUDIO_COLUMNS},
        }
    )
    frame["track_index"] = np.arange(1, len(frame) + 1, dtype=np.int32)
    frame["duration_log"] = np.log1p(frame["duration_ms"].to_numpy(dtype=np.float32))
    frame["eligible_for_recommendation"] = True
    return Catalog(
        frame=frame,
        features=arrays["features"].astype(np.float32),
        feature_mean=arrays["feature_mean"].astype(np.float32),
        feature_std=arrays["feature_std"].astype(np.float32),
    )
