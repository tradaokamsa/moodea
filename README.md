# Moodea: Generative AI Agent for Personalized Music Recommendations

## Overview
Moodea is a full-stack application that uses AI and the Spotify API to generate personalized music playlists based on user mood and preferences, extracted from natural language conversations.

## Tech Stack
- **Frontend:** React
- **Backend:** Go (Gin), previously Node.js/Express
- **Database:** MongoDB
- **AI/NLP:** (Pluggable, e.g., HuggingFace, OpenAI, or custom)
- **Music Data:** Spotify Web API

## Setup

### 1. Backend (Go)
- Copy `.env` from `backend_nodejs` or create a new one in `backend_go` with your secrets (see example below).
- Install Go 1.18+ if running locally, or use Docker Compose for a full stack setup.
- Environment variables are managed via `.env` (not committed to git).

#### Example `.env` for Go backend
```
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8080/auth/callback
JWT_SECRET=your_jwt_secret
JWT_EXPIRES_IN=1h
MONGODB_URI=mongodb://mongo:27017/moodea
```

### 2. Frontend
- See `frontend/README.md` for setup and environment variables.

## Development
- Run the full stack with Docker Compose:
  ```sh
  docker-compose up --build
  ```
- Or run backend and frontend servers concurrently in separate terminals.

---

## Project Structure
```
moodea/
├── backend_go/
│   └── ...
├── backend_nodejs/ (legacy)
│   └── ...
├── frontend/
│   └── ...
├── docker-compose.yml
├── README.md
└── LICENSE
```
