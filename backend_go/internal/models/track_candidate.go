package models

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type TrackCandidate struct {
	ID                 primitive.ObjectID     `bson:"_id,omitempty" json:"id"`
	TrackID            string                 `bson:"track_id" json:"track_id"`
	UserID             string                 `bson:"user_id" json:"user_id"` // Who discovered it
	ReccoBeatsFeatures map[string]interface{} `bson:"reccobeats_features" json:"reccobeats_features"`
	MoodPrediction     map[string]interface{} `bson:"mood_prediction" json:"mood_prediction"`
	CombinedFeatures   map[string]interface{} `bson:"combined_features" json:"combined_features"`
	Approved           bool                   `bson:"approved" json:"approved"`
	Promoted           bool                   `bson:"promoted" json:"promoted"`
	ApprovedBy         string                 `bson:"approved_by,omitempty" json:"approved_by,omitempty"`
	ApprovedAt         int64                  `bson:"approved_at,omitempty" json:"approved_at,omitempty"`
	CreatedAt          time.Time              `bson:"created_at" json:"created_at"`
}

// CreateTrackCandidate inserts a new track candidate.
func CreateTrackCandidate(ctx context.Context, candidate *TrackCandidate) error {
	col := GetTrackCandidateCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	if candidate.CreatedAt.IsZero() {
		candidate.CreatedAt = time.Now().UTC()
	}
	_, err := col.InsertOne(ctx, candidate)
	return err
}

// GetTrackCandidateByTrackID fetches a candidate by track_id.
func GetTrackCandidateByTrackID(ctx context.Context, trackID string) (*TrackCandidate, error) {
	col := GetTrackCandidateCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}
	var candidate TrackCandidate
	if err := col.FindOne(ctx, bson.M{"track_id": trackID}).Decode(&candidate); err != nil {
		return nil, err
	}
	return &candidate, nil
}

// GetExistingTrackIDs returns IDs that already exist in the collection.
func GetExistingTrackIDs(ctx context.Context, trackIDs []string) ([]string, error) {
	col := GetTrackCandidateCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}
	cursor, err := col.Find(ctx, bson.M{"track_id": bson.M{"$in": trackIDs}}, options.Find().SetProjection(bson.M{"track_id": 1}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var existing []string
	for cursor.Next(ctx) {
		var tc TrackCandidate
		if err := cursor.Decode(&tc); err != nil {
			return nil, err
		}
		existing = append(existing, tc.TrackID)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return existing, nil
}

// GetPendingTrackCandidates returns candidates not yet approved.
func GetPendingTrackCandidates(ctx context.Context, limit, offset int64) ([]TrackCandidate, error) {
	col := GetTrackCandidateCollection()
	if col == nil {
		return nil, mongo.ErrClientDisconnected
	}

	opts := options.Find()
	if limit > 0 {
		opts.SetLimit(limit)
	}
	if offset > 0 {
		opts.SetSkip(offset)
	}

	cursor, err := col.Find(ctx, bson.M{"approved": false}, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var candidates []TrackCandidate
	for cursor.Next(ctx) {
		var tc TrackCandidate
		if err := cursor.Decode(&tc); err != nil {
			return nil, err
		}
		candidates = append(candidates, tc)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return candidates, nil
}

// ApproveTrackCandidate marks a candidate approved.
func ApproveTrackCandidate(ctx context.Context, trackID, approvedBy string) error {
	col := GetTrackCandidateCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	update := bson.M{
		"$set": bson.M{
			"approved":    true,
			"approved_by": approvedBy,
			"approved_at": time.Now().UTC().Unix(),
		},
	}
	_, err := col.UpdateOne(ctx, bson.M{"track_id": trackID}, update)
	return err
}

// CreateTrackCandidateIndexes creates necessary indexes.
func CreateTrackCandidateIndexes(ctx context.Context) error {
	col := GetTrackCandidateCollection()
	if col == nil {
		return mongo.ErrClientDisconnected
	}
	model := mongo.IndexModel{
		Keys:    bson.D{{Key: "track_id", Value: 1}},
		Options: options.Index().SetUnique(true),
	}
	_, err := col.Indexes().CreateOne(ctx, model)
	return err
}

// ApproveAllTrackCandidates marks all unapproved candidates as approved.
func ApproveAllTrackCandidates(ctx context.Context, approvedBy string) (int64, error) {
	col := GetTrackCandidateCollection()
	if col == nil {
		return 0, mongo.ErrClientDisconnected
	}
	update := bson.M{
		"$set": bson.M{
			"approved":    true,
			"approved_by": approvedBy,
			"approved_at": time.Now().UTC().Unix(),
		},
	}
	result, err := col.UpdateMany(ctx, bson.M{"approved": false}, update)
	if err != nil {
		return 0, err
	}
	return result.ModifiedCount, nil
}

func TrackCandidateExistByTrackID(ctx context.Context, trackID string) (bool, error) {
    col := GetTrackCandidateCollection()
    if col == nil {
        return false, mongo.ErrClientDisconnected
    }
    filter := bson.M{
        "track_id": trackID,
    }
    opts := options.FindOne().SetProjection(bson.M{"_id": 1})
    err := col.FindOne(ctx, filter, opts).Err()
    if err == mongo.ErrNoDocuments {
        return false, nil // none exist
    }
    if err != nil {
        return false, err
    }
    return true, nil 
}

