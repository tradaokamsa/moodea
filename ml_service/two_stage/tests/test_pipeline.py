from __future__ import annotations

import json

import numpy as np

from src.recommender import RecommenderService
from src.schemas import InteractionRequest, RecommendationRequest


def test_synthetic_training_and_serving_pipeline(trained_artifact_dir, tmp_path):
    event_dir = tmp_path / "events"
    metrics = json.loads((trained_artifact_dir / "metrics.json").read_text())
    assert 0.0 <= metrics["recall_at_100"] <= 1.0
    assert 0.0 <= metrics["ndcg_at_100"] <= 1.0
    assert (trained_artifact_dir / "synthetic_interactions.parquet").exists()
    assert (trained_artifact_dir / "synthetic_impressions.parquet").exists()

    item_embeddings = np.load(trained_artifact_dir / "item_embeddings.npy")
    np.testing.assert_allclose(
        np.linalg.norm(item_embeddings, axis=1),
        np.ones(len(item_embeddings)),
        atol=1e-5,
    )

    service = RecommenderService(trained_artifact_dir, event_dir)
    service.load()
    first = service.recommend(
        RecommendationRequest(user_id="synthetic-user-0000", limit=10, context={"hour": 20})
    )
    assert len(first["tracks"]) == 10
    assert first["metadata"]["mode"] == "personalized"
    assert "ranker_score" in first["tracks"][0]
    assert first["tracks"][0]["attention_history_track_ids"]

    liked_track = first["tracks"][0]["track_id"]
    count = service.record_interaction(
        InteractionRequest(
            user_id="new-user",
            track_id=liked_track,
            interaction_type="like",
            request_id=first["request_id"],
            position=1,
        )
    )
    assert count == 1
    second = service.recommend(RecommendationRequest(user_id="new-user", limit=10))
    assert second["metadata"]["mode"] == "personalized"
    assert liked_track not in {track["track_id"] for track in second["tracks"]}

    interaction = json.loads((event_dir / "interactions.jsonl").read_text().splitlines()[0])
    assert interaction["track_id"] == liked_track
    assert interaction["score"] == 3
    assert (event_dir / "impressions.jsonl").exists()
