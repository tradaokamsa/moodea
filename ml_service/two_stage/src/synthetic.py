from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import uuid

import numpy as np
import pandas as pd

from .catalog import Catalog


@dataclass
class SyntheticDataset:
    user_ids: list[str]
    user_profiles: np.ndarray
    history_indices: list[list[int]]
    train_positive_indices: list[list[int]]
    heldout_positive_indices: list[list[int]]
    preferred_hours: np.ndarray
    interactions: pd.DataFrame
    impressions: pd.DataFrame


def _normalize(values: np.ndarray) -> np.ndarray:
    denominator = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.clip(denominator, 1e-8, None)


def generate_synthetic_dataset(
    catalog: Catalog,
    num_users: int = 256,
    history_size: int = 12,
    train_positives: int = 12,
    heldout_positives: int = 4,
    seed: int = 42,
) -> SyntheticDataset:
    if len(catalog.frame) < history_size + train_positives + heldout_positives + 20:
        raise ValueError("catalog is too small for the requested synthetic dataset")

    rng = np.random.default_rng(seed)
    normalized_features = _normalize(catalog.features)
    track_ids = catalog.track_ids
    user_ids: list[str] = []
    profiles: list[np.ndarray] = []
    histories: list[list[int]] = []
    train_targets: list[list[int]] = []
    heldout_targets: list[list[int]] = []
    preferred_hours: list[int] = []
    interaction_rows: list[dict[str, Any]] = []
    impression_rows: list[dict[str, Any]] = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    mood_labels = catalog.frame["mood_label"].to_numpy(dtype=np.int64)
    mood_members = {label: np.flatnonzero(mood_labels == label) for label in range(4)}

    for user_number in range(num_users):
        user_id = f"synthetic-user-{user_number:04d}"
        primary_mood = int(rng.integers(0, 4))
        secondary_mood = int((primary_mood + rng.integers(1, 4)) % 4)
        seed_indices = np.concatenate(
            [
                rng.choice(mood_members[primary_mood], size=3, replace=False),
                rng.choice(mood_members[secondary_mood], size=2, replace=False),
            ]
        )
        latent_preference = catalog.features[seed_indices].mean(axis=0)
        latent_preference += rng.normal(0.0, 0.15, size=latent_preference.shape)
        latent_preference /= max(np.linalg.norm(latent_preference), 1e-8)

        relevance = normalized_features @ latent_preference
        relevance += rng.normal(0.0, 0.04, size=len(relevance))
        chosen = np.argpartition(
            relevance,
            -(history_size + train_positives + heldout_positives),
        )[-(history_size + train_positives + heldout_positives):]
        chosen = chosen[np.argsort(relevance[chosen])[::-1]]

        history = chosen[:history_size].astype(int).tolist()
        training = chosen[history_size : history_size + train_positives].astype(int).tolist()
        heldout = chosen[history_size + train_positives :].astype(int).tolist()
        profile = catalog.features[history].mean(axis=0).astype(np.float32)
        preferred_hour = int(rng.integers(0, 24))

        user_ids.append(user_id)
        profiles.append(profile)
        histories.append(history)
        train_targets.append(training)
        heldout_targets.append(heldout)
        preferred_hours.append(preferred_hour)

        for position, track_index in enumerate(history):
            observed_at = base_time + timedelta(days=user_number, minutes=position)
            signal = ["spotify_top_track", "spotify_saved", "recently_played"][position % 3]
            interaction_rows.append(
                {
                    "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}:{track_ids[track_index]}:{signal}")),
                    "request_id": None,
                    "session_id": f"bootstrap-{user_id}",
                    "user_id": user_id,
                    "track_id": track_ids[track_index],
                    "interaction_type": signal,
                    "score": 1 if signal != "spotify_saved" else 3,
                    "sample_weight": 0.4 if signal != "spotify_saved" else 0.7,
                    "event_timestamp": observed_at,
                    "source": "synthetic_spotify_bootstrap",
                }
            )

        all_positive = set(history + training + heldout)
        negative_pool = np.setdiff1d(np.arange(len(track_ids)), np.fromiter(all_positive, dtype=np.int64))
        for request_number, positive_index in enumerate(training + heldout):
            request_id = f"synthetic-rec-{user_number:04d}-{request_number:03d}"
            shown_at = base_time + timedelta(days=user_number + 30, minutes=request_number * 5)
            negatives = rng.choice(negative_pool, size=9, replace=False).astype(int).tolist()
            candidate_indices = [positive_index, *negatives]
            rng.shuffle(candidate_indices)
            for rank, track_index in enumerate(candidate_indices, start=1):
                score = float(relevance[track_index])
                impression_rows.append(
                    {
                        "request_id": request_id,
                        "session_id": f"session-{user_id}",
                        "user_id": user_id,
                        "track_id": track_ids[track_index],
                        "retrieval_rank": rank,
                        "retrieval_score": score,
                        "final_rank": rank,
                        "shown_at": shown_at,
                        "model_version": "synthetic-oracle-v1",
                        "catalog_version": "tracks-v1",
                    }
                )
            interaction_type = "like" if request_number % 3 == 0 else "continue"
            interaction_rows.append(
                {
                    "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request_id}:{positive_index}:positive")),
                    "request_id": request_id,
                    "session_id": f"session-{user_id}",
                    "user_id": user_id,
                    "track_id": track_ids[positive_index],
                    "interaction_type": interaction_type,
                    "score": 3 if interaction_type == "like" else 1,
                    "sample_weight": 1.0 if interaction_type == "like" else 0.7,
                    "event_timestamp": shown_at + timedelta(seconds=30),
                    "source": "synthetic_recommendation",
                }
            )
            skipped_index = negatives[0]
            interaction_rows.append(
                {
                    "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request_id}:{skipped_index}:skip")),
                    "request_id": request_id,
                    "session_id": f"session-{user_id}",
                    "user_id": user_id,
                    "track_id": track_ids[skipped_index],
                    "interaction_type": "skip",
                    "score": -1,
                    "sample_weight": 1.0,
                    "event_timestamp": shown_at + timedelta(seconds=5),
                    "source": "synthetic_recommendation",
                }
            )

    return SyntheticDataset(
        user_ids=user_ids,
        user_profiles=np.stack(profiles).astype(np.float32),
        history_indices=histories,
        train_positive_indices=train_targets,
        heldout_positive_indices=heldout_targets,
        preferred_hours=np.asarray(preferred_hours, dtype=np.int64),
        interactions=pd.DataFrame(interaction_rows),
        impressions=pd.DataFrame(impression_rows),
    )


def save_synthetic_dataset(dataset: SyntheticDataset, catalog: Catalog, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dataset.interactions.to_parquet(artifact_dir / "synthetic_interactions.parquet", index=False)
    dataset.impressions.to_parquet(artifact_dir / "synthetic_impressions.parquet", index=False)
    users = []
    for index, user_id in enumerate(dataset.user_ids):
        users.append(
            {
                "user_id": user_id,
                "profile": dataset.user_profiles[index].astype(float).tolist(),
                "history_track_ids": [catalog.track_ids[item] for item in dataset.history_indices[index]],
                "train_positive_track_ids": [
                    catalog.track_ids[item] for item in dataset.train_positive_indices[index]
                ],
                "heldout_positive_track_ids": [
                    catalog.track_ids[item] for item in dataset.heldout_positive_indices[index]
                ],
                "preferred_hour": int(dataset.preferred_hours[index]),
            }
        )
    (artifact_dir / "synthetic_users.json").write_text(
        json.dumps(users, indent=2), encoding="utf-8"
    )
