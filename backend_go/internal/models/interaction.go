package models

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
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
	col := GetInteractionCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	if interaction.CreatedAt.IsZero() {
		interaction.CreatedAt = time.Now().UTC()
	}
	_, err := col.InsertOne(ctx, interaction)
	return err
}

func GetUserInteractions(ctx context.Context, userID string, limit int64) ([]Interaction, error) {
	col := GetInteractionCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}
	findOption := options.Find()
	if limit > 0 {
		findOption.SetLimit(limit)
	}
	cursor, err := col.Find(ctx, bson.M{"user_id": userID}, findOption)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var interactions []Interaction
	for cursor.Next(ctx) {
		var interaction Interaction
		if err := cursor.Decode(&interaction); err != nil {
			return nil, err
		}
		interactions = append(interactions, interaction)
	}
	return interactions, nil
}

func GetInteractionsByTrackID(ctx context.Context, trackID string, limit int64) ([]Interaction, error) {
	col := GetInteractionCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}
	findOptions := options.Find()	
	if limit > 0 {
		findOptions.SetLimit(limit)
	}
	cursor, err := col.Find(ctx, bson.M{"track_id": trackID}, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var interactions []Interaction
	for cursor.Next(ctx) {
		var interaction Interaction
		if err := cursor.Decode(&interaction); err != nil {
			return nil, err
		}
		interactions = append(interactions, interaction)
	}
	return interactions, nil	
}

func CreateInteractionIndexesOnTimestamp(ctx context.Context) error {
	col := GetInteractionCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	model := mongo.IndexModel{
		Keys:    bson.D{{Key: "timestamp", Value: 1}},
		Options: options.Index().SetUnique(false),
	}
	_, err := col.Indexes().CreateOne(ctx, model)
	if err != nil {
		return err
	}
	return err
}	

