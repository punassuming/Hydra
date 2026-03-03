package redisclient

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// New creates a new Redis client from the provided URL, optional password,
// and optional domain-scoped ACL username.
// When domain is non-empty it is used as the Redis ACL username (matching
// the Python worker's behavior where the domain name itself is the username).
func New(redisURL, password, domain string) (*redis.Client, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("invalid REDIS_URL %q: %w", redisURL, err)
	}
	if domain != "" {
		opts.Username = domain
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
