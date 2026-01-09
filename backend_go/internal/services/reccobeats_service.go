package services

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"sync"

	"moodea/backend_go/internal/utils"
)

const (
	reccobeatsAPIBaseURL = "https://api.reccobeats.com/v1/audio-features"
	maxTracksPerRequest  = 40 // Max tracks per API call based on API limits
)

// AudioFeatures represents audio features from ReccoBeats
type AudioFeatures struct {
	TrackID  string                 `json:"track_id"`
	Features map[string]interface{} `json:"features"`
}

// ReccoBeatsAPIResponse represents a single track's audio features from the API
type ReccoBeatsAPIResponse struct {
	ID               string  `json:"id"`
	Href             string  `json:"href"`
	Acousticness     float64 `json:"acousticness"`
	Danceability     float64 `json:"danceability"`
	Energy           float64 `json:"energy"`
	Instrumentalness float64 `json:"instrumentalness"`
	Key              int     `json:"key"`
	Liveness         float64 `json:"liveness"`
	Loudness         float64 `json:"loudness"`
	Mode             int     `json:"mode"`
	Speechiness      float64 `json:"speechiness"`
	Tempo            float64 `json:"tempo"`
	Valence          float64 `json:"valence"`
}

// GetAudioFeaturesBatch fetches audio features from ReccoBeats API for a batch of track IDs
func GetAudioFeaturesBatch(trackIDs []string) (map[string]*AudioFeatures, error) {
	if len(trackIDs) == 0 {
		return make(map[string]*AudioFeatures), nil
	}

	// Build URL with comma-separated track IDs
	idsParam := strings.Join(trackIDs, ",")
	apiURL := fmt.Sprintf("%s?ids=%s", reccobeatsAPIBaseURL, url.QueryEscape(idsParam))

	// Create HTTP client
	client := &http.Client{}

	// Create request
	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Set headers
	req.Header.Add("Accept", "application/json")

	// Execute request
	res, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer res.Body.Close()

	// Check status code
	if res.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(res.Body)
		return nil, fmt.Errorf("API returned status %d: %s", res.StatusCode, string(bodyBytes))
	}

	// Read response body
	body, err := io.ReadAll(res.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	// Parse JSON response - API returns object with "content" key containing array
	var responseWrapper struct {
		Content []ReccoBeatsAPIResponse `json:"content"`
	}
	if err := json.Unmarshal(body, &responseWrapper); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	apiResponses := responseWrapper.Content

	// Convert API response to AudioFeatures map
	// Key: Spotify track ID (extracted from href and matched with input trackIDs)
	result := make(map[string]*AudioFeatures)

	// Create a set of requested track IDs for quick lookup
	requestedTrackIDs := make(map[string]bool)
	for _, trackID := range trackIDs {
		requestedTrackIDs[trackID] = true
	}

	matchedCount := 0
	for _, apiResp := range apiResponses {
		// Extract Spotify track ID from href (format: "https://open.spotify.com/track/0suW7tCGOkM3J54Sgbgi1W")
		spotifyTrackID := ""
		if apiResp.Href != "" {
			if idx := strings.LastIndex(apiResp.Href, "/track/"); idx != -1 {
				spotifyTrackID = apiResp.Href[idx+7:]
				// Remove query params or fragments if any
				if qIdx := strings.Index(spotifyTrackID, "?"); qIdx != -1 {
					spotifyTrackID = spotifyTrackID[:qIdx]
				}
				if fIdx := strings.Index(spotifyTrackID, "#"); fIdx != -1 {
					spotifyTrackID = spotifyTrackID[:fIdx]
				}
			}
		}
		
		// Double check: verify this track ID was in our requested list
		if spotifyTrackID == "" {
			log.Printf("[GetAudioFeaturesBatch] Could not extract track ID from href: %s (ReccoBeats UUID: %s)", 
				apiResp.Href, apiResp.ID)
			continue
		}
		
		if !requestedTrackIDs[spotifyTrackID] {
			log.Printf("[GetAudioFeaturesBatch] WARNING: Extracted track ID %s from href %s not in requested list (ReccoBeats UUID: %s)", 
				spotifyTrackID, apiResp.Href, apiResp.ID)
			continue
		}
		
		// Convert API response to features map
		features := map[string]interface{}{
			"href":             apiResp.Href,
			"acousticness":     apiResp.Acousticness,
			"danceability":     apiResp.Danceability,
			"energy":           apiResp.Energy,
			"instrumentalness": apiResp.Instrumentalness,
			"key":              apiResp.Key,
			"liveness":         apiResp.Liveness,
			"loudness":         apiResp.Loudness,
			"mode":             apiResp.Mode,
			"speechiness":      apiResp.Speechiness,
			"tempo":            apiResp.Tempo,
			"valence":          apiResp.Valence,
		}

		result[spotifyTrackID] = &AudioFeatures{
			TrackID:  spotifyTrackID, // Use Spotify track ID as key
			Features: features,
		}
		matchedCount++
	}

	log.Printf("[GetAudioFeaturesBatch] Successfully matched %d/%d ReccoBeats responses to requested tracks (skipping %d unmatched)", 
	matchedCount, len(apiResponses), len(trackIDs)-matchedCount)
	return result, nil
}

// GetAudioFeatures fetches audio features from ReccoBeats API for multiple track IDs
// It processes tracks in batches concurrently and aggregates the results
func GetAudioFeatures(trackIDs []string) (map[string]*AudioFeatures, error) {
	if len(trackIDs) == 0 {
		return make(map[string]*AudioFeatures), nil
	}

	// Aggregate results from all batches
	var (
		result    = make(map[string]*AudioFeatures)
		resultMu  sync.Mutex
		hasErrors bool
		errorsMu  sync.Mutex
	)

	// Process tracks in batches concurrently
	err := utils.BatchProcess(trackIDs, maxTracksPerRequest, func(batch []string) error {
		batchResult, err := GetAudioFeaturesBatch(batch)
		if err != nil {
			errorsMu.Lock()
			hasErrors = true
			errorsMu.Unlock()
			log.Printf("[GetAudioFeatures] Error fetching batch: %v (skipping %d tracks)", err, len(batch))
			// Skip tracks that couldn't be fetched
			return nil // Don't propagate error to stop batch processing
		}

		// Merge batch results into main result map
		resultMu.Lock()
		for trackID, features := range batchResult {
			result[trackID] = features
		}
		resultMu.Unlock()

		return nil
	})

	if err != nil {
		return nil, fmt.Errorf("batch processing error: %w", err)
	}

	// If there were errors but we have partial results, return what we have
	// The caller can handle missing/empty features
	if hasErrors && len(result) > 0 {
		log.Printf("[GetAudioFeatures] Completed with partial results: %d/%d tracks", len(result), len(trackIDs))
	}

	return result, nil
}
