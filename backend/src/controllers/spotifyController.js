const spotifyService = require('../services/spotifyService');

const getTopTracks = async (req, res) => {
    try {
        const topTracks = await spotifyService.makeSpotifyRequest(
            "/me/top/tracks",
            "GET",
            {
                time_range: "medium_term",
                limit: req.query.limit || 10,
                offset: req.query.offset || 0
            },
            req.user
        );
        res.json(topTracks);
    } catch (error) {
        console.error('Error fetching top tracks:', error);
        res.status(500).json({ error: 'Failed to fetch top tracks' });
    }
};

module.exports = {
    getTopTracks
};