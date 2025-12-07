package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"

	"moodea/backend_go/internal/controllers"
	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/services"
)

func main() {
	// Load environment variables from .env file
	err := godotenv.Load()
	if err != nil {
		log.Println("No .env file found or error loading .env file")
	}

	r := gin.Default()

	r.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"message": "Moodea Go backend (Gin) is running!"})
	})

	r.GET("/auth/login", func(c *gin.Context) {
		// Generate a random state (for demo, use timestamp)
		state := time.Now().Format("20060102150405")
		url := services.GetAuthURL(state)
		c.Redirect(http.StatusFound, url)
	})

	r.GET("/auth/callback", func(c *gin.Context) {
		code := c.Query("code")
		state := c.Query("state")
		if state == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "state_mismatch"})
			return
		}
		tokens, err := services.GetTokens(code)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "token_exchange_failed"})
			return
		}
		userProfile, err := services.GetUserProfile(tokens.AccessToken)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "user_profile_failed"})
			return
		}
		tokenExpiresAt := time.Now().Add(time.Duration(tokens.ExpiresIn) * time.Second).Unix()
		user, err := models.FindOrCreateUser(
			c,
			userProfile.ID,
			userProfile.DisplayName,
			userProfile.Email,
			userProfile.Country,
			tokens.AccessToken,
			tokens.RefreshToken,
			tokenExpiresAt,
		)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "db_failed"})
			return
		}
		token, err := services.GenerateToken(user.SpotifyID, user.SpotifyID, user.Email)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "jwt_failed"})
			return
		}

		// Spawn background goroutine for async feature extraction
		go services.ProcessUserFeaturesAsync(user)

		c.JSON(http.StatusOK, gin.H{"token": token, "user": user})
	})

	r.GET("/auth/me", AuthMiddleware(), func(c *gin.Context) {
		userId := c.GetString("userId")
		user, err := models.GetUserByID(c, userId)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "user_not_found"})
			return
		}
		c.JSON(http.StatusOK, user)
	})

	r.GET("/spotify/top-tracks", AuthMiddleware(), func(c *gin.Context) {
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
	})

	// Interaction endpoints
	r.POST("/interactions", AuthMiddleware(), controllers.RecordInteraction)
	r.GET("/interactions", AuthMiddleware(), controllers.GetUserInteractions)

	// Recommendation endpoints
	r.POST("/recommendations", AuthMiddleware(), controllers.GetRecommendations)

	// Admin endpoints
	admin := r.Group("/admin")
	admin.Use(AuthMiddleware()) // TODO: Add admin authorization middleware
	{
		admin.GET("/track-candidates", controllers.GetTrackCandidates)
		admin.POST("/track-candidates/:trackId/approve", controllers.ApproveTrackCandidate)
	}

	// Initialize Kafka producer on startup
	if err := services.InitializeKafkaProducer(); err != nil {
		log.Printf("Warning: Failed to initialize Kafka producer: %v", err)
	}

	// Initialize MongoDB indexes
	ctx := context.Background()
	if err := models.CreateInteractionIndexes(ctx); err != nil {
		log.Printf("Warning: Failed to create interaction indexes: %v", err)
	}
	if err := models.CreateTrackCandidateIndexes(ctx); err != nil {
		log.Printf("Warning: Failed to create track candidate indexes: %v", err)
	}

	r.Run(":8080")
}

// AuthMiddleware validates JWT and sets userId in context
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		tokenString := c.GetHeader("Authorization")
		if tokenString == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing_token"})
			return
		}
		claims, err := services.VerifyToken(tokenString)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid_token"})
			return
		}
		c.Set("userId", claims.ID)
		c.Next()
	}
}
