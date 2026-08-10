from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    catalog_csv: Path = Path(
        os.getenv("CATALOG_CSV", str(SERVICE_ROOT / "278k_labelled_uri.csv"))
    )
    artifact_dir: Path = Path(
        os.getenv("ARTIFACT_DIR", str(SERVICE_ROOT / "data" / "artifacts"))
    )
    event_dir: Path = Path(
        os.getenv("EVENT_DIR", str(SERVICE_ROOT / "data" / "events"))
    )
    auto_bootstrap: bool = _env_bool("AUTO_BOOTSTRAP_SYNTHETIC", True)
    bootstrap_tracks: int = int(os.getenv("SYNTHETIC_TRACKS", "5000"))
    bootstrap_users: int = int(os.getenv("SYNTHETIC_USERS", "256"))
    bootstrap_epochs: int = int(os.getenv("SYNTHETIC_EPOCHS", "5"))
    random_seed: int = int(os.getenv("RANDOM_SEED", "42"))
    retrieval_candidates: int = int(os.getenv("RETRIEVAL_CANDIDATES", "100"))
    diversity_lambda: float = float(os.getenv("DIVERSITY_LAMBDA", "0.85"))


settings = Settings()
