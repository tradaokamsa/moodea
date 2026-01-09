"""
Track Promotion Service
Promotes approved tracks from MongoDB to Feast track_features FeatureView
"""
from typing import Dict, Any
import os
from pymongo import MongoClient
from datetime import datetime

from feast import FeatureStore
from feature_engineering.feast_client import FeastClient

class TrackPromotionService:
    """
    Service for promoting approved tracks to Feast
    """
    
    def __init__(self):
        """Initialize promotion service"""
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo_client = MongoClient(mongodb_uri)
        self.db = self.mongo_client["moodea"]
        self.track_candidates_collection = self.db["track_candidates"]
        
        feast_repo_path = os.getenv("FEAST_REPO_PATH", "./feast")
        self.feast_client = FeastClient(repo_path=feast_repo_path)
    
    def promote_track(self, track_id: str) -> bool:
        """
        Promote a single track to Feast
        
        Args:
            track_id: Spotify track ID
            approved_by: User ID who approved the track
        
        Returns:
            True if successful
        """
        # Fetch from MongoDB
        track_doc = self.track_candidates_collection.find_one({"track_id": track_id, "approved": True, "promoted": False})
        if not track_doc:
            raise ValueError(f"Track {track_id} not found or not approved")

        # Extract combined_features
        combined_features = track_doc.get("combined_features", {})
        reccobeats_features = track_doc.get("reccobeats_features", {})
        mood_features = track_doc.get("mood_prediction", 0)
        spotify_features = combined_features.get("spotify_features", {})

        feast_features = {
            "track_id": track_id,
            "name": spotify_features.get("name", ""),
            "artists": ", ".join(spotify_features.get("artists", [])),
            "album": spotify_features.get("album", ""),
            "duration_ms": spotify_features.get("duration_ms", 0),
            "danceability": reccobeats_features.get("danceability", 0.0),  
            "energy": reccobeats_features.get("energy", 0.0),
            "valence": reccobeats_features.get("valence", 0.0),
            "tempo": reccobeats_features.get("tempo", 0.0),
            "acousticness": reccobeats_features.get("acousticness", 0.0),
            "instrumentalness": reccobeats_features.get("instrumentalness", 0.0),
            "liveness": reccobeats_features.get("liveness", 0.0),
            "loudness": reccobeats_features.get("loudness", 0.0),
            "speechiness": reccobeats_features.get("speechiness", 0.0),
            "key": reccobeats_features.get("key", 0),
            "mode": reccobeats_features.get("mode", 0),
            "mood": mood_features,
            "discovered_at": track_doc.get("created_at").isoformat() if track_doc.get("created_at") else "",
            "event_timestamp": int(track_doc.get("created_at").timestamp()) if track_doc.get("created_at") else int(datetime.time()),
        }   

        # Write to Feast
        self.feast_client.write_track_features([feast_features])

        # Update MongoDB
        self.track_candidates_collection.update_one(
            {"track_id": track_id},
            {"$set": {"promoted": True}}
        )
        return True
    
    def promote_batch(self, track_ids: List[str]) -> Dict[str, bool]:
        """
        Promote multiple tracks in batch
        
        Args:
            track_ids: List of Spotify track IDs
            approved_by: User ID who approved the tracks
        
        Returns:
            Dict mapping track_id to success status
        """
        results = {}
        for track_id in track_ids:
            try:
                self.promote_track(track_id)
                results[track_id] = True
            except Exception as e:
                results[track_id] = False
        return results
    
    def get_pending_tracks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get tracks pending promotion (approved but not promoted)
        
        Args:
            limit: Maximum number of tracks to return
        
        Returns:
            List of track documents
        """
        pending_tracks = self.track_candidates_collection.find({"approved": True, "promoted": False}, limit=limit)
        return list(pending_tracks)

