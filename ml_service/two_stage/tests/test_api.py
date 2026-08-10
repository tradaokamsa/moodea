from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx

from src import main
from src.recommender import RecommenderService


def test_health_and_cold_start_recommendations(monkeypatch, tmp_path, trained_artifact_dir):
    event_dir = tmp_path / "events"
    catalog_csv = Path(__file__).resolve().parents[1] / "278k_labelled_uri.csv"
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            catalog_csv=catalog_csv,
            artifact_dir=trained_artifact_dir,
            event_dir=event_dir,
            auto_bootstrap=False,
            retrieval_candidates=100,
            diversity_lambda=0.85,
        ),
    )
    monkeypatch.setattr(main, "service", RecommenderService(trained_artifact_dir, event_dir))

    async def exercise_api():
        async with main.app.router.lifespan_context(main.app):
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                health = await client.get("/health")
                assert health.status_code == 200
                assert health.json()["ready"] is True

                response = await client.post(
                    "/recommendations",
                    json={"user_id": "api-new-user", "limit": 5, "mood": "calm"},
                )
                assert response.status_code == 200
                payload = response.json()
                assert len(payload["tracks"]) == 5
                assert payload["metadata"]["mode"] == "content_cold_start"

    asyncio.run(exercise_api())
