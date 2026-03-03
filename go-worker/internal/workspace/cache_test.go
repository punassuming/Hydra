package workspace

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestCacheGetOrCreate_Basic(t *testing.T) {
	tmpDir := t.TempDir()
	cache := &Cache{
		Root:    tmpDir,
		MaxMB:   100,
		TTL:     time.Hour,
		Persist: true,
	}

	fetchCount := 0
	src := &SourceConfig{
		URL:      "https://example.com/repo.git",
		Ref:      "main",
		Protocol: "git",
		Cache:    "auto",
	}

	path1, release1, err := cache.GetOrCreate("prod", "job1", src, func(dest string) error {
		fetchCount++
		os.WriteFile(filepath.Join(dest, "file.txt"), []byte("hello"), 0644)
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if _, err := os.Stat(filepath.Join(path1, "file.txt")); err != nil {
		t.Error("expected file.txt in cache path")
	}
	if fetchCount != 1 {
		t.Errorf("expected 1 fetch, got %d", fetchCount)
	}
	release1()

	// Second call should reuse cache
	path2, release2, err := cache.GetOrCreate("prod", "job1", src, func(dest string) error {
		fetchCount++
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if path1 != path2 {
		t.Error("expected same path for cached entry")
	}
	if fetchCount != 1 {
		t.Errorf("expected 1 fetch (no re-fetch), got %d", fetchCount)
	}
	release2()
}

func TestCacheGetOrCreate_NeverMode(t *testing.T) {
	tmpDir := t.TempDir()
	cache := &Cache{
		Root:    tmpDir,
		MaxMB:   100,
		TTL:     time.Hour,
		Persist: true,
	}

	src := &SourceConfig{
		URL:      "https://example.com/repo.git",
		Ref:      "main",
		Protocol: "git",
		Cache:    "never",
	}

	path1, release1, err := cache.GetOrCreate("prod", "job1", src, func(dest string) error {
		os.WriteFile(filepath.Join(dest, "file.txt"), []byte("hello"), 0644)
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	path2, release2, err := cache.GetOrCreate("prod", "job1", src, func(dest string) error {
		os.WriteFile(filepath.Join(dest, "file.txt"), []byte("hello"), 0644)
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if path1 == path2 {
		t.Error("never mode should create different paths")
	}

	release1()
	release2()

	// After release, temp dirs should be cleaned
	if _, err := os.Stat(path1); err == nil {
		t.Error("expected path1 to be cleaned up")
	}
	if _, err := os.Stat(path2); err == nil {
		t.Error("expected path2 to be cleaned up")
	}
}

func TestCacheGetOrCreate_AlwaysModeMiss(t *testing.T) {
	tmpDir := t.TempDir()
	cache := &Cache{
		Root:    tmpDir,
		MaxMB:   100,
		TTL:     time.Hour,
		Persist: true,
	}

	src := &SourceConfig{
		URL:      "https://example.com/repo.git",
		Ref:      "main",
		Protocol: "git",
		Cache:    "always",
	}

	_, _, err := cache.GetOrCreate("prod", "job1", src, func(dest string) error {
		return nil
	})
	if err == nil {
		t.Error("expected error for always mode with cache miss")
	}
}

func TestCacheKey_Deterministic(t *testing.T) {
	src := &SourceConfig{
		URL:      "https://example.com/repo.git",
		Ref:      "main",
		Path:     "subdir",
		Protocol: "git",
	}
	key1 := cacheKey(src)
	key2 := cacheKey(src)
	if key1 != key2 {
		t.Errorf("expected deterministic cache key, got %q and %q", key1, key2)
	}

	src2 := &SourceConfig{
		URL:      "https://example.com/other.git",
		Ref:      "main",
		Path:     "subdir",
		Protocol: "git",
	}
	key3 := cacheKey(src2)
	if key1 == key3 {
		t.Error("expected different cache keys for different URLs")
	}
}

func TestDirSizeMB(t *testing.T) {
	tmpDir := t.TempDir()
	// Create a 1KB file
	data := make([]byte, 1024)
	os.WriteFile(filepath.Join(tmpDir, "test.bin"), data, 0644)
	size := dirSizeMB(tmpDir)
	if size < 0.0009 || size > 0.002 {
		t.Errorf("expected ~0.001 MB, got %f", size)
	}
}

func TestCleanupAll_Persist(t *testing.T) {
	tmpDir := t.TempDir()
	cache := &Cache{
		Root:    tmpDir,
		MaxMB:   100,
		TTL:     time.Hour,
		Persist: true,
	}
	cache.CleanupAll()
	// Root should still exist
	if _, err := os.Stat(tmpDir); err != nil {
		t.Error("expected root to persist")
	}
}

func TestCleanupAll_NoPersist(t *testing.T) {
	tmpDir := t.TempDir()
	subDir := filepath.Join(tmpDir, "cache")
	os.MkdirAll(subDir, 0755)
	cache := &Cache{
		Root:    subDir,
		MaxMB:   100,
		TTL:     time.Hour,
		Persist: false,
	}
	cache.CleanupAll()
	// Root should be removed
	if _, err := os.Stat(subDir); err == nil {
		t.Error("expected root to be removed when persist=false")
	}
}
