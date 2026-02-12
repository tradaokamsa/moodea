"""
ANN Index Service
FAISS IndexFlatIP for fast approximate nearest-neighbor track retrieval.
"""
import json
import logging
import os
from typing import List, Optional, Tuple

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class ANNIndexService:
    """
    Manages a FAISS inner-product index over item (track) embeddings.

    Because embeddings are L2-normalized in the two-tower model, inner product
    equals cosine similarity.
    """

    def __init__(self, index_path: Optional[str] = None):
        self.index: Optional[faiss.IndexFlatIP] = None
        self.track_ids: List[str] = []
        self.index_path = index_path or os.getenv("ANN_INDEX_PATH", "./data/ann_index.bin")
        self.mapping_path = self.index_path.replace(".bin", "_mapping.json")

        # Try to load existing index
        if os.path.exists(self.index_path) and os.path.exists(self.mapping_path):
            self.load_index()

    def build_index(self, track_ids: List[str], embeddings: np.ndarray):
        """
        Build FAISS index from embeddings.

        Args:
            track_ids: Ordered list of track IDs matching embedding rows.
            embeddings: numpy array of shape [num_tracks, embedding_dim], L2-normalized.
        """
        if embeddings.ndim != 2 or len(track_ids) != embeddings.shape[0]:
            raise ValueError("track_ids length must match embeddings row count")

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings.astype(np.float32))
        self.track_ids = list(track_ids)
        logger.info(f"Built FAISS IndexFlatIP with {len(track_ids)} vectors, dim={dim}")

    def query(self, query_embedding: np.ndarray, k: int = 20) -> List[Tuple[str, float]]:
        """
        Query index for top-k similar tracks.

        Args:
            query_embedding: 1-D or 2-D array [1, dim].
            k: number of results.

        Returns:
            List of (track_id, score) tuples sorted by descending score.
        """
        if self.index is None or len(self.track_ids) == 0:
            return []

        qvec = np.asarray(query_embedding, dtype=np.float32)
        if qvec.ndim == 1:
            qvec = qvec.reshape(1, -1)

        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(qvec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append((self.track_ids[idx], float(score)))
        return results

    def save_index(self, path: Optional[str] = None):
        """Persist FAISS index and track ID mapping to disk."""
        path = path or self.index_path
        mapping_path = path.replace(".bin", "_mapping.json")

        if self.index is None:
            logger.warning("No index to save")
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        faiss.write_index(self.index, path)
        with open(mapping_path, "w") as f:
            json.dump(self.track_ids, f)
        logger.info(f"Saved FAISS index ({self.index.ntotal} vectors) to {path}")

    def load_index(self, path: Optional[str] = None):
        """Load FAISS index and track ID mapping from disk."""
        path = path or self.index_path
        mapping_path = path.replace(".bin", "_mapping.json")

        if not os.path.exists(path) or not os.path.exists(mapping_path):
            logger.warning(f"Index files not found at {path}")
            return

        self.index = faiss.read_index(path)
        with open(mapping_path) as f:
            self.track_ids = json.load(f)
        logger.info(f"Loaded FAISS index ({self.index.ntotal} vectors) from {path}")

    @property
    def is_ready(self) -> bool:
        return self.index is not None and len(self.track_ids) > 0
