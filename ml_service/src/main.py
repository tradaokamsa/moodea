from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import numpy as np
import sys

# Add models to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'models'))
from models.mood.model import MoodPredictor, AudioFeatureProcessor
from services.track_promotion_service import TrackPromotionService
from services.content_based_service import ContentBasedService

app = FastAPI(title="Moodea ML Service", version="1.0.0")
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
    print("Model will need to be trained and saved first.")

# Initialize content-based recommendation service
content_based_service = None
try:
    content_based_service = ContentBasedService()
    print("Content-based recommendation service initialized")
except Exception as e:
    print(f"Warning: Could not initialize content-based service: {e}")


class MoodPredictionRequest(BaseModel):
    """Request for mood prediction"""
    track_ids: List[str]
    audio_features: Dict[str, Dict[str, Any]]  # track_id -> features


class MoodPredictionResponse(BaseModel):
    """Response from mood prediction"""
    predictions: Dict[str, Dict[str, Any]]  # track_id -> mood predictions


class RecommendationRequest(BaseModel):
    """Request for recommendations"""
    user_id: str
    limit: int = 20
    context: Optional[Dict[str, Any]] = None


class RecommendationResponse(BaseModel):
    """Response with recommendations"""
    track_ids: List[str]
    scores: List[float]
    metadata: Optional[Dict[str, Any]] = None


class TrackPromotionRequest(BaseModel):
    """Request to promote track to Feast"""
    track_id: str


@app.post("/ml/mood/predict", response_model=MoodPredictionResponse)
async def predict_mood(request: MoodPredictionRequest):
    """
    Predict mood for tracks based on audio features

    Uses Random Forest classifier for multi-class mood prediction.
    Returns predicted mood class and probabilities for each track.
    """
    if mood_predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Mood prediction model not loaded. Please train and save the model first."
        )

    try:
        # Prepare features for each track
        audio_features_list = []
        valid_track_ids = []

        for track_id in request.track_ids:
            if track_id in request.audio_features:
                audio_features_list.append(request.audio_features[track_id])
                valid_track_ids.append(track_id)

        if not audio_features_list:
            raise HTTPException(
                status_code=400,
                detail="No valid audio features provided"
            )

        # Predict moods
        predictions_list = mood_predictor.predict_batch(audio_features_list)

        # Format response
        predictions_dict = {
            track_id: pred
            for track_id, pred in zip(valid_track_ids, predictions_list)
        }

        return MoodPredictionResponse(predictions=predictions_dict)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error predicting moods: {str(e)}"
        )


@app.post("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    """
    Get personalized track recommendations for a user.

    Uses content-based filtering on audio features and mood.
    Will be upgraded to neural two-tower model in Phase 2.
    """
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
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendations: {str(e)}",
        )


@app.post("/admin/tracks/promote")
async def promote_track(request: TrackPromotionRequest):
    """
    Promote approved track to Feast track_features FeatureView
    """
    try:
        success = track_promotion_service.promote_track(request.track_id)
        if success:
            return {"message": "Track promoted successfully", "track_id": request.track_id, "promoted": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to promote track")
    except ValueError as e:
        # Track not found or not approved
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Log error and return generic message
        import logging
        logging.error(f"Error promoting track {request.track_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error promoting track: {str(e)}")


@app.post("/admin/tracks/promote-batch")
async def promote_batch():
    """
    Promote all approved-but-unpromoted tracks to Feast in batch.
    Reloads the content-based service track index after promotion.
    """
    try:
        pending = track_promotion_service.get_pending_tracks(limit=500)
        if not pending:
            return {"message": "No pending tracks to promote", "promoted": 0, "failed": 0}

        track_ids = [doc["track_id"] for doc in pending]
        results = track_promotion_service.promote_batch(track_ids)

        promoted = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)

        # Reload content-based index with new tracks
        if promoted > 0 and content_based_service is not None:
            content_based_service.reload_tracks()

        return {
            "message": f"Batch promotion complete: {promoted} promoted, {failed} failed",
            "promoted": promoted,
            "failed": failed,
            "results": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in batch promotion: {str(e)}",
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    track_count = 0
    if content_based_service is not None and content_based_service.track_ids:
        track_count = len(content_based_service.track_ids)

    return {
        "status": "ok",
        "mood_model_loaded": mood_predictor is not None,
        "content_based_service": content_based_service is not None,
        "track_count": track_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ML_SERVICE_PORT)
