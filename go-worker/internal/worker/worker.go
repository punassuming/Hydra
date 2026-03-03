// Package worker implements the main worker loop that registers with Redis
// and listens for jobs dispatched by the scheduler.
package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/punassuming/hydra/go-worker/internal/config"
	"github.com/punassuming/hydra/go-worker/internal/executor"
)

// Start registers the worker in Redis and begins the job polling loop.
// It blocks until ctx is cancelled.
func Start(ctx context.Context, cfg *config.Config, rdb *redis.Client) error {
	if err := register(ctx, cfg, rdb); err != nil {
		return fmt.Errorf("worker registration failed: %w", err)
	}

	log.Printf("[worker] %s registered on domain %q (state=%s, concurrency=%d)",
		cfg.WorkerID, cfg.Domain, cfg.InitialState, cfg.MaxConcurrency)

	queueKey := fmt.Sprintf("job_queue:%s:%s", cfg.Domain, cfg.WorkerID)
	return pollLoop(ctx, cfg, rdb, queueKey)
}

// register writes the worker metadata hash into Redis.
func register(ctx context.Context, cfg *config.Config, rdb *redis.Client) error {
	key := fmt.Sprintf("workers:%s:%s", cfg.Domain, cfg.WorkerID)
	fields := map[string]interface{}{
		"worker_id":       cfg.WorkerID,
		"domain":          cfg.Domain,
		"state":           cfg.InitialState,
		"max_concurrency": cfg.MaxConcurrency,
		"registered_at":   time.Now().UTC().Format(time.RFC3339),
	}
	if err := rdb.HSet(ctx, key, fields).Err(); err != nil {
		return err
	}
	// Expire the key after 24 h; the heartbeat loop (TODO) will refresh it.
	return rdb.Expire(ctx, key, 24*time.Hour).Err()
}

// pollLoop blocks on BLPOP waiting for jobs on the worker-specific queue.
func pollLoop(ctx context.Context, cfg *config.Config, rdb *redis.Client, queueKey string) error {
	log.Printf("[worker] listening on queue %q", queueKey)
	for {
		select {
		case <-ctx.Done():
			log.Printf("[worker] shutting down")
			return nil
		default:
		}

		result, err := rdb.BLPop(ctx, 2*time.Second, queueKey).Result()
		if err == redis.Nil {
			// Timeout — no job available; loop again.
			continue
		}
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			log.Printf("[worker] BLPOP error: %v", err)
			time.Sleep(time.Second)
			continue
		}

		// result[0] is the key name, result[1] is the payload.
		if len(result) < 2 {
			continue
		}
		go handleJob(ctx, cfg, result[1])
	}
}

// handleJob decodes and dispatches a single job payload.
func handleJob(ctx context.Context, cfg *config.Config, payload string) {
	var env executor.JobEnvelope
	if err := json.Unmarshal([]byte(payload), &env); err != nil {
		log.Printf("[worker] failed to decode job payload: %v", err)
		return
	}
	log.Printf("[worker] received job %s (run %s)", env.JobID, env.RunID)
	result := executor.Execute(ctx, &env,
		func(line string) { log.Printf("[job:%s:stdout] %s", env.RunID, line) },
		func(line string) { log.Printf("[job:%s:stderr] %s", env.RunID, line) },
	)
	if result.ReturnCode != 0 {
		log.Printf("[worker] job %s finished with exit code %d", env.JobID, result.ReturnCode)
	} else {
		log.Printf("[worker] job %s completed successfully", env.JobID)
	}
}
