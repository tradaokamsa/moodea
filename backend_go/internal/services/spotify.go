package services

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"moodea/backend_go/internal/models"
)

type SpotifyTokens struct {
	AccessToken  string `json:"access_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	RefreshToken string `json:"refresh_token"`
	Scope        string `json:"scope"`
}

type SpotifyUser struct {
	ID          string `json:"id"`
	DisplayName string `json:"display_name"`
	Email       string `json:"email"`
	Country     string `json:"country"`
}

func GetAuthURL(state string) string {
	scopes := []string{
		"user-top-read",
		"user-read-email",
		"user-read-private",
		"user-library-read",
		"user-library-modify",
		"playlist-read-private",
		"playlist-modify-public",
		"playlist-modify-private",
		"user-modify-playback-state",
		"user-read-recently-played",
	}
	params := url.Values{}
	params.Add("client_id", os.Getenv("SPOTIFY_CLIENT_ID"))
	params.Add("response_type", "code")
	params.Add("redirect_uri", os.Getenv("SPOTIFY_REDIRECT_URI"))
	params.Add("state", state)
	params.Add("scope", strings.Join(scopes, " "))
	params.Add("show_dialog", "true")
	return fmt.Sprintf("https://accounts.spotify.com/authorize?%s", params.Encode())
}

func GetTokens(code string) (*SpotifyTokens, error) {
	data := url.Values{}
	data.Set("grant_type", "authorization_code")
	data.Set("code", code)
	data.Set("redirect_uri", os.Getenv("SPOTIFY_REDIRECT_URI"))

	req, err := http.NewRequest("POST", "https://accounts.spotify.com/api/token", strings.NewReader(data.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.SetBasicAuth(os.Getenv("SPOTIFY_CLIENT_ID"), os.Getenv("SPOTIFY_CLIENT_SECRET"))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var tokens SpotifyTokens
	if err := json.Unmarshal(body, &tokens); err != nil {
		return nil, err
	}
	return &tokens, nil
}

func GetUserProfile(accessToken string) (*SpotifyUser, error) {
	req, err := http.NewRequest("GET", "https://api.spotify.com/v1/me", nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+accessToken)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var user SpotifyUser
	if err := json.Unmarshal(body, &user); err != nil {
		return nil, err
	}
	return &user, nil
}

func RefreshAccessToken(refreshToken string) (*SpotifyTokens, error) {
	data := url.Values{}
	data.Set("grant_type", "refresh_token")
	data.Set("refresh_token", refreshToken)

	req, err := http.NewRequest("POST", "https://accounts.spotify.com/api/token", strings.NewReader(data.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.SetBasicAuth(os.Getenv("SPOTIFY_CLIENT_ID"), os.Getenv("SPOTIFY_CLIENT_SECRET"))

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var tokens SpotifyTokens
	if err := json.Unmarshal(body, &tokens); err != nil {
		return nil, err
	}
	return &tokens, nil
}

// MakeSpotifyRequest makes a Spotify API request, refreshing the token if needed
func MakeSpotifyRequest(endpoint, method string, params map[string]string, user *models.User) ([]byte, error) {
	// Check if token is expired or about to expire (within 5 minutes)
	if time.Until(time.Unix(user.TokenExpiresAt, 0)) < 5*time.Minute {
		tokens, err := RefreshAccessToken(user.RefreshToken)
		if err != nil {
			return nil, err
		}
		user.AccessToken = tokens.AccessToken
		if tokens.RefreshToken != "" {
			user.RefreshToken = tokens.RefreshToken
		}
		user.TokenExpiresAt = time.Now().Add(time.Duration(tokens.ExpiresIn) * time.Second).Unix()
		models.SaveUser(context.Background(), user)
	}

	// Build request
	var req *http.Request
	var err error
	urlStr := "https://api.spotify.com/v1" + endpoint
	if method == "GET" && params != nil && len(params) > 0 {
		q := url.Values{}
		for k, v := range params {
			// Only add non-empty values
			if v != "" {
				q.Set(k, v)
			}
		}
		if len(q) > 0 {
			urlStr += "?" + q.Encode()
		}
		req, err = http.NewRequest(method, urlStr, nil)
	} else {
		var body io.Reader
		if params != nil {
			jsonData, _ := json.Marshal(params)
			body = strings.NewReader(string(jsonData))
		}
		req, err = http.NewRequest(method, urlStr, body)
		req.Header.Set("Content-Type", "application/json")
	}
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+user.AccessToken)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("spotify request failed: %w", err)
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	// Check status code and return error if not successful
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("spotify API returned status %d for %s: %s", resp.StatusCode, urlStr, string(bodyBytes))
	}

	return bodyBytes, nil
}
