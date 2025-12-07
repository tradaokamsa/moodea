package services

import (
	"encoding/json"
	"fmt"
	"moodea/backend_go/internal/models"
)

// GetTopTracks fetches user's top tracks
func GetTopTracks(user *models.User, timeRange string, limit, offset int) (map[string]interface{}, error) {
	params := map[string]string{
		"time_range": timeRange,
		"limit":      fmt.Sprintf("%d", limit),
		"offset":     fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/top/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
	}
	return data, nil
}

// GetTopArtists fetches user's top artists
func GetTopArtists(user *models.User, timeRange string, limit int, offset int) ([]map[string]interface{}, error) {
	params := map[string]string{
		"time_range": timeRange,
		"limit":      fmt.Sprintf("%d", limit),
		"offset":     fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/top/artists", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			data = append(data, itemMap)
		}
	}
	return data, nil
}

// GetArtistTopTracks fetches top tracks for a given artist
// market is optional - if not provided, uses the user's account country
func GetArtistTopTracks(user *models.User, artistID string, market string) ([]map[string]interface{}, error) {
	params := map[string]string{}
	// Use provided market, or fall back to user's country, or skip if both are empty
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}
	resp, err := MakeSpotifyRequest("/artists/"+artistID+"/top-tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract tracks from Spotify response
	tracks, ok := result["tracks"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(tracks))
	for _, track := range tracks {
		if trackMap, ok := track.(map[string]interface{}); ok {
			data = append(data, trackMap)
		}
	}
	return data, nil
}

// GetAlbumTracks fetches tracks from an album
// market is optional - if not provided, uses the user's account country
func GetAlbumTracks(user *models.User, albumID string, market string, limit int, offset int) ([]map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	// Use provided market, or fall back to user's country, or skip if both are empty
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}
	resp, err := MakeSpotifyRequest("/albums/"+albumID+"/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			data = append(data, itemMap)
		}
	}
	return data, nil
}

// GetCurrentUserPlaylists fetches user's playlists
func GetCurrentUserPlaylists(user *models.User, limit int, offset int) ([]map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/playlists", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			data = append(data, itemMap)
		}
	}
	return data, nil
}

// GetPlaylistTracks fetches all tracks from a playlist
// market is optional - if not provided, uses the user's account country
func GetPlaylistTracks(user *models.User, playlistID string, market string, fields string, limit int, offset int, additionalTypes string) ([]map[string]interface{}, error) {
	if additionalTypes == "" {
		additionalTypes = "track"
	}
	params := map[string]string{
		"fields":           fields,
		"limit":            fmt.Sprintf("%d", limit),
		"offset":           fmt.Sprintf("%d", offset),
		"additional_types": additionalTypes,
	}
	// Use provided market, or fall back to user's country, or skip if both are empty
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}
	resp, err := MakeSpotifyRequest("/playlists/"+playlistID+"/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			data = append(data, itemMap)
		}
	}
	return data, nil
}

// GetSavedTracks fetches user's saved tracks/library
func GetSavedTracks(user *models.User, limit int, offset int) ([]map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			// Spotify returns items with nested "track" object
			if track, ok := itemMap["track"].(map[string]interface{}); ok {
				data = append(data, track)
			} else {
				data = append(data, itemMap)
			}
		}
	}
	return data, nil
}

// GetRecentlyPlayed fetches user's recently played tracks
func GetRecentlyPlayed(user *models.User, limit int, before int, after int) ([]map[string]interface{}, error) {
	params := map[string]string{
		"limit": fmt.Sprintf("%d", limit),
	}
	if before > 0 {
		params["before"] = fmt.Sprintf("%d", before)
	}
	if after > 0 {
		params["after"] = fmt.Sprintf("%d", after)
	}
	resp, err := MakeSpotifyRequest("/me/player/recently-played", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	// Extract items from Spotify response
	items, ok := result["items"].([]interface{})
	if !ok {
		// If items is not an array, return empty list (user might not have recent plays)
		return []map[string]interface{}{}, nil
	}

	// If items array is empty, return empty list
	if len(items) == 0 {
		return []map[string]interface{}{}, nil
	}

	data := make([]map[string]interface{}, 0, len(items))
	for _, item := range items {
		if itemMap, ok := item.(map[string]interface{}); ok {
			// Spotify returns items with nested "track" object and "played_at" timestamp
			if track, ok := itemMap["track"].(map[string]interface{}); ok {
				// Include played_at timestamp if available
				if playedAt, ok := itemMap["played_at"].(string); ok {
					track["played_at"] = playedAt
				}
				data = append(data, track)
			} else {
				// Fallback: return the whole item if track is not found
				data = append(data, itemMap)
			}
		}
	}
	return data, nil
}
