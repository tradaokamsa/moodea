package models

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
)

type RecommendationSession struct {
	ID          primitive.ObjectID          `bson:"_id,omitempty" json:"id"`
	SessionID   string                      `bson:"session_id" json:"session_id"`
	UserID      string                      `bson:"user_id" json:"user_id"`
	TrackIDs    []string                    `bson:"track_ids" json:"track_ids"`
	Scores      []float64                   `bson:"scores" json:"scores"`
	Timestamp   int64                       `bson:"timestamp" json:"timestamp"`
	Context     map[string]interface{}      `bson:"context,omitempty" json:"context,omitempty"`
	CreatedAt   time.Time                   `bson:"created_at" json:"created_at"`
}

func CreateRecommendationSession(ctx context.Context, session *RecommendationSession) error {
	col := GetRecommendationSessionCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	if session.CreatedAt.IsZero() {
		session.CreatedAt = time.Now().UTC()
	}
	_, err := col.InsertOne(ctx, session)
	return err
}

func GetRecommendationSessionByID(ctx context.Context, sessionID string) (*RecommendationSession, error) {
	col := GetRecommendationSessionCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}
	var session RecommendationSession
	if err := col.FindOne(ctx, bson.M{"session_id": sessionID}).Decode(&session); err != nil {
		return nil, err
	}
	return &session, nil
}

