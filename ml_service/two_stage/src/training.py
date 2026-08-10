from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import random

import faiss
import numpy as np
import torch
import torch.nn.functional as functional

torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from .catalog import Catalog, load_seed_catalog, save_catalog
from .models import DINRanker, TwoTowerModel
from .synthetic import SyntheticDataset, generate_synthetic_dataset, save_synthetic_dataset


@dataclass
class TrainingResult:
    retrieval_loss: float
    ranker_loss: float
    recall_at_100: float
    ndcg_at_100: float
    artifact_dir: Path


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def _device() -> torch.device:
    return torch.device("cpu")


def _context(hours: np.ndarray) -> np.ndarray:
    radians = hours.astype(np.float32) / 24.0 * (2.0 * math.pi)
    return np.stack([np.sin(radians), np.cos(radians)], axis=1).astype(np.float32)


def _train_retrieval(
    model: TwoTowerModel,
    catalog: Catalog,
    dataset: SyntheticDataset,
    epochs: int,
    batch_size: int,
    loss_type: str,
    seed: int,
) -> float:
    device = _device()
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    rng = np.random.default_rng(seed)
    final_loss = 0.0

    for _ in range(epochs):
        order = rng.permutation(len(dataset.user_ids))
        losses: list[float] = []
        for start in range(0, len(order), batch_size):
            user_indices = order[start : start + batch_size]
            if len(user_indices) < 2:
                continue
            positive_indices = np.asarray(
                [rng.choice(dataset.train_positive_indices[index]) for index in user_indices],
                dtype=np.int64,
            )
            user_features = torch.from_numpy(dataset.user_profiles[user_indices]).to(device)
            positive_features = torch.from_numpy(catalog.features[positive_indices]).to(device)
            user_embeddings = model.user_embeddings(user_features)
            positive_embeddings = model.item_embeddings(positive_features)

            if loss_type == "bpr":
                negative_indices = rng.integers(0, len(catalog.frame), size=len(user_indices))
                for row, user_index in enumerate(user_indices):
                    positives = set(dataset.history_indices[user_index]) | set(
                        dataset.train_positive_indices[user_index]
                    ) | set(dataset.heldout_positive_indices[user_index])
                    while int(negative_indices[row]) in positives:
                        negative_indices[row] = rng.integers(0, len(catalog.frame))
                negative_features = torch.from_numpy(catalog.features[negative_indices]).to(device)
                negative_embeddings = model.item_embeddings(negative_features)
                positive_scores = (user_embeddings * positive_embeddings).sum(dim=1)
                negative_scores = (user_embeddings * negative_embeddings).sum(dim=1)
                loss = functional.softplus(-(positive_scores - negative_scores)).mean()
            else:
                logits = user_embeddings @ positive_embeddings.T / 0.07
                labels = torch.arange(len(user_indices), device=device)
                loss = 0.5 * (
                    functional.cross_entropy(logits, labels)
                    + functional.cross_entropy(logits.T, labels)
                )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        final_loss = float(np.mean(losses)) if losses else 0.0
    return final_loss


def _item_embeddings(model: TwoTowerModel, catalog: Catalog, batch_size: int = 2048) -> np.ndarray:
    model.eval()
    values: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(catalog.frame), batch_size):
            features = torch.from_numpy(catalog.features[start : start + batch_size])
            values.append(model.item_embeddings(features).cpu().numpy().astype(np.float32))
    return np.concatenate(values, axis=0)


def _build_index(item_embeddings: np.ndarray) -> faiss.Index:
    index = faiss.IndexFlatIP(item_embeddings.shape[1])
    index.add(np.ascontiguousarray(item_embeddings, dtype=np.float32))
    return index


def _evaluate_retrieval(
    model: TwoTowerModel,
    index: faiss.Index,
    dataset: SyntheticDataset,
    k: int = 100,
) -> tuple[float, float]:
    model.eval()
    with torch.no_grad():
        user_embeddings = model.user_embeddings(torch.from_numpy(dataset.user_profiles)).cpu().numpy()
    search_k = min(index.ntotal, k + 64)
    _, indices = index.search(np.ascontiguousarray(user_embeddings, dtype=np.float32), search_k)
    recalls: list[float] = []
    ndcgs: list[float] = []
    for user_index, retrieved in enumerate(indices):
        excluded = set(dataset.history_indices[user_index]) | set(dataset.train_positive_indices[user_index])
        ranked = [int(item) for item in retrieved if int(item) not in excluded][:k]
        relevant = set(dataset.heldout_positive_indices[user_index])
        hits = [1 if item in relevant else 0 for item in ranked]
        recalls.append(sum(hits) / max(len(relevant), 1))
        dcg = sum(hit / math.log2(rank + 2) for rank, hit in enumerate(hits))
        ideal_hits = min(len(relevant), k)
        idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
        ndcgs.append(dcg / idcg if idcg else 0.0)
    return float(np.mean(recalls)), float(np.mean(ndcgs))


def _padded_history_embeddings(
    histories: list[list[int]], item_embeddings: np.ndarray, max_history: int = 20
) -> tuple[np.ndarray, np.ndarray]:
    result = np.zeros((len(histories), max_history, item_embeddings.shape[1]), dtype=np.float32)
    mask = np.zeros((len(histories), max_history), dtype=bool)
    for row, history in enumerate(histories):
        selected = history[-max_history:]
        result[row, : len(selected)] = item_embeddings[selected]
        mask[row, : len(selected)] = True
    return result, mask


