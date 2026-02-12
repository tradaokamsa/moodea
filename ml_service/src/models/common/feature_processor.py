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
    
    def get_output_dim(self) -> int:
        """Calculate total output dimension of processed features."""
        total = 0
        for config in self.feature_config.values():
            if config['type'] == 'numerical':
                total += config.get('dim', 1)
            else:
                total += config.get('dim', self.embedding_dim)
        return total

    def forward(self, features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Process features into tensor representations

        Args:
            features: Dict of feature_name -> tensor

        Returns:
            Concatenated feature tensor [batch_size, feature_dim]
        """
        processed = []
        batch_size = features[list(features.keys())[0]].shape[0]
        device = features[list(features.keys())[0]].device

        for feat_name, config in self.feature_config.items():
            if feat_name not in features:
                # Missing feature - use zero tensor
                if config['type'] == 'numerical':
                    dim = config.get('dim', 1)
                    processed.append(torch.zeros(batch_size, dim, device=device))
                else:
                    processed.append(torch.zeros(
                        batch_size,
                        config.get('dim', self.embedding_dim),
                        device=device,
                    ))
                continue

            feat_tensor = features[feat_name]

            if config['type'] == 'numerical':
                # Numerical features (supports multi-dim via config 'dim')
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
    Create feature configuration for user features.

    Aligned with Feast schema in feast/features/user_features.py:
      - listening_pattern_score  (Float32)
      - preference_vector        (Array(Float32), 9-dim weighted avg of audio features)
      - top_artists              (Array(String)  -> multi_hot int IDs)
      - top_genres               (Array(String)  -> multi_hot int IDs)
    """
    return {
        # Numerical features
        'listening_pattern_score': {'type': 'numerical', 'dim': 1},
        'preference_vector': {'type': 'numerical', 'dim': 9},  # 9 audio-feature dims

        # Multi-hot categorical (IDs built from vocabulary during training)
        'top_artists': {
            'type': 'multi_hot',
            'size': 10000,  # artist vocab size
            'dim': 64,
        },
        'top_genres': {
            'type': 'multi_hot',
            'size': 200,  # genre vocab size
            'dim': 32,
        },
    }


def create_item_feature_config() -> Dict[str, Dict[str, Any]]:
    """
    Create feature configuration for item (track) features.

    Aligned with Feast schema in feast/features/track_features.py:
      - danceability, energy, valence, tempo, acousticness,
        instrumentalness, liveness, loudness, speechiness (Float32)
      - key   (Int64, 0-11)
      - mode  (Int64, 0-1)
      - mood  (Int64, 0-3: sad/happy/energetic/calm)
    """
    return {
        # Numerical audio features
        'danceability':      {'type': 'numerical', 'dim': 1},
        'energy':            {'type': 'numerical', 'dim': 1},
        'valence':           {'type': 'numerical', 'dim': 1},
        'tempo':             {'type': 'numerical', 'dim': 1},
        'acousticness':      {'type': 'numerical', 'dim': 1},
        'instrumentalness':  {'type': 'numerical', 'dim': 1},
        'liveness':          {'type': 'numerical', 'dim': 1},
        'loudness':          {'type': 'numerical', 'dim': 1},
        'speechiness':       {'type': 'numerical', 'dim': 1},

        # Categorical features
        'key':  {'type': 'categorical', 'size': 12, 'dim': 16},  # 12 musical keys
        'mode': {'type': 'categorical', 'size': 2,  'dim': 8},   # major / minor
        'mood': {'type': 'categorical', 'size': 4,  'dim': 16},  # sad/happy/energetic/calm
    }

