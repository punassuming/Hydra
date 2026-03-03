// Package workspace implements workspace caching for the Go worker,
// persisting fetched source directories across job runs to avoid
// repeated git clones and file copies.
package workspace

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	osexec "os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"sync"
	"time"
)

// Cache provides thread-safe workspace caching backed by the local filesystem.
type Cache struct {
	Root    string
	MaxMB   int
	TTL     time.Duration
	Persist bool
	mu      sync.Mutex
}

// New creates a new Cache instance from environment variables.
func New() *Cache {
	root := os.Getenv("WORKER_WORKSPACE_CACHE_DIR")
	if root == "" {
		root = filepath.Join(os.TempDir(), "hydra-workspace-cache")
	}
	maxMB := 1024
	if v, err := strconv.Atoi(os.Getenv("WORKER_WORKSPACE_CACHE_MAX_MB")); err == nil && v > 0 {
		maxMB = v
	}
	ttl := 3600
	if v, err := strconv.Atoi(os.Getenv("WORKER_WORKSPACE_CACHE_TTL")); err == nil && v > 0 {
		ttl = v
	}
	persist := true
	if p := os.Getenv("WORKER_WORKSPACE_CACHE_PERSIST"); p == "false" || p == "0" || p == "no" {
		persist = false
	}
	os.MkdirAll(root, 0755)
	return &Cache{
		Root:    root,
		MaxMB:   maxMB,
		TTL:     time.Duration(ttl) * time.Second,
		Persist: persist,
	}
}

// SourceConfig mirrors the source fields relevant for cache keying.
type SourceConfig struct {
	URL      string `json:"url"`
	Ref      string `json:"ref"`
	Path     string `json:"path"`
	Protocol string `json:"protocol"`
	Cache    string `json:"cache"` // "auto" | "always" | "never"
}

// GetOrCreate returns the workspace path for the given source config.
// fetchFn is called when the cache entry does not exist and needs to be
// populated.  The returned cleanup function should be called after the
// workspace is no longer needed (it is a no-op for cached entries).
func (c *Cache) GetOrCreate(domain, jobID string, src *SourceConfig, fetchFn func(destDir string) error) (string, func(), error) {
	cacheMode := src.Cache
	if cacheMode == "" {
		cacheMode = "auto"
	}

	if cacheMode == "never" {
		tmpDir, err := os.MkdirTemp("", fmt.Sprintf("hydra-source-%s-", jobID))
		if err != nil {
			return "", nil, fmt.Errorf("failed to create temp dir: %w", err)
		}
		if err := fetchFn(tmpDir); err != nil {
			os.RemoveAll(tmpDir)
			return "", nil, err
		}
		return tmpDir, func() { os.RemoveAll(tmpDir) }, nil
	}

	key := cacheKey(src)
	path := filepath.Join(c.Root, domain, jobID, key)

	c.mu.Lock()
	defer c.mu.Unlock()

	if info, err := os.Stat(path); err == nil && info.IsDir() {
		c.touch(path)
		if cacheMode != "always" {
			protocol := src.Protocol
			if protocol == "" {
				protocol = "git"
			}
			if protocol == "git" {
				c.gitUpdate(path, src.Ref)
			}
		}
		c.evictIfNeeded()
		return path, func() {}, nil
	}

	if cacheMode == "always" {
		return "", nil, fmt.Errorf("cache mode is 'always' but no cached workspace exists at %s", path)
	}

	os.MkdirAll(path, 0755)
	if err := fetchFn(path); err != nil {
		os.RemoveAll(path)
		return "", nil, err
	}
	c.touch(path)
	c.evictIfNeeded()
	return path, func() {}, nil
}

// CleanupAll removes the entire cache tree (called on worker shutdown if
// Persist is false).
func (c *Cache) CleanupAll() {
	if !c.Persist {
		os.RemoveAll(c.Root)
	}
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

func cacheKey(src *SourceConfig) string {
	data, _ := json.Marshal(map[string]string{
		"url":      src.URL,
		"ref":      src.Ref,
		"path":     src.Path,
		"protocol": src.Protocol,
	})
	h := sha256.Sum256(data)
	return fmt.Sprintf("%x", h[:8])
}

func (c *Cache) touch(path string) {
	sentinel := filepath.Join(path, ".hydra_cache_ts")
	os.WriteFile(sentinel, []byte(fmt.Sprintf("%f", float64(time.Now().Unix()))), 0644)
}

func lastUsed(path string) float64 {
	sentinel := filepath.Join(path, ".hydra_cache_ts")
	data, err := os.ReadFile(sentinel)
	if err != nil {
		return 0
	}
	v, _ := strconv.ParseFloat(string(data), 64)
	return v
}

func (c *Cache) gitUpdate(cachePath, ref string) {
	// Best-effort fast update.
	run := func(args ...string) {
		cmd := osexec.Command(args[0], args[1:]...)
		cmd.Dir = cachePath
		_ = cmd.Run()
	}
	run("git", "fetch", "-q", "origin")
	if ref != "" {
		run("git", "checkout", ref)
	}
	run("git", "pull", "-q", "--ff-only")
}

func dirSizeMB(path string) float64 {
	var total int64
	filepath.WalkDir(path, func(_ string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		info, err := d.Info()
		if err == nil {
			total += info.Size()
		}
		return nil
	})
	return float64(total) / (1024 * 1024)
}

type cacheEntry struct {
	ts   float64
	path string
}

func (c *Cache) evictIfNeeded() {
	total := dirSizeMB(c.Root)
	if total <= float64(c.MaxMB) {
		return
	}
	var entries []cacheEntry
	filepath.WalkDir(c.Root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || !d.IsDir() {
			return nil
		}
		sentinel := filepath.Join(path, ".hydra_cache_ts")
		if _, serr := os.Stat(sentinel); serr == nil {
			entries = append(entries, cacheEntry{ts: lastUsed(path), path: path})
		}
		return nil
	})
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].ts < entries[j].ts
	})
	for _, e := range entries {
		if dirSizeMB(c.Root) <= float64(c.MaxMB) {
			break
		}
		os.RemoveAll(e.path)
	}
}
