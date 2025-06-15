const spotifyService = require('../services/spotifyService');
const authService = require('../services/authService');
const User = require('../models/User');

const login = (req, res) => {
  const authUrl = spotifyService.getAuthUrl();
  res.redirect(authUrl);
};

const callback = async (req, res) => {
  const { code, state } = req.query;
  if (state === null) {
    res.redirect('/#' +
      querystring.stringify({
        error: 'state_mismatch'
      }));
  } else {
    try {
      // Get tokens from Spotify
      const tokens = await spotifyService.getTokens(code);

      // Get user profile from Spotify
      const spotifyUser = await spotifyService.getUserProfile(tokens.access_token);

      // Find or create user in our database (without storing tokens)
      const user = await authService.findOrCreateUser(spotifyUser, tokens);

      // Generate JWT token
      const token = authService.generateToken(user);
    
      console.log('User %s logged in with Spotify', user.displayName);
      console.log('JWT token is %s', token);
      console.log('Spotify access token is %s', user.accessToken);

      // // Redirect to frontend with token
      // res.redirect(`${process.env.FRONTEND_URL}/auth/callback?token=${token}`);
    } catch (error) {
      console.error('Auth callback error:', error);
      // res.redirect(`${process.env.FRONTEND_URL}/auth/error`);
    }
  }
};

const getCurrentUser = async (req, res) => {
  try {
    const user = await User.findById(req.user.id).select('-accessToken -refreshToken -tokenExpiresAt');
    res.json(user);
  } catch (error) {
    res.status(500).json({ error: 'Error fetching user data' });
  }
};

module.exports = {
  login,
  callback,
  getCurrentUser
}; 