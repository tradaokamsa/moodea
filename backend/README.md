# Moodea Backend

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```
2. Create a `.env` file in the backend root with the following variables:
   ```env
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:5000/api/spotify/callback
   MONGODB_URI=your_mongodb_uri
   JWT_SECRET=your_jwt_secret
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

## Project Structure
- `src/controllers/` - Route logic
- `src/models/` - Mongoose models
- `src/routes/` - Express routes
- `src/services/` - Spotify, NLP, recommendation logic
- `src/utils/` - Helper functions
- `src/app.js` - Express app setup
- `src/server.js` - Entry point 