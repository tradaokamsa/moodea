"""
Interaction Feature Aggregation Pipeline

Aggregates raw interactions from MongoDB into per-(user_id, track_id) features
and writes to Feast interaction_features Parquet.
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pymongo import MongoClient

logger = logging.getLogger(__name__)

SCORE_MAP = {"like": 3, "continue": 1, "skip": -1}


class InteractionFeaturePipeline:
    """Aggregate raw interactions per (user, track) and write to Parquet."""

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
        self.parquet_path = Path(feast_repo) / "data" / "parquet" / "interaction_features.parquet"

    def compute(self, user_ids: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Compute interaction features.

        For each (user_id, track_id) pair: total_score, interaction_count,
        last_interaction_score, recency_score.
        """
        query = {}
        if user_ids:
            query["user_id"] = {"$in": user_ids}

        interactions = list(self.db["interactions"].find(query))
        if not interactions:
            logger.warning("No interactions found")
            return pd.DataFrame()

        now_ts = datetime.utcnow().timestamp()

        # Group by (user_id, track_id)
        groups: dict = {}
        for inter in interactions:
            key = (inter["user_id"], inter["track_id"])
            groups.setdefault(key, []).append(inter)

        rows = []
        for (uid, tid), inters in groups.items():
            scores = [SCORE_MAP.get(i.get("interaction_type", ""), 0) for i in inters]
            timestamps = [i.get("timestamp", 0) for i in inters]

            total_score = float(sum(scores))
            interaction_count = len(inters)
            last_ts = max(timestamps) if timestamps else 0
            last_interaction_score = float(scores[timestamps.index(last_ts)]) if timestamps else 0.0

            # Recency score: exponential decay based on hours since last interaction
            hours_since = (now_ts - last_ts) / 3600.0 if last_ts > 0 else 999.0
            recency_score = float(2.0 ** (-hours_since / 168.0))  # half-life = 1 week

            rows.append({
                "user_id": uid,
                "track_id": tid,
                "total_score": total_score,
                "interaction_count": interaction_count,
                "last_interaction_score": last_interaction_score,
                "recency_score": recency_score,
                "event_timestamp": int(now_ts),
                "created_at": datetime.utcnow(),
            })

        df = pd.DataFrame(rows)

        # Write to Parquet
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        if self.parquet_path.exists():
            existing = pd.read_parquet(self.parquet_path)
            df = pd.concat([existing, df]).drop_duplicates(
                subset=["user_id", "track_id"], keep="last"
            ).reset_index(drop=True)

        df.to_parquet(self.parquet_path, index=False)
        logger.info(f"Wrote interaction features for {len(rows)} pairs to {self.parquet_path}")
        return df
