package services

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// MoodPrediction represents mood prediction result
type MoodPrediction struct {
	TrackID       string               `json:"track_id"`
	Labels        []string             `json:"labels"`
	Probabilities map[string]float64   `json:"probabilities"`
}

// PredictMoodForTracks calls Python ML service for mood prediction
func PredictMoodForTracks(trackIDs []string, audioFeatures map[string]*AudioFeatures) (map[string]*MoodPrediction, error) {
	if len(trackIDs) == 0 {
		return make(map[string]*MoodPrediction), nil
	}

	// Get ML service URL from environment or use default
	mlServiceURL := os.Getenv("ML_SERVICE_URL")
	if mlServiceURL == "" {
		mlServiceURL = "http://localhost:8001"
	}

	// Prepare request body
	requestBody := map[string]interface{}{
		"track_ids":     trackIDs,
		"audio_features": make(map[string]map[string]interface{}),
	}

	// Convert audio features to the format expected by ML service
	for trackID, features := range audioFeatures {
		if features != nil && features.Features != nil {
			requestBody["audio_features"].(map[string]map[string]interface{})[trackID] = features.Features
		}
	}

	jsonData, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// Create HTTP client with timeout
	client := &http.Client{
		Timeout: 30 * time.Second,
	}

	// Make request to ML service
	resp, err := client.Post(mlServiceURL+"/ml/mood/predict", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to call ML service: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ML service returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	// Parse response
	var response struct {
		Predictions map[string]map[string]interface{} `json:"predictions"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	// Convert response to MoodPrediction map
	result := make(map[string]*MoodPrediction)
	for trackID, predData := range response.Predictions {
		prediction := &MoodPrediction{
			TrackID: trackID,
		}

		// Extract labels
		if labels, ok := predData["labels"].([]interface{}); ok {
			prediction.Labels = make([]string, len(labels))
			for i, label := range labels {
				if str, ok := label.(string); ok {
					prediction.Labels[i] = str
				}
			}
		}

		// Extract probabilities
		if probs, ok := predData["probabilities"].(map[string]interface{}); ok {
			prediction.Probabilities = make(map[string]float64)
			for key, val := range probs {
				if num, ok := val.(float64); ok {
					prediction.Probabilities[key] = num
				}
			}
		}

		result[trackID] = prediction
	}

	return result, nil
}

