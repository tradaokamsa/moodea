const jwt = require('jsonwebtoken');
const User = require('../models/User');

const JWT_SECRET = process.env.JWT_SECRET;
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN;

const generateToken = (user) => {
  return jwt.sign(
    { 
      id: user._id,
      spotifyId: user.spotifyId,
      email: user.email 
    },
    JWT_SECRET,
    { expiresIn: JWT_EXPIRES_IN }
  );
};

const verifyToken = (token) => {
  try {
    return jwt.verify(token, JWT_SECRET);
  } catch (error) {
    throw new Error('Invalid token');
  }
};

const findOrCreateUser = async (spotifyUser, tokens) => {
  const { id: spotifyId, email, displayName, country } = spotifyUser;
  
  let user = await User.findOne({ spotifyId });
  
  if (!user) {
    user = await User.create({
      spotifyId,
      email,
      displayName,
      country
    });
  }
  
  return user;
};

module.exports = {
  generateToken,
  verifyToken,
  findOrCreateUser
}; 