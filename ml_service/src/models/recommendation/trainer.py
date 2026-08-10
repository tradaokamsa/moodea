"""
Training utilities for recommendation models
"""
import torch
import torch.optim as optim
from torch.utils.data import DataLoader
from typing import Optional
from tqdm import tqdm
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from models.recommendation.models import TwoTowerModel, RerankerModel
from models.common.losses import BPRLoss, TripletLoss, InBatchNegativeLoss, RankingLoss, PairwiseRankingLoss


class TwoTowerTrainer:
    """
    Trainer for two-tower recommendation model
    """
    
    def __init__(
        self,
        model: TwoTowerModel,
        loss_type: str = "bpr",
        learning_rate: float = 1e-3,
        device: Optional[torch.device] = None,
        l2_reg: float = 0.0,
        margin: float = 1.0
    ):
        """
        Initialize trainer
        
        Args:
            model: TwoTowerModel instance
            loss_type: Loss type ('bpr', 'triplet', 'in_batch')
            learning_rate: Learning rate
            device: Device to train on (default: cuda if available)
            l2_reg: L2 regularization coefficient
            margin: Margin for triplet loss
        """
        self.model = model
        self.device = device if device else torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.model.to(self.device)
        
        # Setup loss function
        if loss_type == "bpr":
            self.loss_fn = BPRLoss()
        elif loss_type == "triplet":
            self.loss_fn = TripletLoss(margin=margin)
        elif loss_type == "in_batch":
            self.loss_fn = InBatchNegativeLoss()
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")
        
        self.loss_type = loss_type
        
        # Setup optimizer
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=l2_reg
        )
        
        # Training history
        self.train_losses = []
        self.val_losses = []
    
    def train_epoch(
        self,
        dataloader: DataLoader,
        progress_bar: bool = True
    ) -> float:
        """
        Train for one epoch
        
        Args:
            dataloader: Training DataLoader
            progress_bar: Whether to show progress bar
        
        Returns:
            Average training loss
        """
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        iterator = tqdm(dataloader, desc="Training") if progress_bar else dataloader
        
        for batch in iterator:
            # Move batch to device
            # Handle both dict and tensor formats
            if isinstance(batch['user_features'], dict):
                user_features = {
                    k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                    for k, v in batch['user_features'].items()
                }
            else:
                # If it's already a tensor, convert to dict format expected by model
                # This is a simplified case - in practice you'd have proper feature dict
                user_features = {'features': batch['user_features'].to(self.device)}
            
            if isinstance(batch['item_features'], dict):
                item_features = {
                    k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                    for k, v in batch['item_features'].items()
                }
            else:
                item_features = {'features': batch['item_features'].to(self.device)}
            
            # Compute loss based on loss type
            labels = batch['labels'].to(self.device)
            
            if self.loss_type == "bpr":
                # For BPR, we need positive and negative scores
                # Filter positive and negative pairs
                positive_mask = labels > 0
                negative_mask = ~positive_mask
                
                if positive_mask.sum() > 0 and negative_mask.sum() > 0:
                    # Get positive pairs
                    pos_user_feat = {k: v[positive_mask] for k, v in user_features.items()}
                    pos_item_feat = {k: v[positive_mask] for k, v in item_features.items()}
                    
                    # Get negative pairs
                    neg_user_feat = {k: v[negative_mask] for k, v in user_features.items()}
                    neg_item_feat = {k: v[negative_mask] for k, v in item_features.items()}
                    
                    positive_scores = self.model(pos_user_feat, pos_item_feat)
                    negative_scores = self.model(neg_user_feat, neg_item_feat)
                    loss = self.loss_fn(positive_scores, negative_scores)
                else:
                    continue
            
            elif self.loss_type == "triplet":
                # For triplet loss, batch should contain anchor, positive, negative
                # This is a simplified version - in practice you'd structure the batch differently
                user_emb = self.model.get_user_embedding(user_features)
                item_emb = self.model.get_item_embedding(item_features)
                # Simplified: treat first half as positives, second half as negatives
                batch_size = user_emb.shape[0]
                mid = batch_size // 2
                anchor = user_emb[:mid]
                positive = item_emb[:mid]
                negative = item_emb[mid:mid*2] if mid*2 <= batch_size else item_emb[mid:]
                loss = self.loss_fn(anchor, positive, negative)
            
            elif self.loss_type == "in_batch":
                user_emb = self.model.get_user_embedding(user_features)
                item_emb = self.model.get_item_embedding(item_features)
                loss = self.loss_fn(user_emb, item_emb)
            
            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        avg_loss = total_loss / num_batches if num_batches > 0 else 0.0
        self.train_losses.append(avg_loss)
        return avg_loss
    
    def validate(
        self,
        dataloader: DataLoader
    ) -> float:
        """
        Validate model
        
        Args:
            dataloader: Validation DataLoader
        
        Returns:
            Average validation loss
        """
        self.model.eval()
        total_loss = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for batch in dataloader:
                # Handle both dict and tensor formats
                if isinstance(batch['user_features'], dict):
                    user_features = {
                        k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                        for k, v in batch['user_features'].items()
                    }
                else:
                    user_features = {'features': batch['user_features'].to(self.device)}
                
                if isinstance(batch['item_features'], dict):
                    item_features = {
                        k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                        for k, v in batch['item_features'].items()
                    }
                else:
                    item_features = {'features': batch['item_features'].to(self.device)}
                
                # Compute loss (similar to training)
                labels = batch['labels'].to(self.device)
                
                if self.loss_type == "bpr":
                    positive_mask = labels > 0
                    negative_mask = ~positive_mask
                    
                    if positive_mask.sum() > 0 and negative_mask.sum() > 0:
                        pos_user_feat = {k: v[positive_mask] for k, v in user_features.items()}
                        pos_item_feat = {k: v[positive_mask] for k, v in item_features.items()}
                        neg_user_feat = {k: v[negative_mask] for k, v in user_features.items()}
                        neg_item_feat = {k: v[negative_mask] for k, v in item_features.items()}
                        
                        positive_scores = self.model(pos_user_feat, pos_item_feat)
                        negative_scores = self.model(neg_user_feat, neg_item_feat)
                        loss = self.loss_fn(positive_scores, negative_scores)
                    else:
                        continue
                
                elif self.loss_type == "in_batch":
                    user_emb = self.model.get_user_embedding(user_features)
                    item_emb = self.model.get_item_embedding(item_features)
                    loss = self.loss_fn(user_emb, item_emb)
                
                total_loss += loss.item()
                num_batches += 1
        
        avg_loss = total_loss / num_batches if num_batches > 0 else 0.0
        self.val_losses.append(avg_loss)
        return avg_loss
    
    def train(
        self,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
        num_epochs: int = 10,
        save_path: Optional[str] = None
    ):
        """
        Train model for multiple epochs
        
        Args:
            train_loader: Training DataLoader
            val_loader: Optional validation DataLoader
            num_epochs: Number of training epochs
            save_path: Optional path to save best model
        """
        best_val_loss = float('inf')
        
        for epoch in range(num_epochs):
            print(f"\nEpoch {epoch + 1}/{num_epochs}")
            train_loss = self.train_epoch(train_loader)
            print(f"Train Loss: {train_loss:.4f}")
            
            if val_loader is not None:
                val_loss = self.validate(val_loader)
                print(f"Val Loss: {val_loss:.4f}")
                
                # Save best model
                if val_loss < best_val_loss and save_path:
                    best_val_loss = val_loss
                    torch.save(self.model.state_dict(), save_path)
                    print(f"Saved best model to {save_path}")
        
        print("\nTraining complete!")


