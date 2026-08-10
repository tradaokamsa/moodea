# Moodea ML recommendation service

The raw catalog is intentionally not stored in Git. Before training or building
the Docker image, place `278k_labelled_uri.csv` in the `ml_service/two_stage/` directory,
or set `CATALOG_CSV` to another compatible catalog path.

This service provides a runnable two-stage recommendation backend:

1. A two-tower retrieval model produces 128-dimensional L2-normalized user and track embeddings.
2. FAISS retrieves the top 100 tracks with inner-product search.
3. A DIN-style candidate-aware ranker attends over user history and produces fine-ranking scores.
4. A greedy MMR-style pass adds content diversity before returning the top 20.

The initial development artifacts are trained from the labelled track catalog and reproducible synthetic users, impressions, and interactions. Real interaction logs can replace the synthetic builder without changing the serving API.

## Local setup

From `ml_service/two_stage/`:

```sh
python3 -m src.bootstrap --tracks 5000 --users 256 --epochs 5
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

Run the regression tests with development dependencies:

```sh
pip install -r requirements-dev.txt
pytest -q
```

With no artifacts present, startup automatically runs the same synthetic bootstrap when `AUTO_BOOTSTRAP_SYNTHETIC=true`.

## API

Health and catalog:

```sh
curl http://localhost:8001/health
curl http://localhost:8001/catalog/stats
```

Known synthetic user:

```sh
curl -X POST http://localhost:8001/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"synthetic-user-0000","limit":20,"context":{"hour":20}}'
```

Cold-start by mood:

```sh
curl -X POST http://localhost:8001/recommendations \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"new-user","limit":20,"mood":"energetic"}'
```

Record feedback using the `request_id` returned by recommendations:

```sh
curl -X POST http://localhost:8001/interactions \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"new-user","track_id":"TRACK_ID","interaction_type":"like","request_id":"REQUEST_ID"}'
```

Runtime impressions and interactions are appended to `data/events/*.jsonl`. Synthetic source tables and model metrics are written to `data/artifacts/`.

The generated training tables are:

- `synthetic_impressions.parquet`: one row per shown candidate, including request, user, track, retrieval rank/score, final rank, timestamp, and model/catalog versions.
- `synthetic_interactions.parquet`: one row per positive or negative signal, including stable event ID, attribution IDs, user, track, event type, score, sample weight, timestamp, and source.
- `synthetic_users.json`: development user profiles plus history/train/held-out track IDs.

At runtime, always send the recommendation `request_id` back with the interaction. `like`, `continue`, and `skip` map to weights `3`, `1`, and `-1`. The online user state updates immediately; JSONL logs are the durable input for the next offline dataset build. Kafka is optional in local development and the Go backend uses a logged stub when `KAFKA_BROKERS` is empty.

Each recommended track exposes the stages of the two-stage model:

- `retrieval_rank` and `retrieval_score`: where FAISS/two-tower retrieval placed it.
- `ranker_score`: the candidate-aware DIN output before score blending.
- `final_rank`: its position after ranking and diversity selection.
- `attention_history_track_ids`: up to three historical tracks receiving the strongest DIN attention for that candidate.

## Point-in-time-correct datasets

Build retrieval and ranking examples from the synthetic event tables:

```sh
python3 -m src.build_dataset
```

Build them from live serving logs:

```sh
python3 -m src.build_dataset \
  --impressions data/events/impressions.jsonl \
  --interactions data/events/interactions.jsonl \
  --output-dir data/datasets/live
```

The default 24-hour attribution window means a recommendation is not emitted as a training row until its label has matured. An attributed like/continue becomes a positive, a skip becomes a negative, and a mature impression without feedback becomes a low-weight negative. For every row, `history_track_ids` contains only positive events whose timestamps are strictly earlier than `feature_timestamp`; the builder fails if it detects future-history leakage.

Outputs:

- `ranking_examples.parquet`: every mature impression with label, weight, retrieval/ranking fields, and historical tracks as of impression time.
- `retrieval_examples.parquet`: positive targets and the history available before their impressions.
- `dataset_report.json`: source counts, label distribution, deduplication count, attribution settings, and leakage violations.

## Training variants

In-batch contrastive learning is the default:

```sh
python3 -m src.bootstrap --loss in_batch
```

BPR uses explicitly aligned `(user, positive, negative)` triples:

```sh
python3 -m src.bootstrap --loss bpr
```

Every training run writes `metrics.json` with retrieval loss, ranker loss, Recall@100, and NDCG@100.
