package services

import (
	"moodea/backend_go/internal/models"
)

// GetTopArtists fetches user's top artists
func GetTopArtists(user *models.User, timeRange string, limit int) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetArtistTracks fetches tracks for a given artist
func GetArtistTracks(user *models.User, artistID string, limit int) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetAlbumTracks fetches tracks from an album
func GetAlbumTracks(user *models.User, albumID string) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetUserPlaylists fetches user's playlists
func GetUserPlaylists(user *models.User, limit int) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetPlaylistTracks fetches all tracks from a playlist
func GetPlaylistTracks(user *models.User, playlistID string) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetSavedTracks fetches user's saved tracks/library
func GetSavedTracks(user *models.User, limit int) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

// GetRecentlyPlayed fetches user's recently played tracks
func GetRecentlyPlayed(user *models.User, limit int) ([]map[string]interface{}, error) {
	// TODO: Implement
	return nil, nil
}

