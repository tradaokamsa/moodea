"""
User Feature Computation Pipeline

Reads interactions + track_candidates from MongoDB, computes per-user features
(top_artists, top_genres, listening_pattern_score, preference_vector) and writes
them to the Feast user_features Parquet file.
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pymongo import MongoClient

logger = logging.getLogger(__name__)

AUDIO_FEATURES = [
    "danceability", "energy", "valence", "tempo", "acousticness",
    "instrumentalness", "liveness", "loudness", "speechiness",
]

SCORE_WEIGHTS = {"like": 3.0, "continue": 1.0, "skip": -1.0}


class UserFeaturePipeline:
    """Compute user-level features from MongoDB and write to Parquet."""

    def __init__(self):
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo = MongoClient(mongodb_uri)
        self.db = self.mongo["moodea"]

        feast_repo = os.getenv("FEAST_REPO_PATH", "./feast")
        if not os.path.isabs(feast_repo):
            if feast_repo.startswith("./"):
                project_root = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
                feast_repo = os.path.join(project_root, feast_repo[2:])
            else:
                feast_repo = os.path.abspath(feast_repo)
        self.parquet_path = Path(feast_repo) / "data" / "parquet" / "user_features.parquet"
        self.track_parquet_path = Path(feast_repo) / "data" / "parquet" / "track_features.parquet"

    def _load_track_features(self) -> Dict[str, Dict]:
        """Load track features from Parquet into a lookup dict."""
        if not self.track_parquet_path.exists():
            return {}
        df = pd.read_parquet(self.track_parquet_path)
        result: Dict[str, Dict] = {}
        for _, row in df.iterrows():
            tid = row["track_id"]
            result[tid] = {
                "audio": np.array([row.get(f, 0.0) for f in AUDIO_FEATURES], dtype=np.float64),
                "artists": str(row.get("artists", "")),
                "mood": int(row.get("mood", 0)),
            }
        return result

    def compute(self, user_ids: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Compute user features for the given user IDs (or all users with interactions).

        Returns the resulting DataFrame and writes it to Parquet.
        """
        track_lookup = self._load_track_features()
        if not track_lookup:
            logger.warning("No track features found; cannot compute user features")
            return pd.DataFrame()

        # Determine user IDs
        if user_ids is None:
            user_ids = self.db["interactions"].distinct("user_id")
            # Also include users who have track_candidates but no interactions
            candidate_users = self.db["track_candidates"].distinct("user_id")
            user_ids = list(set(user_ids) | set(candidate_users))

        rows = []
        now_ts = int(datetime.utcnow().timestamp())

        for uid in user_ids:
            interactions = list(self.db["interactions"].find({"user_id": uid}))

            # --- preference_vector (9-dim weighted avg of audio features) ---
            weighted_sum = np.zeros(len(AUDIO_FEATURES), dtype=np.float64)
            total_weight = 0.0
            artist_counts: Dict[str, float] = {}
            genre_set: set = set()

            for inter in interactions:
                tid = inter.get("track_id")
                itype = inter.get("interaction_type", "")
                weight = SCORE_WEIGHTS.get(itype, 0.0)
                track = track_lookup.get(tid)
                if track is None:
                    continue

                if weight > 0:
                    weighted_sum += weight * track["audio"]
                    total_weight += weight

                # artist frequency (use absolute weight)
                artist_str = track["artists"]
                for artist in artist_str.split(", "):
                    artist = artist.strip()
                    if artist:
                        artist_counts[artist] = artist_counts.get(artist, 0) + abs(weight)

            if total_weight > 0:
                preference_vector = (weighted_sum / total_weight).tolist()
            else:
                # Fallback: average of user's discovered tracks
                discovered = list(
                    self.db["track_candidates"].find({"user_id": uid}, {"track_id": 1}).limit(50)
                )
                vecs = []
                for doc in discovered:
                    track = track_lookup.get(doc.get("track_id"))
                    if track is not None:
                        vecs.append(track["audio"])
                preference_vector = np.mean(vecs, axis=0).tolist() if vecs else [0.0] * len(AUDIO_FEATURES)

            # --- top_artists (top 10 by weighted interaction count) ---
            sorted_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)
            top_artists = [a for a, _ in sorted_artists[:10]]

            # --- top_genres: we don't have genre in Feast yet, use mood distribution as proxy ---
            top_genres = list(genre_set)[:10] if genre_set else []

            # --- listening_pattern_score ---
            positive_count = sum(1 for i in interactions if SCORE_WEIGHTS.get(i.get("interaction_type", ""), 0) > 0)
            total_count = len(interactions) if interactions else 1
            listening_pattern_score = float(positive_count) / float(total_count)

            rows.append({
                "user_id": uid,
                "top_artists": top_artists,
                "top_genres": top_genres,
                "listening_pattern_score": listening_pattern_score,
                "preference_vector": preference_vector,
                "event_timestamp": now_ts,
                "created_at": datetime.utcnow(),
            })

        df = pd.DataFrame(rows)
        if df.empty:
            logger.warning("No user features computed")
            return df

        # Write to Parquet (overwrite per user, merge with existing)
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        if self.parquet_path.exists():
            existing = pd.read_parquet(self.parquet_path)
            df = pd.concat([existing, df]).drop_duplicates(subset=["user_id"], keep="last").reset_index(drop=True)

        df.to_parquet(self.parquet_path, index=False)
        logger.info(f"Wrote user features for {len(rows)} users to {self.parquet_path}")
        return df
