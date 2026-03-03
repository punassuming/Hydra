# Design: Executor Improvements — SQL, User Control, Workspace Caching & New Capabilities

**Status:** Draft — Review before implementation  
**Scope:** Python worker (`worker/`), Go worker (`go-worker/`), Scheduler models (`scheduler/models/`), Scheduler dispatch (`scheduler/scheduler.py`)

---

## Table of Contents

1. [SQL Execution Management](#1-sql-execution-management)
2. [Cross-Platform User Impersonation / Execution Control](#2-cross-platform-user-impersonation--execution-control)
3. [Workspace Caching](#3-workspace-caching)
4. [New Executor Capabilities](#4-new-executor-capabilities)
5. [Migration & Compatibility](#5-migration--compatibility)
6. [Implementation Order](#6-implementation-order)

---

## 1. SQL Execution Management

### Current State

| Area | Python Worker | Go Worker |
|---|---|---|
| SQL executor support | ✅ Yes — generates temp Python script using `pymongo` / `sqlalchemy` | ❌ Not implemented |
| Credential resolution | ✅ Scheduler resolves `credential_ref` → `connection_uri` at dispatch | Same (scheduler-side) |
| Dialect support | postgres, mysql, mssql, oracle, mongodb | N/A |
| Capability advertisement | Always advertises `sql` | Does not advertise `sql` |
| Output format | JSON (rows for relational, command result for mongo) | N/A |
| Security | `connection_uri` masked in API responses via `_sanitize_job_response()` | N/A |

### Problems

1. **Go worker has no SQL executor** — SQL jobs dispatched to a Go worker fail silently.
2. **Python worker's SQL is fragile** — It generates a temp Python script and execs it. Driver availability is checked at runtime, not at registration. A worker advertising `sql` may fail at execution if `sqlalchemy` or `pymongo` isn't installed.
3. **No result pagination or size limits** — `SELECT *` on a large table dumps all rows to stdout as JSON.
4. **Connection pooling** — Each execution creates a new connection. For repeated SQL jobs on the same worker there's no reuse.
5. **No transaction control** — Cannot run multi-statement transactions or control commit/rollback behavior.

### Proposed Design

#### 1a. Go Worker: Native SQL Executor

Add `execSQL()` to `go-worker/internal/executor/executor.go` using Go's `database/sql` + dialect drivers:

| Dialect | Go Driver Package |
|---|---|
| postgres | `github.com/lib/pq` |
| mysql | `github.com/go-sql-driver/mysql` |
| mssql | `github.com/denisenkom/go-mssqldb` |
| oracle | `github.com/sijms/go-ora/v2` |
| mongodb | `go.mongodb.org/mongo-driver/mongo` |

**Implementation sketch:**

```go
func execSQL(ctx context.Context, spec *ExecutorSpec, env map[string]string,
    onStdout, onStderr func(string)) *ExecResult {

    connURI := spec.ConnectionURI
    if connURI == "" {
        return &ExecResult{1, "", "sql executor requires connection_uri"}
    }

    dialect := spec.Dialect
    if dialect == "mongodb" {
        return execMongoDB(ctx, connURI, spec.Query, spec.Database, onStdout, onStderr)
    }
    return execRelationalSQL(ctx, dialect, connURI, spec.Query, onStdout, onStderr)
}
```

**New fields on `ExecutorSpec` (Go):**
```go
type ExecutorSpec struct {
    // ... existing fields ...
    Dialect       string `json:"dialect,omitempty"`
    ConnectionURI string `json:"connection_uri,omitempty"`
    Query         string `json:"query,omitempty"`
    Database      string `json:"database,omitempty"`
}
```

**Capability detection:** Only advertise `sql` if the Go binary was compiled with driver support (always true since drivers are compiled in, unlike Python's runtime check).

#### 1b. Python Worker: Improve SQL Robustness

- **Check driver availability at registration** (`_detect_capabilities`): Probe for `sqlalchemy` and `pymongo` imports. Only advertise `sql` if at least one is present.
- **Add row-count limit**: Default 10,000 rows; configurable via `executor.max_rows` field.
- **Add `autocommit` control**: New optional field `executor.autocommit` (default `true` for backwards compatibility). When `false`, wrap in explicit transaction with commit.
- **Structured output**: Output JSON with `{"rows": [...], "row_count": N, "truncated": bool}` envelope.

#### 1c. Scheduler Model Updates

```python
class SqlExecutor(ExecutorBase):
    type: Literal["sql"] = "sql"
    dialect: Literal["postgres", "mysql", "mssql", "oracle", "mongodb"] = "postgres"
    connection_uri: Optional[str] = None
    credential_ref: Optional[str] = None
    query: str
    database: Optional[str] = None
    max_rows: int = Field(default=10000, ge=1, le=100000)
    autocommit: bool = True
```

#### 1d. Connection Pooling (Future Phase)

Connection pooling is a natural fit for workspace caching (Section 3). When a workspace is cached for a job, a connection pool can be maintained alongside it and reused across successive runs. This is deferred to a second phase.

---

## 2. Cross-Platform User Impersonation / Execution Control

### Current State

| Area | Python Worker | Go Worker |
|---|---|---|
| Impersonation | `sudo -n -u <user>` (Linux only) | ❌ Not implemented |
| Kerberos | `kinit -kt` before execution (Linux only) | ❌ Not implemented |
| Platform check | Fails with error on non-Linux | N/A |
| Scope | Applies to entire command via prefix | N/A |

### Problems

1. **Go worker has no user impersonation** — `executor.impersonate_user` is ignored.
2. **Windows impersonation not supported** — `sudo` doesn't exist on Windows. Windows uses `runas` or process token manipulation.
3. **macOS impersonation not supported** — macOS has `sudo` but different behavior than Linux.
4. **No validation at dispatch** — Scheduler dispatches jobs with `impersonate_user` to workers that can't handle it.
5. **Kerberos only on Python worker** — Go worker has no Kerberos bootstrap.

### Proposed Design

#### 2a. Unified Impersonation Abstraction

Define a platform-aware impersonation strategy in both workers:

| Platform | Method | Mechanism |
|---|---|---|
| Linux | `sudo -n -u <user> --` | Prefix command (current behavior) |
| macOS | `sudo -n -u <user> --` | Same as Linux (compatible) |
| Windows | `runas /user:<user>` or `Start-Process -Credential` | Native Windows; requires password or saved credential |

**For the Go worker**, implement `withImpersonation()`:

```go
func withImpersonation(cmd []string, user string) ([]string, error) {
    if user == "" {
        return cmd, nil
    }
    switch runtime.GOOS {
    case "linux", "darwin":
        return append([]string{"sudo", "-n", "-u", user, "--"}, cmd...), nil
    case "windows":
        // Windows: use runas (interactive) — limited; prefer
        // running the worker service as the target user instead
        return nil, fmt.Errorf("impersonation via runas not supported in non-interactive mode; " +
            "configure the worker service to run as the target user")
    default:
        return nil, fmt.Errorf("impersonation not supported on %s", runtime.GOOS)
    }
}
```

**For the Python worker**, extend `_with_impersonation()` to support macOS:

```python
def _with_impersonation(cmd: list[str]) -> list[str]:
    if not impersonate_user:
        return cmd
    if platform.system().lower() in ("linux", "darwin"):
        return ["sudo", "-n", "-u", impersonate_user, "--"] + cmd
    raise RuntimeError(
        f"impersonation not supported on {platform.system()}; "
        "configure the worker service to run as the target user"
    )
```

#### 2b. Kerberos Support in Go Worker

Add `kerberosInit()` to the Go executor:

```go
func kerberosInit(ctx context.Context, kerberos map[string]string, user string, env map[string]string) error {
    principal := kerberos["principal"]
    keytab := kerberos["keytab"]
    if principal == "" || keytab == "" {
        return nil
    }
    cmd := []string{"kinit", "-kt", keytab, principal}
    if user != "" {
        cmd, _ = withImpersonation(cmd, user)
    }
    // Set KRB5CCNAME if ccache specified
    if cc := kerberos["ccache"]; cc != "" {
        env["KRB5CCNAME"] = cc
    }
    result := runCommand(ctx, cmd, env, "", nil, nil)
    if result.ReturnCode != 0 {
        return fmt.Errorf("kerberos init failed: %s", result.Stderr)
    }
    return nil
}
```

#### 2c. Go Worker Model Updates

Add impersonation and kerberos fields to `ExecutorSpec`:

```go
type ExecutorSpec struct {
    // ... existing fields ...
    ImpersonateUser string            `json:"impersonate_user,omitempty"`
    Kerberos        map[string]string `json:"kerberos,omitempty"`
}
```

#### 2d. Affinity-Based Dispatch Validation

Add a new affinity check in the scheduler: if a job specifies `executor.impersonate_user`, only dispatch to workers whose OS supports it (Linux/macOS). Workers already report `os` in their heartbeat metadata.

```python
# In scheduler/utils/affinity.py
def passes_affinity(job, worker):
    # ... existing checks ...
    executor = job.get("executor", {})
    if executor.get("impersonate_user"):
        worker_os = worker.get("os", "").lower()
        if worker_os not in ("linux", "darwin"):
            return False
    return True
```

#### 2e. Windows Strategy: Service Account Model

For Windows, instead of per-command impersonation, the recommended approach is:

1. **Run the worker service as the target user** — Configure the Windows service or Docker container to run under the appropriate service account.
2. **Multiple workers per user** — Deploy one worker per service account, using `allowed_users` affinity to route jobs.
3. **Future**: Investigate `CreateProcessAsUser` Win32 API for true per-command impersonation (complex, requires `SeAssignPrimaryTokenPrivilege`).

Document this pattern in the deployment guide.

---

## 3. Workspace Caching

### Current State

Both workers create a fresh `tempfile.mkdtemp()` / `os.MkdirTemp()` for every job run that uses a `source` config, then clean it up after execution. This means:

- Git clone happens every time (network I/O, time).
- Python venvs are rebuilt every time (`prepare_python_command` creates temp venvs).
- No reuse of downloaded dependencies or cloned repos.

### Proposed Design

#### 3a. Source Workspace Cache

Introduce a per-worker **workspace cache directory** that persists across runs. Key concept:

```
<cache_root>/<domain>/<job_id>/<content_hash>/
```

Where `content_hash` = hash of `(source.url, source.ref, source.path, source.protocol)`.

**Cache lifecycle:**
1. **First run**: Clone/copy source to cache dir. Execute from cache dir.
2. **Subsequent runs (same source config)**: Reuse cached dir. For git sources, do `git fetch && git checkout` (fast) instead of full clone.
3. **Source config changes**: New `content_hash` → new cache entry. Old entry eligible for eviction.
4. **Eviction**: LRU-based. Configurable max cache size via `WORKER_WORKSPACE_CACHE_MAX_MB` (default: 1024 MB). Evict oldest unused entries when limit exceeded.
5. **Worker shutdown**: Optionally clean all caches (configurable via `WORKER_WORKSPACE_CACHE_PERSIST`, default `true`).

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `WORKER_WORKSPACE_CACHE_DIR` | OS temp dir + `/hydra-workspace-cache` (Python: `tempfile.gettempdir()`, Go: `os.TempDir()`) | Root directory for cached workspaces |
| `WORKER_WORKSPACE_CACHE_MAX_MB` | `1024` | Maximum total cache size in MB. Size limit takes precedence over TTL — entries within TTL are still evicted (oldest first) if total size exceeds this limit. |
| `WORKER_WORKSPACE_CACHE_PERSIST` | `true` | Keep cache across worker restarts |
| `WORKER_WORKSPACE_CACHE_TTL` | `3600` | Seconds of inactivity before a cache entry is eligible for eviction. Entries within TTL may still be evicted if the size limit is exceeded. |

**Locking:** Use file-based locks (`.lock` files) to prevent concurrent runs from the same job from colliding on the same cache entry. Each execution acquires a shared read lock; cache updates (git pull, eviction) acquire exclusive write locks.

#### 3b. Python Environment Cache

For Python executor jobs, cache the prepared virtual environment:

```
<cache_root>/<domain>/<job_id>/venv/<requirements_hash>/
```

Where `requirements_hash` = hash of `(environment.requirements, environment.requirements_file_content, environment.python_version)`.

- First run: Create venv, install packages, execute.
- Subsequent runs: Reuse venv, skip install (or run `pip install --dry-run` check).
- Requirements change: New hash → new venv. Old venv evicted per LRU.

#### 3c. Implementation Outline (Python Worker)

```python
# worker/utils/workspace_cache.py

class WorkspaceCache:
    def __init__(self, cache_root, max_mb, ttl_seconds):
        self.cache_root = cache_root
        self.max_mb = max_mb
        self.ttl = ttl_seconds
    
    def get_or_create(self, domain, job_id, source_config) -> (str, Callable):
        """Returns (workspace_path, release_lock_fn)."""
        cache_key = self._cache_key(source_config)  # hash of (url, ref, path, protocol)
        cache_path = os.path.join(self.cache_root, domain, job_id, cache_key)
        protocol = source_config.get("protocol") or "git"  # default to git per SourceConfig
        
        if os.path.exists(cache_path):
            self._touch(cache_path)  # Update last-used timestamp
            if protocol == "git":
                self._git_update(cache_path, source_config)
            lock = self._acquire_lock(cache_path)
            return cache_path, lambda: self._release_lock(lock)
        
        # Create new cache entry
        os.makedirs(cache_path, exist_ok=True)
        self._fetch_source(cache_path, source_config)
        self._evict_if_needed()
        lock = self._acquire_lock(cache_path)
        return cache_path, lambda: self._release_lock(lock)
```

#### 3d. Implementation Outline (Go Worker)

```go
// go-worker/internal/workspace/cache.go

type WorkspaceCache struct {
    Root   string
    MaxMB  int
    TTL    time.Duration
    mu     sync.Mutex
}

func (c *WorkspaceCache) GetOrCreate(domain, jobID string, src *executor.Source) (string, func(), error) {
    key := cacheKey(src)
    path := filepath.Join(c.Root, domain, jobID, key)
    
    if info, err := os.Stat(path); err == nil && info.IsDir() {
        c.touch(path)
        protocol := src.Protocol
        if protocol == "" {
            protocol = "git"  // default to git per SourceConfig
        }
        if protocol == "git" {
            c.gitUpdate(path, src)
        }
        release := c.acquireLock(path)
        return path, release, nil
    }
    
    os.MkdirAll(path, 0755)
    if err := c.fetchSource(path, src); err != nil {
        return "", nil, err
    }
    c.evictIfNeeded()
    release := c.acquireLock(path)
    return path, release, nil
}
```

#### 3e. Cache Invalidation

Jobs can force a fresh workspace by setting a new field:

```python
class SourceConfig(BaseModel):
    # ... existing fields ...
    cache: Literal["auto", "always", "never"] = "auto"
```

- `auto` (default): Use cache if available, create if not.
- `always`: Always use cache; error if cache miss. Useful when cache is expected to be pre-populated (e.g., CI pipelines that seed workspaces before job execution, or debugging cache behavior).
- `never`: Always create fresh workspace (current behavior).

---

## 4. New Executor Capabilities

With both Python and Go workers, we can leverage each language's strengths:

### 4a. HTTP/API Executor (Go Worker Advantage)

A new executor type for making HTTP requests — useful for triggering external APIs, webhooks, or health checks:

```python
class HttpExecutor(ExecutorBase):
    type: Literal["http"] = "http"
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = None
    expected_status: List[int] = Field(default=[200])
    timeout_seconds: int = 30
    credential_ref: Optional[str] = None  # For Bearer/API key auth
```

Go is natural for this (built-in `net/http`, no external dependencies). Python implementation would use `requests` or `urllib`.

**Use cases:** REST API triggers, webhook calls, health checks, API testing jobs.

### 4b. File Transfer Executor

A new executor for managed file transfers between systems:

```python
class FileTransferExecutor(ExecutorBase):
    type: Literal["file_transfer"] = "file_transfer"
    protocol: Literal["scp", "sftp", "s3", "gcs", "azure_blob"] = "scp"
    source_path: str
    destination_path: str
    credential_ref: Optional[str] = None
    recursive: bool = False
```

### 4c. Container Executor (Both Workers)

Execute jobs inside a specified container image:

```python
class ContainerExecutor(ExecutorBase):
    type: Literal["container"] = "container"
    image: str
    command: str
    runtime: Literal["docker", "podman"] = "docker"
    volumes: List[str] = Field(default_factory=list)
    network: Optional[str] = None
```

Both workers shell out to `docker run` / `podman run`. The Go worker could also use the Docker SDK directly for tighter integration.

### 4d. Composite / Pipeline Executor

Run a sequence of steps within a single job:

```python
class PipelineExecutor(ExecutorBase):
    type: Literal["pipeline"] = "pipeline"
    steps: List[ExecutorConfig]  # Ordered list of executors to run sequentially
    fail_fast: bool = True       # Stop on first failure
```

Each step inherits the workspace/env of the previous step. This enables multi-stage jobs (clone → build → test → deploy) without separate job definitions.

### 4e. Capability Comparison Matrix

| Capability | Python Worker | Go Worker | Notes |
|---|---|---|---|
| Shell | ✅ | ✅ | Parity |
| External | ✅ | ✅ | Parity |
| Python | ✅ (native venv/uv) | ✅ (shells out) | Python worker has richer env support |
| PowerShell | ✅ | ✅ | Parity |
| Batch | ✅ (Windows) | ✅ (Windows) | Parity |
| SQL | ✅ (pymongo/sqlalchemy) | 🔲 **To add** | Go native drivers |
| HTTP | 🔲 **To add** | 🔲 **To add** | Go has advantage (stdlib) |
| File Transfer | 🔲 Future | 🔲 Future | Both shell out |
| Container | 🔲 Future | 🔲 Future | Both shell out or SDK |
| Pipeline | 🔲 Future | 🔲 Future | Both |
| Impersonation | ✅ Linux | 🔲 **To add** | Extend to macOS |
| Kerberos | ✅ Linux | 🔲 **To add** | |
| Workspace Cache | 🔲 **To add** | 🔲 **To add** | |

---

## 5. Migration & Compatibility

### Backwards Compatibility

All changes are **additive**:

- New `SqlExecutor` fields (`max_rows`, `autocommit`) have defaults matching current behavior.
- New `SourceConfig.cache` field defaults to `auto` (unchanged behavior when not set).
- `ExecutorSpec` changes in Go are additive (new optional JSON fields).
- Impersonation behavior on Linux is unchanged; macOS support is a new code path.
- Workers that don't support workspace caching will continue with temp dirs.

### Schema Versioning

No schema version bump needed — all new fields are optional with defaults.

### Rollout Strategy

1. Deploy scheduler with updated models first (new fields are optional).
2. Deploy workers with new capabilities. Old workers continue to work.
3. Enable new features in job definitions as workers are upgraded.

---

## 6. Implementation Order

### Phase 1: Core Parity (Immediate)

| # | Task | Files Changed | Effort |
|---|---|---|---|
| 1.1 | Go worker: Add SQL executor with Go native drivers | `go-worker/internal/executor/executor.go`, `go.mod` | Medium |
| 1.2 | Go worker: Add impersonation + Kerberos | `go-worker/internal/executor/executor.go` | Small |
| 1.3 | Python worker: Extend impersonation to macOS | `worker/executor.py` | Small |
| 1.4 | Python worker: Improve SQL capability detection | `worker/executor.py` | Small |
| 1.5 | Scheduler: Add `max_rows`, `autocommit` to SqlExecutor model | `scheduler/models/executor.py` | Small |
| 1.6 | Scheduler: Add impersonation affinity check | `scheduler/utils/affinity.py` | Small |
| 1.7 | Tests for all above | `tests/`, `go-worker/*_test.go` | Medium |

### Phase 2: Workspace Caching

| # | Task | Files Changed | Effort |
|---|---|---|---|
| 2.1 | Python worker: Workspace cache module | `worker/utils/workspace_cache.py` (new) | Medium |
| 2.2 | Python worker: Integrate cache into executor | `worker/executor.py` | Medium |
| 2.3 | Go worker: Workspace cache package | `go-worker/internal/workspace/cache.go` (new) | Medium |
| 2.4 | Go worker: Integrate cache into executor | `go-worker/internal/executor/executor.go` | Medium |
| 2.5 | Scheduler: Add `cache` field to SourceConfig | `scheduler/models/job_definition.py` | Small |
| 2.6 | Python venv caching integration | `worker/utils/python_env.py` | Medium |
| 2.7 | Tests for caching | `tests/`, `go-worker/*_test.go` | Medium |

### Phase 3: New Executors

| # | Task | Files Changed | Effort |
|---|---|---|---|
| 3.1 | HTTP executor model + Python implementation | `scheduler/models/executor.py`, `worker/executor.py` | Medium |
| 3.2 | HTTP executor Go implementation | `go-worker/internal/executor/executor.go` | Small |
| 3.3 | Tests for HTTP executor | `tests/`, `go-worker/*_test.go` | Small |
| 3.4 | Container executor (future) | — | Large |
| 3.5 | Pipeline executor (future) | — | Large |

### Phase 4: Documentation & Deployment

| # | Task | Files Changed | Effort |
|---|---|---|---|
| 4.1 | Update architecture docs | `doc/architecture.md`, `AGENTS.md` | Small |
| 4.2 | Windows deployment guide for user control | `doc/` (new) | Small |
| 4.3 | Update README with new features | `README.md` | Small |

---

## Open Questions

1. **SQL driver compilation for Go**: Should we use build tags to optionally include heavy SQL drivers (oracle, mssql), or always compile them all in?
2. **Workspace cache cleanup on job deletion**: Should the scheduler notify workers to clean cached workspaces when a job is deleted?
3. **HTTP executor credential resolution**: Should the scheduler resolve `credential_ref` for HTTP executor? Two options: (a) resolve at dispatch like SQL (simpler for workers but exposes credentials in Redis transit), or (b) resolve worker-side if we add limited Mongo read access for credentials. The current architecture favors scheduler-side resolution since workers are Redis-only. Credentials are already exposed in the job envelope for SQL — same pattern would apply here. Transport security relies on Redis TLS + domain-scoped ACL.
4. **Pipeline executor scope**: Should pipeline steps share the same workspace, or should each step get its own?
5. **Cache coherency for multi-worker**: If a job runs on different workers, each maintains its own cache. Is this acceptable, or do we need shared cache (e.g., NFS mount)?
