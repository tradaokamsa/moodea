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
    Get personalized track recommendations for a user
    
    TODO: Implement
    - Retrieve user_features from Redis (Feast online store)
    - Generate user embedding using user tower
    - Query in-memory ANN index for candidate tracks
    - Rerank candidates using reranker model
    - Return top-k track IDs with scores
    """
    # TODO: Implement recommendation logic
    # For now, return empty recommendations to prevent 501 errors
    # This allows the system to work while full implementation is in progress
    return RecommendationResponse(
        track_ids=[],
        scores=[],
        metadata={"message": "Recommendation system not yet fully implemented"}
    )


@app.post("/admin/tracks/promote")
async def promote_track(request: TrackPromotionRequest):
    """
    Promote approved track to Feast track_features FeatureView
    """     
    success = track_promotion_service.promote_track(request.track_id)
    if success:
        return {"message": "Track promoted successfully", "track_id": request.track_id, "promoted": True}
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to promote track: {request.track_id}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "mood_model_loaded": mood_predictor is not None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ML_SERVICE_PORT)