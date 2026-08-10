"""
Inference Pipeline
Low-latency recommendation inference using trained models and FAISS ANN index.

Target latency: <50ms for the complete inference path.
  - Redis / Parquet feature fetch  ~1ms
  - User embedding generation      ~1ms
  - FAISS ANN query                ~1ms
  - Reranker batch inference       ~5ms
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from pymongo import MongoClient

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.common.feature_processor import create_user_feature_config, create_item_feature_config
from models.recommendation.models import TwoTowerModel, RerankerModel
from services.ann_index_service import ANNIndexService

logger = logging.getLogger(__name__)

MODEL_DIR = os.getenv("MODEL_DIR", "./models/recommendation")
DATA_DIR = os.getenv("DATA_DIR", "./data")
FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "./feast")

AUDIO_FEATURES = [
    "danceability", "energy", "valence", "tempo", "acousticness",
    "instrumentalness", "liveness", "loudness", "speechiness",
]


def _resolve_feast_path() -> Path:
    repo = FEAST_REPO_PATH
    if not os.path.isabs(repo):
        if repo.startswith("./"):
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            repo = os.path.join(project_root, repo[2:])
        else:
            repo = os.path.abspath(repo)
    return Path(repo)


class InferencePipeline:
    """
    Low-latency inference pipeline for neural recommendations.

    Loads models and FAISS index at startup, then serves recommendations
    via get_recommendations().
    """

    def __init__(self):
        self.device = torch.device("cpu")  # CPU for low-latency single-request inference
        self.feast_path = _resolve_feast_path()
        self.model_dir = Path(MODEL_DIR)
        self.data_dir = Path(DATA_DIR)

        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo = MongoClient(mongodb_uri)
        self.db = self.mongo["moodea"]

        # Models (loaded lazily)
        self.two_tower: Optional[TwoTowerModel] = None
        self.reranker: Optional[RerankerModel] = None
        self.ann_service: Optional[ANNIndexService] = None

        # Caches
        self._user_features_cache: Dict[str, Dict[str, Any]] = {}
        self._item_features_cache: Dict[str, Dict[str, Any]] = {}

        self._load_models()
        self._load_item_features()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _load_models(self):
        """Load trained models and ANN index."""
        user_config = create_user_feature_config()
        item_config = create_item_feature_config()

        # Two-tower model
        tt_path = self.model_dir / "two_tower_model.pt"
        if tt_path.exists():
            self.two_tower = TwoTowerModel(
                user_feature_config=user_config,
                item_feature_config=item_config,
                embedding_dim=128,
            )
            self.two_tower.load_state_dict(torch.load(str(tt_path), map_location=self.device))
            self.two_tower.eval()
            logger.info("Two-tower model loaded")
        else:
            logger.warning(f"Two-tower model not found at {tt_path}")

        # Reranker model
        rr_path = self.model_dir / "reranker_model.pt"
        if rr_path.exists():
            self.reranker = RerankerModel(embedding_dim=128)
            self.reranker.load_state_dict(torch.load(str(rr_path), map_location=self.device))
            self.reranker.eval()
            logger.info("Reranker model loaded")
        else:
            logger.warning(f"Reranker model not found at {rr_path}")

        # ANN index
        ann_path = str(self.data_dir / "ann_index.bin")
        self.ann_service = ANNIndexService(index_path=ann_path)
        if self.ann_service.is_ready:
            logger.info(f"ANN index loaded ({self.ann_service.index.ntotal} tracks)")
        else:
            logger.warning("ANN index not available")

    def _load_item_features(self):
        """Pre-load item features for reranking."""
        track_pq = self.feast_path / "data" / "parquet" / "track_features.parquet"
        if not track_pq.exists():
            return
        df = pd.read_parquet(track_pq)
        for _, row in df.iterrows():
            tid = row["track_id"]
            feat: Dict[str, Any] = {}
            for af in AUDIO_FEATURES:
                feat[af] = np.float32(row.get(af, 0.0))
            feat["key"] = int(row.get("key", 0))
            feat["mode"] = int(row.get("mode", 0))
            feat["mood"] = int(row.get("mood", 0))
            self._item_features_cache[tid] = feat

    @property
    def is_ready(self) -> bool:
        return (
            self.two_tower is not None
            and self.ann_service is not None
            and self.ann_service.is_ready
        )

    def reload_models(self):
        """Hot-reload models (e.g. after retraining)."""
        self._load_models()
        self._load_item_features()

    # ------------------------------------------------------------------
    # 1. Get user features
    # ------------------------------------------------------------------

    def get_user_features(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user features. Tries Feast Parquet first, falls back to
        computing from MongoDB interactions.
        """
        # Try Parquet cache
        user_pq = self.feast_path / "data" / "parquet" / "user_features.parquet"
        if user_pq.exists():
            df = pd.read_parquet(user_pq)
            row = df[df["user_id"] == user_id]
            if not row.empty:
                r = row.iloc[0]
                feat: Dict[str, Any] = {}
                feat["listening_pattern_score"] = np.float32(r.get("listening_pattern_score", 0.0))
                pref = r.get("preference_vector", [0.0] * 9)
                feat["preference_vector"] = np.array(pref if isinstance(pref, list) else [0.0] * 9, dtype=np.float32)
                # Pad multi-hot to 10
                artists = r.get("top_artists", [])
                feat["top_artists"] = np.zeros(10, dtype=np.int64)
                genres = r.get("top_genres", [])
                feat["top_genres"] = np.zeros(10, dtype=np.int64)
                return feat

        # Fallback: compute on-the-fly from interactions
        return self._compute_user_features_fallback(user_id)

    def _compute_user_features_fallback(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Minimal user feature computation from MongoDB for cold-start."""
        interactions = list(self.db["interactions"].find({"user_id": user_id}))
        track_pq = self.feast_path / "data" / "parquet" / "track_features.parquet"
        if not track_pq.exists():
            return None

        df = pd.read_parquet(track_pq)
        track_lookup = {}
        for _, row in df.iterrows():
            track_lookup[row["track_id"]] = np.array(
                [row.get(f, 0.0) for f in AUDIO_FEATURES], dtype=np.float64
            )

        score_weights = {"like": 3.0, "continue": 1.0, "skip": -1.0}
        weighted_sum = np.zeros(len(AUDIO_FEATURES), dtype=np.float64)
        total_weight = 0.0
        positive_count = 0

        for inter in interactions:
            itype = inter.get("interaction_type", "")
            weight = score_weights.get(itype, 0.0)
            if weight > 0:
                positive_count += 1
            track = track_lookup.get(inter.get("track_id"))
            if track is not None and weight > 0:
                weighted_sum += weight * track
                total_weight += weight

        if total_weight > 0:
            pref_vec = (weighted_sum / total_weight).astype(np.float32)
        else:
            # Use discovered tracks
            discovered = list(
                self.db["track_candidates"].find({"user_id": user_id}, {"track_id": 1}).limit(50)
            )
            vecs = [track_lookup[d["track_id"]] for d in discovered if d.get("track_id") in track_lookup]
            pref_vec = np.mean(vecs, axis=0).astype(np.float32) if vecs else np.zeros(9, dtype=np.float32)

        total = max(len(interactions), 1)
        return {
            "listening_pattern_score": np.float32(positive_count / total),
            "preference_vector": pref_vec,
            "top_artists": np.zeros(10, dtype=np.int64),
            "top_genres": np.zeros(10, dtype=np.int64),
        }

    # ------------------------------------------------------------------
    # 2. Generate user embedding
    # ------------------------------------------------------------------

    def generate_user_embedding(self, user_features: Dict[str, Any]) -> np.ndarray:
        """Forward pass through user tower. Returns 1-D embedding."""
        tensor_feats = {}
        for k, v in user_features.items():
            t = torch.tensor(v) if not isinstance(v, torch.Tensor) else v
            tensor_feats[k] = t.unsqueeze(0)  # add batch dim

        with torch.no_grad():
            emb = self.two_tower.get_user_embedding(tensor_feats)
        return emb.squeeze(0).numpy()

    # ------------------------------------------------------------------
    # 3. Retrieve candidates
    # ------------------------------------------------------------------

    def retrieve_candidates(self, user_embedding: np.ndarray, k: int = 100) -> List[Tuple[str, float]]:
        """FAISS ANN query for top-k candidate tracks."""
        return self.ann_service.query(user_embedding, k=k)

    # ------------------------------------------------------------------
    # 4. Rerank candidates
    # ------------------------------------------------------------------

    def rerank_candidates(
        self,
        user_embedding: np.ndarray,
        candidates: List[Tuple[str, float]],
        k: int = 20,
    ) -> List[Tuple[str, float]]:
        """Score candidates with reranker and return top-k."""
        if self.reranker is None or not candidates:
            return candidates[:k]

        user_emb_tensor = torch.tensor(user_embedding, dtype=torch.float32).unsqueeze(0)

        # Build item embedding batch from cached features
        valid_candidates = []
        item_feat_list: Dict[str, list] = {}
        for tid, score in candidates:
            feats = self._item_features_cache.get(tid)
            if feats is None:
                continue
            valid_candidates.append((tid, score))
            for key, val in feats.items():
                item_feat_list.setdefault(key, []).append(val)

        if not valid_candidates:
            return candidates[:k]

        # Build item embeddings via item tower
        tensor_feats = {}
        for key, vals in item_feat_list.items():
            if isinstance(vals[0], np.ndarray):
                tensor_feats[key] = torch.tensor(np.stack(vals))
            else:
                tensor_feats[key] = torch.tensor(vals)

        with torch.no_grad():
            item_embs = self.two_tower.get_item_embedding(tensor_feats)
            user_emb_batch = user_emb_tensor.expand(item_embs.shape[0], -1)
            rerank_scores = self.reranker(user_emb_batch, item_embs).numpy()

        # Combine retrieval score and reranker score
        scored = []
        for i, (tid, retrieval_score) in enumerate(valid_candidates):
            combined = 0.7 * float(rerank_scores[i]) + 0.3 * retrieval_score
            scored.append((tid, combined))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    # ------------------------------------------------------------------
    # 5. Full pipeline
    # ------------------------------------------------------------------

    def get_recommendations(
        self,
        user_id: str,
        limit: int = 20,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get personalized neural recommendations for a user.

        Full pipeline: features -> embedding -> ANN -> rerank -> result.
        """
        if not self.is_ready:
            return {
                "track_ids": [],
                "scores": [],
                "metadata": {"message": "Neural inference pipeline not ready (models not loaded)"},
            }

        # 1. Get user features
        user_features = self.get_user_features(user_id)
        if user_features is None:
            return {
                "track_ids": [],
                "scores": [],
                "metadata": {"message": "No features available for user"},
            }

        # 2. Generate user embedding
        user_embedding = self.generate_user_embedding(user_features)

        # 3. Retrieve candidates
        candidates = self.retrieve_candidates(user_embedding, k=100)
        if not candidates:
            return {
                "track_ids": [],
                "scores": [],
                "metadata": {"message": "No candidates found in ANN index"},
            }

        # 4. Rerank
        reranked = self.rerank_candidates(user_embedding, candidates, k=limit)

        # 5. Exclude already-interacted tracks
        interacted = set()
        for inter in self.db["interactions"].find({"user_id": user_id}, {"track_id": 1}):
            interacted.add(inter.get("track_id"))

        final = [(tid, score) for tid, score in reranked if tid not in interacted][:limit]

        return {
            "track_ids": [tid for tid, _ in final],
            "scores": [score for _, score in final],
            "metadata": {
                "method": "neural_two_tower",
                "candidates_retrieved": len(candidates),
                "reranked": len(reranked),
                "excluded_interacted": len(interacted),
            },
        }
