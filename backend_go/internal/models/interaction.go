package models

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

type Interaction struct {
	ID              primitive.ObjectID          `bson:"_id,omitempty" json:"id"`
	UserID          string                      `bson:"user_id" json:"user_id"`
	TrackID         string                      `bson:"track_id" json:"track_id"`
	InteractionType string                      `bson:"interaction_type" json:"interaction_type"` // "skip", "continue", "like"
	Score           int                         `bson:"score" json:"score"`                       // -1, 1, 3
	SessionID       string                      `bson:"session_id" json:"session_id"`
	Timestamp       int64                       `bson:"timestamp" json:"timestamp"`
	Context         map[string]interface{}      `bson:"context,omitempty" json:"context,omitempty"`
	CreatedAt       time.Time                   `bson:"created_at" json:"created_at"`
}

func CreateInteraction(ctx context.Context, interaction *Interaction) error {
	// TODO: Implement
	return nil
}

func GetUserInteractions(ctx context.Context, userID string, limit int64) ([]Interaction, error) {
	// TODO: Implement
	return nil, nil
}

func GetInteractionsByTrackID(ctx context.Context, trackID string, limit int64) ([]Interaction, error) {
	// TODO: Implement
	return nil, nil
}

func CreateInteractionIndexes(ctx context.Context) error {
	// TODO: Implement
	return nil
}

