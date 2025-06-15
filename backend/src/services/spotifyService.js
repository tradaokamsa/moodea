const axios = require('axios');
const crypto = require('crypto');

const SPOTIFY_CLIENT_ID = process.env.SPOTIFY_CLIENT_ID;
const SPOTIFY_CLIENT_SECRET = process.env.SPOTIFY_CLIENT_SECRET;
const SPOTIFY_REDIRECT_URI = process.env.SPOTIFY_REDIRECT_URI;

const generateRandomString = (length) => {
  return crypto
  .randomBytes(60)
  .toString('hex')
  .slice(0, length);
}

const getAuthUrl = () => {
  const state = generateRandomString(16);
  const scopes = [
    "user-top-read",
    "user-read-email",
    "user-read-private",
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-modify-playback-state"
  ];
  const params = new URLSearchParams({
    client_id: SPOTIFY_CLIENT_ID,
    redirect_uri: SPOTIFY_REDIRECT_URI,
    response_type: 'code',
    state: state,
    scope: scopes.join(' '),
    show_dialog: true
  });

  return `https://accounts.spotify.com/authorize?${params.toString()}`;
};

const getTokens = async (code) => {
  const params = new URLSearchParams();
  params.append('grant_type', 'authorization_code');
  params.append('code', code);
  params.append('redirect_uri', SPOTIFY_REDIRECT_URI);

  const response = await axios.post('https://accounts.spotify.com/api/token', params, {
    headers: {
      'Authorization': `Basic ${Buffer.from(`${SPOTIFY_CLIENT_ID}:${SPOTIFY_CLIENT_SECRET}`).toString('base64')}`,
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  });

  return response.data;
};

const refreshAccessToken = async (refreshToken) => {
  const params = new URLSearchParams();
  params.append('grant_type', 'refresh_token');
  params.append('refresh_token', refreshToken);

  const response = await axios.post('https://accounts.spotify.com/api/token', params, {
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'Authorization': `Basic ${Buffer.from(`${SPOTIFY_CLIENT_ID}:${SPOTIFY_CLIENT_SECRET}`).toString('base64')}`
    }
  });

  return response.data;
};

const getUserProfile = async (accessToken) => {
  const response = await axios.get('https://api.spotify.com/v1/me', {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  return response.data;
};

// Function to make Spotify API requests with access token (automatically refreshes token if needed)
const makeSpotifyRequest = async (endpoint, method = 'GET', data = null, user) => {
  // Check if token is expired or about to expire (within 5 minutes)
  const isTokenExpired = new Date(user.tokenExpiresAt) - new Date() < 300000; // 5 minutes in milliseconds

  if (isTokenExpired) {
    // Refresh the token
    const newTokens = await refreshAccessToken(user.refreshToken);
    
    // Update user's tokens in database
    user.accessToken = newTokens.access_token;
    user.refreshToken = newTokens.refresh_token || user.refreshToken; // Keep old refresh token if new one isn't provided
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
    data
  });

  return response.data;
};

module.exports = {
  getAuthUrl,
  getTokens,
  refreshAccessToken,
  getUserProfile,
  makeSpotifyRequest
};