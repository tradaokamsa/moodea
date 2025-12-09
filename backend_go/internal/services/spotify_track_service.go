package services

import (
	"encoding/json"
	"runtime"
	"strings"
	"sync"

	"moodea/backend_go/internal/models"
	"moodea/backend_go/internal/utils"
)

// TrackDetail represents detailed track information
type TrackDetail struct {
	ID               string                   `json:"id"`
	Name             string                   `json:"name"`
	Album            map[string]interface{}   `json:"album"`
	Artists          []map[string]interface{} `json:"artists"`
	Popularity       int                      `json:"popularity"`
	DurationMs       int                      `json:"duration_ms"`
	DiscNumber       int                      `json:"disc_number"`
	AvailableMarkets []string                 `json:"available_markets"`
	Explicit         bool                     `json:"explicit"`
	Href             string                   `json:"href"`
	IsPlayable       bool                     `json:"is_playable"`
	TrackNumber      int                      `json:"track_number"`
	Type             string                   `json:"type"`
	Uri              string                   `json:"uri"`
	IsLocal          bool                     `json:"is_local"`
}

// fetchTracksBatch fetches up to 50 tracks using the Spotify /tracks?ids=... endpoint
func fetchTracksBatch(user *models.User, market string, trackIDs []string) ([]*TrackDetail, error) {
	params := map[string]string{
		"ids": strings.Join(trackIDs, ","),
	}
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}

	resp, err := MakeSpotifyRequest("/tracks", "GET", params, user)
	if err != nil {
		return nil, err
	}

	var result struct {
		Tracks []struct {
			ID               string                   `json:"id"`
			Name             string                   `json:"name"`
			Album            map[string]interface{}   `json:"album"`
			Artists          []map[string]interface{} `json:"artists"`
			Popularity       int                      `json:"popularity"`
			DurationMs       int                      `json:"duration_ms"`
			DiscNumber       int                      `json:"disc_number"`
			AvailableMarkets []string                 `json:"available_markets"`
			Explicit         bool                     `json:"explicit"`
			Href             string                   `json:"href"`
			IsPlayable       bool                     `json:"is_playable"`
			TrackNumber      int                      `json:"track_number"`
			Type             string                   `json:"type"`
			Uri              string                   `json:"uri"`
			IsLocal          bool                     `json:"is_local"`
		} `json:"tracks"`
	}

	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}

	details := make([]*TrackDetail, 0, len(result.Tracks))
	for _, t := range result.Tracks {
		// skip nil tracks (e.g., unavailable in market)
		if t.ID == "" {
			continue
		}
		details = append(details, &TrackDetail{
			ID:               t.ID,
			Name:             t.Name,
			Album:            t.Album,
			Artists:          t.Artists,
			Popularity:       t.Popularity,
			DurationMs:       t.DurationMs,
			DiscNumber:       t.DiscNumber,
			AvailableMarkets: t.AvailableMarkets,
			Explicit:         t.Explicit,
			Href:             t.Href,
			IsPlayable:       t.IsPlayable,
			TrackNumber:      t.TrackNumber,
			Type:             t.Type,
			Uri:              t.Uri,
			IsLocal:          t.IsLocal,
		})
	}

	return details, nil
}

// FetchTrackDetails fetches detailed track info from Spotify
func FetchTrackDetails(user *models.User, market string, trackID string) (*TrackDetail, error) {
	params := map[string]string{}
	if market != "" {
		params["market"] = market
	} else if user.Country != "" {
		params["market"] = user.Country
	}
	resp, err := MakeSpotifyRequest("/tracks/"+trackID, "GET", params, user)
	if err != nil {
		return nil, err
	}
	var result map[string]interface{}
	if err := json.Unmarshal(resp, &result); err != nil {
		return nil, err
	}
	track := &TrackDetail{
		ID:               result["id"].(string),
		Name:             result["name"].(string),
		Album:            result["album"].(map[string]interface{}),
		Artists:          result["artists"].([]map[string]interface{}),
		Popularity:       result["popularity"].(int),
		DurationMs:       result["duration_ms"].(int),
		DiscNumber:       result["disc_number"].(int),
		AvailableMarkets: result["available_markets"].([]string),
		Explicit:         result["explicit"].(bool),
		Href:             result["href"].(string),
		IsPlayable:       result["is_playable"].(bool),
		TrackNumber:      result["track_number"].(int),
		Type:             result["type"].(string),
		Uri:              result["uri"].(string),
		IsLocal:          result["is_local"].(bool),
	}
	return track, nil
}

// FetchMultipleTracksConcurrent fetches multiple track details concurrently
func FetchMultipleTracksConcurrent(user *models.User, market string, trackIDs []string) ([]*TrackDetail, error) {
	var (
		errOnce sync.Once
		err     error
	)

	if market == "" && user.Country != "" {
		market = user.Country
	}

	if len(trackIDs) == 0 {
		return []*TrackDetail{}, nil
	}

	// Map track ID to original indices to preserve order and handle duplicates
	pos := make(map[string][]int, len(trackIDs))
	for i, id := range trackIDs {
		pos[id] = append(pos[id], i)
	}

	tracks := make([]*TrackDetail, len(trackIDs))

	// Batch up to 50 IDs per Spotify API limits
	batchSize := 50
	wp := utils.NewWorkerPool(runtime.NumCPU())
	for start := 0; start < len(trackIDs); start += batchSize {
		end := start + batchSize
		if end > len(trackIDs) {
			end = len(trackIDs)
		}
		batch := trackIDs[start:end]

		// capture batch slice
		b := batch
		wp.Submit(func() {
			details, fetchErr := fetchTracksBatch(user, market, b)
			if fetchErr != nil {
				errOnce.Do(func() {
					err = fetchErr
				})
				return
			}
			for _, d := range details {
				if idxs, ok := pos[d.ID]; ok {
					for _, idx := range idxs {
						tracks[idx] = d
					}
				}
			}
		})
	}

	wp.Close()
	wp.Wait()
	return tracks, err
}
