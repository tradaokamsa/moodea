from __future__ import annotations

import torch
from torch import nn
import torch.nn.functional as functional


class Tower(nn.Module):
    def __init__(self, input_dim: int, embedding_dim: int = 128):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, embedding_dim),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return functional.normalize(self.network(features), p=2, dim=-1)


class TwoTowerModel(nn.Module):
    def __init__(self, feature_dim: int, embedding_dim: int = 128):
        super().__init__()
        self.feature_dim = feature_dim
        self.embedding_dim = embedding_dim
        self.user_tower = Tower(feature_dim, embedding_dim)
        self.item_tower = Tower(feature_dim, embedding_dim)

    def user_embeddings(self, features: torch.Tensor) -> torch.Tensor:
        return self.user_tower(features)

    def item_embeddings(self, features: torch.Tensor) -> torch.Tensor:
        return self.item_tower(features)

    def forward(self, user_features: torch.Tensor, item_features: torch.Tensor) -> torch.Tensor:
        return (self.user_embeddings(user_features) * self.item_embeddings(item_features)).sum(dim=-1)


class DINRanker(nn.Module):
    """Candidate-aware ranker with DIN-style attention over historical tracks."""

    def __init__(self, embedding_dim: int = 128, context_dim: int = 2):
        super().__init__()
        self.embedding_dim = embedding_dim
        self.context_dim = context_dim
        self.attention = nn.Sequential(
            nn.Linear(embedding_dim * 4, 128),
            nn.ReLU(),
            nn.Linear(128, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )
        rank_input_dim = embedding_dim * 5 + context_dim + 1
        self.ranker = nn.Sequential(
            nn.Linear(rank_input_dim, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward_with_attention(
        self,
        user_embedding: torch.Tensor,
        history_embeddings: torch.Tensor,
        history_mask: torch.Tensor,
        candidate_embedding: torch.Tensor,
        context: torch.Tensor,
        retrieval_score: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        candidate_expanded = candidate_embedding.unsqueeze(1).expand_as(history_embeddings)
        attention_features = torch.cat(
            [
                history_embeddings,
                candidate_expanded,
                history_embeddings - candidate_expanded,
                history_embeddings * candidate_expanded,
            ],
            dim=-1,
        )
        attention_logits = self.attention(attention_features).squeeze(-1)
        attention_logits = attention_logits.masked_fill(~history_mask, -1e9)
        attention_weights = torch.softmax(attention_logits, dim=1)
        attended_history = torch.sum(history_embeddings * attention_weights.unsqueeze(-1), dim=1)

        combined = torch.cat(
            [
                user_embedding,
                attended_history,
                candidate_embedding,
                user_embedding * candidate_embedding,
                torch.abs(user_embedding - candidate_embedding),
                context,
                retrieval_score.reshape(-1, 1),
            ],
            dim=-1,
        )
        return self.ranker(combined).squeeze(-1), attention_weights

    def forward(
        self,
        user_embedding: torch.Tensor,
        history_embeddings: torch.Tensor,
        history_mask: torch.Tensor,
        candidate_embedding: torch.Tensor,
        context: torch.Tensor,
        retrieval_score: torch.Tensor,
    ) -> torch.Tensor:
        scores, _ = self.forward_with_attention(
            user_embedding,
            history_embeddings,
            history_mask,
            candidate_embedding,
            context,
            retrieval_score,
        )
        return scores
