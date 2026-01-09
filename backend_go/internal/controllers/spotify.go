package controllers

import (
	"net/http"
	"strconv"

	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/services"

	"github.com/gin-gonic/gin"
)

// HandleGetTopTracks handles GET /spotify/top-tracks
func HandleGetTopTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	timeRange := c.DefaultQuery("time_range", "medium_term")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	data, err := services.GetTopTracks(user, timeRange, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch top tracks"})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetTopArtists(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	timeRange := c.DefaultQuery("time_range", "medium_term")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	data, err := services.GetTopArtists(user, timeRange, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch top artists", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetArtistTopTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	artistID := c.Query("artist_id")
	if artistID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "artist_id is required"})
		return
	}

	market := c.Query("market") // Optional - if empty, Spotify uses user's account country

	data, err := services.GetArtistTopTracks(user, artistID, market)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch artist top tracks", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetAlbumTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	albumID := c.Query("album_id")
	if albumID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "album_id is required"})
		return
	}

	market := c.Query("market") // Optional - if empty, Spotify uses user's account country
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	data, err := services.GetAlbumTracks(user, albumID, market, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch album tracks", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetCurrentUserPlaylists(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	data, err := services.GetCurrentUserPlaylists(user, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch current user playlists", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetPlaylistTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	playlistID := c.Query("playlist_id")
	if playlistID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "playlist_id is required"})
		return
	}

	market := c.Query("market") // Optional - if empty, Spotify uses user's account country
	fields := c.DefaultQuery("fields", "items(track(id,name,artists,album))")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	additionalTypes := c.DefaultQuery("additional_types", "track")
	data, err := services.GetPlaylistTracks(user, playlistID, market, fields, limit, offset, additionalTypes)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch playlist tracks", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetSavedTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	data, err := services.GetSavedTracks(user, limit, offset, "")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch saved tracks", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}

func HandleGetRecentlyPlayed(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}

	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	before, _ := strconv.Atoi(c.DefaultQuery("before", "0"))
	after, _ := strconv.Atoi(c.DefaultQuery("after", "0"))
	data, err := services.GetRecentlyPlayed(user, limit, before, after)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch recently played", "details": err.Error()})
		return
	}

	c.JSON(http.StatusOK, data)
}