def _train_ranker(
    ranker: DINRanker,
    model: TwoTowerModel,
    item_embeddings: np.ndarray,
    index: faiss.Index,
    dataset: SyntheticDataset,
    epochs: int,
    seed: int,
) -> float:
    rng = np.random.default_rng(seed + 1)
    model.eval()
    with torch.no_grad():
        user_embeddings = model.user_embeddings(torch.from_numpy(dataset.user_profiles)).cpu().numpy()
    history_embeddings, history_mask = _padded_history_embeddings(
        dataset.history_indices, item_embeddings
    )
    _, retrieved = index.search(np.ascontiguousarray(user_embeddings, dtype=np.float32), 100)
    positive_indices = np.asarray(
        [targets[0] for targets in dataset.train_positive_indices], dtype=np.int64
    )
    negative_indices: list[int] = []
    for user_index, candidates in enumerate(retrieved):
        excluded = set(dataset.history_indices[user_index]) | set(
            dataset.train_positive_indices[user_index]
        ) | set(dataset.heldout_positive_indices[user_index])
        available = [int(item) for item in candidates if int(item) not in excluded]
        negative_indices.append(available[0] if available else int(rng.integers(0, len(item_embeddings))))
    negative_indices_array = np.asarray(negative_indices, dtype=np.int64)

    positive_embeddings = item_embeddings[positive_indices]
    negative_embeddings = item_embeddings[negative_indices_array]
    positive_retrieval = np.sum(user_embeddings * positive_embeddings, axis=1).astype(np.float32)
    negative_retrieval = np.sum(user_embeddings * negative_embeddings, axis=1).astype(np.float32)
    contexts = _context(dataset.preferred_hours)

    optimizer = torch.optim.AdamW(ranker.parameters(), lr=2e-3, weight_decay=1e-5)
    ranker.train()
    final_loss = 0.0
    batch_size = 64
    for _ in range(max(1, epochs)):
        order = rng.permutation(len(dataset.user_ids))
        losses: list[float] = []
        for start in range(0, len(order), batch_size):
            rows = order[start : start + batch_size]
            user_tensor = torch.from_numpy(user_embeddings[rows])
            history_tensor = torch.from_numpy(history_embeddings[rows])
            mask_tensor = torch.from_numpy(history_mask[rows])
            context_tensor = torch.from_numpy(contexts[rows])
            positive_logits = ranker(
                user_tensor,
                history_tensor,
                mask_tensor,
                torch.from_numpy(positive_embeddings[rows]),
                context_tensor,
                torch.from_numpy(positive_retrieval[rows]),
            )
            negative_logits = ranker(
                user_tensor,
                history_tensor,
                mask_tensor,
                torch.from_numpy(negative_embeddings[rows]),
                context_tensor,
                torch.from_numpy(negative_retrieval[rows]),
            )
            pointwise = functional.binary_cross_entropy_with_logits(
                torch.cat([positive_logits, negative_logits]),
                torch.cat([torch.ones_like(positive_logits), torch.zeros_like(negative_logits)]),
            )
            pairwise = functional.softplus(-(positive_logits - negative_logits)).mean()
            loss = pointwise + 0.25 * pairwise
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        final_loss = float(np.mean(losses)) if losses else 0.0
    return final_loss


def train_synthetic_pipeline(
    catalog_csv: Path,
    artifact_dir: Path,
    max_tracks: int = 5000,
    num_users: int = 256,
    epochs: int = 5,
    ranker_epochs: int = 3,
    loss_type: str = "in_batch",
    seed: int = 42,
) -> TrainingResult:
    _seed_everything(seed)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_seed_catalog(catalog_csv, max_tracks=max_tracks, seed=seed)
    manifest = save_catalog(catalog, artifact_dir, catalog_csv)
    synthetic = generate_synthetic_dataset(catalog, num_users=num_users, seed=seed)
    save_synthetic_dataset(synthetic, catalog, artifact_dir)

    model = TwoTowerModel(feature_dim=catalog.feature_dim, embedding_dim=128)
    retrieval_loss = _train_retrieval(
        model,
        catalog,
        synthetic,
        epochs=max(1, epochs),
        batch_size=min(128, num_users),
        loss_type=loss_type,
        seed=seed,
    )
    item_embeddings = _item_embeddings(model, catalog)
    index = _build_index(item_embeddings)
    recall, ndcg = _evaluate_retrieval(model, index, synthetic, k=100)

    ranker = DINRanker(embedding_dim=128, context_dim=2)
    ranker_loss = _train_ranker(
        ranker,
        model,
        item_embeddings,
        index,
        synthetic,
        epochs=ranker_epochs,
        seed=seed,
    )

    torch.save(
        {
            "state_dict": model.state_dict(),
            "feature_dim": catalog.feature_dim,
            "embedding_dim": 128,
        },
        artifact_dir / "two_tower.pt",
    )
    torch.save(
        {"state_dict": ranker.state_dict(), "embedding_dim": 128, "context_dim": 2},
        artifact_dir / "din_ranker.pt",
    )
    np.save(artifact_dir / "item_embeddings.npy", item_embeddings)
    faiss.write_index(index, str(artifact_dir / "faiss.index"))
    metrics: dict[str, Any] = {
        "retrieval_loss": retrieval_loss,
        "ranker_loss": ranker_loss,
        "recall_at_100": recall,
        "ndcg_at_100": ndcg,
        "loss_type": loss_type,
        "synthetic_users": num_users,
        "epochs": epochs,
    }
    (artifact_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest.update(
        {
            "model_version": "two-tower-synthetic-v1",
            "ranker_version": "din-synthetic-v1",
            "synthetic_users": num_users,
            "metrics": metrics,
        }
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return TrainingResult(
        retrieval_loss=retrieval_loss,
        ranker_loss=ranker_loss,
        recall_at_100=recall,
        ndcg_at_100=ndcg,
        artifact_dir=artifact_dir,
    )
