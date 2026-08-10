from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
import json
import logging
import math
import uuid

import numpy as np
from .catalog import AUDIO_COLUMNS, MOOD_NAMES, Catalog, load_catalog_artifacts

import faiss
import torch

torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from .models import DINRanker, TwoTowerModel
from .schemas import InteractionRequest, RecommendationRequest


logger = logging.getLogger(__name__)


@dataclass
class UserState:
    profile: np.ndarray
    history_indices: list[int] = field(default_factory=list)
    excluded_indices: set[int] = field(default_factory=set)
    positive_weight: float = 0.0
    interaction_count: int = 0


class RecommenderService:
    def __init__(self, artifact_dir: Path, event_dir: Path, diversity_lambda: float = 0.85):
        self.artifact_dir = artifact_dir
        self.event_dir = event_dir
        self.diversity_lambda = diversity_lambda
        self.lock = RLock()
        self.catalog: Catalog | None = None
        self.model: TwoTowerModel | None = None
        self.ranker: DINRanker | None = None
        self.index: faiss.Index | None = None
        self.item_embeddings: np.ndarray | None = None
        self.track_to_index: dict[str, int] = {}
        self.users: dict[str, UserState] = {}
        self.manifest: dict[str, Any] = {}

    @property
    def ready(self) -> bool:
        return all(
            value is not None
            for value in [self.catalog, self.model, self.ranker, self.index, self.item_embeddings]
        )

    def load(self) -> None:
        logger.info("loading recommender artifacts from %s", self.artifact_dir)
        catalog = load_catalog_artifacts(self.artifact_dir)
        track_ids = catalog.track_ids
        track_to_index = {track_id: index for index, track_id in enumerate(track_ids)}
        item_embeddings = np.load(self.artifact_dir / "item_embeddings.npy").astype(np.float32)
        manifest_path = self.artifact_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        retrieval_checkpoint = torch.load(
            self.artifact_dir / "two_tower.pt", map_location="cpu", weights_only=False
        )
        model = TwoTowerModel(
            feature_dim=int(retrieval_checkpoint["feature_dim"]),
            embedding_dim=int(retrieval_checkpoint["embedding_dim"]),
        )
        model.load_state_dict(retrieval_checkpoint["state_dict"])
        model.eval()

        ranker_checkpoint = torch.load(
            self.artifact_dir / "din_ranker.pt", map_location="cpu", weights_only=False
        )
        ranker = DINRanker(
            embedding_dim=int(ranker_checkpoint["embedding_dim"]),
            context_dim=int(ranker_checkpoint["context_dim"]),
        )
        ranker.load_state_dict(ranker_checkpoint["state_dict"])
        ranker.eval()
        index = faiss.read_index(str(self.artifact_dir / "faiss.index"))

        users: dict[str, UserState] = {}
        users_path = self.artifact_dir / "synthetic_users.json"
        if users_path.exists():
            for row in json.loads(users_path.read_text(encoding="utf-8")):
                history = [
                    track_to_index[track_id]
                    for track_id in row["history_track_ids"]
                    if track_id in track_to_index
                ]
                users[row["user_id"]] = UserState(
                    profile=np.asarray(row["profile"], dtype=np.float32),
                    history_indices=history,
                    excluded_indices=set(history),
                    positive_weight=float(len(history)),
                    interaction_count=len(history),
                )

        with self.lock:
            self.catalog = catalog
            self.model = model
            self.ranker = ranker
            self.index = index
            self.item_embeddings = item_embeddings
            self.track_to_index = track_to_index
            self.users = users
            self.manifest = manifest
            self.event_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "recommender ready: catalog_size=%d known_users=%d",
            len(catalog.frame),
            len(users),
        )

    def _cold_start_profile(self, request: RecommendationRequest) -> tuple[np.ndarray, list[int]]:
        assert self.catalog is not None
        seed_indices = [
            self.track_to_index[track_id]
            for track_id in request.seed_track_ids
            if track_id in self.track_to_index
        ]
        if seed_indices:
            return self.catalog.features[seed_indices].mean(axis=0).astype(np.float32), seed_indices
        if request.mood:
            mood_label = MOOD_NAMES.index(request.mood)
            members = np.flatnonzero(
                self.catalog.frame["mood_label"].to_numpy(dtype=np.int64) == mood_label
            )
            return self.catalog.features[members].mean(axis=0).astype(np.float32), []
        return self.catalog.features.mean(axis=0).astype(np.float32), []

    @staticmethod
    def _context_vector(context: dict[str, Any]) -> np.ndarray:
        hour = context.get("hour", datetime.now(timezone.utc).hour)
        try:
            hour_value = float(hour) % 24.0
        except (TypeError, ValueError):
            hour_value = float(datetime.now(timezone.utc).hour)
        radians = hour_value / 24.0 * (2.0 * math.pi)
        return np.asarray([math.sin(radians), math.cos(radians)], dtype=np.float32)

    def _history_tensors(self, history_indices: list[int], batch_size: int) -> tuple[torch.Tensor, torch.Tensor]:
        assert self.item_embeddings is not None
        max_history = 20
        selected = history_indices[-max_history:]
        values = np.zeros((max_history, self.item_embeddings.shape[1]), dtype=np.float32)
        mask = np.zeros(max_history, dtype=bool)
        if selected:
            values[: len(selected)] = self.item_embeddings[selected]
            mask[: len(selected)] = True
        return (
            torch.from_numpy(np.repeat(values[None, :, :], batch_size, axis=0)),
            torch.from_numpy(np.repeat(mask[None, :], batch_size, axis=0)),
        )

    def _diversify(self, candidate_indices: list[int], scores: np.ndarray, limit: int) -> list[int]:
        assert self.item_embeddings is not None
        selected: list[int] = []
        remaining = list(range(len(candidate_indices)))
        score_min = float(scores.min()) if len(scores) else 0.0
        score_range = max(float(scores.max()) - score_min, 1e-8) if len(scores) else 1.0
        normalized_scores = (scores - score_min) / score_range
        while remaining and len(selected) < limit:
            best_position = remaining[0]
            best_value = float("-inf")
            for position in remaining:
                relevance = float(normalized_scores[position])
                if selected:
                    similarity = max(
                        float(
                            np.dot(
                                self.item_embeddings[candidate_indices[position]],
                                self.item_embeddings[candidate_indices[other]],
                            )
                        )
                        for other in selected
                    )
                else:
                    similarity = 0.0
                value = self.diversity_lambda * relevance - (1.0 - self.diversity_lambda) * similarity
                if value > best_value:
                    best_value = value
                    best_position = position
            selected.append(best_position)
            remaining.remove(best_position)
        return selected

    def recommend(self, request: RecommendationRequest, retrieval_candidates: int = 100) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError("recommender artifacts are not loaded")
        assert self.catalog is not None
        assert self.model is not None
        assert self.ranker is not None
        assert self.index is not None
        assert self.item_embeddings is not None

        with self.lock:
            state = self.users.get(request.user_id)
            if state:
                profile = state.profile.copy()
                history_indices = list(state.history_indices)
                excluded = set(state.excluded_indices)
                mode = "personalized"
            else:
                profile, history_indices = self._cold_start_profile(request)
                excluded = set(history_indices)
                mode = "content_cold_start"

        with torch.no_grad():
            user_embedding_tensor = self.model.user_embeddings(
                torch.from_numpy(profile.reshape(1, -1))
            )
        user_embedding = user_embedding_tensor.numpy().astype(np.float32)
        search_k = min(self.index.ntotal, max(retrieval_candidates + len(excluded), request.limit))
        retrieval_scores, retrieved = self.index.search(user_embedding, search_k)
        filtered: list[tuple[int, float, int]] = []
        for retrieval_rank, (item_index, score) in enumerate(
            zip(retrieved[0], retrieval_scores[0]), start=1
        ):
            item_index = int(item_index)
            if item_index < 0 or item_index in excluded:
                continue
            filtered.append((item_index, float(score), retrieval_rank))
            if len(filtered) >= retrieval_candidates:
                break
        if not filtered:
            return {"request_id": str(uuid.uuid4()), "tracks": [], "metadata": {"mode": mode}}

        candidate_indices = [item[0] for item in filtered]
        raw_retrieval_scores = np.asarray([item[1] for item in filtered], dtype=np.float32)
        candidate_embeddings = self.item_embeddings[candidate_indices]
        count = len(candidate_indices)
        history_tensor, history_mask = self._history_tensors(history_indices, count)
        context = np.repeat(self._context_vector(request.context)[None, :], count, axis=0)
        with torch.no_grad():
            ranker_logits_tensor, attention_weights_tensor = self.ranker.forward_with_attention(
                user_embedding_tensor.repeat(count, 1),
                history_tensor,
                history_mask,
                torch.from_numpy(candidate_embeddings),
                torch.from_numpy(context),
                torch.from_numpy(raw_retrieval_scores),
            )
            ranker_logits = ranker_logits_tensor.numpy()
            attention_weights = attention_weights_tensor.numpy()
        blended_scores = 0.75 * ranker_logits + 0.25 * raw_retrieval_scores
        sorted_positions = np.argsort(blended_scores)[::-1]
        sorted_indices = [candidate_indices[position] for position in sorted_positions]
        sorted_scores = blended_scores[sorted_positions]
        diverse_positions = self._diversify(sorted_indices, sorted_scores, request.limit)

        request_id = str(uuid.uuid4())
        tracks: list[dict[str, Any]] = []
        impression_rows: list[dict[str, Any]] = []
        for final_rank, sorted_position in enumerate(diverse_positions, start=1):
            item_index = sorted_indices[sorted_position]
            original_position = candidate_indices.index(item_index)
            row = self.catalog.frame.iloc[item_index]
            audio = {column: float(row[column]) for column in AUDIO_COLUMNS}
            attention_history: list[str] = []
            selected_history = history_indices[-20:]
            if selected_history:
                strongest = np.argsort(attention_weights[original_position, : len(selected_history)])[::-1][
                    :3
                ]
                attention_history = [
                    self.catalog.track_ids[selected_history[int(position)]] for position in strongest
                ]
            track = {
                "track_id": str(row["track_id"]),
                "score": float(sorted_scores[sorted_position]),
                "ranker_score": float(ranker_logits[original_position]),
                "retrieval_score": float(raw_retrieval_scores[original_position]),
                "retrieval_rank": int(filtered[original_position][2]),
                "final_rank": final_rank,
                "mood": MOOD_NAMES[int(row["mood_label"])],
                "audio_features": audio,
                "attention_history_track_ids": attention_history,
            }
            tracks.append(track)
            impression_rows.append(
                {
                    "request_id": request_id,
                    "user_id": request.user_id,
                    "track_id": track["track_id"],
                    "retrieval_rank": track["retrieval_rank"],
                    "retrieval_score": track["retrieval_score"],
                    "ranker_score": track["ranker_score"],
                    "final_rank": final_rank,
                    "final_score": track["score"],
                    "shown_at": datetime.now(timezone.utc).isoformat(),
                    "model_version": self.manifest.get("model_version"),
                    "catalog_version": self.manifest.get("catalog_version"),
                    "context": request.context,
                }
            )
        self._append_jsonl(self.event_dir / "impressions.jsonl", impression_rows)
        return {
            "request_id": request_id,
            "tracks": tracks,
            "metadata": {
                "mode": mode,
                "catalog_version": self.manifest.get("catalog_version"),
                "model_version": self.manifest.get("model_version"),
                "ranker_version": self.manifest.get("ranker_version"),
                "retrieval_candidates": len(filtered),
                "diversity_lambda": self.diversity_lambda,
            },
        }

    def record_interaction(self, request: InteractionRequest) -> int:
        if not self.ready or self.catalog is None:
            raise RuntimeError("recommender artifacts are not loaded")
        if request.track_id not in self.track_to_index:
            raise KeyError(request.track_id)
        item_index = self.track_to_index[request.track_id]
        weights = {"skip": -1.0, "continue": 1.0, "like": 3.0}
        weight = weights[request.interaction_type]
        with self.lock:
            state = self.users.get(request.user_id)
            if state is None:
                state = UserState(
                    profile=np.zeros(self.catalog.feature_dim, dtype=np.float32),
                    positive_weight=0.0,
                )
                self.users[request.user_id] = state
            if weight > 0:
                total_weight = state.positive_weight + weight
                state.profile = (
                    state.profile * state.positive_weight + self.catalog.features[item_index] * weight
                ) / max(total_weight, 1e-8)
                state.positive_weight = total_weight
                state.history_indices.append(item_index)
            state.excluded_indices.add(item_index)
            state.interaction_count += 1
            interaction_count = state.interaction_count

        event = request.model_dump(mode="json")
        event.update(
            {
                "score": int(weight),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "model_version": self.manifest.get("model_version"),
                "catalog_version": self.manifest.get("catalog_version"),
            }
        )
        self._append_jsonl(self.event_dir / "interactions.jsonl", [event])
        return interaction_count

    def _append_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
