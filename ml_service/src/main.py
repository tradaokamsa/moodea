from __future__ import annotations

from contextlib import asynccontextmanager
from threading import Lock
import json

from fastapi import FastAPI, HTTPException

from .config import settings
from .recommender import RecommenderService
from .schemas import (
    BootstrapRequest,
    InteractionRequest,
    InteractionResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from .training import train_synthetic_pipeline


service = RecommenderService(
    artifact_dir=settings.artifact_dir,
    event_dir=settings.event_dir,
    diversity_lambda=settings.diversity_lambda,
)
training_lock = Lock()


def _artifacts_exist() -> bool:
    required = [
        "catalog.npz",
        "catalog.parquet",
        "two_tower.pt",
        "din_ranker.pt",
        "item_embeddings.npy",
        "faiss.index",
        "manifest.json",
    ]
    return all((settings.artifact_dir / filename).exists() for filename in required)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not _artifacts_exist():
        if not settings.auto_bootstrap:
            raise RuntimeError(
                "recommendation artifacts are missing; run `python -m src.bootstrap`"
            )
        train_synthetic_pipeline(
            catalog_csv=settings.catalog_csv,
            artifact_dir=settings.artifact_dir,
            max_tracks=settings.bootstrap_tracks,
            num_users=settings.bootstrap_users,
            epochs=settings.bootstrap_epochs,
            seed=settings.random_seed,
        )
    service.load()
    yield


app = FastAPI(title="Moodea Recommendation ML Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if service.ready else "starting",
        "ready": service.ready,
        "catalog_size": len(service.catalog.frame) if service.catalog is not None else 0,
        "known_users": len(service.users),
        "model_version": service.manifest.get("model_version"),
        "ranker_version": service.manifest.get("ranker_version"),
    }


@app.get("/catalog/stats")
def catalog_stats() -> dict:
    if not service.ready or service.catalog is None:
        raise HTTPException(status_code=503, detail="service not ready")
    quality_path = settings.artifact_dir / "quality_report.json"
    return {
        "manifest": service.manifest,
        "quality": json.loads(quality_path.read_text(encoding="utf-8")),
    }


@app.post("/recommendations", response_model=RecommendationResponse)
def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    try:
        result = service.recommend(
            request,
            retrieval_candidates=settings.retrieval_candidates,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    tracks = result["tracks"]
    return RecommendationResponse(
        request_id=result["request_id"],
        user_id=request.user_id,
        tracks=tracks,
        track_ids=[track["track_id"] for track in tracks],
        scores=[track["score"] for track in tracks],
        metadata=result["metadata"],
    )


@app.post("/interactions", response_model=InteractionResponse)
def interactions(request: InteractionRequest) -> InteractionResponse:
    try:
        count = service.record_interaction(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"track not in catalog: {error.args[0]}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return InteractionResponse(
        accepted=True,
        event_id=request.event_id,
        user_id=request.user_id,
        profile_interactions=count,
    )


@app.post("/admin/bootstrap-synthetic")
def bootstrap_synthetic(request: BootstrapRequest) -> dict:
    if not training_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="training is already in progress")
    try:
        result = train_synthetic_pipeline(
            catalog_csv=settings.catalog_csv,
            artifact_dir=settings.artifact_dir,
            max_tracks=request.max_tracks,
            num_users=request.num_users,
            epochs=request.epochs,
            ranker_epochs=request.ranker_epochs,
            loss_type=request.loss_type,
            seed=request.seed,
        )
        service.load()
        return {
            "status": "trained",
            "retrieval_loss": result.retrieval_loss,
            "ranker_loss": result.ranker_loss,
            "recall_at_100": result.recall_at_100,
            "ndcg_at_100": result.ndcg_at_100,
        }
    finally:
        training_lock.release()
