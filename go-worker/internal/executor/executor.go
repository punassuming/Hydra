// Package executor implements the job execution engine for the Go worker,
// supporting shell, external, batch, python, and powershell executor types.
package executor

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Data model — matches the JSON envelope dispatched by the scheduler.
// ---------------------------------------------------------------------------

// Schedule holds cron/interval scheduling metadata.
type Schedule struct {
	Mode      string  `json:"mode"`
	NextRunAt *string `json:"next_run_at"`
	Cron      string  `json:"cron,omitempty"`
	Interval  int     `json:"interval,omitempty"`
}

// Completion defines success/failure criteria for a run.
type Completion struct {
	ExitCodes         []int    `json:"exit_codes"`
	StdoutContains    []string `json:"stdout_contains"`
	StdoutNotContains []string `json:"stdout_not_contains"`
	StderrContains    []string `json:"stderr_contains"`
	StderrNotContains []string `json:"stderr_not_contains"`
}

// Source describes a git (or other) source to fetch before execution.
type Source struct {
	URL      string `json:"url,omitempty"`
	Ref      string `json:"ref,omitempty"`
	Path     string `json:"path,omitempty"`
	Token    string `json:"token,omitempty"`
	Protocol string `json:"protocol,omitempty"`
	Sparse   bool   `json:"sparse,omitempty"`
}

// ExecutorSpec holds the executor configuration from the job definition.
type ExecutorSpec struct {
	Type        string            `json:"type"`
	Script      string            `json:"script,omitempty"`
	Shell       string            `json:"shell,omitempty"`
	Env         map[string]string `json:"env,omitempty"`
	Workdir     string            `json:"workdir,omitempty"`
	Args        []string          `json:"args,omitempty"`
	Command     string            `json:"command,omitempty"`
	Code        string            `json:"code,omitempty"`
	Interpreter string            `json:"interpreter,omitempty"`
}

// JobDef is the full job definition nested inside the envelope.
type JobDef struct {
	ID                 string       `json:"_id"`
	User               string       `json:"user,omitempty"`
	Executor           ExecutorSpec `json:"executor"`
	Timeout            int          `json:"timeout,omitempty"`
	Retries            int          `json:"retries,omitempty"`
	BypassConcurrency  bool         `json:"bypass_concurrency,omitempty"`
	Schedule           *Schedule    `json:"schedule,omitempty"`
	Completion         *Completion  `json:"completion,omitempty"`
	Source             *Source      `json:"source,omitempty"`
}

// JobEnvelope is the top-level payload dispatched by the scheduler.
type JobEnvelope struct {
	JobID        string            `json:"job_id"`
	RunID        string            `json:"run_id"`
	DispatchTS   float64           `json:"dispatch_ts"`
	EnqueuedTS   float64           `json:"enqueued_ts"`
	RetryAttempt int               `json:"retry_attempt"`
	Params       map[string]string `json:"params,omitempty"`
	Job          JobDef            `json:"job"`
}

// ExecResult carries the outcome of a job execution.
type ExecResult struct {
	ReturnCode int
	Stdout     string
	Stderr     string
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Execute runs the job described by env. Stdout/stderr lines are streamed to
// the optional callback functions as they are produced.
func Execute(ctx context.Context, env *JobEnvelope, onStdout, onStderr func(string)) *ExecResult {
	spec := &env.Job.Executor
	execType := strings.ToLower(strings.TrimSpace(spec.Type))
	if execType == "" {
		execType = "shell"
	}

	// Build merged environment: OS env + executor env + params.
	mergedEnv := buildEnv(spec.Env, env.Params)
	workdir := spec.Workdir
	args := spec.Args

	// Apply job-level timeout via context.
	if env.Job.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(env.Job.Timeout)*time.Second)
		defer cancel()
	}

	switch execType {
	case "shell":
		return execShell(ctx, spec, args, mergedEnv, workdir, onStdout, onStderr)
	case "external":
		return execExternal(ctx, spec, args, mergedEnv, workdir, onStdout, onStderr)
	case "batch":
		return execBatch(ctx, spec, args, mergedEnv, workdir, onStdout, onStderr)
	case "python":
		return execPython(ctx, spec, args, mergedEnv, workdir, onStdout, onStderr)
	case "powershell":
		return execPowershell(ctx, spec, args, mergedEnv, workdir, onStdout, onStderr)
	default:
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("unsupported executor type: %s", execType)}
	}
}

// ---------------------------------------------------------------------------
// Executor type handlers
// ---------------------------------------------------------------------------

