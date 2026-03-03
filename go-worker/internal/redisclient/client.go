package redisclient

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// New creates a new Redis client from the provided URL and optional password.
// It parses the URL and overrides the password when one is supplied.
func New(redisURL, password string) (*redis.Client, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("invalid REDIS_URL %q: %w", redisURL, err)
	}
	if password != "" {
		opts.Password = password
	}

	client := redis.NewClient(opts)
	if err := client.Ping(context.Background()).Err(); err != nil {
		return nil, fmt.Errorf("redis ping failed: %w", err)
	}
	return client, nil
}
