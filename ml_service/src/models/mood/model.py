import numpy as np
from typing import Dict, List, Any, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import RobustScaler
import joblib
import os


class MoodPredictor:
    """
    Multi-class classification model for mood prediction using Random Forest
    
    Takes audio features (e.g., from ReccoBeats) and predicts mood class.
    Mood labels: sad (0), happy (1), energetic (2), calm (3)
    """
    
    def __init__(
        self,
        n_estimators: int = 100,
        random_state: int = 42,
        model_path: Optional[str] = None
    ):
        """
        Initialize mood predictor model
        
        Args:
            n_estimators: Number of trees in random forest
            random_state: Random seed for reproducibility
            model_path: Optional path to load pre-trained model
        """
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.mood_labels = ['sad', 'happy', 'energetic', 'calm']
        self.num_moods = 4
        
        # Initialize model
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
            verbose=0
        )
        
        # Scaler for feature preprocessing
        self.scaler = RobustScaler()
        
        # Feature processor
        self.feature_processor = AudioFeatureProcessor()
        
        # Load model if path provided
        if model_path and os.path.exists(model_path):
            self.load(model_path)
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """
        Train the model
        
        Args:
            X: Feature array [n_samples, n_features]
            y: Labels [n_samples]
        """
        # Fit scaler
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled, y)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict mood classes
        
        Args:
            X: Feature array [n_samples, n_features]
        
        Returns:
            Predicted class labels [n_samples]
        """
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict mood probabilities
        
        Args:
            X: Feature array [n_samples, n_features]
        
        Returns:
            Probability array [n_samples, num_moods]
        """
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)
    
    def predict_dict(self, audio_features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict mood for a single track from feature dict
        
        Args:
            audio_features: Dict mapping feature name -> value
        
        Returns:
            Dict with predicted mood, probabilities, and label name
        """
        # Process features
        feature_array = self.feature_processor.process_dict(audio_features)
        feature_array = feature_array.reshape(1, -1)
        
        # Predict
        predicted_class = self.predict(feature_array)[0]
        probabilities = self.predict_proba(feature_array)[0]
        
        return {
            'predicted_class': int(predicted_class),
            'predicted_mood': self.mood_labels[predicted_class],
            'probabilities': {
                self.mood_labels[i]: float(prob) 
                for i, prob in enumerate(probabilities)
            }
        }
    
    def predict_batch(self, audio_features_list: List[Dict[str, float]]) -> List[Dict[str, Any]]:
        """
        Predict moods for multiple tracks
        
        Args:
            audio_features_list: List of feature dicts
        
        Returns:
            List of prediction dicts
        """
        # Process all features
        feature_arrays = [
            self.feature_processor.process_dict(feat) 
            for feat in audio_features_list
        ]
        X = np.array(feature_arrays)
        
        # Predict
        predicted_classes = self.predict(X)
        probabilities = self.predict_proba(X)
        
        # Format results
        results = []
        for i, (pred_class, probs) in enumerate(zip(predicted_classes, probabilities)):
            results.append({
                'predicted_class': int(pred_class),
                'predicted_mood': self.mood_labels[pred_class],
                'probabilities': {
                    self.mood_labels[j]: float(prob) 
                    for j, prob in enumerate(probs)
                }
            })
        
        return results
    
    def save(self, filepath: str):
        """
        Save model to file
        
        Args:
            filepath: Path to save model
        """
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_processor': self.feature_processor,
            'mood_labels': self.mood_labels,
            'n_estimators': self.n_estimators,
            'random_state': self.random_state
        }, filepath)
        print(f"Model saved to {filepath}")
    
    def load(self, filepath: str):
        """
        Load model from file
        
        Args:
            filepath: Path to load model from
        """
        data = joblib.load(filepath)
        self.model = data['model']
        self.scaler = data['scaler']
        self.feature_processor = data['feature_processor']
        self.mood_labels = data['mood_labels']
        self.n_estimators = data.get('n_estimators', 100)
        self.random_state = data.get('random_state', 42)
        print(f"Model loaded from {filepath}")


class AudioFeatureProcessor:
    """
    Utility class to process audio features into model input format
    Matches the feature engineering from the experiment notebook
    """
    
    def __init__(self):
        """
        Initialize audio feature processor
        """
        # Original feature names from dataset
        self.original_features = [
            'duration (ms)', 'danceability', 'energy', 'loudness', 
            'speechiness', 'acousticness', 'instrumentalness', 
            'liveness', 'valence', 'tempo'
        ]
        
        # Processed feature names (after engineering)
        self.processed_feature_names = [
            'danceability', 'energy', 'loudness', 'speechiness',
            'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo',
            'duration_sec'
        ]
    
    def process_dict(self, audio_features: Dict[str, float]) -> np.ndarray:
        """
        Process audio features dict into feature array
        
        Args:
            audio_features: Dict mapping feature name -> value
        
        Returns:
            Feature array [n_features]
        """
        # Extract original features
        duration_ms = audio_features.get('duration (ms)', audio_features.get('duration', 0.0))
        danceability = audio_features.get('danceability', 0.0)
        energy = audio_features.get('energy', 0.0)
        loudness = audio_features.get('loudness', 0.0)
        speechiness = audio_features.get('speechiness', 0.0)
        acousticness = audio_features.get('acousticness', 0.0)
        instrumentalness = audio_features.get('instrumentalness', 0.0)
        liveness = audio_features.get('liveness', 0.0)
        valence = audio_features.get('valence', 0.0)
        tempo = audio_features.get('tempo', 0.0)
        
        # Feature engineering (matching experiment notebook)
        duration_sec = duration_ms / 1000.0 if duration_ms > 0 else 0.0
        
        # Build feature array in the same order as processed_feature_names
        feature_array = np.array([
            danceability,
            energy,
            loudness,
            speechiness,
            acousticness,
            instrumentalness,
            liveness,
            valence,
            tempo,
            duration_sec
        ])
        
        return feature_array
    
    def process_batch(self, audio_features_list: List[Dict[str, float]]) -> np.ndarray:
        """
        Process batch of audio features
        
        Args:
            audio_features_list: List of feature dicts
        
        Returns:
            Feature array [batch_size, n_features]
        """
        feature_arrays = [self.process_dict(feat) for feat in audio_features_list]
        return np.array(feature_arrays)