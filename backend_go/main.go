package main

import (
	"log"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/gin-contrib/cors"
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

	// CORS for frontend on http://localhost:3000
	corsConfig := cors.Config{
		AllowOrigins:     []string{"http://localhost:3000"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization"},
		AllowCredentials: true,
	}
	r.Use(cors.New(corsConfig))

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
			log.Printf("Database error: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{
				"error":   "db_failed",
				"details": err.Error(),
			})
			return
		}
		token, err := services.GenerateToken(user.SpotifyID, user.SpotifyID, user.Email)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "jwt_failed"})
			return
		}

		// Spawn background goroutine for async feature extraction
		go services.ProcessUserFeaturesAsync(user)

		// If FRONTEND_URL is set, redirect to frontend callback with token in query,
		// otherwise fall back to JSON response (useful for API testing/tools).
		frontendURL := os.Getenv("FRONTEND_URL")
		if frontendURL != "" {
			redirectURL, err := url.Parse(frontendURL)
			if err != nil {
				log.Printf("Invalid FRONTEND_URL: %v", err)
				c.JSON(http.StatusOK, gin.H{"token": token, "user": user})
				return
			}
			redirectURL.Path = "/auth/callback"
			q := redirectURL.Query()
			q.Set("token", token)
			redirectURL.RawQuery = q.Encode()
			c.Redirect(http.StatusFound, redirectURL.String())
			return
		}

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

	// Spotify endpoints
	spotify := r.Group("/spotify")
	spotify.Use(AuthMiddleware())
	{
		spotify.GET("/top-tracks", controllers.HandleGetTopTracks)
		spotify.GET("/top-artists", controllers.HandleGetTopArtists)
		spotify.GET("/artist-top-tracks", controllers.HandleGetArtistTopTracks)
		spotify.GET("/album-tracks", controllers.HandleGetAlbumTracks)
		spotify.GET("/current-user-playlists", controllers.HandleGetCurrentUserPlaylists)
		spotify.GET("/playlist-tracks", controllers.HandleGetPlaylistTracks)
		spotify.GET("/saved-tracks", controllers.HandleGetSavedTracks)
		spotify.GET("/recently-played", controllers.HandleGetRecentlyPlayed)
		spotify.GET("/tracks", controllers.HandleGetTracks)
	}

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
		admin.POST("/track-candidates/approve-all", controllers.ApproveAllTrackCandidates)
	}

	// Initialize Kafka producer on startup
	if err := services.InitializeKafkaProducer(); err != nil {
		log.Printf("Warning: Failed to initialize Kafka producer: %v", err)
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

		if len(tokenString) > 7 && tokenString[:7] == "Bearer " {
			tokenString = tokenString[7:]
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
