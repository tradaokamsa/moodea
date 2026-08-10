from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from src.dataset import build_point_in_time_datasets


def test_point_in_time_history_attribution_and_label_maturity():
    impressions = pd.DataFrame(
        [
            {"request_id": "r1", "user_id": "u1", "track_id": "c1", "shown_at": "2025-01-02T12:00:00Z"},
            {"request_id": "r2", "user_id": "u1", "track_id": "c2", "shown_at": "2025-01-03T12:00:00Z"},
            {"request_id": "r3", "user_id": "u1", "track_id": "c3", "shown_at": "2025-01-05T00:00:00Z"},
        ]
    )
    interactions = pd.DataFrame(
        [
            {"event_id": "history", "request_id": None, "user_id": "u1", "track_id": "h1", "interaction_type": "like", "event_timestamp": "2025-01-01T12:00:00Z"},
            {"event_id": "response", "request_id": "r1", "user_id": "u1", "track_id": "c1", "interaction_type": "continue", "event_timestamp": "2025-01-02T13:00:00Z"},
            {"event_id": "response", "request_id": "r1", "user_id": "u1", "track_id": "c1", "interaction_type": "like", "event_timestamp": "2025-01-02T14:00:00Z"},
            {"event_id": "late", "request_id": "r2", "user_id": "u1", "track_id": "c2", "interaction_type": "like", "event_timestamp": "2025-01-04T13:00:00Z"},
            {"event_id": "future", "request_id": None, "user_id": "u1", "track_id": "future-track", "interaction_type": "like", "event_timestamp": "2025-01-04T10:00:00Z"},
        ]
    )

    result = build_point_in_time_datasets(
        impressions,
        interactions,
        as_of=datetime(2025, 1, 5, 12, tzinfo=timezone.utc),
        attribution_window=timedelta(hours=24),
        max_history=20,
    )

    rows = result.ranking_examples.set_index("request_id")
    assert list(rows.index) == ["r1", "r2"]
    assert rows.loc["r1", "label"] == 1
    assert rows.loc["r1", "interaction_type"] == "continue"
    assert rows.loc["r1", "history_track_ids"] == ["h1"]
    assert rows.loc["r2", "label"] == 0
    assert rows.loc["r2", "interaction_type"] == "no_response"
    assert rows.loc["r2", "history_track_ids"] == ["h1", "c1"]
    assert "future-track" not in rows.loc["r2", "history_track_ids"]
    assert result.report["deduplicated_interactions"] == 1
    assert result.report["point_in_time_leakage_violations"] == 0
    assert result.retrieval_examples.iloc[0]["positive_track_id"] == "c1"
