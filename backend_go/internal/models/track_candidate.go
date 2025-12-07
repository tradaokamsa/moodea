package models

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

type TrackCandidate struct {
	ID                 primitive.ObjectID          `bson:"_id,omitempty" json:"id"`
	TrackID            string                      `bson:"track_id" json:"track_id"`
	UserID             string                      `bson:"user_id" json:"user_id"` // Who discovered it
	ReccoBeatsFeatures map[string]interface{}     `bson:"reccobeats_features" json:"reccobeats_features"`
	MoodPrediction     map[string]interface{}      `bson:"mood_prediction" json:"mood_prediction"`
	CombinedFeatures   map[string]interface{}      `bson:"combined_features" json:"combined_features"`
	Approved           bool                        `bson:"approved" json:"approved"`
	Promoted           bool                        `bson:"promoted" json:"promoted"`
	ApprovedBy         string                      `bson:"approved_by,omitempty" json:"approved_by,omitempty"`
	ApprovedAt         int64                       `bson:"approved_at,omitempty" json:"approved_at,omitempty"`
	CreatedAt          time.Time                   `bson:"created_at" json:"created_at"`
}

func CreateTrackCandidate(ctx context.Context, candidate *TrackCandidate) error {
	// TODO: Implement
	return nil
}

func GetTrackCandidateByTrackID(ctx context.Context, trackID string) (*TrackCandidate, error) {
	// TODO: Implement
	return nil, nil
}

func GetExistingTrackIDs(ctx context.Context, trackIDs []string) ([]string, error) {
	// TODO: Implement
	return nil, nil
}

func GetPendingTrackCandidates(ctx context.Context, limit, offset int64) ([]TrackCandidate, error) {
	// TODO: Implement
	return nil, nil
}

func ApproveTrackCandidate(ctx context.Context, trackID, approvedBy string) error {
	// TODO: Implement
	return nil
}

func CreateTrackCandidateIndexes(ctx context.Context) error {
	// TODO: Implement
	return nil
}

