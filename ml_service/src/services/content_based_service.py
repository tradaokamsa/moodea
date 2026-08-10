"""
Content-Based Recommendation Service
Uses audio feature similarity and mood matching for recommendations.
No model training required - works immediately with promoted tracks.
"""
import os
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pymongo import MongoClient
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity


class ContentBasedService:
    """
    Content-based recommendation using audio features + mood.

    Builds a feature matrix from promoted tracks in Feast Parquet,
    computes user profile vectors from interaction history,
    and ranks candidates by cosine similarity.
    """

    AUDIO_FEATURES = [
        "danceability", "energy", "valence", "tempo",
        "acousticness", "instrumentalness", "liveness",
        "loudness", "speechiness",
    ]
    NUM_MOODS = 4  # 0=sad, 1=happy, 2=energetic, 3=calm
    SCORE_WEIGHTS = {"like": 3.0, "continue": 1.0, "skip": -1.0}

    def __init__(self):
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo_client = MongoClient(mongodb_uri)
        self.db = self.mongo_client["moodea"]
        self.interactions_collection = self.db["interactions"]
        self.track_candidates_collection = self.db["track_candidates"]

        feast_repo_path = os.getenv("FEAST_REPO_PATH", "./feast")
        if not os.path.isabs(feast_repo_path):
            if feast_repo_path.startswith("./"):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
                feast_repo_path = os.path.join(project_root, feast_repo_path[2:])
            else:
                feast_repo_path = os.path.abspath(feast_repo_path)

        self.parquet_path = Path(feast_repo_path) / "data" / "parquet" / "track_features.parquet"

        # In-memory state (rebuilt on load)
        self.track_df: Optional[pd.DataFrame] = None
        self.feature_matrix: Optional[np.ndarray] = None
        self.scaler: Optional[StandardScaler] = None
        self.track_ids: List[str] = []

        self._load_tracks()

    # ------------------------------------------------------------------
    # Track loading & feature matrix
    # ------------------------------------------------------------------

    def _load_tracks(self):
        """Load promoted tracks from Feast Parquet and build feature matrix."""
        if not self.parquet_path.exists():
            print(f"Warning: Track features parquet not found at {self.parquet_path}")
            return

        df = pd.read_parquet(self.parquet_path)
        if df.empty:
            print("Warning: Track features parquet is empty")
            return

        # Ensure audio feature columns exist
        missing = [f for f in self.AUDIO_FEATURES if f not in df.columns]
        if missing:
            print(f"Warning: Missing audio feature columns: {missing}")
            return

        self.track_df = df.copy()
        self.track_ids = df["track_id"].tolist()

        # Build raw feature matrix: audio features + mood one-hot
        audio_matrix = df[self.AUDIO_FEATURES].fillna(0.0).values.astype(np.float64)

        mood_col = df["mood"].fillna(0).astype(int).values
        mood_onehot = np.zeros((len(df), self.NUM_MOODS), dtype=np.float64)
        for i, m in enumerate(mood_col):
            if 0 <= m < self.NUM_MOODS:
                mood_onehot[i, m] = 1.0

        raw_matrix = np.hstack([audio_matrix, mood_onehot])

        # Normalize
        self.scaler = StandardScaler()
        self.feature_matrix = self.scaler.fit_transform(raw_matrix)

        print(f"ContentBasedService loaded {len(self.track_ids)} tracks ({raw_matrix.shape[1]}-dim features)")

    def reload_tracks(self):
        """Reload tracks from Parquet (e.g., after new promotions)."""
        self._load_tracks()

    # ------------------------------------------------------------------
    # User profile
    # ------------------------------------------------------------------

    def _build_user_profile(self, user_id: str) -> Optional[np.ndarray]:
        """
        Build a user profile vector from interaction history.

        Falls back to discovered tracks if no interactions exist.
        Returns a normalized feature vector in the same space as the
        track feature matrix, or None if no signal at all.
        """
        if self.feature_matrix is None or len(self.track_ids) == 0:
            return None

        track_id_to_idx = {tid: i for i, tid in enumerate(self.track_ids)}

        # ---- Try interactions first ----
        interactions = list(
            self.interactions_collection.find({"user_id": user_id})
        )

        if interactions:
            weighted_sum = np.zeros(self.feature_matrix.shape[1], dtype=np.float64)
            total_weight = 0.0

            for inter in interactions:
                tid = inter.get("track_id")
                itype = inter.get("interaction_type", "")
                weight = self.SCORE_WEIGHTS.get(itype, 0.0)
                if weight <= 0:
                    continue  # skip negative interactions for profile building
                idx = track_id_to_idx.get(tid)
                if idx is not None:
                    weighted_sum += weight * self.feature_matrix[idx]
                    total_weight += weight

            if total_weight > 0:
                return weighted_sum / total_weight

        # ---- Cold-start fallback: use user's discovered tracks ----
        discovered = list(
            self.track_candidates_collection.find(
                {"user_id": user_id},
                {"track_id": 1},
            ).limit(50)
        )

        if discovered:
            vectors = []
            for doc in discovered:
                idx = track_id_to_idx.get(doc.get("track_id"))
                if idx is not None:
                    vectors.append(self.feature_matrix[idx])
            if vectors:
                return np.mean(vectors, axis=0)

        return None

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def get_recommendations(
        self,
        user_id: str,
        limit: int = 20,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get content-based recommendations for a user.

        Returns:
            Dict with track_ids, scores, metadata
        """
        if self.feature_matrix is None or len(self.track_ids) == 0:
            return {
                "track_ids": [],
                "scores": [],
                "metadata": {"message": "No tracks available for recommendation"},
            }

        user_profile = self._build_user_profile(user_id)
        if user_profile is None:
            return {
                "track_ids": [],
                "scores": [],
                "metadata": {"message": "No user signal available (no interactions or discovered tracks)"},
            }

        # Compute cosine similarity between user profile and all tracks
        similarities = cosine_similarity(
            user_profile.reshape(1, -1), self.feature_matrix
        )[0]

        # Exclude already-interacted tracks
        interacted_ids = set()
        interactions = self.interactions_collection.find(
            {"user_id": user_id}, {"track_id": 1}
        )
        for inter in interactions:
            interacted_ids.add(inter.get("track_id"))

        # Build candidate list excluding interacted
        candidates: List[Tuple[int, float]] = []
        for i, sim in enumerate(similarities):
            if self.track_ids[i] not in interacted_ids:
                candidates.append((i, float(sim)))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_k = candidates[:limit]

        result_track_ids = [self.track_ids[i] for i, _ in top_k]
        result_scores = [score for _, score in top_k]

        return {
            "track_ids": result_track_ids,
            "scores": result_scores,
            "metadata": {
                "method": "content_based",
                "total_tracks": len(self.track_ids),
                "excluded_interacted": len(interacted_ids),
            },
        }
