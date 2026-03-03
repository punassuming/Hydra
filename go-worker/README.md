# Hydra Go Worker

A Go implementation of the Hydra worker, designed to achieve feature parity with
the existing Python worker (`worker/`).

## Status

**Scaffold only.** The project structure is in place and the module builds, but
job execution is not yet implemented. See `internal/executor/executor.go` for the
placeholder that will grow into a full execution engine.

## Prerequisites

- Go 1.24 or later
- A running Redis instance (default: `redis://localhost:6379/0`)
- A valid Hydra scheduler with a provisioned domain token

## Configuration

The worker is configured entirely through environment variables (same as the
Python worker). You can also place a `.env` file in the working directory and it
will be loaded automatically at startup.

| Variable         | Default                        | Description                            |
|------------------|--------------------------------|----------------------------------------|
| `API_TOKEN`      | *(required)*                   | Domain token issued by the scheduler   |
| `DOMAIN`         | `prod`                         | Domain this worker belongs to          |
| `WORKER_ID`      | `worker-<hostname>-<pid>`      | Unique worker identifier               |
| `WORKER_TAGS`    | *(none)*                       | Comma-separated affinity tags          |
| `ALLOWED_USERS`  | *(none)*                       | Comma-separated allowed users          |
| `MAX_CONCURRENCY`| `2`                            | Maximum concurrent jobs                |
| `WORKER_STATE`   | `online`                       | Initial state (`online`/`draining`/`offline`) |
| `REDIS_URL`      | `redis://localhost:6379/0`     | Redis connection URL                   |
| `REDIS_PASSWORD` | *(none)*                       | Redis ACL password (domain-scoped)     |

## Building

```bash
# Native binary for the current platform
go build -o hydra-go-worker ./...

# Cross-compile for Linux (e.g. for Docker images)
GOOS=linux GOARCH=amd64 go build -o hydra-go-worker-linux ./...

# Cross-compile for Windows
GOOS=windows GOARCH=amd64 go build -o hydra-go-worker.exe ./...

# Cross-compile for macOS (Apple Silicon)
GOOS=darwin GOARCH=arm64 go build -o hydra-go-worker-darwin ./...
```

## Running

```bash
API_TOKEN=<domain_token> DOMAIN=prod \
  REDIS_URL=redis://localhost:6379/0 \
  ./hydra-go-worker
```

## Project Structure

```
go-worker/
├── main.go                         # Entry point
├── go.mod / go.sum                 # Go module
├── README.md                       # This file
└── internal/
    ├── config/
    │   └── config.go               # Environment-variable configuration
    ├── redisclient/
    │   └── client.go               # Redis connection setup (go-redis)
    ├── executor/
    │   └── executor.go             # Job execution engine (placeholder)
    └── worker/
        └── worker.go               # Worker registration + job polling loop
```
