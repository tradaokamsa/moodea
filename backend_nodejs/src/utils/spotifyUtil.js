const axios = require('axios');
const spotifyService = require('../services/spotifyService');

// Function to make Spotify API requests with access token (automatically refreshes token if needed)
const makeSpotifyRequest = async (endpoint, method = 'GET', data = null, user) => {
  try {
      // Check if token is expired or about to expire (within 5 minutes)
      const isTokenExpired = new Date(user.tokenExpiresAt) - new Date() < 300000;

      if (isTokenExpired) {
          const newTokens = await spotifyService.refreshAccessToken(user.refreshToken);
          user.accessToken = newTokens.access_token;
          user.refreshToken = newTokens.refresh_token || user.refreshToken;
          user.tokenExpiresAt = new Date(Date.now() + newTokens.expires_in * 1000);
          await user.save();
      }

      // Make the request with the current/updated access token
      const response = await axios({
          method,
          url: `https://api.spotify.com/v1${endpoint}`,
          headers: {
              'Authorization': `Bearer ${user.accessToken}`,
              'Content-Type': 'application/json'
          },
          params: method === 'GET' ? data : undefined, // Use params for GET requests
          data: method !== 'GET' ? data : undefined    // Use data for non-GET requests
      });

      return response.data;
  } catch (error) {
      console.error('Spotify API error:', error.response?.data || error.message);
      throw error;
  }
};

module.exports = {
    makeSpotifyRequest
};