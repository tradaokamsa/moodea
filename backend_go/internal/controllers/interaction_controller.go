package controllers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/services"
)


type interactionRequest struct {
	TrackID         string                 `json:"track_id" binding:"required"`
	InteractionType string                 `json:"interaction_type" binding:"required"` // skip | continue | like
	SessionID       string                 `json:"session_id"`
}

func mapInteractionTypeToScore(interactionType string) (int, bool) {
	switch interactionType {
	case "skip":
		return -1, true
	case "continue":
		return 1, true
	case "like":
		return 3, true
	}
	return 0, false // default to 0 for unknown interaction types
}

// RecordInteraction handles POST /interactions
func RecordInteraction(c *gin.Context) {
	// 1. Parse request body (user_id, track_id, interaction_type, session_id, context)
	// 2. Map interaction_type to score (skip=-1, continue=1, like=3)
	// 3. Create Interaction model and store in MongoDB
	// 4. Create InteractionEvent and send to Kafka
	// 5. Return success response
	var req interactionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	score, ok := mapInteractionTypeToScore(req.InteractionType)
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid interaction type"})
		return
	}
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}
	interaction := &models.Interaction{
		UserID:          userId,
		TrackID:         req.TrackID,
		InteractionType: req.InteractionType,
		Score:           score,
		SessionID:       req.SessionID,
		Timestamp:       time.Now().Unix(),
		Context:         map[string]interface{}{},
	}
	if err := models.CreateInteraction(c.Request.Context(), interaction); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// emit interaction event to Kafka
	_ = services.ProduceInteractionEvent(&services.InteractionEvent{
		UserID:          userId,
		TrackID:         req.TrackID,
		InteractionType: req.InteractionType,
		Score:           score,
		SessionID:       req.SessionID,
		Timestamp:       time.Now().Unix(),
		Context:         map[string]interface{}{},
	})

	// Invalidate recommendation cache so next request gets fresh results
	InvalidateRecoCache(userId)

	c.JSON(http.StatusOK, gin.H{"message": "interaction recorded"})
}

// GetUserInteractions handles GET /interactions
func GetUserInteractions(c *gin.Context) {
	// userId := c.GetString("userId")
	// Get interactions from MongoDB
	// Return interactions
	userId := c.GetString("userId")
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}
	limit := int64(100)
	interactions, err := models.GetUserInteractions(c.Request.Context(), userId, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return	
	}
	c.JSON(http.StatusOK, gin.H{"interactions": interactions, "limit": limit})
}

