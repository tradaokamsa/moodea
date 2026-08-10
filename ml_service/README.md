# ML Service

Python FastAPI service for mood prediction, recommendation inference, and track promotion.

## Structure

- `src/main.py`: FastAPI application with endpoints
- `src/services/`: Service modules (ANN index, track promotion)
- `src/pipelines/`: Training and inference pipelines
- `src/feature_engineering/`: Feast client wrapper
- `src/mlflow/`: MLFlow integration

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

