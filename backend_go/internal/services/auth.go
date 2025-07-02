package services

import (
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type UserClaims struct {
	ID        string `json:"id"`
	SpotifyID string `json:"spotifyId"`
	Email     string `json:"email"`
	jwt.RegisteredClaims
}

func GenerateToken(id, spotifyId, email string) (string, error) {
	secret := os.Getenv("JWT_SECRET")
	expiresIn := os.Getenv("JWT_EXPIRES_IN")
	dur, err := time.ParseDuration(expiresIn)
	if err != nil {
		dur = time.Hour
	}
	claims := UserClaims{
		ID:        id,
		SpotifyID: spotifyId,
		Email:     email,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(dur)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

func VerifyToken(tokenString string) (*UserClaims, error) {
	secret := os.Getenv("JWT_SECRET")
	token, err := jwt.ParseWithClaims(tokenString, &UserClaims{}, func(token *jwt.Token) (interface{}, error) {
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}
	if claims, ok := token.Claims.(*UserClaims); ok && token.Valid {
		return claims, nil
	}
	return nil, err
}
