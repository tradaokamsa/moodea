package services

import (
	"context"
	"log"
	"runtime"
	"sync"
	"time"

	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/utils"
)

// ProcessUserFeaturesAsync orchestrates entire login flow for track processing
// This function runs asynchronously and handles errors gracefully, continuing processing
// even if individual steps fail.
func ProcessUserFeaturesAsync(user *models.User) {
	// Flow:
	// 1. Fetch all user-related tracks concurrently (top tracks, artists, playlists, saved, recently played)
	// 2. Deduplicate track IDs (check MongoDB track_candidates and optionally Feast track_features)
	// 3. For new tracks only:
	//    - Fetch ReccoBeats audio features (concurrent batches)
	//    - Call Python ML service for mood prediction
	//    - Combine features (Spotify metadata + ReccoBeats + mood)
	//    - Store as TrackCandidate in MongoDB (approved=false)
	// 4. Send user-events to Kafka
	go func() {
		ctx := context.Background()

		// Step 1: Fetch all user-related tracks concurrently
		log.Printf("[ProcessUserFeaturesAsync] Starting track extraction for user %s", user.SpotifyID)
		allTrackIDs, err := ExtractAllUserTracksIDs(user)
		if err != nil {
			log.Printf("[ProcessUserFeaturesAsync] Error extracting track IDs: %v", err)
			return
		}
		log.Printf("[ProcessUserFeaturesAsync] Extracted %d total track IDs", len(allTrackIDs))

		if len(allTrackIDs) == 0 {
			log.Printf("[ProcessUserFeaturesAsync] No tracks found for user %s", user.SpotifyID)
			// Still send user event with empty tracks
			sendUserEvent(user, allTrackIDs)
			return
		}

		// Step 2: Deduplicate track IDs (check MongoDB track_candidates)
		newTrackIDs, err := DeduplicateTracksIDs(ctx, allTrackIDs)
		if err != nil {
			log.Printf("[ProcessUserFeaturesAsync] Error deduplicating tracks: %v", err)
			// Continue with all tracks if deduplication fails
			newTrackIDs = allTrackIDs
		}
		log.Printf("[ProcessUserFeaturesAsync] Found %d new tracks after deduplication", len(newTrackIDs))

		// Step 3: Process new tracks (fetch features, predict mood, store candidates)
		if len(newTrackIDs) > 0 {
			processNewTracks(ctx, user, newTrackIDs)
		}

		// Step 4: Send user-events to Kafka
		sendUserEvent(user, allTrackIDs)

		log.Printf("[ProcessUserFeaturesAsync] Completed processing for user %s", user.SpotifyID)
	}()
}

// processNewTracks processes new tracks: fetches features, predicts mood, and stores as candidates
func processNewTracks(ctx context.Context, user *models.User, trackIDs []string) {
	if len(trackIDs) == 0 {
		return
	}

	// Process tracks in batches for better concurrency and resource management
	batchSize := 50
	totalBatches := (len(trackIDs) + batchSize - 1) / batchSize
	log.Printf("[processNewTracks] Processing %d tracks in %d batches", len(trackIDs), totalBatches)

	wp := utils.NewWorkerPool(runtime.NumCPU())
	var processedCount int64
	var processedMu sync.Mutex

	for i := 0; i < len(trackIDs); i += batchSize {
		end := i + batchSize
		if end > len(trackIDs) {
			end = len(trackIDs)
		}
		batch := trackIDs[i:end]

		wp.Submit(func() {
			processTrackBatch(ctx, user, batch)
			processedMu.Lock()
			processedCount += int64(len(batch))
			current := processedCount
			processedMu.Unlock()
			log.Printf("[processNewTracks] Processed %d/%d tracks", current, len(trackIDs))
		})
	}

	wp.Close()
	wp.Wait()
	log.Printf("[processNewTracks] Completed processing all %d tracks", len(trackIDs))
}

