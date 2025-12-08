package models

import (
	"context"
	"log"
	"os"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

var (
	clientInstance    *mongo.Client
	clientInstanceErr error
	mongoOnce         sync.Once
)

const dbName = "moodea"
const userCollectionName = "users"
const trackCandidateCollectionName = "track_candidates"
const interactionCollectionName = "interactions"

func getMongoClient() (*mongo.Client, error) {
	mongoOnce.Do(func() {
		uri := os.Getenv("MONGODB_URI")
		if uri == "" {
			uri = "mongodb://localhost:27017"
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
		if err != nil {
			clientInstanceErr = err
			return
		}
		clientInstance = client
	})
	return clientInstance, clientInstanceErr
}

func GetUserCollection() *mongo.Collection {
	client, err := getMongoClient()
	if err != nil {
		log.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	return client.Database(dbName).Collection(userCollectionName)
}

func GetTrackCandidateCollection() *mongo.Collection {
	client, err := getMongoClient()
	if err != nil {
		log.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	return client.Database(dbName).Collection(trackCandidateCollectionName)
}

func GetInteractionCollection() *mongo.Collection {
	client, err := getMongoClient()
	if err != nil {
		log.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	return client.Database(dbName).Collection(interactionCollectionName)
}