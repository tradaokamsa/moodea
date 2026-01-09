package services

import (
	"encoding/json"
	"fmt"
	"moodea/backend_go/internal/models"
)

// GetTopTracks fetches user's top tracks
func GetTopTracks(user *models.User, timeRange string, limit int, offset int) (map[string]interface{}, error) {
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
func GetTopArtists(user *models.User, timeRange string, limit int, offset int) (map[string]interface{}, error) {
	params := map[string]string{
		"time_range": timeRange,
		"limit":      fmt.Sprintf("%d", limit),
		"offset":     fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/top/artists", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
	}
	return data, nil
}

// GetArtistTopTracks fetches top tracks for a given artist
// market is optional - if not provided, uses the user's account country
func GetArtistTopTracks(user *models.User, artistID string, market string) (map[string]interface{}, error) {
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

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
	}
	return data, nil
}

// GetUserSavedAlbums fetches user's saved albums
func GetUserSavedAlbums(user *models.User, limit int, offset int, market string) (map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}

	resp, err := MakeSpotifyRequest("/me/albums", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
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
func GetCurrentUserPlaylists(user *models.User, limit int, offset int) (map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	resp, err := MakeSpotifyRequest("/me/playlists", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
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
func GetSavedTracks(user *models.User, limit int, offset int, market string) (map[string]interface{}, error) {
	params := map[string]string{
		"limit":  fmt.Sprintf("%d", limit),
		"offset": fmt.Sprintf("%d", offset),
	}
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}
	resp, err := MakeSpotifyRequest("/me/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	if err := json.Unmarshal(resp, &data); err != nil {
		return nil, err
	}
	return data, nil
}

// GetRecentlyPlayed fetches user's recently played tracks
func GetRecentlyPlayed(user *models.User, limit int, before int, after int) (map[string]interface{}, error) {
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

	return result, nil
}