// processTrackBatch processes a batch of tracks concurrently
func processTrackBatch(ctx context.Context, user *models.User, trackIDs []string) {
	if len(trackIDs) == 0 {
		return
	}

	// Step 3a: Fetch ReccoBeats audio features (concurrent batches)
	reccobeatsFeatures, err := GetAudioFeatures(trackIDs)
	if err != nil {
		log.Printf("[processTrackBatch] Error fetching ReccoBeats features for batch: %v", err)
		// Continue processing with empty features map
		reccobeatsFeatures = make(map[string]*AudioFeatures)
	}

	// Step 3b: Fetch Spotify track metadata concurrently
	spotifyTracks, err := FetchMultipleTracksConcurrent(user, "", trackIDs)
	if err != nil {
		log.Printf("[processTrackBatch] Error fetching Spotify track details: %v", err)
		// Continue with what we have - some tracks may still have metadata
	}

	// Create a map of track ID to Spotify track detail
	spotifyMap := make(map[string]*TrackDetail)
	for _, track := range spotifyTracks {
		if track != nil {
			spotifyMap[track.ID] = track
		}
	}

	// Step 3c: Call Python ML service for mood prediction
	moodPredictions, err := PredictMoodForTracks(trackIDs, reccobeatsFeatures)
	if err != nil {
		log.Printf("[processTrackBatch] Error predicting mood for tracks: %v", err)
		// Continue processing with empty predictions map
		moodPredictions = make(map[string]*MoodPrediction)
	}

	// Step 3d: Process each track to combine features and store
	// Only process tracks that have ReccoBeats features
	for trackID, features := range reccobeatsFeatures {
		if features == nil || features.Features == nil || len(features.Features) == 0 {
			log.Printf("[processTrackBatch] Skipping track %s - no ReccoBeats features", trackID)
			continue
		}
		processSingleTrack(ctx, user, trackID, spotifyMap[trackID], features, moodPredictions[trackID])
	}
}

// processSingleTrack combines features and stores a single track candidate
func processSingleTrack(
	ctx context.Context,
	user *models.User,
	trackID string,
	spotifyTrack *TrackDetail,
	reccobeatsFeatures *AudioFeatures,
	moodPrediction *MoodPrediction,
) {
	// Prepare combined features map
	combinedFeatures := make(map[string]interface{})

	// Add Spotify metadata
	if spotifyTrack != nil {
		spotifyData := map[string]interface{}{
			"id":          spotifyTrack.ID,
			"name":        spotifyTrack.Name,
			"album":       spotifyTrack.Album,
			"artists":     spotifyTrack.Artists,
			"popularity":  spotifyTrack.Popularity,
			"duration_ms": spotifyTrack.DurationMs,
			"explicit":    spotifyTrack.Explicit,
		}
		combinedFeatures["spotify"] = spotifyData
	}

	// Add ReccoBeats features
	var reccobeatsData map[string]interface{}
	if reccobeatsFeatures != nil && reccobeatsFeatures.Features != nil {
		reccobeatsData = reccobeatsFeatures.Features
		combinedFeatures["reccobeats"] = reccobeatsData
	} else {
		combinedFeatures["reccobeats"] = nil
	}

	// Add mood prediction
	var moodData map[string]interface{}
	if moodPrediction != nil {
		moodData = map[string]interface{}{
			"labels":        moodPrediction.Labels,
			"probabilities": moodPrediction.Probabilities,
		}
		combinedFeatures["mood"] = moodData
	} else {
		combinedFeatures["mood"] = nil
	}

	// Convert ReccoBeats features to map[string]interface{} for storage
	var reccobeatsFeaturesMap map[string]interface{}
	if reccobeatsFeatures != nil {
		reccobeatsFeaturesMap = reccobeatsFeatures.Features
		if reccobeatsFeaturesMap == nil {
			reccobeatsFeaturesMap = make(map[string]interface{})
		}
	}

	// Convert mood prediction to map[string]interface{} for storage
	var moodPredictionMap map[string]interface{}
	if moodPrediction != nil {
		moodPredictionMap = map[string]interface{}{
			"labels":        moodPrediction.Labels,
			"probabilities": moodPrediction.Probabilities,
		}
	}

	// Create TrackCandidate
	candidate := &models.TrackCandidate{
		TrackID:            trackID,
		UserID:             user.SpotifyID,
		ReccoBeatsFeatures: reccobeatsFeaturesMap,
		MoodPrediction:     moodPredictionMap,
		CombinedFeatures:   combinedFeatures,
		Approved:           false,
		Promoted:           false,
		CreatedAt:          time.Now().UTC(),
	}

	// Store in MongoDB
	err := models.CreateTrackCandidate(ctx, candidate)
	if err != nil {
		log.Printf("[processSingleTrack] Error storing track candidate %s: %v", trackID, err)
		// Don't return - continue processing other tracks
		return
	}

	log.Printf("[processSingleTrack] Stored track candidate %s for user %s", trackID, user.SpotifyID)
}

