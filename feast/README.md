# Feast Feature Store

Centralized feature management with Redis (online) and Parquet/DuckDB (offline).

## Structure

- `feature_store.yaml`: Feast configuration
- `features/`: FeatureView definitions (track_features, user_features, interaction_features)
- `data/parquet/`: Offline feature storage (Parquet files)
- `registry/`: Feast registry (SQLite database)

## Setup

1. Initialize Feast:
```bash
feast apply
```

2. Materialize features (optional):
```bash
feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
```

## Feature Views

- **track_features**: Global track catalog (offline-only)
- **user_features**: User preferences (online + offline)
- **interaction_features**: Interaction history (online + offline)

