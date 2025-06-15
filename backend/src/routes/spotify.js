const express = require('express');
const router = express.Router();
const spotifyController = require('../controllers/spotifyController');
const { authenticate } = require('../middleware/auth');


// Get top tracks (protected route)
router.get('/me/top/tracks', authenticate, spotifyController.getTopTracks);

module.exports = router;