"""
Recommendation Models
Includes two-tower model and reranker model
"""
import torch
import torch.nn as nn
from typing import Dict, Any, Optional
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from models.common.feature_processor import FeatureProcessor, create_user_feature_config, create_item_feature_config


class UserTower(nn.Module):
    """
    User tower network that maps user features to embedding space
    
    Architecture:
    - Feature processing (numerical + categorical embeddings)
    - Multi-layer feedforward network
    - L2 normalization for cosine similarity
    """
    
    def __init__(
        self,
        feature_config: Optional[Dict[str, Dict[str, Any]]] = None,
        embedding_dim: int = 128,
        hidden_dims: list = [256, 128],
        dropout: float = 0.2,
        feature_embedding_dim: int = 32
    ):
        """
        Initialize user tower
        
        Args:
            feature_config: Feature configuration dict (if None, uses default)
            embedding_dim: Output embedding dimension
            hidden_dims: List of hidden layer dimensions
            dropout: Dropout rate
            feature_embedding_dim: Embedding dimension for categorical features
        """
        super().__init__()
        self.embedding_dim = embedding_dim
        
        # Use default config if not provided
        if feature_config is None:
            feature_config = create_user_feature_config()
        
        # Feature processor
        self.feature_processor = FeatureProcessor(
            feature_config,
            embedding_dim=feature_embedding_dim
        )
        
        # Calculate input dimension (sum of all processed feature dimensions)
        # This is computed dynamically, but we'll approximate based on config
        feature_processor_output_dim = sum(
            config.get('dim', feature_embedding_dim) if config['type'] != 'numerical'
            else 1
            for config in feature_config.values()
        )
        
        # Build feedforward layers
        layers = []
        input_dim = feature_processor_output_dim
        
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(input_dim, hidden_dim))
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            input_dim = hidden_dim
        
        # Final layer to embedding dimension
        layers.append(nn.Linear(input_dim, embedding_dim))
        self.mlp = nn.Sequential(*layers)
        
        # L2 normalization for cosine similarity
        self.normalize = True
    
    def forward(self, user_features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Forward pass through user tower
        
        Args:
            user_features: Dict of user feature tensors
        
        Returns:
            User embeddings [batch_size, embedding_dim]
        """
        # Process features
        processed_features = self.feature_processor(user_features)
        
        # Pass through MLP
        embeddings = self.mlp(processed_features)
        
        # L2 normalize for cosine similarity
        if self.normalize:
            embeddings = nn.functional.normalize(embeddings, p=2, dim=1)
        
        return embeddings


class ItemTower(nn.Module):
    """
    Item (track) tower network that maps item features to embedding space
    
    Architecture:
    - Feature processing (numerical + categorical embeddings)
    - Multi-layer feedforward network
    - L2 normalization for cosine similarity
    """
    
    def __init__(
        self,
        feature_config: Optional[Dict[str, Dict[str, Any]]] = None,
        embedding_dim: int = 128,
        hidden_dims: list = [256, 128],
        dropout: float = 0.2,
        feature_embedding_dim: int = 32
    ):
        """
        Initialize item tower
        
        Args:
            feature_config: Feature configuration dict (if None, uses default)
            embedding_dim: Output embedding dimension (must match user tower)
            hidden_dims: List of hidden layer dimensions
            dropout: Dropout rate
            feature_embedding_dim: Embedding dimension for categorical features
        """
        super().__init__()
        self.embedding_dim = embedding_dim
        
        # Use default config if not provided
        if feature_config is None:
            feature_config = create_item_feature_config()
        
        # Feature processor
        self.feature_processor = FeatureProcessor(
            feature_config,
            embedding_dim=feature_embedding_dim
        )
        
        # Calculate input dimension
        feature_processor_output_dim = sum(
            config.get('dim', feature_embedding_dim) if config['type'] != 'numerical'
            else 1
            for config in feature_config.values()
        )
        
        # Build feedforward layers
        layers = []
        input_dim = feature_processor_output_dim
        
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(input_dim, hidden_dim))
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            input_dim = hidden_dim
        
        # Final layer to embedding dimension
        layers.append(nn.Linear(input_dim, embedding_dim))
        self.mlp = nn.Sequential(*layers)
        
        # L2 normalization for cosine similarity
        self.normalize = True
    
    def forward(self, item_features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Forward pass through item tower
        
        Args:
            item_features: Dict of item feature tensors
        
        Returns:
            Item embeddings [batch_size, embedding_dim]
        """
        # Process features
        processed_features = self.feature_processor(item_features)
        
        # Pass through MLP
        embeddings = self.mlp(processed_features)
        
        # L2 normalize for cosine similarity
        if self.normalize:
            embeddings = nn.functional.normalize(embeddings, p=2, dim=1)
        
        return embeddings


class TwoTowerModel(nn.Module):
    """
    Complete two-tower model combining user and item towers
    
    This model computes similarity scores between user and item embeddings
    using cosine similarity (dot product of normalized embeddings)
    """
    
    def __init__(
        self,
        user_feature_config: Optional[Dict[str, Dict[str, Any]]] = None,
        item_feature_config: Optional[Dict[str, Dict[str, Any]]] = None,
        embedding_dim: int = 128,
        user_hidden_dims: list = [256, 128],
        item_hidden_dims: list = [256, 128],
        dropout: float = 0.2,
        feature_embedding_dim: int = 32
    ):
        """
        Initialize two-tower model
        
        Args:
            user_feature_config: User feature configuration
            item_feature_config: Item feature configuration
            embedding_dim: Shared embedding dimension
            user_hidden_dims: User tower hidden layer dimensions
            item_hidden_dims: Item tower hidden layer dimensions
            dropout: Dropout rate
            feature_embedding_dim: Feature embedding dimension
        """
        super().__init__()
        
        self.embedding_dim = embedding_dim
        
        # Initialize towers
        self.user_tower = UserTower(
            feature_config=user_feature_config,
            embedding_dim=embedding_dim,
            hidden_dims=user_hidden_dims,
            dropout=dropout,
            feature_embedding_dim=feature_embedding_dim
        )
        
        self.item_tower = ItemTower(
            feature_config=item_feature_config,
            embedding_dim=embedding_dim,
            hidden_dims=item_hidden_dims,
            dropout=dropout,
            feature_embedding_dim=feature_embedding_dim
        )
    
    def forward(
        self,
        user_features: Dict[str, torch.Tensor],
        item_features: Dict[str, torch.Tensor]
    ) -> torch.Tensor:
        """
        Forward pass computing similarity scores
        
        Args:
            user_features: Dict of user feature tensors
            item_features: Dict of item feature tensors
        
        Returns:
            Similarity scores [batch_size] (cosine similarity/dot product)
        """
        # Get embeddings
        user_emb = self.user_tower(user_features)
        item_emb = self.item_tower(item_features)
        
        # Compute similarity (dot product of normalized embeddings = cosine similarity)
        scores = (user_emb * item_emb).sum(dim=1)
        
        return scores
    
    def get_user_embedding(self, user_features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Get user embedding (for inference)
        
        Args:
            user_features: Dict of user feature tensors
        
        Returns:
            User embeddings [batch_size, embedding_dim]
        """
        return self.user_tower(user_features)
    
    def get_item_embedding(self, item_features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Get item embedding (for inference/ANN index building)
        
        Args:
            item_features: Dict of item feature tensors
        
        Returns:
            Item embeddings [batch_size, embedding_dim]
        """
        return self.item_tower(item_features)
    
    def get_item_embeddings_batch(
        self,
        item_features_batch: Dict[str, torch.Tensor]
    ) -> torch.Tensor:
        """
        Get item embeddings for a batch of items
        
        Args:
            item_features_batch: Dict of feature_name -> [batch_size, ...] tensors
        
        Returns:
            Item embeddings [batch_size, embedding_dim]
        """
        return self.item_tower(item_features_batch)


class RerankerModel(nn.Module):
    """
    Reranker model that combines user and item embeddings with context
    to predict fine-grained relevance scores.
    
    Architecture:
    - Concatenate user embedding, item embedding, and context features
    - Multi-layer feedforward network
    - Output single relevance score
    """
    
    def __init__(
        self,
        embedding_dim: int = 128,
        context_dim: int = 0,
        hidden_dims: list = [256, 128, 64],
        dropout: float = 0.2,
        output_dim: int = 1
    ):
        """
        Initialize reranker model
        
        Args:
            embedding_dim: Dimension of user/item embeddings
            context_dim: Dimension of context features (e.g., time of day, device type)
            hidden_dims: List of hidden layer dimensions
            dropout: Dropout rate
            output_dim: Output dimension (1 for score, or num_classes for classification)
        """
        super().__init__()
        
        # Input: user_emb + item_emb + context = 2 * embedding_dim + context_dim
        input_dim = 2 * embedding_dim + context_dim
        
        # Build feedforward layers
        layers = []
        current_dim = input_dim
        
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(current_dim, hidden_dim))
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            current_dim = hidden_dim
        
        # Final output layer
        layers.append(nn.Linear(current_dim, output_dim))
        self.mlp = nn.Sequential(*layers)
    
    def forward(
        self,
        user_emb: torch.Tensor,
        item_emb: torch.Tensor,
        context: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Forward pass through reranker
        
        Args:
            user_emb: User embeddings [batch_size, embedding_dim]
            item_emb: Item embeddings [batch_size, embedding_dim]
            context: Optional context features [batch_size, context_dim]
        
        Returns:
            Relevance scores [batch_size, output_dim]
        """
        # Concatenate embeddings
        if context is not None:
            combined = torch.cat([user_emb, item_emb, context], dim=1)
        else:
            combined = torch.cat([user_emb, item_emb], dim=1)
        
        # Pass through MLP
        scores = self.mlp(combined)
        
        return scores.squeeze(-1) if scores.shape[-1] == 1 else scores

