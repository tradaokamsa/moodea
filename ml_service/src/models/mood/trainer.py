import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, confusion_matrix,
    accuracy_score, f1_score, precision_score, recall_score
)
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from models.mood.model import MoodPredictor, AudioFeatureProcessor


class MoodTrainer:
    """
    Trainer for mood prediction model (Random Forest)
    """
    
    def __init__(
        self,
        model: MoodPredictor,
        random_state: int = 42
    ):
        """
        Initialize mood trainer
        
        Args:
            model: MoodPredictor instance
            random_state: Random seed
        """
        self.model = model
        self.random_state = random_state
    
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        save_path: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Train model
        
        Args:
            X_train: Training features [n_samples, n_features]
            y_train: Training labels [n_samples]
            X_val: Optional validation features
            y_val: Optional validation labels
            save_path: Optional path to save model
        
        Returns:
            Dict with training metrics
        """
        # Train model
        print("Training Random Forest model...")
        self.model.fit(X_train, y_train)
        
        # Evaluate on training set
        y_train_pred = self.model.predict(X_train)
        train_acc = accuracy_score(y_train, y_train_pred)
        train_f1 = f1_score(y_train, y_train_pred, average='weighted')
        
        metrics = {
            'train_accuracy': train_acc,
            'train_f1': train_f1
        }
        
        print(f"Train Accuracy: {train_acc:.4f}")
        print(f"Train F1: {train_f1:.4f}")
        
        # Evaluate on validation set if provided
        if X_val is not None and y_val is not None:
            y_val_pred = self.model.predict(X_val)
            val_acc = accuracy_score(y_val, y_val_pred)
            val_f1 = f1_score(y_val, y_val_pred, average='weighted')
            val_precision = precision_score(y_val, y_val_pred, average='weighted')
            val_recall = recall_score(y_val, y_val_pred, average='weighted')
            
            metrics.update({
                'val_accuracy': val_acc,
                'val_f1': val_f1,
                'val_precision': val_precision,
                'val_recall': val_recall
            })
            
            print(f"\nValidation Accuracy: {val_acc:.4f}")
            print(f"Validation F1: {val_f1:.4f}")
            print(f"Validation Precision: {val_precision:.4f}")
            print(f"Validation Recall: {val_recall:.4f}")
            
            # Classification report
            print("\nClassification Report:")
            print(classification_report(
                y_val, y_val_pred,
                target_names=self.model.mood_labels
            ))
        
        # Save model if path provided
        if save_path:
            self.model.save(save_path)
        
        return metrics
    
    def evaluate(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Dict[str, Any]:
        """
        Evaluate model on test set
        
        Args:
            X: Test features [n_samples, n_features]
            y: Test labels [n_samples]
        
        Returns:
            Dict with evaluation metrics and predictions
        """
        y_pred = self.model.predict(X)
        y_proba = self.model.predict_proba(X)
        
        accuracy = accuracy_score(y, y_pred)
        f1 = f1_score(y, y_pred, average='weighted')
        precision = precision_score(y, y_pred, average='weighted')
        recall = recall_score(y, y_pred, average='weighted')
        
        metrics = {
            'accuracy': accuracy,
            'f1': f1,
            'precision': precision,
            'recall': recall,
            'predictions': y_pred,
            'probabilities': y_proba
        }
        
        return metrics