class RerankerTrainer:
    """
    Trainer for reranker model
    """
    
    def __init__(
        self,
        reranker: RerankerModel,
        learning_rate: float = 1e-3,
        device: Optional[torch.device] = None,
        loss_type: str = "mse"
    ):
        """
        Initialize reranker trainer
        
        Args:
            reranker: RerankerModel instance
            learning_rate: Learning rate
            device: Device to train on
            loss_type: Loss type ('mse', 'bce', 'pairwise')
        """
        self.reranker = reranker
        self.device = device if device else torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.reranker.to(self.device)
        
        # Setup loss
        if loss_type in ["mse", "bce"]:
            self.loss_fn = RankingLoss(loss_type=loss_type)
        elif loss_type == "pairwise":
            self.loss_fn = PairwiseRankingLoss()
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")
        
        self.loss_type = loss_type
        
        # Setup optimizer
        self.optimizer = optim.Adam(
            self.reranker.parameters(),
            lr=learning_rate
        )
    
    def train_epoch(
        self,
        dataloader: DataLoader,
        progress_bar: bool = True
    ) -> float:
        """Train reranker for one epoch"""
        self.reranker.train()
        total_loss = 0.0
        num_batches = 0
        
        iterator = tqdm(dataloader, desc="Training Reranker") if progress_bar else dataloader
        
        for batch in iterator:
            user_emb = batch['user_emb'].to(self.device)
            item_emb = batch['item_emb'].to(self.device)
            context = batch.get('context', None)
            if context is not None:
                context = context.to(self.device)
            
            targets = batch['targets'].to(self.device)
            
            # Forward pass
            predictions = self.reranker(user_emb, item_emb, context)
            
            # Compute loss
            if self.loss_type == "pairwise":
                # For pairwise, need positive and negative scores
                positive_mask = targets > 0
                negative_mask = ~positive_mask
                if positive_mask.sum() > 0 and negative_mask.sum() > 0:
                    positive_scores = predictions[positive_mask]
                    negative_scores = predictions[negative_mask]
                    loss = self.loss_fn(positive_scores, negative_scores)
                else:
                    continue
            else:
                loss = self.loss_fn(predictions, targets)
            
            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        return total_loss / num_batches if num_batches > 0 else 0.0

