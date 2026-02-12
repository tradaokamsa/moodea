from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import logging
import sys

# Add src/ to path so models, services, pipelines are importable
sys.path.insert(0, os.path.dirname(__file__))
from models.mood.model import MoodPredictor, AudioFeatureProcessor
from services.track_promotion_service import TrackPromotionService
from services.content_based_service import ContentBasedService

logger = logging.getLogger(__name__)

app = FastAPI(title="Moodea ML Service", version="2.0.0")
track_promotion_service = TrackPromotionService()

# Environment variables
ML_SERVICE_PORT = int(os.getenv("ML_SERVICE_PORT", "8001"))
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
FEAST_REPO_PATH = os.getenv("FEAST_REPO_PATH", "./feast")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MOOD_MODEL_PATH = os.getenv("MOOD_MODEL_PATH", "./models/mood/best_mood_model.pkl")

# Initialize mood predictor
mood_predictor = None
try:
    mood_predictor = MoodPredictor(model_path=MOOD_MODEL_PATH)
    print(f"Mood prediction model loaded from {MOOD_MODEL_PATH}")
except Exception as e:
    print(f"Warning: Could not load mood model from {MOOD_MODEL_PATH}: {e}")

# Initialize content-based recommendation service
content_based_service = None
try:
    content_based_service = ContentBasedService()
    print("Content-based recommendation service initialized")
except Exception as e:
    print(f"Warning: Could not initialize content-based service: {e}")

# Initialize neural inference pipeline (Phase 2)
inference_pipeline = None
try:
    from pipelines.inference_pipeline import InferencePipeline
    inference_pipeline = InferencePipeline()
    if inference_pipeline.is_ready:
        print("Neural inference pipeline initialized and ready")
    else:
        print("Neural inference pipeline initialized (models not loaded yet - run /admin/train first)")
except Exception as e:
    print(f"Warning: Could not initialize neural inference pipeline: {e}")


# ---- Request / Response models ----

class MoodPredictionRequest(BaseModel):
    track_ids: List[str]
    audio_features: Dict[str, Dict[str, Any]]

class MoodPredictionResponse(BaseModel):
    predictions: Dict[str, Dict[str, Any]]

class RecommendationRequest(BaseModel):
    user_id: str
    limit: int = 20
    context: Optional[Dict[str, Any]] = None

class RecommendationResponse(BaseModel):
    track_ids: List[str]
    scores: List[float]
    metadata: Optional[Dict[str, Any]] = None

class TrackPromotionRequest(BaseModel):
    track_id: str


# ---- Endpoints ----

