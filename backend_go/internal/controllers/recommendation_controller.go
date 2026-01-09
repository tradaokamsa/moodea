package controllers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"moodea/backend_go/internal/models"
)

type recommendationRequest struct {
	Limit   int                    `json:"limit"`
	Context map[string]interface{} `json:"context,omitempty"`
}

type recommendationResponse struct {
	TrackIDs []string  `json:"track_ids"`
	Scores   []float64 `json:"scores"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

// GetRecommendations handles POST /recommendations
func GetRecommendations(c *gin.Context) {
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	var req recommendationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		// Default values if no body provided
		req.Limit = 20
		req.Context = make(map[string]interface{})
	}

	if req.Limit <= 0 {
		req.Limit = 20
	}

	// Call ML service
	mlServiceURL := getMLServiceURL()
	requestBody := map[string]interface{}{
		"user_id": userId,
		"limit":   req.Limit,
		"context": req.Context,
	}

	jsonData, err := json.Marshal(requestBody)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to marshal request"})
		return
	}

	resp, err := http.Post(mlServiceURL+"/recommendations", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("failed to call ML service: %v", err)})
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		c.JSON(resp.StatusCode, gin.H{"error": fmt.Sprintf("ML service error: %s", string(bodyBytes))})
		return
	}

	var mlResponse recommendationResponse
	if err := json.NewDecoder(resp.Body).Decode(&mlResponse); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to decode ML service response"})
		return
	}

	// Store recommendation session
	sessionID := fmt.Sprintf("%s_%d", userId, time.Now().Unix())
	session := &models.RecommendationSession{
		SessionID: sessionID,
		UserID:    userId,
		TrackIDs:  mlResponse.TrackIDs,
		Scores:    mlResponse.Scores,
		Timestamp: time.Now().Unix(),
		Context:   req.Context,
		CreatedAt: time.Now().UTC(),
	}

	if err := models.CreateRecommendationSession(c.Request.Context(), session); err != nil {
		// Log error but don't fail the request
		fmt.Printf("Warning: Failed to store recommendation session: %v\n", err)
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"track_ids":  mlResponse.TrackIDs,
		"scores":     mlResponse.Scores,
		"metadata":   mlResponse.Metadata,
	})
}

// GetTrackCandidates handles GET /admin/track-candidates
func GetTrackCandidates(c *gin.Context) {
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	limit := int64(50)
	offset := int64(0)

	if limitStr := c.DefaultQuery("limit", "50"); limitStr != "" {
		if parsed, err := strconv.ParseInt(limitStr, 10, 64); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if offsetStr := c.DefaultQuery("offset", "0"); offsetStr != "" {
		if parsed, err := strconv.ParseInt(offsetStr, 10, 64); err == nil {
			offset = parsed
		}
	}

	candidates, err := models.GetPendingTrackCandidates(c.Request.Context(), limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"candidates": candidates,
		"limit":     limit,
		"offset":    offset,
	})
}

// ApproveTrackCandidate handles POST /admin/track-candidates/:trackId/approve
func ApproveTrackCandidate(c *gin.Context) {
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	trackID := c.Param("trackId")
	if trackID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "track_id is required"})
		return
	}

	if err := models.ApproveTrackCandidate(c.Request.Context(), trackID, userId); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "track candidate approved", "track_id": trackID})
}

// Helper functions
func getMLServiceURL() string {
	// Default to localhost, can be overridden via environment variable
	url := "http://localhost:8001"
	if envURL := getEnv("ML_SERVICE_URL", ""); envURL != "" {
		url = envURL
	}
	return url
}

func getEnv(key, defaultValue string) string {
	// Use os.Getenv for environment variable lookup
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}
