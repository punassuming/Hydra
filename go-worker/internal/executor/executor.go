// Package executor will contain the job execution engine for the Go worker.
// It is a placeholder for future implementation of shell, python, and other
// executor types mirroring the Python worker's executor.py.
package executor

import (
	"encoding/json"
	"fmt"
)

// JobEnvelope represents the minimal job payload dispatched by the scheduler.
// Fields will be expanded as executor types are implemented.
type JobEnvelope struct {
	JobID    string          `json:"job_id"`
	RunID    string          `json:"run_id"`
	Executor json.RawMessage `json:"executor"`
}

// Execute runs the job described by env.
// TODO: implement shell, python, batch, and external executor types.
func Execute(env *JobEnvelope) error {
	return fmt.Errorf("executor not yet implemented for job %s (run %s)", env.JobID, env.RunID)
}
