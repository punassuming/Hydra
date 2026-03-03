package config

import (
	"os"
	"testing"
)

func setEnv(t *testing.T, key, value string) {
	t.Helper()
	t.Setenv(key, value)
}

func TestLoad_RequiresAPIToken(t *testing.T) {
	os.Unsetenv("API_TOKEN")
	_, err := Load()
	if err == nil {
		t.Fatal("expected error when API_TOKEN is missing")
	}
}

func TestLoad_DefaultValues(t *testing.T) {
	setEnv(t, "API_TOKEN", "test-token")
	os.Unsetenv("DOMAIN")
	os.Unsetenv("WORKER_ID")
	os.Unsetenv("MAX_CONCURRENCY")
	os.Unsetenv("WORKER_STATE")
	os.Unsetenv("REDIS_URL")
	os.Unsetenv("DEPLOYMENT_TYPE")
	os.Unsetenv("WORKER_METRICS_SAMPLE_SECONDS")
	os.Unsetenv("WORKER_METRICS_WINDOW_SECONDS")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Domain != "prod" {
		t.Errorf("expected domain 'prod', got %q", cfg.Domain)
	}
	if cfg.MaxConcurrency != 2 {
		t.Errorf("expected max_concurrency 2, got %d", cfg.MaxConcurrency)
	}
	if cfg.InitialState != "online" {
		t.Errorf("expected initial_state 'online', got %q", cfg.InitialState)
	}
	if cfg.RedisURL != "redis://localhost:6379/0" {
		t.Errorf("expected redis url default, got %q", cfg.RedisURL)
	}
	if cfg.DeploymentType != "docker" {
		t.Errorf("expected deployment_type 'docker', got %q", cfg.DeploymentType)
	}
	if cfg.MetricsSampleSeconds != 15.0 {
		t.Errorf("expected metrics_sample_seconds 15.0, got %f", cfg.MetricsSampleSeconds)
	}
	if cfg.MetricsWindowSeconds != 1800 {
		t.Errorf("expected metrics_window_seconds 1800, got %d", cfg.MetricsWindowSeconds)
	}
}

func TestLoad_CustomValues(t *testing.T) {
	setEnv(t, "API_TOKEN", "my-token")
	setEnv(t, "DOMAIN", "staging")
	setEnv(t, "WORKER_ID", "w1")
	setEnv(t, "MAX_CONCURRENCY", "8")
	setEnv(t, "WORKER_STATE", "draining")
	setEnv(t, "WORKER_TAGS", "gpu,fast")
	setEnv(t, "ALLOWED_USERS", "alice,bob")
	setEnv(t, "REDIS_URL", "redis://myhost:6380/1")
	setEnv(t, "REDIS_PASSWORD", "secret")
	setEnv(t, "DEPLOYMENT_TYPE", "kubernetes")
	setEnv(t, "WORKER_METRICS_SAMPLE_SECONDS", "30")
	setEnv(t, "WORKER_METRICS_WINDOW_SECONDS", "3600")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Domain != "staging" {
		t.Errorf("domain: got %q", cfg.Domain)
	}
	if cfg.WorkerID != "w1" {
		t.Errorf("worker_id: got %q", cfg.WorkerID)
	}
	if cfg.MaxConcurrency != 8 {
		t.Errorf("max_concurrency: got %d", cfg.MaxConcurrency)
	}
	if cfg.InitialState != "draining" {
		t.Errorf("initial_state: got %q", cfg.InitialState)
	}
	if len(cfg.Tags) != 2 || cfg.Tags[0] != "gpu" || cfg.Tags[1] != "fast" {
		t.Errorf("tags: got %v", cfg.Tags)
	}
	if len(cfg.AllowedUsers) != 2 {
		t.Errorf("allowed_users: got %v", cfg.AllowedUsers)
	}
	if cfg.RedisPassword != "secret" {
		t.Errorf("redis_password: got %q", cfg.RedisPassword)
	}
	if cfg.DeploymentType != "kubernetes" {
		t.Errorf("deployment_type: got %q", cfg.DeploymentType)
	}
	if cfg.MetricsSampleSeconds != 30.0 {
		t.Errorf("metrics_sample_seconds: got %f", cfg.MetricsSampleSeconds)
	}
	if cfg.MetricsWindowSeconds != 3600 {
		t.Errorf("metrics_window_seconds: got %d", cfg.MetricsWindowSeconds)
	}
}

func TestInitialState_DisabledLegacy(t *testing.T) {
	setEnv(t, "WORKER_STATE", "disabled")
	if got := initialState(); got != "offline" {
		t.Errorf("expected 'offline' for 'disabled', got %q", got)
	}
}

func TestInitialState_UnknownDefaultsOnline(t *testing.T) {
	setEnv(t, "WORKER_STATE", "bogus")
	if got := initialState(); got != "online" {
		t.Errorf("expected 'online' for unknown state, got %q", got)
	}
}

func TestMetricsSampleSeconds_Minimum(t *testing.T) {
	setEnv(t, "WORKER_METRICS_SAMPLE_SECONDS", "0.5")
	if got := metricsSampleSeconds(); got != 15.0 {
		t.Errorf("expected 15.0 for value below minimum, got %f", got)
	}
}

func TestMetricsWindowSeconds_Minimum(t *testing.T) {
	setEnv(t, "WORKER_METRICS_WINDOW_SECONDS", "10")
	if got := metricsWindowSeconds(); got != 1800 {
		t.Errorf("expected 1800 for value below minimum, got %d", got)
	}
}

func TestSplitCSV(t *testing.T) {
	tests := []struct {
		input    string
		expected int
	}{
		{"", 0},
		{"a,b,c", 3},
		{" a , b , c ", 3},
		{",,,", 0},
	}
	for _, tt := range tests {
		got := splitCSV(tt.input)
		if len(got) != tt.expected {
			t.Errorf("splitCSV(%q): got %d items, want %d", tt.input, len(got), tt.expected)
		}
	}
}
