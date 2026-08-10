"""
Feast Client Wrapper
Provides convenient interface for interacting with Feast feature store
"""
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from feast import FeatureStore
import pandas as pd


class FeastClient:
    """
    Wrapper for Feast feature store operations
    """
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize Feast client
        
        Args:
            repo_path: Path to Feast repository
        """
        self.repo_path = repo_path or os.getenv("FEAST_REPO_PATH", "./feast")
        
        # Resolve to absolute path if relative
        if not os.path.isabs(self.repo_path):
            # Try to resolve relative to project root
            # Option 1: If FEAST_REPO_PATH starts with ./, resolve from project root
            if self.repo_path.startswith("./"):
                # Get project root (assuming this is 4 levels up from this file)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                self.repo_path = os.path.join(project_root, self.repo_path[2:])  # Remove "./"
            else:
                # Already relative path without ./, resolve from current working directory
                self.repo_path = os.path.abspath(self.repo_path)

        self.store = FeatureStore(repo_path=self.repo_path)
    
    def get_online_features(self, entity_ids: List[str], feature_view: str, features: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Retrieve features from online store (Redis)
        
        Args:
            entity_ids: List of entity IDs (e.g., user_ids or track_ids)
            feature_view: Name of feature view
            features: Optional list of specific features to retrieve
        
        Returns:
            Dict mapping entity_id to feature dict
        """
        from feast import EntityKey
        from feast import Value

        # Build entity keys
        entity_keys = [
            EntityKey(entity_name=feature_view.split("_")[0] + "_id", entity_value=Value(string_value=eid))
            for eid in entity_ids
        ]

        # Get feature view
        fv = self.store.get_feature_view(feature_view)

        # Retrieve features
        online_features = self.store.get_online_features(
            features=[f"{feature_view}:{feat}" for feat in (features or [])],
            entity_rows=[{"user_id": eid} for eid in entity_ids]
        )

        # Format response
        result = {}
        for i, eid in enumerate(entity_ids):
            result[eid] = {
                feat: online_features.to_dict()[f"{feature_view}:{feat}"][i]
                for feat in (features or [])
            }
        return result
    
    def get_offline_features(self, entity_ids: List[str], feature_view: str, timestamp: Optional[datetime] = None) -> Any:
        """
        Retrieve features from offline store (Parquet)
        
        Args:
            entity_ids: List of entity IDs
            feature_view: Name of feature view
            timestamp: Optional timestamp for point-in-time features
        
        Returns:
            DataFrame with features
        """
        # Create entity dataframe
        entity_df = pd.DataFrame({
            f"{feature_view.split('_')[0]}_id": entity_ids
        })
        if timestamp:
            entity_df["event_timestamp"] = timestamp
        else:
            entity_df["event_timestamp"] = pd.Timestamp.now()

        # Get historical features
        training_df = self.store.get_historical_features(
            entity_df=entity_df,
            features=[f"{feature_view}:*"]
        )
        return training_df.to_df()
    
    def write_track_features(self, track_features: List[Dict[str, Any]]):
        """
        Write track features to Feast offline store
        
        Args:
            track_features: List of track feature dicts
        """
        # Convert to DataFrame
        df = pd.DataFrame(track_features)

        # Ensure required columns
        required_cols = ["track_id", "event_timestamp"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Add created_at if missing
        if "created_at" not in df.columns:
            df["created_at"] = pd.Timestamp.now()

        # Ensure event_timestamp is int64
        if "event_timestamp" in df.columns:
            df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], unit="s")

        # Write to Parquet
        parquet_path = Path(self.repo_path) / "data" / "parquet" / "track_features.parquet"
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        # Append or overwrite based on existing file
        if parquet_path.exists():
            existing_df = pd.read_parquet(parquet_path)
            df = pd.concat([existing_df, df]).drop_duplicates(subset=["track_id"], keep="last").reset_index(drop=True)
        df.to_parquet(parquet_path, index=False)
    
    def materialize_features(self, feature_view: str, start_date: datetime, end_date: datetime):
        """
        Materialize features from offline to online store
        
        Args:
            feature_view: Name of feature view
            start_date: Start date for materialization
            end_date: End date for materialization
        """
        # Materialize features
        self.store.materialize(
            start_date=start_date,
            end_date=end_date,
            feature_views=[feature_view]
        )

