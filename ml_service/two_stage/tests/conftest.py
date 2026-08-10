from __future__ import annotations

from pathlib import Path

import pytest

from src.training import train_synthetic_pipeline


@pytest.fixture(scope="session")
def trained_artifact_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    artifact_dir = tmp_path_factory.mktemp("ml-artifacts")
    train_synthetic_pipeline(
        catalog_csv=Path(__file__).resolve().parents[1] / "278k_labelled_uri.csv",
        artifact_dir=artifact_dir,
        max_tracks=200,
        num_users=16,
        epochs=1,
        ranker_epochs=1,
        seed=9,
    )
    return artifact_dir
