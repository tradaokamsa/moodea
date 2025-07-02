package controllers

import (
	"encoding/json"
	"net/http"

	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/services"

	"github.com/gin-gonic/gin"
)

func GetTopTracks(c *gin.Context) {
	userId := c.GetString("userId")
	user, err := models.GetUserByID(c, userId)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user_not_found"})
		return
	}
	params := map[string]string{
		"time_range": c.DefaultQuery("time_range", "medium_term"),
		"limit":      c.DefaultQuery("limit", "10"),
		"offset":     c.DefaultQuery("offset", "0"),
	}
	resp, err := services.MakeSpotifyRequest("/me/top/tracks", "GET", params, user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch top tracks"})
		return
	}
	var data interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to parse response"})
		return
	}
	c.JSON(http.StatusOK, data)
}