@app.post("/ml/mood/predict", response_model=MoodPredictionResponse)
async def predict_mood(request: MoodPredictionRequest):
    """Predict mood for tracks based on audio features."""
    if mood_predictor is None:
        raise HTTPException(status_code=503, detail="Mood prediction model not loaded.")

    try:
        audio_features_list = []
        valid_track_ids = []
        for track_id in request.track_ids:
            if track_id in request.audio_features:
                audio_features_list.append(request.audio_features[track_id])
                valid_track_ids.append(track_id)

        if not audio_features_list:
            raise HTTPException(status_code=400, detail="No valid audio features provided")

        predictions_list = mood_predictor.predict_batch(audio_features_list)
        predictions_dict = dict(zip(valid_track_ids, predictions_list))
        return MoodPredictionResponse(predictions=predictions_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting moods: {str(e)}")


@app.post("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    """
    Get personalized track recommendations.

    Uses neural two-tower model if trained, otherwise falls back to
    content-based filtering.
    """
    # Try neural pipeline first
    if inference_pipeline is not None and inference_pipeline.is_ready:
        try:
            result = inference_pipeline.get_recommendations(
                user_id=request.user_id,
                limit=request.limit,
                context=request.context,
            )
            if result["track_ids"]:
                return RecommendationResponse(
                    track_ids=result["track_ids"],
                    scores=result["scores"],
                    metadata=result.get("metadata"),
                )
        except Exception as e:
            logger.warning(f"Neural inference failed, falling back to content-based: {e}")

    # Fallback to content-based
    if content_based_service is None:
        return RecommendationResponse(
            track_ids=[],
            scores=[],
            metadata={"message": "Recommendation service not available"},
        )

    try:
        result = content_based_service.get_recommendations(
            user_id=request.user_id,
            limit=request.limit,
            context=request.context,
        )
        return RecommendationResponse(
            track_ids=result["track_ids"],
            scores=result["scores"],
            metadata=result.get("metadata"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@app.post("/admin/tracks/promote")
async def promote_track(request: TrackPromotionRequest):
    """Promote approved track to Feast track_features FeatureView."""
    try:
        success = track_promotion_service.promote_track(request.track_id)
        if success:
            return {"message": "Track promoted successfully", "track_id": request.track_id, "promoted": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to promote track")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error promoting track {request.track_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error promoting track: {str(e)}")


@app.post("/admin/tracks/promote-batch")
async def promote_batch():
    """Promote all approved-but-unpromoted tracks to Feast in batch."""
    try:
        pending = track_promotion_service.get_pending_tracks(limit=500)
        if not pending:
            return {"message": "No pending tracks to promote", "promoted": 0, "failed": 0}

        track_ids = [doc["track_id"] for doc in pending]
        results = track_promotion_service.promote_batch(track_ids)

        promoted = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)

        if promoted > 0 and content_based_service is not None:
            content_based_service.reload_tracks()

        return {
            "message": f"Batch promotion complete: {promoted} promoted, {failed} failed",
            "promoted": promoted,
            "failed": failed,
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in batch promotion: {str(e)}")


@app.post("/admin/train")
async def train_models(background_tasks: BackgroundTasks):
    """
    Trigger full training pipeline (two-tower + reranker + FAISS index).
    Runs in the background.
    """
    def _run_training():
        try:
            from pipelines.training_pipeline import TrainingPipeline
            pipeline = TrainingPipeline()
            result = pipeline.run()
            logger.info(f"Training complete: {result}")
            # Reload models in inference pipeline
            if inference_pipeline is not None:
                inference_pipeline.reload_models()
                logger.info("Inference pipeline models reloaded after training")
        except Exception as e:
            logger.error(f"Training pipeline failed: {e}")

    background_tasks.add_task(_run_training)
    return {"message": "Training pipeline started in background", "status": "running"}


@app.post("/admin/materialize")
async def materialize_features():
    """Materialize user_features and interaction_features from Parquet to Redis."""
    try:
        from pipelines.materialization_pipeline import MaterializationPipeline
        pipeline = MaterializationPipeline()
        result = pipeline.materialize()
        return {"message": "Materialization complete", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Materialization failed: {str(e)}")


@app.post("/admin/compute-features")
async def compute_features():
    """Compute user and interaction features from MongoDB and write to Parquet."""
    try:
        from pipelines.user_feature_pipeline import UserFeaturePipeline
        from pipelines.interaction_feature_pipeline import InteractionFeaturePipeline

        user_df = UserFeaturePipeline().compute()
        interaction_df = InteractionFeaturePipeline().compute()

        return {
            "message": "Feature computation complete",
            "users_computed": len(user_df),
            "interaction_pairs_computed": len(interaction_df),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feature computation failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    track_count = 0
    if content_based_service is not None and content_based_service.track_ids:
        track_count = len(content_based_service.track_ids)

    neural_ready = inference_pipeline is not None and inference_pipeline.is_ready
    ann_count = 0
    if neural_ready and inference_pipeline.ann_service and inference_pipeline.ann_service.index:
        ann_count = inference_pipeline.ann_service.index.ntotal

    return {
        "status": "ok",
        "mood_model_loaded": mood_predictor is not None,
        "content_based_service": content_based_service is not None,
        "track_count": track_count,
        "neural_inference_ready": neural_ready,
        "two_tower_loaded": inference_pipeline is not None and inference_pipeline.two_tower is not None,
        "reranker_loaded": inference_pipeline is not None and inference_pipeline.reranker is not None,
        "ann_index_size": ann_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ML_SERVICE_PORT)
