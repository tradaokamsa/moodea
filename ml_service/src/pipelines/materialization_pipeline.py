"""
Materialization Pipeline
Materializes user_features and interaction_features from Parquet to Redis
via Feast online store.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "./feast")


def _resolve_feast_path() -> str:
    repo = FEAST_REPO_PATH
    if not os.path.isabs(repo):
        if repo.startswith("./"):
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            repo = os.path.join(project_root, repo[2:])
        else:
            repo = os.path.abspath(repo)
    return repo


class MaterializationPipeline:
    """
    Materialize features from Parquet (offline) to Redis (online).

    Only user_features and interaction_features have online=True;
    track_features stays offline-only.
    """

    def __init__(self):
        self.repo_path = _resolve_feast_path()

    def materialize(
        self,
        feature_views: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Materialize features to Redis online store.

        Args:
            feature_views: Views to materialize (default: user_features, interaction_features)
            start_date: Start of materialization window (default: 90 days ago)
            end_date: End of materialization window (default: now)

        Returns:
            Summary dict.
        """
        from feast import FeatureStore

        store = FeatureStore(repo_path=self.repo_path)

        if feature_views is None:
            feature_views = ["user_features", "interaction_features"]

        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        results = {}
        for fv_name in feature_views:
            try:
                store.materialize(
                    start_date=start_date,
                    end_date=end_date,
                    feature_views=[fv_name],
                )
                results[fv_name] = "success"
                logger.info(f"Materialized {fv_name} to online store")
            except Exception as e:
                results[fv_name] = f"error: {str(e)}"
                logger.error(f"Failed to materialize {fv_name}: {e}")

        return {
            "materialized": results,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    def materialize_incremental(
        self,
        feature_views: Optional[List[str]] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Incremental materialization (only new/updated records since last run).
        """
        from feast import FeatureStore

        store = FeatureStore(repo_path=self.repo_path)

        if feature_views is None:
            feature_views = ["user_features", "interaction_features"]

        if end_date is None:
            end_date = datetime.utcnow()

        results = {}
        for fv_name in feature_views:
            try:
                store.materialize_incremental(
                    end_date=end_date,
                    feature_views=[fv_name],
                )
                results[fv_name] = "success"
                logger.info(f"Incrementally materialized {fv_name}")
            except Exception as e:
                results[fv_name] = f"error: {str(e)}"
                logger.error(f"Failed incremental materialization for {fv_name}: {e}")

        return {
            "materialized": results,
            "end_date": end_date.isoformat(),
        }
