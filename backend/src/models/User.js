const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
  email: {
    type: String,
    required: true,
    unique: true
  },
  spotifyId: {
    type: String,
    required: true,
    unique: true
  },
  displayName: {
    type: String,
    required: true
  },
  country: {
    type: String,
    required: true
  }
}, {
  timestamps: true
});

module.exports = mongoose.model('User', userSchema); 