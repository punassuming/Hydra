package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/joho/godotenv"

	"github.com/punassuming/hydra/go-worker/internal/config"
	"github.com/punassuming/hydra/go-worker/internal/redisclient"
	"github.com/punassuming/hydra/go-worker/internal/worker"
)

func main() {
	// Load .env if present (ignored when the file is absent).
	_ = godotenv.Load()

	log.Println("Hydra Go Worker starting…")

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("configuration error: %v", err)
	}

	rdb, err := redisclient.New(cfg.RedisURL, cfg.RedisPassword, cfg.Domain)
	if err != nil {
		log.Fatalf("redis connection error: %v", err)
	}
	defer rdb.Close()

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	if err := worker.Start(ctx, cfg, rdb); err != nil {
		log.Fatalf("worker error: %v", err)
	}
}
