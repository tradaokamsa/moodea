const express = require('express');
const cors = require('cors');

const app = express();

app.use(cors());
app.use(express.json());

// Auth routes
const authRoutes = require('./routes/auth');
app.use('/api/auth', authRoutes);

// Spotify routes
const spotifyRoutes = require('./routes/spotify');
app.use('/api/spotify', spotifyRoutes);

app.get('/', (req, res) => {
  res.send('Moodea Music Recommender Backend');
});

module.exports = app; 