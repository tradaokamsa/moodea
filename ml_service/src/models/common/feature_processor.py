"""
Feature processing utilities for handling different feature types
Used by recommendation models
"""
import torch
import torch.nn as nn
from typing import Dict, List, Any, Optional
import numpy as np


class FeatureProcessor(nn.Module):
    """
    Processes raw features into tensors for model input
    
    Handles:
    - Numerical features (continuous)
    - Categorical features (embedding lookup)
    - Multi-hot categorical features (bag of embeddings)
    """
    
    def __init__(
        self,
        feature_config: Dict[str, Dict[str, Any]],
        embedding_dim: int = 32
    ):
        """
        Initialize feature processor
        
        Args:
            feature_config: Dict mapping feature_name -> {
                'type': 'numerical' | 'categorical' | 'multi_hot',
                'size': int (vocab size for categorical/multi_hot),
                'dim': int (embedding dimension, optional)
            }
            embedding_dim: Default embedding dimension for categorical features
        """
        super().__init__()
        self.feature_config = feature_config
        self.embedding_dim = embedding_dim
        
        # Create embeddings for categorical features
        self.embeddings = nn.ModuleDict()
        for feat_name, config in feature_config.items():
            if config['type'] in ['categorical', 'multi_hot']:
                vocab_size = config['size']
                emb_dim = config.get('dim', embedding_dim)
                self.embeddings[feat_name] = nn.Embedding(
                    vocab_size,
                    emb_dim,
                    padding_idx=0  # 0 is reserved for padding/missing
                )
    
    def forward(self, features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Process features into tensor representations
        
        Args:
            features: Dict of feature_name -> tensor
        
        Returns:
            Concatenated feature tensor [batch_size, feature_dim]
        """
        processed = []
        
        for feat_name, config in self.feature_config.items():
            if feat_name not in features:
                # Missing feature - use zero tensor
                if config['type'] == 'numerical':
                    processed.append(torch.zeros(
                        features[list(features.keys())[0]].shape[0],
                        1,
                        device=features[list(features.keys())[0]].device
                    ))
                else:
                    processed.append(torch.zeros(
                        features[list(features.keys())[0]].shape[0],
                        config.get('dim', self.embedding_dim),
                        device=features[list(features.keys())[0]].device
                    ))
                continue
            
            feat_tensor = features[feat_name]
            
            if config['type'] == 'numerical':
                # Numerical features: normalize if needed
                if feat_tensor.dim() == 1:
                    feat_tensor = feat_tensor.unsqueeze(1)
                processed.append(feat_tensor.float())
            
            elif config['type'] == 'categorical':
                # Single categorical: embedding lookup
                emb = self.embeddings[feat_name](feat_tensor.long())
                processed.append(emb)
            
            elif config['type'] == 'multi_hot':
                # Multi-hot categorical: bag of embeddings
                # feat_tensor is [batch_size, max_items] with item IDs
                # For padding (0), embedding will be zero due to padding_idx
                emb = self.embeddings[feat_name](feat_tensor.long())
                # Average pooling over items (ignoring padding)
                mask = (feat_tensor > 0).float().unsqueeze(-1)
                emb_sum = (emb * mask).sum(dim=1)
                item_count = mask.sum(dim=1).clamp(min=1)  # Avoid division by zero
                emb_avg = emb_sum / item_count
                processed.append(emb_avg)
        
        # Concatenate all processed features
        return torch.cat(processed, dim=1)


def create_user_feature_config() -> Dict[str, Dict[str, Any]]:
    """
    Create feature configuration for user features
    
    Returns:
        Feature config dict for user features
    """
    # Example configuration - adjust based on actual user features
    return {
        # Numerical features (normalized)
        'avg_listening_time': {'type': 'numerical'},
        'total_tracks_played': {'type': 'numerical'},
        'num_artists_followed': {'type': 'numerical'},
        'num_playlists_created': {'type': 'numerical'},
        
        # Categorical features
        'primary_genre': {
            'type': 'categorical',
            'size': 100,  # Adjust based on actual vocab size
            'dim': 32
        },
        'listening_time_slot': {
            'type': 'categorical',
            'size': 24,  # 24 hours
            'dim': 16
        },
        
        # Multi-hot categorical (top artists, genres)
        'top_artists': {
            'type': 'multi_hot',
            'size': 10000,  # Adjust based on artist vocab size
            'dim': 64,
        },
        'top_genres': {
            'type': 'multi_hot',
            'size': 100,  # Adjust based on genre vocab size
            'dim': 32,
        },
    }


def create_item_feature_config() -> Dict[str, Dict[str, Any]]:
    """
    Create feature configuration for item (track) features
    
    Returns:
        Feature config dict for item features
    """
    # Example configuration - adjust based on actual track features
    return {
        # Numerical features (ReccoBeats audio features)
        'danceability': {'type': 'numerical'},
        'energy': {'type': 'numerical'},
        'valence': {'type': 'numerical'},
        'acousticness': {'type': 'numerical'},
        'instrumentalness': {'type': 'numerical'},
        'liveness': {'type': 'numerical'},
        'speechiness': {'type': 'numerical'},
        'tempo': {'type': 'numerical'},
        'loudness': {'type': 'numerical'},
        
        # Mood predictions (numerical scores)
        'mood_happy': {'type': 'numerical'},
        'mood_sad': {'type': 'numerical'},
        'mood_energetic': {'type': 'numerical'},
        'mood_calm': {'type': 'numerical'},
        
        # Categorical features
        'genre': {
            'type': 'categorical',
            'size': 100,  # Adjust based on genre vocab size
            'dim': 32
        },
        'artist_id': {
            'type': 'categorical',
            'size': 10000,  # Adjust based on artist vocab size
            'dim': 64
        },
        'key': {
            'type': 'categorical',
            'size': 12,  # 12 keys in music
            'dim': 16
        },
        'mode': {
            'type': 'categorical',
            'size': 2,  # Major/Minor
            'dim': 8
        },
        'time_signature': {
            'type': 'categorical',
            'size': 5,  # Common time signatures
            'dim': 8
        },
    }

