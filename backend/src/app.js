const express = require('express');
const cors = require('cors');

const app = express();

app.use(cors());
app.use(express.json());

// Placeholder for routes
// const spotifyRoutes = require('./routes/spotify');
// app.use('/api/spotify', spotifyRoutes);

app.get('/', (req, res) => {
  res.send('Moodea Music Recommender Backend');
});

module.exports = app; 