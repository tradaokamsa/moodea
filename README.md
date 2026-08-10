# Moodea 🎵

**A Real-Time Music Recommendation System Powered by Machine Learning**

Moodea is a production-ready, full-stack music recommendation platform that combines Spotify's rich music data with advanced ML models to deliver personalized music recommendations in real-time. The system features high-concurrency processing, low-latency inference, and a scalable microservices architecture.

---

## 🎯 Overview

Moodea provides personalized music recommendations based on:
- **Audio Features**: Danceability, energy, valence, tempo, and more
- **Mood Prediction**: ML-powered mood classification (happy, sad, energetic, calm)
- **User Interactions**: Real-time learning from user likes, skips, and continues
- **Listening Patterns**: Analysis of top tracks, artists, playlists, and listening history

The system is designed for **low-latency inference** (<50ms) and **high-throughput processing** (100+ parallel tasks) with real-time feature updates via Kafka streaming.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React :3000)                         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     GO BACKEND (Gin :8080)                              │
│                                                                         │
│  Auth: Spotify OAuth → JWT          Spotify API Proxy (8 endpoints)     │
│  WorkerPool (NumCPU workers)        BatchProcess[T] (50/batch)          │
│  ProcessUserFeaturesAsync           6 concurrent goroutines + nested    │
│  Kafka SyncProducer (stub mode)     Redis response cache (5-min TTL)    │
│                                                                         │
│  Topics produced:                                                       │
│    • user-events (login, track discovery)                               │
│    • interaction-events (skip/continue/like with scores)                │
└──────┬────────────┬──────────────┬──────────────┬───────────────────────┘
       │            │              │              │
  ┌────▼──┐   ┌────▼────┐   ┌────▼────┐   ┌────▼──────────────────┐
  │MongoDB│   │  Redis  │   │  Kafka  │   │ ML Service (FastAPI   │
  │:27017 │   │  :6379  │   │  :9092  │   │ :8001)                │
  └───────┘   └────┬────┘   └────┬────┘   │                      │
                   │              │        │ Endpoints:            │
              Feast Online    ┌───┴───┐    │  POST /ml/mood/predict│
              Store (user &   │       │    │  POST /recommendations│
              interaction     │       │    │  POST /admin/train    │
              features)       │       │    │  POST /admin/materialize
                              │       │    │  POST /admin/tracks/* │
                              ▼       ▼    └──────────┬────────────┘
                         ┌─────────────┐              │
                         │   FLINK     │     ┌────────▼─────────┐
                         │   :8081     │     │ Inference Pipeline│
                         │             │     │                   │
                         │ Jobs:       │     │ 1. Redis feature  │
                         │ • interact  │     │    fetch (~1ms)   │
                         │   aggregat. │     │ 2. User embedding │
                         │ • user      │     │    (~1ms)         │
                         │   features  │     │ 3. FAISS ANN      │
                         │             │     │    query (~1ms)   │
                         │ Windowed    │     │ 4. Reranker       │
                         │ aggregation │     │    (~5ms)         │
                         │ exactly-once│     │ Target: <50ms     │
                         └──────┬──────┘     └──────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   FEAST FEATURE STORE │
                    │                       │
                    │ Offline: Parquet      │
                    │   • track_features    │
                    │   • user_features     │
                    │   • interaction_feat. │
                    │                       │
                    │ Online: Redis         │
                    │   • user_features     │
                    │   • interaction_feat. │
                    └───────────────────────┘
```

---

## ✨ Features

### Current (Phase 1 - Content-Based)
- ✅ **Spotify OAuth Authentication** - Secure user login with JWT tokens
- ✅ **High-Concurrency Track Extraction** - Worker pools processing 100+ parallel tasks
- ✅ **Audio Feature Extraction** - 9 audio features from Spotify API
- ✅ **Mood Prediction** - Random Forest classifier for mood classification
- ✅ **Content-Based Recommendations** - Cosine similarity on audio features + mood
- ✅ **Track Candidate Management** - MongoDB storage with approval workflow
- ✅ **Feast Feature Store Integration** - Offline Parquet storage for track features
- ✅ **User Interaction Recording** - Like, skip, continue with scoring
- ✅ **Kafka Event Publishing** - User events and interaction events (stub mode)

### Planned (Phases 2-6)
- 🔄 **Neural Two-Tower Model** - Learned embeddings for better recommendations
- 🔄 **FAISS ANN Index** - Sub-millisecond candidate retrieval
- 🔄 **Low-Latency Inference** - Redis-backed online features (<50ms)
- 🔄 **Real-Time Streaming** - Kafka consumers for feature updates
- 🔄 **Apache Flink Processing** - Windowed aggregations with exactly-once semantics
- 🔄 **MLflow Model Registry** - Model versioning and tracking
- 🔄 **Next.js Frontend** - Modern React app with Tailwind CSS
- 🔄 **Periodic Retraining** - Automated model updates

---

## 🛠️ Tech Stack

### Backend
- **Go 1.24+** with **Gin** framework
- **MongoDB** - User data, track candidates, interactions
- **Redis** - Response caching + Feast online store
- **Kafka** - Event streaming (optional, stub mode supported)
- **Apache Flink** - Stream processing (planned)

### ML Service
- **Python 3.12+** with **FastAPI**
- **PyTorch** - Deep learning models
- **scikit-learn** - Mood prediction (Random Forest)
- **FAISS** - Approximate nearest neighbor search
- **Feast** - Feature store (Redis + Parquet)
- **MLflow** - Model tracking and registry

### Frontend
- **React 18** (current) / **Next.js 14** (planned)
- **TypeScript** (planned)
- **Tailwind CSS** (planned)

### Infrastructure
- **Docker** & **Docker Compose** - Containerization
- **Spotify Web API** - Music data and audio features

---

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose**
- **Spotify Developer Account** - [Create app](https://developer.spotify.com/dashboard)
- **Go 1.24+** (for local backend development)
- **Python 3.12+** (for local ML service development)

### 1. Clone Repository

```bash
git clone <repository-url>
cd moodea
```

### 2. Configure Environment Variables

#### Backend (`.env` in `backend_go/`)

```bash
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8080/auth/callback
JWT_SECRET=your_jwt_secret_key_min_32_chars
JWT_EXPIRES_IN=24h
MONGODB_URI=mongodb://mongo:27017/moodea
ML_SERVICE_URL=http://ml_service:8001
KAFKA_BROKERS=kafka:9092  # Optional, system works without Kafka
```

#### ML Service (`.env` in `ml_service/`)

```bash
ML_SERVICE_PORT=8001
MONGODB_URI=mongodb://mongo:27017/moodea
REDIS_HOST=redis
REDIS_PORT=6379
FEAST_REPO_PATH=/app/feast
MOOD_MODEL_PATH=./models/mood/best_mood_model.pkl
MLFLOW_TRACKING_URI=http://mlflow:5000  # Optional
```

### 3. Start Services

```bash
docker-compose up --build
```

This starts:
- **Backend Go** on `http://localhost:8080`
- **ML Service** on `http://localhost:8001`
- **Frontend** on `http://localhost:3000`
- **MongoDB** on `localhost:27017`
- **Redis** on `localhost:6379`

### 4. Initialize Feast Feature Store

```bash
# In a new terminal
docker-compose exec ml_service bash
cd /app/feast
feast apply
```

### 5. Train Mood Model (First Time)

```bash
# Inside ml_service container
cd /app
python -m src.models.mood.train  # Train and save mood model
```

### 6. Promote Tracks to Feast

```bash
# Via API (after approving tracks in admin panel)
curl -X POST http://localhost:8001/admin/tracks/promote-batch \
  -H "Content-Type: application/json"
```

---

## 📖 API Documentation

### Authentication

#### Login (OAuth Flow)
```http
GET /auth/login
```
Redirects to Spotify OAuth. After callback, returns JWT token.

#### Get Current User
```http
GET /auth/me
Authorization: Bearer <jwt_token>
```

### Spotify Endpoints

All require `Authorization: Bearer <jwt_token>` header.

```http
GET /spotify/top-tracks?time_range=medium_term&limit=20
GET /spotify/top-artists?time_range=short_term&limit=20
GET /spotify/artist-top-tracks?artist_id=<id>&limit=10
GET /spotify/album-tracks?album_id=<id>
GET /spotify/current-user-playlists?limit=20
GET /spotify/playlist-tracks?playlist_id=<id>
GET /spotify/saved-tracks?limit=20
GET /spotify/recently-played?limit=20
```

### Recommendations

```http
POST /recommendations
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "limit": 20,
  "context": {}
}
```

**Response:**
```json
{
  "track_ids": ["spotify:track:...", ...],
  "scores": [0.95, 0.89, ...],
  "metadata": {
    "method": "content_based",
    "user_interactions_count": 15
  }
}
```

### Interactions

#### Record Interaction
```http
POST /interactions
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "track_id": "spotify:track:...",
  "interaction_type": "like",  // "like", "skip", "continue"
  "score": 3,  // like=3, continue=1, skip=-1
  "session_id": "optional_session_id",
  "context": {}
}
```

#### Get User Interactions
```http
GET /interactions?limit=50
Authorization: Bearer <jwt_token>
```

### Admin Endpoints

#### Get Track Candidates
```http
GET /admin/track-candidates?status=pending&limit=50
Authorization: Bearer <jwt_token>
```

#### Approve Track
```http
POST /admin/track-candidates/:trackId/approve
Authorization: Bearer <jwt_token>
```

#### Approve All Tracks
```http
POST /admin/track-candidates/approve-all
Authorization: Bearer <jwt_token>
```

### ML Service Endpoints

#### Mood Prediction
```http
POST http://localhost:8001/ml/mood/predict
Content-Type: application/json

{
  "track_ids": ["spotify:track:..."],
  "audio_features": {
    "spotify:track:...": {
      "danceability": 0.8,
      "energy": 0.7,
      ...
    }
  }
}
```

#### Promote Track to Feast
```http
POST http://localhost:8001/admin/tracks/promote
Content-Type: application/json

{
  "track_id": "spotify:track:..."
}
```

#### Batch Promote Tracks
```http
POST http://localhost:8001/admin/tracks/promote-batch
```

#### Health Check
```http
GET http://localhost:8001/health
```

---

## 📁 Project Structure

```
moodea/
├── backend_go/                 # Go backend service
│   ├── internal/
│   │   ├── controllers/        # HTTP handlers
│   │   ├── models/             # Database models
│   │   ├── services/           # Business logic
│   │   └── utils/              # Utilities (WorkerPool, etc.)
│   ├── main.go                 # Entry point
│   ├── go.mod
│   └── Dockerfile
│
├── ml_service/                 # Python ML service
│   ├── src/
│   │   ├── main.py            # FastAPI app
│   │   ├── models/             # ML models (mood, recommendation)
│   │   ├── services/           # Services (content-based, ANN, promotion)
│   │   ├── pipelines/          # Training & inference pipelines
│   │   ├── feature_engineering/ # Feast client
│   │   └── mlflow/             # MLflow integration
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                   # React frontend (to be upgraded to Next.js)
│   ├── src/
│   │   ├── App.js
│   │   ├── components/
│   │   └── pages/
│   ├── package.json
│   └── Dockerfile
│
├── feast/                      # Feast feature store
│   ├── feature_store.yaml
│   ├── features/               # FeatureView definitions
│   │   ├── track_features.py
│   │   ├── user_features.py
│   │   └── interaction_features.py
│   └── data/parquet/           # Offline feature storage
│
├── docker-compose.yml          # Docker orchestration
├── PROJECT_PLAN.md            # Detailed implementation plan
└── README.md                  # This file
```

---

## 🔧 Development

### Local Development (Without Docker)

#### Backend
```bash
cd backend_go
go mod download
go run main.go
```

#### ML Service
```bash
cd ml_service
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

#### Frontend
```bash
cd frontend
npm install
npm start
```

### Running Tests

```bash
# Backend tests
cd backend_go
go test ./...

# ML service tests
cd ml_service
pytest tests/
```

### Code Quality

```bash
# Go formatting
cd backend_go
go fmt ./...
golangci-lint run

# Python formatting
cd ml_service
black src/
flake8 src/
```

---

## 🎯 Development Roadmap

See [PROJECT_PLAN.md](./PROJECT_PLAN.md) for detailed implementation phases.

### Phase 1: Content-Based Recommendations ✅
- Content-based service with cosine similarity
- Batch track promotion
- Basic recommendation endpoint

### Phase 2: Neural Recommendations + Low-Latency (In Progress)
- Two-tower neural model training
- FAISS ANN index
- Redis-backed online inference
- Materialization pipeline

### Phase 3: Real-Time Streaming (Planned)
- Kafka consumers for feature updates
- Real-time user/interaction feature computation

### Phase 4: Apache Flink (Planned)
- Windowed aggregations
- Exactly-once processing
- High-throughput stream processing

### Phase 5: Production Hardening (Planned)
- MLflow model registry
- Admin authorization
- Enhanced monitoring
- Periodic retraining

### Phase 6: Next.js Frontend (Planned)
- Modern React app with TypeScript
- Tailwind CSS styling
- Full user interface

---

## 🐛 Troubleshooting

### MongoDB Connection Issues
```bash
# Check if MongoDB is running
docker-compose ps mongo

# View MongoDB logs
docker-compose logs mongo
```

### Redis Connection Issues
```bash
# Test Redis connection
docker-compose exec redis redis-cli ping

# Check Redis keys
docker-compose exec redis redis-cli KEYS "*"
```

### Feast Feature Store Issues
```bash
# Re-apply Feast configuration
docker-compose exec ml_service bash
cd /app/feast
feast teardown  # Careful: deletes data
feast apply
```

### ML Service Not Loading Models
- Ensure mood model is trained: `python -m src.models.mood.train`
- Check `MOOD_MODEL_PATH` in `.env` points to correct file
- Verify model file exists in container

### Kafka Not Available
- System works in stub mode without Kafka
- Set `KAFKA_BROKERS` to empty string to disable
- Kafka is optional for Phase 1-2

---

## 📊 Performance Characteristics

### Backend (Go)
- **Concurrent Processing**: 100+ parallel tasks via worker pools
- **Batch Processing**: 50 tracks per batch
- **Goroutine Concurrency**: 6 concurrent feature extraction streams
- **Response Time**: <100ms for most endpoints

### ML Service (Python)
- **Mood Prediction**: ~5ms per track (batch processing)
- **Content-Based Recommendations**: ~20-50ms (depends on track count)
- **Neural Inference** (Phase 2): Target <50ms end-to-end
  - Redis feature fetch: ~1ms
  - User embedding: ~1ms
  - FAISS ANN query: ~1ms
  - Reranker: ~5ms

### Feature Store (Feast)
- **Offline Storage**: Parquet files (batch processing)
- **Online Storage**: Redis (sub-millisecond lookups)
- **Materialization**: Incremental updates supported

---

## 🔐 Security

- **JWT Authentication** - Secure token-based auth
- **OAuth 2.0** - Spotify OAuth flow
- **Environment Variables** - Secrets stored in `.env` (not committed)
- **Admin Authorization** - Planned middleware for admin endpoints
- **Rate Limiting** - Planned for Spotify API proxy endpoints

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow Go and Python style guides
- Write tests for new features
- Update documentation
- Ensure Docker builds succeed

---

## 📝 License

See [LICENSE](./LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Spotify** - For the comprehensive Web API
- **Feast** - For the feature store framework
- **Apache Flink** - For stream processing capabilities
- **FAISS** - For efficient similarity search

---

## 📧 Contact & Support

For questions, issues, or contributions:
- Open an issue on GitHub
- Check [PROJECT_PLAN.md](./PROJECT_PLAN.md) for implementation details

---

**Built with ❤️ for music lovers everywhere**
