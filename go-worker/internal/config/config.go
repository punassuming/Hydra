package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds all worker configuration read from environment variables.
type Config struct {
	WorkerID             string
	Domain               string
	DomainToken          string
	Tags                 []string
	AllowedUsers         []string
	MaxConcurrency       int
	InitialState         string
	RedisURL             string
	RedisPassword        string
	DeploymentType       string
	MetricsSampleSeconds float64
	MetricsWindowSeconds int
}

// Load reads environment variables and returns a populated Config.
// It returns an error if any required variable is missing.
func Load() (*Config, error) {
	domainToken := strings.TrimSpace(os.Getenv("API_TOKEN"))
	if domainToken == "" {
		return nil, fmt.Errorf("API_TOKEN is required for domain-scoped worker registration")
	}

	return &Config{
		WorkerID:             workerID(),
		Domain:               domain(),
		DomainToken:          domainToken,
		Tags:                 splitCSV(os.Getenv("WORKER_TAGS")),
		AllowedUsers:         splitCSV(os.Getenv("ALLOWED_USERS")),
		MaxConcurrency:       maxConcurrency(),
		InitialState:         initialState(),
		RedisURL:             redisURL(),
		RedisPassword:        strings.TrimSpace(os.Getenv("REDIS_PASSWORD")),
		DeploymentType:       deploymentType(),
		MetricsSampleSeconds: metricsSampleSeconds(),
		MetricsWindowSeconds: metricsWindowSeconds(),
	}, nil
}

func workerID() string {
	if id := strings.TrimSpace(os.Getenv("WORKER_ID")); id != "" {
		return id
	}
	hostname, _ := os.Hostname()
	return fmt.Sprintf("worker-%s-%d", hostname, os.Getpid())
}

func domain() string {
	if d := strings.TrimSpace(os.Getenv("DOMAIN")); d != "" {
		return d
	}
	return "prod"
}

func maxConcurrency() int {
	v, err := strconv.Atoi(os.Getenv("MAX_CONCURRENCY"))
	if err != nil || v < 1 {
		return 2
	}
	return v
}

func initialState() string {
	state := strings.ToLower(strings.TrimSpace(os.Getenv("WORKER_STATE")))
	switch state {
	case "online", "draining", "offline":
		return state
	case "disabled":
		// Legacy alias — map to "offline" to match the scheduler API.
		return "offline"
	default:
		return "online"
	}
}

func redisURL() string {
	if u := strings.TrimSpace(os.Getenv("REDIS_URL")); u != "" {
		return u
	}
	return "redis://localhost:6379/0"
}

func deploymentType() string {
	if dt := strings.TrimSpace(os.Getenv("DEPLOYMENT_TYPE")); dt != "" {
		return dt
	}
	return "docker"
}

func metricsSampleSeconds() float64 {
	v, err := strconv.ParseFloat(os.Getenv("WORKER_METRICS_SAMPLE_SECONDS"), 64)
	if err != nil || v < 2.0 {
		return 15.0
	}
	return v
}

func metricsWindowSeconds() int {
	v, err := strconv.Atoi(os.Getenv("WORKER_METRICS_WINDOW_SECONDS"))
	if err != nil || v < 60 {
		return 1800
	}
	return v
}

func splitCSV(s string) []string {
	var out []string
	for _, part := range strings.Split(s, ",") {
		if t := strings.TrimSpace(part); t != "" {
			out = append(out, t)
		}
	}
	return out
}
