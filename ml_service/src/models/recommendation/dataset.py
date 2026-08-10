"""
Dataset utilities for training recommendation models
"""
import torch
from torch.utils.data import Dataset, DataLoader
from typing import Dict, List, Any
import pandas as pd
import numpy as np


class RecommendationDataset(Dataset):
    """
    Dataset for training two-tower model.

    Each sample returns Dict[str, value] for user/item features so that the
    collate function can stack each feature key separately into
    ``{feature_name: Tensor}``.
    """

    def __init__(
        self,
        user_features: Dict[str, Dict[str, Any]],
        item_features: Dict[str, Dict[str, Any]],
        interactions: pd.DataFrame,
        negative_sampling: bool = True,
        num_negatives: int = 1,
    ):
        """
        Args:
            user_features: user_id -> {feature_name: value} (numpy arrays / scalars)
            item_features: item_id -> {feature_name: value}
            interactions: DataFrame with columns [user_id, item_id, score, ...]
            negative_sampling: sample random negatives per positive
            num_negatives: number of negatives per positive
        """
        self.user_features = user_features
        self.item_features = item_features
        self.interactions = interactions.copy()
        self.negative_sampling = negative_sampling
        self.num_negatives = num_negatives

        self.all_item_ids = list(item_features.keys())

        # Keep only interactions whose entities have features
        valid_users = set(user_features.keys())
        valid_items = set(item_features.keys())
        self.interactions = self.interactions[
            (self.interactions["user_id"].isin(valid_users))
            & (self.interactions["item_id"].isin(valid_items))
        ].reset_index(drop=True)

    def __len__(self) -> int:
        if self.negative_sampling:
            return len(self.interactions) * (1 + self.num_negatives)
        return len(self.interactions)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        if self.negative_sampling:
            interaction_idx = idx // (1 + self.num_negatives)
            is_positive = (idx % (1 + self.num_negatives)) == 0

            interaction = self.interactions.iloc[interaction_idx]
            user_id = interaction["user_id"]
            positive_item_id = interaction["item_id"]

            if is_positive:
                item_id = positive_item_id
                label = 1.0
            else:
                user_items = set(
                    self.interactions[self.interactions["user_id"] == user_id][
                        "item_id"
                    ].values
                )
                negative_candidates = [
                    iid for iid in self.all_item_ids if iid not in user_items
                ]
                item_id = (
                    np.random.choice(negative_candidates)
                    if negative_candidates
                    else np.random.choice(self.all_item_ids)
                )
                label = 0.0
        else:
            interaction = self.interactions.iloc[idx]
            user_id = interaction["user_id"]
            item_id = interaction["item_id"]
            score = interaction.get("score", 1.0)
            label = 1.0 if score > 0 else 0.0

        # Return per-feature dicts so collate_fn can stack by key
        return {
            "user_features": self.user_features[user_id],
            "item_features": self.item_features[item_id],
            "label": label,
            "user_id": user_id,
            "item_id": item_id,
        }


def collate_fn(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Collate function that batches each feature key separately.

    Returns::

        {
            'user_features': {feat_name: Tensor[batch_size, ...]},
            'item_features': {feat_name: Tensor[batch_size, ...]},
            'labels': Tensor[batch_size],
        }
    """
    labels = torch.tensor([item["label"] for item in batch], dtype=torch.float32)

    def _stack_feature_dicts(key: str) -> Dict[str, torch.Tensor]:
        feat_dicts = [item[key] for item in batch]
        feature_names = feat_dicts[0].keys()
        stacked: Dict[str, torch.Tensor] = {}
        for fname in feature_names:
            vals = [fd[fname] for fd in feat_dicts]
            if isinstance(vals[0], np.ndarray):
                stacked[fname] = torch.tensor(np.stack(vals))
            elif isinstance(vals[0], torch.Tensor):
                stacked[fname] = torch.stack(vals)
            else:
                # scalar
                stacked[fname] = torch.tensor(vals)
        return stacked

    return {
        "user_features": _stack_feature_dicts("user_features"),
        "item_features": _stack_feature_dicts("item_features"),
        "labels": labels,
    }


def create_data_loader(
    dataset: RecommendationDataset,
    batch_size: int = 256,
    shuffle: bool = True,
    num_workers: int = 0,
) -> DataLoader:
    """Create DataLoader for recommendation dataset."""
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_fn,
    )