func execShell(ctx context.Context, spec *ExecutorSpec, args []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	script := spec.Script
	if script == "" {
		return &ExecResult{ReturnCode: 1, Stderr: "shell executor requires a non-empty script"}
	}

	shell := spec.Shell
	if shell == "" {
		shell = "bash"
	}

	tmp, err := writeTempFile("hydra-sh-", ".sh", script)
	if err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("failed to write temp script: %v", err)}
	}
	defer os.Remove(tmp)

	var cmd []string
	if shell == "bash" {
		cmd = append([]string{"/bin/bash", "-l", tmp}, args...)
	} else {
		cmd = append([]string{shell, tmp}, args...)
	}
	return runCommand(ctx, cmd, env, workdir, onStdout, onStderr)
}

func execExternal(ctx context.Context, spec *ExecutorSpec, args []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	binary := spec.Command
	if binary == "" {
		return &ExecResult{ReturnCode: 1, Stderr: "external executor requires a non-empty command"}
	}
	cmd := append([]string{binary}, args...)
	return runCommand(ctx, cmd, env, workdir, onStdout, onStderr)
}

func execBatch(ctx context.Context, spec *ExecutorSpec, args []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	script := spec.Script
	if script == "" {
		return &ExecResult{ReturnCode: 1, Stderr: "batch executor requires a non-empty script"}
	}

	shell := spec.Shell
	if shell == "" {
		shell = "cmd"
	}

	suffix := ".sh"
	if shell == "cmd" {
		suffix = ".bat"
	}

	tmp, err := writeTempFile("hydra-batch-", suffix, script)
	if err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("failed to write temp script: %v", err)}
	}
	defer os.Remove(tmp)

	var cmd []string
	if shell == "cmd" {
		cmd = append([]string{"cmd", "/c", tmp}, args...)
	} else {
		cmd = append([]string{shell, tmp}, args...)
	}
	return runCommand(ctx, cmd, env, workdir, onStdout, onStderr)
}

func execPython(ctx context.Context, spec *ExecutorSpec, args []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	code := spec.Code
	if code == "" {
		return &ExecResult{ReturnCode: 1, Stderr: "python executor requires non-empty code"}
	}

	interpreter := spec.Interpreter
	if interpreter == "" {
		interpreter = findPython()
		if interpreter == "" {
			return &ExecResult{ReturnCode: 1, Stderr: "no python interpreter found (tried python3, python)"}
		}
	}

	tmp, err := writeTempFile("hydra-py-", ".py", code)
	if err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("failed to write temp script: %v", err)}
	}
	defer os.Remove(tmp)

	cmd := append([]string{interpreter, tmp}, args...)
	return runCommand(ctx, cmd, env, workdir, onStdout, onStderr)
}

func execPowershell(ctx context.Context, spec *ExecutorSpec, args []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	script := spec.Script
	if script == "" {
		return &ExecResult{ReturnCode: 1, Stderr: "powershell executor requires a non-empty script"}
	}

	shell := spec.Shell
	if shell == "" {
		shell = "pwsh"
	}

	cmd := append([]string{shell, "-NoProfile", "-Command", script}, args...)
	return runCommand(ctx, cmd, env, workdir, onStdout, onStderr)
}

// ---------------------------------------------------------------------------
// Core subprocess runner
// ---------------------------------------------------------------------------

// Conventional exit codes for signals.
const (
	exitCodeTimeout  = 137 // SIGKILL
	exitCodeCanceled = 130 // SIGINT
)

// runCommand executes a command with context-based timeout, streaming
// stdout/stderr lines via callbacks, and returns the aggregated result.
func runCommand(ctx context.Context, cmdArgs []string, env map[string]string, workdir string, onStdout, onStderr func(string)) *ExecResult {
	if len(cmdArgs) == 0 {
		return &ExecResult{ReturnCode: 1, Stderr: "empty command"}
	}

	c := exec.CommandContext(ctx, cmdArgs[0], cmdArgs[1:]...)

	// Merge environment: start with current process env, overlay extras.
	c.Env = mergeOSEnv(env)

	if workdir != "" {
		c.Dir = workdir
	}

	stdoutPipe, err := c.StdoutPipe()
	if err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("stdout pipe: %v", err)}
	}
	stderrPipe, err := c.StderrPipe()
	if err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("stderr pipe: %v", err)}
	}

	if err := c.Start(); err != nil {
		return &ExecResult{ReturnCode: 1, Stderr: fmt.Sprintf("start: %v", err)}
	}

	var stdoutBuf, stderrBuf strings.Builder
	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		scanner := bufio.NewScanner(stdoutPipe)
		for scanner.Scan() {
			line := scanner.Text()
			stdoutBuf.WriteString(line)
			stdoutBuf.WriteByte('\n')
			if onStdout != nil {
				onStdout(line)
			}
		}
	}()

	go func() {
		defer wg.Done()
		scanner := bufio.NewScanner(stderrPipe)
		for scanner.Scan() {
			line := scanner.Text()
			stderrBuf.WriteString(line)
			stderrBuf.WriteByte('\n')
			if onStderr != nil {
				onStderr(line)
			}
		}
	}()

	wg.Wait()
	err = c.Wait()

	rc := 0
	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			rc = exitErr.ExitCode()
		} else if ctx.Err() == context.DeadlineExceeded {
			rc = exitCodeTimeout
			stderrBuf.WriteString("process killed: timeout exceeded\n")
		} else if ctx.Err() == context.Canceled {
			rc = exitCodeCanceled
		} else {
			rc = 1
			stderrBuf.WriteString(fmt.Sprintf("exec error: %v\n", err))
		}
	}

	return &ExecResult{
		ReturnCode: rc,
		Stdout:     stdoutBuf.String(),
		Stderr:     stderrBuf.String(),
	}
}

