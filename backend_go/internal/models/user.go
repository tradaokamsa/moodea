package models

import (
	"context"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

type User struct {
	ID             primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	SpotifyID      string             `bson:"spotifyId" json:"spotifyId"`
	DisplayName    string             `bson:"displayName" json:"displayName"`
	Email          string             `bson:"email" json:"email"`
	Country        string             `bson:"country" json:"country"`
	AccessToken    string             `bson:"accessToken" json:"accessToken"`
	RefreshToken   string             `bson:"refreshToken" json:"refreshToken"`
	TokenExpiresAt int64              `bson:"tokenExpiresAt" json:"tokenExpiresAt"`
}

var users = map[string]*User{} // key: SpotifyID

func FindOrCreateUser(ctx context.Context, spotifyId, displayName, email, country, accessToken, refreshToken string, tokenExpiresAt int64) (*User, error) {
	col := GetUserCollection()
	var user User
	err := col.FindOne(ctx, bson.M{"spotifyId": spotifyId}).Decode(&user)
	if err == nil {
		// Update tokens
		update := bson.M{
			"$set": bson.M{
				"accessToken":    accessToken,
				"refreshToken":   refreshToken,
				"tokenExpiresAt": tokenExpiresAt,
			},
		}
		_, err := col.UpdateOne(ctx, bson.M{"_id": user.ID}, update)
		if err != nil {
			return nil, err
		}
		user.AccessToken = accessToken
		user.RefreshToken = refreshToken
		user.TokenExpiresAt = tokenExpiresAt
		return &user, nil
	}
	// Create new user
	user = User{
		SpotifyID:      spotifyId,
		DisplayName:    displayName,
		Email:          email,
		Country:        country,
		AccessToken:    accessToken,
		RefreshToken:   refreshToken,
		TokenExpiresAt: tokenExpiresAt,
	}
	res, err := col.InsertOne(ctx, user)
	if err != nil {
		return nil, err
	}
	user.ID = res.InsertedID.(primitive.ObjectID)
	return &user, nil
}

func GetUserByID(ctx context.Context, id string) (*User, error) {
	col := GetUserCollection()
	var user User
	err := col.FindOne(ctx, bson.M{"spotifyId": id}).Decode(&user)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func SaveUser(ctx context.Context, user *User) error {
	col := GetUserCollection()
	filter := bson.M{"_id": user.ID}
	update := bson.M{"$set": user}
	_, err := col.UpdateOne(ctx, filter, update)
	return err
}
