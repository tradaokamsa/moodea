package services

import (
	"context"

	"moodea/backend_go/internal/models"
)

// ProcessUserFeaturesAsync orchestrates entire login flow for track processing
func ProcessUserFeaturesAsync(user *models.User) {
	// TODO: Implement
	// Flow:
	// 1. Fetch all user-related tracks concurrently (top tracks, artists, playlists, saved, recently played)
	// 2. Deduplicate track IDs (check MongoDB track_candidates and optionally Feast track_features)
	// 3. For new tracks only:
	//    - Fetch ReccoBeats audio features (concurrent batches)
	//    - Call Python ML service for mood prediction
	//    - Combine features (Spotify metadata + ReccoBeats + mood)
	//    - Store as TrackCandidate in MongoDB (approved=false)
	// 4. Send user-events to Kafka
	// 5. Handle errors gracefully (log, continue processing)
}

// ExtractAllUserTracks fetches all user-related tracks from Spotify concurrently
func ExtractAllUserTracksIDs(user *models.User) ([]string, error) {
	trackIDs := []string{}

	// GetTopTracks
	topTracks, err := GetTopTracks(user, "short_term", 50, 0)
	if err != nil {
		return nil, err
	}
	totalTracks := int(topTracks["total"].(float64))
	for i := 0; i < totalTracks; i += 50 {
		tracks, err := GetTopTracks(user, "short_term", 50, i)
		if err != nil {
			return nil, err
		}
		items := tracks["items"].([]interface{})
		for _, item := range items {
			trackIDs = append(trackIDs, item.(map[string]interface{})["id"].(string))
		}
	}

	// GetTopArtists + GetArtistTopTracks
	topArtists, err := GetTopArtists(user, "short_term", 50, 0)
	if err != nil {
		return nil, err
	}
	totalArtists := int(topArtists["total"].(float64))
	for i := 0; i < totalArtists; i += 50 {
		artists, err := GetTopArtists(user, "short_term", 50, i)
		if err != nil {
			return nil, err
		}
		items := artists["items"].([]interface{})
		for _, item := range items {
			currentArtistID := item.(map[string]interface{})["id"].(string)
			artistTopTracks, err := GetArtistTopTracks(user, currentArtistID, "")
			if err != nil {
				return nil, err
			}
			tracks := artistTopTracks["tracks"].([]interface{})
			for _, track := range tracks {
				trackIDs = append(trackIDs, track.(map[string]interface{})["id"].(string))
			}
		}
	}

	// GetUserSavedAlbums + GetAlbumTracks
	userSavedAlbums, err := GetUserSavedAlbums(user, 50, 0, "")
	if err != nil {
		return nil, err
	}
	totalAlbums := int(userSavedAlbums["total"].(float64))
	for i := 0; i < totalAlbums; i += 50 {
		albums, err := GetUserSavedAlbums(user, 50, i, "")
		if err != nil {
			return nil, err
		}
		items := albums["items"].([]interface{})
		for _, item := range items {
			currentAlbumID := item.(map[string]interface{})["id"].(string)
			albumTracks, err := GetAlbumTracks(user, currentAlbumID, "", 50, 0)
			if err != nil {
				return nil, err
			}
			for _, track := range albumTracks {
				trackID := track["id"].(string)
				trackIDs = append(trackIDs, trackID)
			}
		}
	}

	// GetCurrentUserPlaylists + GetPlaylistTracks
	top50Playlists, err := GetCurrentUserPlaylists(user, 50, 0)
	if err != nil {
		return nil, err
	}
	itemsPlaylists := top50Playlists["items"].([]interface{})
	for _, item := range itemsPlaylists {
		currentPlaylistID := item.(map[string]interface{})["id"].(string)
		playlistTracks, err := GetPlaylistTracks(user, currentPlaylistID, "", "items(track(id))", 50, 0, "")
		if err != nil {
			return nil, err
		}
		for _, playlistTrack := range playlistTracks {
			currentPlaylistTrackID := playlistTrack["track"].(map[string]interface{})["id"].(string)
			trackIDs = append(trackIDs, currentPlaylistTrackID)
		}
	}

	// GetSavedTracks
	savedTracks, err := GetSavedTracks(user, 50, 0, "")
	if err != nil {
		return nil, err
	}
	totalSavedTracks := int(savedTracks["total"].(float64))
	for i := 0; i < totalSavedTracks; i += 50 {
		savedTracks, err := GetSavedTracks(user, 50, i, "")
		if err != nil {
			return nil, err
		}
		items := savedTracks["items"].([]interface{})
		for _, item := range items {
			currentSavedTrackID := item.(map[string]interface{})["id"].(string)
			trackIDs = append(trackIDs, currentSavedTrackID)
		}
	}

	// GetRecentlyPlayed
	recentlyPlayed, err := GetRecentlyPlayed(user, 50, 0, 0)
	if err != nil {
		return nil, err
	}
	items := recentlyPlayed["items"].([]interface{})
	for _, item := range items {
		currentRecentlyPlayedTrackObject := item.(map[string]interface{})["track"].(map[string]interface{})
		currentRecentlyPlayedTrackID := currentRecentlyPlayedTrackObject["id"].(string)
		trackIDs = append(trackIDs, currentRecentlyPlayedTrackID)
	}

	return trackIDs, nil
}

// DeduplicateTracks checks MongoDB track_candidates for existing tracks, returns only new track IDs
func DeduplicateTracksIDs(ctx context.Context, trackIDs []string) ([]string, error) {
	if len(trackIDs) == 0 {
		return []string{}, nil
	}

	nonDuplicatedTrackIDs := []string{}
	for _, trackID := range trackIDs {
		trackCandidateExist, err := models.TrackCandidateExistByTrackID(ctx, trackID)
		if err != nil {
			return []string{}, err
		}
		if !trackCandidateExist {
			nonDuplicatedTrackIDs = append(nonDuplicatedTrackIDs, trackID)
		}
	}
	return nonDuplicatedTrackIDs, nil
}
