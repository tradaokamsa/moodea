# ML Service

Python FastAPI service for mood prediction, recommendation inference, and track promotion.

The standalone synthetic two-tower + DIN implementation is isolated in
`two_stage/`. It has its own dependencies, Dockerfile, API, tests, and setup
instructions so it can be evaluated without replacing the Feast/MLflow stack.

## Structure

- `src/main.py`: FastAPI application with endpoints
- `src/services/`: Service modules (ANN index, track promotion)
- `src/pipelines/`: Training and inference pipelines
- `src/feature_engineering/`: Feast client wrapper
- `src/mlflow/`: MLFlow integration
- `two_stage/`: standalone two-tower retrieval, FAISS, and DIN ranking service

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (copy `.env.example` to `.env`)

3. Run service:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

## Endpoints

- `POST /ml/mood/predict`: Predict mood for tracks
- `POST /recommendations`: Get personalized recommendations
- `POST /admin/tracks/promote`: Promote track to Feast
- `GET /health`: Health check