// sendUserEvent sends user-events to Kafka
func sendUserEvent(user *models.User, trackIDs []string) {
	event := &UserEvent{
		UserID:    user.SpotifyID,
		EventType: "user_login_tracks_discovered",
		Timestamp: time.Now().Unix(),
		Data: map[string]interface{}{
			"total_tracks": len(trackIDs),
			"track_ids":    trackIDs,
			// Add other relevant user data if needed
		},
	}

	err := ProduceUserEvent(event)
	if err != nil {
		log.Printf("[sendUserEvent] Error sending user event to Kafka: %v", err)
		// This is non-critical, continue even if Kafka fails
		return
	}

	log.Printf("[sendUserEvent] Sent user event to Kafka for user %s with %d tracks", user.SpotifyID, len(trackIDs))
}

// ExtractAllUserTracksIDs fetches all user-related tracks from Spotify concurrently
func ExtractAllUserTracksIDs(user *models.User) ([]string, error) {
	var (
		trackIDsMu sync.Mutex
		trackIDs   = make([]string, 0)
		wg         sync.WaitGroup
	)

	// Helper function to safely append track IDs
	appendTrackIDs := func(ids []string) {
		if len(ids) == 0 {
			return
		}
		trackIDsMu.Lock()
		defer trackIDsMu.Unlock()
		trackIDs = append(trackIDs, ids...)
	}

	// Helper function to extract track IDs from items
	extractTrackIDsFromItems := func(items []interface{}) []string {
		ids := make([]string, 0, len(items))
		for _, item := range items {
			if itemMap, ok := item.(map[string]interface{}); ok {
				if trackID, ok := itemMap["id"].(string); ok && trackID != "" {
					ids = append(ids, trackID)
				}
			}
		}
		return ids
	}

	// Task 1: GetTopTracks (medium_term only)
	wg.Add(1)
	go func() {
		defer wg.Done()
		timeRange := "medium_term"
		// Get first page to determine total
		topTracks, err := GetTopTracks(user, timeRange, 50, 0)
		if err != nil {
			log.Printf("Error fetching top tracks for %s: %v", timeRange, err)
			return
		}

		totalTracks, ok := topTracks["total"].(float64)
		if !ok {
			log.Printf("Invalid total in top tracks response for %s", timeRange)
			return
		}

		total := int(totalTracks)
		var paginationWg sync.WaitGroup

		// Process all pages concurrently
		for i := 0; i < total; i += 50 {
			offset := i
			paginationWg.Add(1)
			go func(o int) {
				defer paginationWg.Done()
				tracks, err := GetTopTracks(user, timeRange, 50, o)
				if err != nil {
					log.Printf("Error fetching top tracks page (offset %d) for %s: %v", o, timeRange, err)
					return
				}

				items, ok := tracks["items"].([]interface{})
				if !ok {
					return
				}

				ids := extractTrackIDsFromItems(items)
				appendTrackIDs(ids)
			}(offset)
		}
		paginationWg.Wait()
	}()

	// Task 2: GetTopArtists + GetArtistTopTracks (medium_term only)
	wg.Add(1)
	go func() {
		defer wg.Done()
		timeRange := "medium_term"
		// Get first page to determine total
		topArtists, err := GetTopArtists(user, timeRange, 20, 0)
		if err != nil {
			log.Printf("Error fetching top artists for %s: %v", timeRange, err)
			return
		}

		totalArtists, ok := topArtists["total"].(float64)
		if !ok {
			log.Printf("Invalid total in top artists response for %s", timeRange)
			return
		}

		total := int(totalArtists)
		var paginationWg sync.WaitGroup

		// Process all artist pages concurrently
		for i := 0; i < total; i += 20 {
			offset := i
			paginationWg.Add(1)
			go func(o int) {
				defer paginationWg.Done()
				artists, err := GetTopArtists(user, timeRange, 20, o)
				if err != nil {
					log.Printf("Error fetching top artists page (offset %d) for %s: %v", o, timeRange, err)
					return
				}

				items, ok := artists["items"].([]interface{})
				if !ok {
					return
				}

				// Fetch tracks for all artists in this page concurrently
				var artistWg sync.WaitGroup
				for _, item := range items {
					if itemMap, ok := item.(map[string]interface{}); ok {
						artistID, ok := itemMap["id"].(string)
						if !ok || artistID == "" {
							continue
						}

						artistWg.Add(1)
						go func(aID string) {
							defer artistWg.Done()
							artistTopTracks, err := GetArtistTopTracks(user, aID, "")
							if err != nil {
								log.Printf("Error fetching top tracks for artist %s: %v", aID, err)
								return
							}

							tracks, ok := artistTopTracks["tracks"].([]interface{})
							if !ok {
								return
							}

							ids := extractTrackIDsFromItems(tracks)
							appendTrackIDs(ids)
						}(artistID)
					}
				}
				artistWg.Wait()
			}(offset)
		}
		paginationWg.Wait()
	}()

	// Task 3: GetUserSavedAlbums + GetAlbumTracks
	wg.Add(1)
	go func() {
		defer wg.Done()
		// Get first page to determine total
		userSavedAlbums, err := GetUserSavedAlbums(user, 50, 0, "")
		if err != nil {
			log.Printf("Error fetching saved albums: %v", err)
			return
		}

		totalAlbums, ok := userSavedAlbums["total"].(float64)
		if !ok {
			log.Printf("Invalid total in saved albums response")
			return
		}

		total := int(totalAlbums)
		var paginationWg sync.WaitGroup

		// Process all album pages concurrently
		for i := 0; i < total; i += 50 {
			offset := i
			paginationWg.Add(1)
			go func(o int) {
				defer paginationWg.Done()
				albums, err := GetUserSavedAlbums(user, 50, o, "")
				if err != nil {
					log.Printf("Error fetching saved albums page (offset %d): %v", o, err)
					return
				}

				items, ok := albums["items"].([]interface{})
				if !ok {
					return
				}

				// Fetch tracks for all albums in this page concurrently
				var albumWg sync.WaitGroup
				for _, item := range items {
					if itemMap, ok := item.(map[string]interface{}); ok {
						albumID, ok := itemMap["id"].(string)
						if !ok || albumID == "" {
							continue
						}

						albumWg.Add(1)
						go func(aID string) {
							defer albumWg.Done()
							albumTracks, err := GetAlbumTracks(user, aID, "", 50, 0)
							if err != nil {
								log.Printf("Error fetching tracks for album %s: %v", aID, err)
								return
							}

							ids := make([]string, 0, len(albumTracks))
							for _, track := range albumTracks {
								if trackID, ok := track["id"].(string); ok && trackID != "" {
									ids = append(ids, trackID)
								}
							}
							appendTrackIDs(ids)
						}(albumID)
					}
				}
				albumWg.Wait()
			}(offset)
		}
		paginationWg.Wait()
	}()

	// Task 4: GetCurrentUserPlaylists + GetPlaylistTracks
	wg.Add(1)
	go func() {
		defer wg.Done()
		// Get first page of playlists
		top50Playlists, err := GetCurrentUserPlaylists(user, 50, 0)
		if err != nil {
			log.Printf("Error fetching playlists: %v", err)
			return
		}

		itemsPlaylists, ok := top50Playlists["items"].([]interface{})
		if !ok {
			log.Printf("Invalid items in playlists response")
			return
		}

		// Fetch tracks for all playlists concurrently
		var playlistWg sync.WaitGroup
		for _, item := range itemsPlaylists {
			if itemMap, ok := item.(map[string]interface{}); ok {
				playlistID, ok := itemMap["id"].(string)
				if !ok || playlistID == "" {
					continue
				}

				playlistWg.Add(1)
				go func(pID string) {
					defer playlistWg.Done()
					playlistTracks, err := GetPlaylistTracks(user, pID, "", "items(track(id))", 50, 0, "")
					if err != nil {
						log.Printf("Error fetching tracks for playlist %s: %v", pID, err)
						return
					}

					ids := make([]string, 0, len(playlistTracks))
					for _, playlistTrack := range playlistTracks {
						if trackMap, ok := playlistTrack["track"].(map[string]interface{}); ok {
							if trackID, ok := trackMap["id"].(string); ok && trackID != "" {
								ids = append(ids, trackID)
							}
						}
					}
					appendTrackIDs(ids)
				}(playlistID)
			}
		}
		playlistWg.Wait()
	}()

	// Task 5: GetSavedTracks
	wg.Add(1)
	go func() {
		defer wg.Done()
		// Get first page to determine total
		savedTracks, err := GetSavedTracks(user, 50, 0, "")
		if err != nil {
			log.Printf("Error fetching saved tracks: %v", err)
			return
		}

		totalSavedTracks, ok := savedTracks["total"].(float64)
		if !ok {
			log.Printf("Invalid total in saved tracks response")
			return
		}

		total := int(totalSavedTracks)
		var paginationWg sync.WaitGroup

		// Process all pages concurrently
		for i := 0; i < total; i += 50 {
			offset := i
			paginationWg.Add(1)
			go func(o int) {
				defer paginationWg.Done()
				savedTracksPage, err := GetSavedTracks(user, 50, o, "")
				if err != nil {
					log.Printf("Error fetching saved tracks page (offset %d): %v", o, err)
					return
				}

				items, ok := savedTracksPage["items"].([]interface{})
				if !ok {
					return
				}

				ids := make([]string, 0, len(items))
				for _, item := range items {
					if itemMap, ok := item.(map[string]interface{}); ok {
						if trackMap, ok := itemMap["track"].(map[string]interface{}); ok {
							if trackID, ok := trackMap["id"].(string); ok && trackID != "" {
								ids = append(ids, trackID)
							}
						}
					}
				}
				appendTrackIDs(ids)
			}(offset)
		}
		paginationWg.Wait()
	}()

	// Task 6: GetRecentlyPlayed
	wg.Add(1)
	go func() {
		defer wg.Done()
		recentlyPlayed, err := GetRecentlyPlayed(user, 50, 0, 0)
		if err != nil {
			log.Printf("Error fetching recently played tracks: %v", err)
			return
		}

		items, ok := recentlyPlayed["items"].([]interface{})
		if !ok {
			log.Printf("Invalid items in recently played response")
			return
		}

		ids := make([]string, 0, len(items))
		for _, item := range items {
			if itemMap, ok := item.(map[string]interface{}); ok {
				if trackMap, ok := itemMap["track"].(map[string]interface{}); ok {
					if trackID, ok := trackMap["id"].(string); ok && trackID != "" {
						ids = append(ids, trackID)
					}
				}
			}
		}
		appendTrackIDs(ids)
	}()

	// Wait for all tasks to complete
	wg.Wait()

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
