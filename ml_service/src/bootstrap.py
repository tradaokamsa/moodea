from __future__ import annotations

import argparse
import json

from .config import settings
from .training import train_synthetic_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic Moodea recommendation artifacts")
    parser.add_argument("--tracks", type=int, default=settings.bootstrap_tracks)
    parser.add_argument("--users", type=int, default=settings.bootstrap_users)
    parser.add_argument("--epochs", type=int, default=settings.bootstrap_epochs)
    parser.add_argument("--ranker-epochs", type=int, default=3)
    parser.add_argument("--loss", choices=["in_batch", "bpr"], default="in_batch")
    parser.add_argument("--seed", type=int, default=settings.random_seed)
    args = parser.parse_args()
    result = train_synthetic_pipeline(
        catalog_csv=settings.catalog_csv,
        artifact_dir=settings.artifact_dir,
        max_tracks=args.tracks,
        num_users=args.users,
        epochs=args.epochs,
        ranker_epochs=args.ranker_epochs,
        loss_type=args.loss,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "artifact_dir": str(result.artifact_dir),
                "retrieval_loss": result.retrieval_loss,
                "ranker_loss": result.ranker_loss,
                "recall_at_100": result.recall_at_100,
                "ndcg_at_100": result.ndcg_at_100,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
