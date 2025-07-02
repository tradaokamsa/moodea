const spotifyUtil = require('../utils/spotifyUtil');

const getTopTracks = async (req, res) => {
    try {
        const topTracks = await spotifyUtil.makeSpotifyRequest(
            "/me/top/tracks",
            "GET",
            {
                time_range: "medium_term",
                limit: req.query.limit || 10,
                offset: req.query.offset || 0
            },
            req.user
        );
        console.log('Top tracks fetched successfully:', topTracks);
        res.json(topTracks);
    } catch (error) {
        console.error('Error fetching top tracks:', error);
        res.status(500).json({ error: 'Failed to fetch top tracks' });
    }
};

module.exports = {
    getTopTracks
};