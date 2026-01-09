"""
Dataset utilities for training recommendation models
"""
import torch
from torch.utils.data import Dataset, DataLoader
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np


class RecommendationDataset(Dataset):
    """
    Dataset for training two-tower model
    
    Provides positive and negative pairs for contrastive learning
    """
    
    def __init__(
        self,
        user_features: Dict[str, np.ndarray],
        item_features: Dict[str, np.ndarray],
        interactions: pd.DataFrame,
        negative_sampling: bool = True,
        num_negatives: int = 1
    ):
        """
        Initialize recommendation dataset
        
        Args:
            user_features: Dict of user_id -> feature arrays
            item_features: Dict of item_id -> feature arrays
            interactions: DataFrame with columns [user_id, item_id, score, ...]
            negative_sampling: Whether to sample negatives (True) or use provided (False)
            num_negatives: Number of negatives per positive (if negative_sampling=True)
        """
        self.user_features = user_features
        self.item_features = item_features
        self.interactions = interactions.copy()
        self.negative_sampling = negative_sampling
        self.num_negatives = num_negatives
        
        # Get all item IDs for negative sampling
        self.all_item_ids = list(item_features.keys())
        
        # Filter interactions to only include users/items with features
        valid_users = set(user_features.keys())
        valid_items = set(item_features.keys())
        self.interactions = self.interactions[
            (self.interactions['user_id'].isin(valid_users)) &
            (self.interactions['item_id'].isin(valid_items))
        ].reset_index(drop=True)
    
    def __len__(self) -> int:
        """Get dataset size"""
        if self.negative_sampling:
            return len(self.interactions) * (1 + self.num_negatives)
        else:
            return len(self.interactions)
    
    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """
        Get a training sample
        
        Returns:
            Dict with user_features, item_features, label (1 for positive, 0 for negative)
        """
        if self.negative_sampling:
            # Alternate between positive and negative samples
            interaction_idx = idx // (1 + self.num_negatives)
            is_positive = (idx % (1 + self.num_negatives)) == 0
            
            interaction = self.interactions.iloc[interaction_idx]
            user_id = interaction['user_id']
            positive_item_id = interaction['item_id']
            
            if is_positive:
                item_id = positive_item_id
                label = 1.0
            else:
                # Sample negative item (not in user's interactions)
                user_items = set(self.interactions[
                    self.interactions['user_id'] == user_id
                ]['item_id'].values)
                negative_candidates = [iid for iid in self.all_item_ids if iid not in user_items]
                
                if negative_candidates:
                    item_id = np.random.choice(negative_candidates)
                else:
                    item_id = np.random.choice(self.all_item_ids)
                label = 0.0
        else:
            # Use provided labels
            interaction = self.interactions.iloc[idx]
            user_id = interaction['user_id']
            item_id = interaction['item_id']
            # Use score as label (normalize if needed)
            score = interaction.get('score', 1.0)
            label = 1.0 if score > 0 else 0.0
        
        # Get features
        user_feat = self.user_features[user_id]
        item_feat = self.item_features[item_id]
        
        return {
            'user_features': user_feat,
            'item_features': item_feat,
            'label': label,
            'user_id': user_id,
            'item_id': item_id
        }


def collate_fn(batch: List[Dict[str, Any]]) -> Dict[str, torch.Tensor]:
    """
    Collate function for DataLoader
    
    Converts list of dicts into batched tensors
    """
    # This is a simplified version - in practice, you'd need to handle
    # different feature types (numerical, categorical, multi-hot) properly
    user_features_list = [item['user_features'] for item in batch]
    item_features_list = [item['item_features'] for item in batch]
    labels = torch.tensor([item['label'] for item in batch], dtype=torch.float32)
    
    # Convert to tensors (assuming features are already in correct format)
    # In practice, you'd want to properly handle Dict[str, Tensor] features
    return {
        'user_features': torch.tensor(np.array(user_features_list), dtype=torch.float32),
        'item_features': torch.tensor(np.array(item_features_list), dtype=torch.float32),
        'labels': labels
    }


def create_data_loader(
    dataset: RecommendationDataset,
    batch_size: int = 256,
    shuffle: bool = True,
    num_workers: int = 0
) -> DataLoader:
    """
    Create DataLoader for recommendation dataset
    
    Args:
        dataset: RecommendationDataset instance
        batch_size: Batch size
        shuffle: Whether to shuffle data
        num_workers: Number of worker processes
    
    Returns:
        DataLoader instance
    """
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_fn
    )