// ---------------------------------------------------------------------------
// Capability / shell detection (used during worker registration)
// ---------------------------------------------------------------------------

// DetectCapabilities returns the list of executor types this worker supports.
func DetectCapabilities() []string {
	caps := []string{"shell", "external"}

	if findPython() != "" {
		caps = append(caps, "python")
	}
	if findPowershell() != "" {
		caps = append(caps, "powershell")
	}
	if runtime.GOOS == "windows" {
		caps = append(caps, "batch")
	}
	return caps
}

// DetectShells returns the list of shell interpreters available on this system.
func DetectShells() []string {
	isWindows := runtime.GOOS == "windows"
	type probe struct {
		name string
		cmd  []string
	}

	var candidates []probe
	if isWindows {
		candidates = []probe{
			{"bash", []string{"bash", "--version"}},
			{"cmd", []string{"cmd", "/c", "echo ok"}},
			{"powershell", []string{"powershell", "-Command", "echo ok"}},
			{"pwsh", []string{"pwsh", "-Command", "echo ok"}},
		}
	} else {
		candidates = []probe{
			{"bash", []string{"/bin/bash", "--version"}},
			{"sh", []string{"/bin/sh", "--version"}},
			{"pwsh", []string{"pwsh", "-Command", "echo ok"}},
		}
	}

	var found []string
	for _, c := range candidates {
		if probeCmd(c.cmd) {
			found = append(found, c.name)
		}
	}
	return found
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// buildEnv merges executor-level env vars and job params into a single map.
// Params are prefixed with HYDRA_PARAM_ to avoid collisions.
func buildEnv(executorEnv, params map[string]string) map[string]string {
	merged := make(map[string]string, len(executorEnv)+len(params))
	for k, v := range executorEnv {
		merged[k] = v
	}
	for k, v := range params {
		merged["HYDRA_PARAM_"+k] = v
	}
	return merged
}

// mergeOSEnv returns os.Environ() with the extra key=value pairs overlaid.
func mergeOSEnv(extra map[string]string) []string {
	base := os.Environ()
	if len(extra) == 0 {
		return base
	}
	// Index existing vars for fast override.
	idx := make(map[string]int, len(base))
	for i, entry := range base {
		if k, _, ok := strings.Cut(entry, "="); ok {
			idx[k] = i
		}
	}
	for k, v := range extra {
		if i, exists := idx[k]; exists {
			base[i] = k + "=" + v
		} else {
			base = append(base, k+"="+v)
		}
	}
	return base
}

// writeTempFile creates a temporary file with the given prefix, suffix, and
// content, returning its path. The caller is responsible for removal.
func writeTempFile(prefix, suffix, content string) (string, error) {
	f, err := os.CreateTemp("", prefix+"*"+suffix)
	if err != nil {
		return "", err
	}
	path := f.Name()
	if _, err := f.WriteString(content); err != nil {
		f.Close()
		os.Remove(path)
		return "", err
	}
	if err := f.Close(); err != nil {
		os.Remove(path)
		return "", err
	}
	// Make script files executable.
	if err := os.Chmod(path, 0700); err != nil {
		log.Printf("[executor] chmod warning: %v", err)
	}
	return path, nil
}

// findPython returns the first available Python interpreter or "".
func findPython() string {
	for _, interp := range []string{"python3", "python"} {
		if probeCmd([]string{interp, "--version"}) {
			return interp
		}
	}
	return ""
}

// findPowershell returns the first available PowerShell binary or "".
func findPowershell() string {
	for _, ps := range []string{"pwsh", "powershell"} {
		if probeCmd([]string{ps, "-Command", "echo ok"}) {
			return ps
		}
	}
	return ""
}

// probeCmd runs a command with a short timeout and returns true if it exits 0.
func probeCmd(args []string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, args[0], args[1:]...)
	cmd.Stdout = nil
	cmd.Stderr = nil
	return cmd.Run() == nil
}
