import { PythonEnvironment } from "../../types";
import { JobPayload } from "../../api/jobs";

export const defaultAffinity = {
  os: ["linux"] as string[],
  tags: [] as string[],
  allowed_users: [] as string[],
  hostnames: [] as string[],
  subnets: [] as string[],
  deployment_types: [] as string[],
};

export const createDefaultPythonEnvironment = (): PythonEnvironment => ({
  type: "system",
  python_version: "python3",
  requirements: [],
  requirements_file: null,
});

export const createDefaultPythonExecutor = () => ({
  type: "python" as const,
  code: "# Add your Python here\nprint('hello')",
  interpreter: "python3",
  environment: createDefaultPythonEnvironment(),
});

export const createDefaultPayload = (): JobPayload => ({
  name: "",
  user: "default",
  priority: 5,
  affinity: {
    os: [...defaultAffinity.os],
    tags: [],
    allowed_users: [],
    hostnames: [],
    subnets: [],
    deployment_types: [],
  },
  executor: { type: "shell", script: "echo 'hello world'", shell: "bash" },
  retries: 0,
  timeout: 60,
  bypass_concurrency: false,
  source: null,
  schedule: {
    mode: "immediate",
    enabled: true,
    cron: "",
    interval_seconds: 300,
    start_at: null,
    end_at: null,
    next_run_at: null,
    timezone: "UTC",
  },
  completion: {
    exit_codes: [0],
    stdout_contains: [],
    stdout_not_contains: [],
    stderr_contains: [],
    stderr_not_contains: [],
  },
  tags: [],
  depends_on: [],
  retry_count: 0,
  max_retries: 0,
  retry_delay_seconds: 0,
  on_failure_webhooks: [],
  on_failure_email_to: [],
  on_failure_email_credential_ref: "",
  sla_max_duration_seconds: null,
});

/** Executor-type-aware defaults for timeout and OS affinity. */
export const EXECUTOR_DEFAULTS: Record<string, { timeout: number; os: string[] }> = {
  shell: { timeout: 60, os: ["linux"] },
  python: { timeout: 300, os: ["linux"] },
  batch: { timeout: 60, os: ["windows"] },
  powershell: { timeout: 120, os: ["windows"] },
  sql: { timeout: 120, os: [] },
  http: { timeout: 30, os: [] },
  external: { timeout: 60, os: ["linux"] },
  sensor: { timeout: 3600, os: [] },
};

export type FormScheduleMode = JobPayload["schedule"]["mode"] | "dependency";

export const parseList = (value: string) =>
  value
    .split(/\n|,/)
    .map((s) => s.trim())
    .filter(Boolean);

export interface WorkerHints {
  os: string[];
  tags: string[];
  users: string[];
  hostnames: string[];
  subnets: string[];
  deployments: string[];
  pythonVersions: string[];
  capabilities: string[];
  shells: string[];
}
