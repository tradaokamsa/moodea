"""
Training Pipeline
Orchestrates model training: load labels, load features, build dataset,
train two-tower model, train reranker, build FAISS ANN index.
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from pymongo import MongoClient

# Local imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.common.feature_processor import create_user_feature_config, create_item_feature_config
from models.recommendation.models import TwoTowerModel, RerankerModel
from models.recommendation.trainer import TwoTowerTrainer, RerankerTrainer
from models.recommendation.dataset import RecommendationDataset, create_data_loader
from services.ann_index_service import ANNIndexService
from pipelines.user_feature_pipeline import UserFeaturePipeline
from pipelines.interaction_feature_pipeline import InteractionFeaturePipeline

logger = logging.getLogger(__name__)

# Paths
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


class TrainingPipeline:
    """Full training pipeline for the two-tower + reranker recommendation system."""

    def __init__(
        self,
        embedding_dim: int = 128,
        epochs: int = 10,
        batch_size: int = 256,
        learning_rate: float = 1e-3,
        loss_type: str = "in_batch",
        device: Optional[torch.device] = None,
    ):
        self.embedding_dim = embedding_dim
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.loss_type = loss_type
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")

        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo = MongoClient(mongodb_uri)
        self.db = self.mongo["moodea"]

        self.feast_path = _resolve_feast_path()
        self.model_dir = Path(MODEL_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load labels
    # ------------------------------------------------------------------

    def load_labels(self) -> pd.DataFrame:
        """Load interaction labels from MongoDB as a DataFrame."""
        interactions = list(self.db["interactions"].find(
            {},
            {"_id": 0, "user_id": 1, "track_id": 1, "score": 1, "timestamp": 1, "interaction_type": 1},
        ))
        if not interactions:
            raise ValueError("No interactions found in MongoDB")

        df = pd.DataFrame(interactions)
        df.rename(columns={"track_id": "item_id"}, inplace=True)
        logger.info(f"Loaded {len(df)} interaction labels")
        return df

    # ------------------------------------------------------------------
    # 2. Load / compute features
    # ------------------------------------------------------------------

    def load_features(self, labels: pd.DataFrame) -> Tuple[
        Dict[str, Dict[str, Any]],
        Dict[str, Dict[str, Any]],
    ]:
        """
        Load item features from Feast Parquet and user features from Parquet
        (computing them first if needed).

        Returns:
            (user_features_dict, item_features_dict)
            where each dict maps entity_id -> {feature_name: value}.
        """
        # --- Item features ---
        track_pq = self.feast_path / "data" / "parquet" / "track_features.parquet"
        if not track_pq.exists():
            raise FileNotFoundError(f"Track features parquet not found: {track_pq}")
        track_df = pd.read_parquet(track_pq)

        item_features: Dict[str, Dict[str, Any]] = {}
        for _, row in track_df.iterrows():
            tid = row["track_id"]
            feat: Dict[str, Any] = {}
            for af in AUDIO_FEATURES:
                feat[af] = np.float32(row.get(af, 0.0))
            feat["key"] = int(row.get("key", 0))
            feat["mode"] = int(row.get("mode", 0))
            feat["mood"] = int(row.get("mood", 0))
            item_features[tid] = feat

        # --- User features ---
        # Compute / refresh user features
        user_pipeline = UserFeaturePipeline()
        unique_users = labels["user_id"].unique().tolist()
        user_pipeline.compute(user_ids=unique_users)

        user_pq = self.feast_path / "data" / "parquet" / "user_features.parquet"
        if not user_pq.exists():
            raise FileNotFoundError(f"User features parquet not found: {user_pq}")
        user_df = pd.read_parquet(user_pq)

        # Build artist / genre vocabularies for multi-hot encoding
        all_artists: set = set()
        all_genres: set = set()
        for _, row in user_df.iterrows():
            artists = row.get("top_artists", [])
            genres = row.get("top_genres", [])
            if isinstance(artists, list):
                all_artists.update(artists)
            if isinstance(genres, list):
                all_genres.update(genres)
        artist_vocab = {a: i + 1 for i, a in enumerate(sorted(all_artists))}  # 0 = padding
        genre_vocab = {g: i + 1 for i, g in enumerate(sorted(all_genres))}

        user_features: Dict[str, Dict[str, Any]] = {}
        for _, row in user_df.iterrows():
            uid = row["user_id"]
            feat: Dict[str, Any] = {}

            feat["listening_pattern_score"] = np.float32(row.get("listening_pattern_score", 0.0))

            pref = row.get("preference_vector", [0.0] * 9)
            if isinstance(pref, list):
                feat["preference_vector"] = np.array(pref, dtype=np.float32)
            else:
                feat["preference_vector"] = np.zeros(9, dtype=np.float32)

            # Multi-hot encode artists (pad to 10)
            artists = row.get("top_artists", [])
            artist_ids = [artist_vocab.get(a, 0) for a in (artists if isinstance(artists, list) else [])]
            artist_ids = (artist_ids + [0] * 10)[:10]
            feat["top_artists"] = np.array(artist_ids, dtype=np.int64)

            genres = row.get("top_genres", [])
            genre_ids = [genre_vocab.get(g, 0) for g in (genres if isinstance(genres, list) else [])]
            genre_ids = (genre_ids + [0] * 10)[:10]
            feat["top_genres"] = np.array(genre_ids, dtype=np.int64)

            user_features[uid] = feat

        logger.info(f"Loaded features: {len(user_features)} users, {len(item_features)} items")
        return user_features, item_features

    # ------------------------------------------------------------------
    # 3. Build training dataset
    # ------------------------------------------------------------------

    def build_training_dataset(
        self,
        labels: pd.DataFrame,
        user_features: Dict[str, Dict[str, Any]],
        item_features: Dict[str, Dict[str, Any]],
    ) -> Tuple[RecommendationDataset, RecommendationDataset]:
        """Build train/val datasets with time-based 80/20 split."""
        labels = labels.sort_values("timestamp").reset_index(drop=True)
        split_idx = int(len(labels) * 0.8)
        train_labels = labels.iloc[:split_idx]
        val_labels = labels.iloc[split_idx:]

        train_ds = RecommendationDataset(
            user_features=user_features,
            item_features=item_features,
            interactions=train_labels,
            negative_sampling=True,
            num_negatives=1,
        )
        val_ds = RecommendationDataset(
            user_features=user_features,
            item_features=item_features,
            interactions=val_labels,
            negative_sampling=True,
            num_negatives=1,
        )
        logger.info(f"Dataset split: train={len(train_ds)}, val={len(val_ds)}")
        return train_ds, val_ds

    # ------------------------------------------------------------------
    # 4. Train retrieval model
    # ------------------------------------------------------------------

    def train_retrieval_model(
        self,
        train_ds: RecommendationDataset,
        val_ds: RecommendationDataset,
    ) -> TwoTowerModel:
        """Train the two-tower retrieval model."""
        user_config = create_user_feature_config()
        item_config = create_item_feature_config()

        model = TwoTowerModel(
            user_feature_config=user_config,
            item_feature_config=item_config,
            embedding_dim=self.embedding_dim,
        )

        trainer = TwoTowerTrainer(
            model=model,
            loss_type=self.loss_type,
            learning_rate=self.learning_rate,
            device=self.device,
        )

        train_loader = create_data_loader(train_ds, batch_size=self.batch_size, shuffle=True)
        val_loader = create_data_loader(val_ds, batch_size=self.batch_size, shuffle=False)

        save_path = str(self.model_dir / "two_tower_model.pt")
        trainer.train(
            train_loader=train_loader,
            val_loader=val_loader,
            num_epochs=self.epochs,
            save_path=save_path,
        )

        # Ensure we save even if validation was never best
        if not os.path.exists(save_path):
            torch.save(model.state_dict(), save_path)

        logger.info(f"Two-tower model saved to {save_path}")
        return model

    # ------------------------------------------------------------------
    # 5. Train reranker model
    # ------------------------------------------------------------------

    def train_reranker_model(
        self,
        retrieval_model: TwoTowerModel,
        train_ds: RecommendationDataset,
        val_ds: RecommendationDataset,
    ) -> RerankerModel:
        """Train the reranker model using embeddings from the retrieval model."""
        reranker = RerankerModel(embedding_dim=self.embedding_dim)
        trainer = RerankerTrainer(
            reranker=reranker,
            learning_rate=self.learning_rate,
            device=self.device,
            loss_type="mse",
        )

        # Generate embedding-based dataset for reranker
        retrieval_model.eval()
        retrieval_model.to(self.device)

        train_loader = create_data_loader(train_ds, batch_size=self.batch_size, shuffle=True)

        for epoch in range(self.epochs):
            reranker.train()
            total_loss = 0.0
            n_batches = 0

            for batch in train_loader:
                user_feats = {k: v.to(self.device) for k, v in batch["user_features"].items()}
                item_feats = {k: v.to(self.device) for k, v in batch["item_features"].items()}
                labels = batch["labels"].to(self.device)

                with torch.no_grad():
                    user_emb = retrieval_model.get_user_embedding(user_feats)
                    item_emb = retrieval_model.get_item_embedding(item_feats)

                predictions = reranker(user_emb, item_emb)
                loss = torch.nn.MSELoss()(predictions, labels)

                trainer.optimizer.zero_grad()
                loss.backward()
                trainer.optimizer.step()

                total_loss += loss.item()
                n_batches += 1

            avg_loss = total_loss / max(n_batches, 1)
            logger.info(f"Reranker epoch {epoch + 1}/{self.epochs} - loss: {avg_loss:.4f}")

        save_path = str(self.model_dir / "reranker_model.pt")
        torch.save(reranker.state_dict(), save_path)
        logger.info(f"Reranker model saved to {save_path}")
        return reranker

    # ------------------------------------------------------------------
    # 6. Build ANN index
    # ------------------------------------------------------------------

    def build_ann_index(
        self,
        retrieval_model: TwoTowerModel,
        item_features: Dict[str, Dict[str, Any]],
    ) -> ANNIndexService:
        """Generate item embeddings and build FAISS ANN index."""
        retrieval_model.eval()
        retrieval_model.to(self.device)

        track_ids = list(item_features.keys())
        all_embeddings = []

        # Process in batches
        batch_size = 512
        for i in range(0, len(track_ids), batch_size):
            batch_ids = track_ids[i : i + batch_size]
            # Build feature tensors
            batch_feats: Dict[str, list] = {}
            for tid in batch_ids:
                feats = item_features[tid]
                for k, v in feats.items():
                    batch_feats.setdefault(k, []).append(v)

            tensor_feats = {}
            for k, vals in batch_feats.items():
                if isinstance(vals[0], np.ndarray):
                    tensor_feats[k] = torch.tensor(np.stack(vals)).to(self.device)
                else:
                    tensor_feats[k] = torch.tensor(vals).to(self.device)

            with torch.no_grad():
                embs = retrieval_model.get_item_embedding(tensor_feats)
            all_embeddings.append(embs.cpu().numpy())

        embeddings = np.concatenate(all_embeddings, axis=0)

        ann_service = ANNIndexService(
            index_path=str(self.data_dir / "ann_index.bin")
        )
        ann_service.build_index(track_ids, embeddings)
        ann_service.save_index()
        logger.info(f"ANN index built and saved ({len(track_ids)} tracks)")
        return ann_service

    # ------------------------------------------------------------------
    # 7. Run full pipeline
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Execute the full training pipeline."""
        logger.info("=== Starting Training Pipeline ===")

        # Compute interaction features first
        logger.info("Step 0: Computing interaction features...")
        InteractionFeaturePipeline().compute()

        # 1. Load labels
        logger.info("Step 1: Loading labels...")
        labels = self.load_labels()

        # 2. Load features
        logger.info("Step 2: Loading features...")
        user_features, item_features = self.load_features(labels)

        # 3. Build dataset
        logger.info("Step 3: Building datasets...")
        train_ds, val_ds = self.build_training_dataset(labels, user_features, item_features)

        # 4. Train retrieval model
        logger.info("Step 4: Training two-tower retrieval model...")
        retrieval_model = self.train_retrieval_model(train_ds, val_ds)

        # 5. Train reranker
        logger.info("Step 5: Training reranker model...")
        reranker_model = self.train_reranker_model(retrieval_model, train_ds, val_ds)

        # 6. Build ANN index
        logger.info("Step 6: Building ANN index...")
        ann_service = self.build_ann_index(retrieval_model, item_features)

        logger.info("=== Training Pipeline Complete ===")
        return {
            "labels_count": len(labels),
            "users_count": len(user_features),
            "items_count": len(item_features),
            "train_size": len(train_ds),
            "val_size": len(val_ds),
            "ann_index_size": ann_service.index.ntotal if ann_service.index else 0,
            "model_dir": str(self.model_dir),
            "timestamp": datetime.utcnow().isoformat(),
        }
