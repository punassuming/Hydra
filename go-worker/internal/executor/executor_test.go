package executor

import (
	"context"
	"strings"
	"testing"
)

func TestExecShell_Basic(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-1",
		RunID: "run-1",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "echo hello world",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 0 {
		t.Fatalf("expected rc=0, got %d, stderr=%s", result.ReturnCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "hello world") {
		t.Errorf("expected stdout to contain 'hello world', got %q", result.Stdout)
	}
}

func TestExecShell_WithEnv(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-2",
		RunID: "run-2",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "echo $MY_VAR",
				Env:    map[string]string{"MY_VAR": "test_value"},
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 0 {
		t.Fatalf("expected rc=0, got %d, stderr=%s", result.ReturnCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "test_value") {
		t.Errorf("expected stdout to contain 'test_value', got %q", result.Stdout)
	}
}

func TestExecShell_Timeout(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-3",
		RunID: "run-3",
		Job: JobDef{
			Timeout: 1,
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "sleep 30",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode == 0 {
		t.Fatalf("expected non-zero rc for timeout, got 0")
	}
}

func TestExecShell_Failure(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-4",
		RunID: "run-4",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "exit 42",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 42 {
		t.Errorf("expected rc=42, got %d", result.ReturnCode)
	}
}

func TestExecExternal(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-5",
		RunID: "run-5",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:    "external",
				Command: "echo",
				Args:    []string{"hello", "external"},
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 0 {
		t.Fatalf("expected rc=0, got %d, stderr=%s", result.ReturnCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "hello external") {
		t.Errorf("expected stdout to contain 'hello external', got %q", result.Stdout)
	}
}

func TestExecShell_StreamCallbacks(t *testing.T) {
	var stdoutLines []string
	env := &JobEnvelope{
		JobID: "test-6",
		RunID: "run-6",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "echo line1\necho line2\necho line3",
			},
		},
	}
	result := Execute(context.Background(), env,
		func(line string) { stdoutLines = append(stdoutLines, line) },
		nil,
	)
	if result.ReturnCode != 0 {
		t.Fatalf("expected rc=0, got %d", result.ReturnCode)
	}
	if len(stdoutLines) != 3 {
		t.Errorf("expected 3 stdout callback calls, got %d", len(stdoutLines))
	}
}

func TestExecShell_EmptyScript(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-7",
		RunID: "run-7",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 1 {
		t.Errorf("expected rc=1 for empty script, got %d", result.ReturnCode)
	}
}

func TestExecShell_Params(t *testing.T) {
	env := &JobEnvelope{
		JobID:  "test-8",
		RunID:  "run-8",
		Params: map[string]string{"FOO": "bar"},
		Job: JobDef{
			Executor: ExecutorSpec{
				Type:   "shell",
				Script: "echo $HYDRA_PARAM_FOO",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 0 {
		t.Fatalf("expected rc=0, got %d, stderr=%s", result.ReturnCode, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "bar") {
		t.Errorf("expected stdout to contain 'bar' from param, got %q", result.Stdout)
	}
}

func TestDetectCapabilities(t *testing.T) {
	caps := DetectCapabilities()
	// Should always include shell and external.
	found := make(map[string]bool)
	for _, c := range caps {
		found[c] = true
	}
	if !found["shell"] {
		t.Error("capabilities should include 'shell'")
	}
	if !found["external"] {
		t.Error("capabilities should include 'external'")
	}
}

func TestDetectShells(t *testing.T) {
	shells := DetectShells()
	// On Linux CI, bash should be available.
	found := false
	for _, s := range shells {
		if s == "bash" {
			found = true
		}
	}
	if !found {
		t.Error("DetectShells should find bash on Linux")
	}
}

func TestBuildEnv(t *testing.T) {
	env := buildEnv(
		map[string]string{"A": "1"},
		map[string]string{"B": "2"},
	)
	if env["A"] != "1" {
		t.Errorf("expected A=1, got %q", env["A"])
	}
	if env["HYDRA_PARAM_B"] != "2" {
		t.Errorf("expected HYDRA_PARAM_B=2, got %q", env["HYDRA_PARAM_B"])
	}
}

func TestUnsupportedExecutorType(t *testing.T) {
	env := &JobEnvelope{
		JobID: "test-unsupported",
		RunID: "run-unsupported",
		Job: JobDef{
			Executor: ExecutorSpec{
				Type: "unknown_type",
			},
		},
	}
	result := Execute(context.Background(), env, nil, nil)
	if result.ReturnCode != 1 {
		t.Errorf("expected rc=1 for unsupported type, got %d", result.ReturnCode)
	}
	if !strings.Contains(result.Stderr, "unsupported") {
		t.Errorf("expected stderr to mention unsupported, got %q", result.Stderr)
	}
}
