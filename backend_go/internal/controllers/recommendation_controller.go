package controllers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"

	"moodea/backend_go/internal/models"
)

var redisClient *redis.Client

const recoCacheTTL = 5 * time.Minute

func init() {
	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "localhost:6379"
	}
	redisClient = redis.NewClient(&redis.Options{
		Addr: redisAddr,
	})
	// Non-blocking ping; caching gracefully degrades if Redis is down
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := redisClient.Ping(ctx).Err(); err != nil {
			fmt.Printf("Warning: Redis not reachable at %s: %v (caching disabled)\n", redisAddr, err)
		}
	}()
}

type recommendationRequest struct {
	Limit   int                    `json:"limit"`
	Context map[string]interface{} `json:"context,omitempty"`
}

type recommendationResponse struct {
	TrackIDs []string               `json:"track_ids"`
	Scores   []float64              `json:"scores"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

// recoCacheKey returns the Redis key for a user's cached recommendations.
func recoCacheKey(userID string) string {
	return fmt.Sprintf("reco:%s", userID)
}

// InvalidateRecoCache removes the cached recommendations for a user.
func InvalidateRecoCache(userID string) {
	if redisClient == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	_ = redisClient.Del(ctx, recoCacheKey(userID)).Err()
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

	// --- Check Redis cache ---
	cacheKey := recoCacheKey(userId)
	if redisClient != nil {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 500*time.Millisecond)
		cached, err := redisClient.Get(ctx, cacheKey).Bytes()
		cancel()
		if err == nil {
			var cachedResp gin.H
			if json.Unmarshal(cached, &cachedResp) == nil {
				cachedResp["cache_hit"] = true
				c.JSON(http.StatusOK, cachedResp)
				return
			}
		}
	}

	// --- Cache miss: call ML service ---
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
		fmt.Printf("Warning: Failed to store recommendation session: %v\n", err)
	}

	responseBody := gin.H{
		"session_id": sessionID,
		"track_ids":  mlResponse.TrackIDs,
		"scores":     mlResponse.Scores,
		"metadata":   mlResponse.Metadata,
	}

	// --- Store in Redis cache ---
	if redisClient != nil {
		if cacheData, err := json.Marshal(responseBody); err == nil {
			ctx, cancel := context.WithTimeout(c.Request.Context(), 500*time.Millisecond)
			_ = redisClient.Set(ctx, cacheKey, cacheData, recoCacheTTL).Err()
			cancel()
		}
	}

	c.JSON(http.StatusOK, responseBody)
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
		"limit":      limit,
		"offset":     offset,
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

// ApproveAllTrackCandidates handles POST /admin/track-candidates/approve-all
func ApproveAllTrackCandidates(c *gin.Context) {
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}

	count, err := models.ApproveAllTrackCandidates(c.Request.Context(), userId)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":  fmt.Sprintf("Approved %d track candidates", count),
		"approved": count,
	})
}

// Helper functions
func getMLServiceURL() string {
	url := "http://localhost:8001"
	if envURL := getEnv("ML_SERVICE_URL", ""); envURL != "" {
		url = envURL
	}
	return url
}

func getEnv(key, defaultValue string) string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}
