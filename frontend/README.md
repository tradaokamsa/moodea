# Moodea Frontend

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```
2. Create a `.env` file in the frontend root with the following variable:
   ```env
   REACT_APP_API_BASE_URL=http://localhost:5000/api
   ```
3. Start the React app:
   ```bash
   npm start
   ```

## Project Structure
- `src/components/` - React components (Chatbot, Playlist, Login, etc.)
- `src/pages/` - Main pages (Home, Dashboard, etc.)
- `src/services/` - API calls to backend
- `src/utils/` - Helper functions
- `src/App.js` - Main app component
- `src/index.js` - Entry point 