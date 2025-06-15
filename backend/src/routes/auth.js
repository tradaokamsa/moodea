const express = require('express');
const router = express.Router();
const authController = require('../controllers/authController');
const { authenticate } = require('../middleware/auth');

// Initiate Spotify OAuth flow
router.get('/login', authController.login);

// Spotify OAuth callback
router.get('/callback', authController.callback);

// Get current user (protected route)
router.get('/me', authenticate, authController.getCurrentUser);

module.exports = router; 