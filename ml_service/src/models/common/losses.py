"""
Loss functions for training recommendation models
Includes BPR loss, triplet loss, and ranking losses
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional


class BPRLoss(nn.Module):
    """
    Bayesian Personalized Ranking (BPR) Loss
    
    Optimizes the probability that a positive item is ranked higher
    than a negative item for a given user.
    
    Loss = -log(sigmoid(score_positive - score_negative))
    """
    
    def __init__(self):
        """Initialize BPR loss"""
        super().__init__()
    
    def forward(
        self,
        positive_scores: torch.Tensor,
        negative_scores: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute BPR loss
        
        Args:
            positive_scores: Scores for positive user-item pairs [batch_size]
            negative_scores: Scores for negative user-item pairs [batch_size]
        
        Returns:
            BPR loss scalar
        """
        # Compute score difference
        score_diff = positive_scores - negative_scores
        
        # BPR loss: -log(sigmoid(score_diff))
        # Using log1p for numerical stability: -log(sigmoid(x)) = -log(1/(1+exp(-x))) = log(1+exp(-x))
        loss = F.softplus(-score_diff).mean()
        
        return loss


class TripletLoss(nn.Module):
    """
    Triplet Loss for contrastive learning
    
    Ensures that positive items are closer to the user embedding
    than negative items by a margin.
    
    Loss = max(0, margin + distance(anchor, positive) - distance(anchor, negative))
    """
    
    def __init__(self, margin: float = 1.0, distance: str = "cosine"):
        """
        Initialize triplet loss
        
        Args:
            margin: Margin for triplet loss
            distance: Distance metric ('cosine' or 'euclidean')
        """
        super().__init__()
        self.margin = margin
        self.distance = distance
    
    def forward(
        self,
        anchor_emb: torch.Tensor,
        positive_emb: torch.Tensor,
        negative_emb: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute triplet loss
        
        Args:
            anchor_emb: Anchor embeddings (user) [batch_size, embedding_dim]
            positive_emb: Positive embeddings (positive items) [batch_size, embedding_dim]
            negative_emb: Negative embeddings (negative items) [batch_size, embedding_dim]
        
        Returns:
            Triplet loss scalar
        """
        if self.distance == "cosine":
            # For normalized embeddings, cosine distance = 1 - cosine similarity
            # Cosine similarity = dot product of normalized vectors
            pos_sim = (anchor_emb * positive_emb).sum(dim=1)
            neg_sim = (anchor_emb * negative_emb).sum(dim=1)
            pos_dist = 1 - pos_sim
            neg_dist = 1 - neg_sim
        else:  # euclidean
            pos_dist = F.pairwise_distance(anchor_emb, positive_emb)
            neg_dist = F.pairwise_distance(anchor_emb, negative_emb)
        
        # Triplet loss: max(0, margin + positive_distance - negative_distance)
        loss = F.relu(self.margin + pos_dist - neg_dist).mean()
        
        return loss


class InBatchNegativeLoss(nn.Module):
    """
    In-batch negative sampling loss
    
    Uses all other items in the batch as negatives for each user.
    Efficient for training with large batch sizes.
    """
    
    def __init__(self, temperature: float = 1.0):
        """
        Initialize in-batch negative loss
        
        Args:
            temperature: Temperature parameter for softmax (larger = softer distribution)
        """
        super().__init__()
        self.temperature = temperature
    
    def forward(
        self,
        user_emb: torch.Tensor,
        item_emb: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute in-batch negative loss
        
        Args:
            user_emb: User embeddings [batch_size, embedding_dim]
            item_emb: Item embeddings [batch_size, embedding_dim]
            (assumes positive pairs are at same indices)
        
        Returns:
            Loss scalar (cross-entropy over in-batch negatives)
        """
        batch_size = user_emb.shape[0]
        
        # Compute similarity matrix [batch_size, batch_size]
        # Each row i: similarity of user i to all items
        # Diagonal (i, i) is the positive pair
        similarity_matrix = torch.matmul(user_emb, item_emb.t()) / self.temperature
        
        # Labels: diagonal elements are positives (index i)
        labels = torch.arange(batch_size, device=user_emb.device)
        
        # Cross-entropy loss: maximize similarity to positive, minimize to negatives
        loss = F.cross_entropy(similarity_matrix, labels)
        
        return loss


class CombinedLoss(nn.Module):
    """
    Combined loss function using multiple loss components
    
    Can combine BPR loss with regularization terms
    """
    
    def __init__(
        self,
        primary_loss: str = "bpr",
        l2_reg: float = 0.0,
        margin: float = 1.0
    ):
        """
        Initialize combined loss
        
        Args:
            primary_loss: Primary loss type ('bpr', 'triplet', 'in_batch')
            l2_reg: L2 regularization coefficient
            margin: Margin for triplet loss (if used)
        """
        super().__init__()
        self.l2_reg = l2_reg
        
        if primary_loss == "bpr":
            self.primary_loss_fn = BPRLoss()
        elif primary_loss == "triplet":
            self.primary_loss_fn = TripletLoss(margin=margin)
        elif primary_loss == "in_batch":
            self.primary_loss_fn = InBatchNegativeLoss()
        else:
            raise ValueError(f"Unknown primary loss: {primary_loss}")
    
    def forward(
        self,
        positive_scores: Optional[torch.Tensor] = None,
        negative_scores: Optional[torch.Tensor] = None,
        anchor_emb: Optional[torch.Tensor] = None,
        positive_emb: Optional[torch.Tensor] = None,
        negative_emb: Optional[torch.Tensor] = None,
        user_emb: Optional[torch.Tensor] = None,
        item_emb: Optional[torch.Tensor] = None,
        model_params: Optional[list] = None
    ) -> torch.Tensor:
        """
        Compute combined loss
        
        Args:
            positive_scores: For BPR loss
            negative_scores: For BPR loss
            anchor_emb: For triplet loss
            positive_emb: For triplet loss
            negative_emb: For triplet loss
            user_emb: For in-batch negative loss
            item_emb: For in-batch negative loss
            model_params: Model parameters for L2 regularization
        
        Returns:
            Combined loss scalar
        """
        # Compute primary loss
        if isinstance(self.primary_loss_fn, BPRLoss):
            loss = self.primary_loss_fn(positive_scores, negative_scores)
        elif isinstance(self.primary_loss_fn, TripletLoss):
            loss = self.primary_loss_fn(anchor_emb, positive_emb, negative_emb)
        elif isinstance(self.primary_loss_fn, InBatchNegativeLoss):
            loss = self.primary_loss_fn(user_emb, item_emb)
        else:
            raise ValueError("Unknown loss function type")
        
        # Add L2 regularization
        if self.l2_reg > 0 and model_params is not None:
            l2_norm = sum(p.pow(2.0).sum() for p in model_params)
            loss = loss + self.l2_reg * l2_norm
        
        return loss


class RankingLoss(nn.Module):
    """
    Ranking loss for reranker model
    
    Can use pointwise (MSE, BCE) or pairwise (ranknet) losses
    """
    
    def __init__(self, loss_type: str = "mse"):
        """
        Initialize ranking loss
        
        Args:
            loss_type: Loss type ('mse', 'bce', 'ranknet')
        """
        super().__init__()
        self.loss_type = loss_type
        
        if loss_type == "mse":
            self.loss_fn = nn.MSELoss()
        elif loss_type == "bce":
            self.loss_fn = nn.BCEWithLogitsLoss()
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")
    
    def forward(
        self,
        predictions: torch.Tensor,
        targets: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute ranking loss
        
        Args:
            predictions: Predicted scores [batch_size]
            targets: Target scores (relevance labels) [batch_size]
        
        Returns:
            Loss scalar
        """
        if self.loss_type == "mse":
            return self.loss_fn(predictions, targets.float())
        elif self.loss_type == "bce":
            # For binary classification (relevant/not relevant)
            return self.loss_fn(predictions, targets.float())
        else:
            raise ValueError(f"Unknown loss type: {self.loss_type}")


class PairwiseRankingLoss(nn.Module):
    """
    Pairwise ranking loss (RankNet style)
    
    Optimizes that positive items are ranked higher than negative items
    """
    
    def __init__(self):
        """Initialize pairwise ranking loss"""
        super().__init__()
    
    def forward(
        self,
        positive_scores: torch.Tensor,
        negative_scores: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute pairwise ranking loss
        
        Args:
            positive_scores: Scores for positive items [batch_size]
            negative_scores: Scores for negative items [batch_size]
        
        Returns:
            Loss scalar
        """
        # RankNet loss: log(1 + exp(-(pos_score - neg_score)))
        score_diff = positive_scores - negative_scores
        loss = torch.nn.functional.softplus(-score_diff).mean()
        
        return loss

