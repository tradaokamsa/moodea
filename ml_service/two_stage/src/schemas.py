from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    context: dict[str, Any] = Field(default_factory=dict)
    seed_track_ids: list[str] = Field(default_factory=list)
    mood: Literal["sad", "happy", "energetic", "calm"] | None = None


class RecommendedTrack(BaseModel):
    track_id: str
    score: float
    ranker_score: float
    retrieval_score: float
    retrieval_rank: int
    final_rank: int
    mood: str | None = None
    audio_features: dict[str, float] = Field(default_factory=dict)
    attention_history_track_ids: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    request_id: str
    user_id: str
    tracks: list[RecommendedTrack]
    track_ids: list[str]
    scores: list[float]
    metadata: dict[str, Any]


class InteractionRequest(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    interaction_type: Literal["skip", "continue", "like"]
    request_id: str | None = None
    session_id: str | None = None
    position: int | None = Field(default=None, ge=1)
    play_ms: int | None = Field(default=None, ge=0)
    track_duration_ms: int | None = Field(default=None, gt=0)
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = Field(default_factory=dict)


class InteractionResponse(BaseModel):
    accepted: bool
    event_id: str
    user_id: str
    profile_interactions: int


class BootstrapRequest(BaseModel):
    max_tracks: int = Field(default=5000, ge=200, le=277938)
    num_users: int = Field(default=256, ge=16, le=10000)
    epochs: int = Field(default=5, ge=1, le=100)
    ranker_epochs: int = Field(default=3, ge=1, le=100)
    loss_type: Literal["in_batch", "bpr"] = "in_batch"
    seed: int = 42
