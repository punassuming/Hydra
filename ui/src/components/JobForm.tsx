import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Typography,
  Steps,
} from "antd";
import { JobDefinition, PythonEnvironment } from "../types";
import { JobPayload, ValidationResult, fetchWorkers, fetchJobs, generateJob } from "../api/jobs";
import { useActiveDomain } from "../context/ActiveDomainContext";

const defaultAffinity = {
  os: ["linux"],
  tags: [] as string[],
  allowed_users: [] as string[],
  hostnames: [] as string[],
  subnets: [] as string[],
  deployment_types: [] as string[],
  executor_types: [] as string[],
};

const createDefaultPythonEnvironment = (): PythonEnvironment => ({
  type: "system",
  python_version: "python3",
  requirements: [],
  requirements_file: null,
  venv_path: null,
});

const createDefaultPythonExecutor = () => ({
  type: "python" as const,
  code: "# Add your Python here\nprint('hello')",
  interpreter: "python3",
  environment: createDefaultPythonEnvironment(),
});

const createDefaultPayload = (): JobPayload => ({
  name: "",
  user: "default",
  // queue removed
  priority: 5,
  affinity: {
    os: [...defaultAffinity.os],
    tags: [],
    allowed_users: [],
    hostnames: [],
    subnets: [],
    deployment_types: [],
    executor_types: [],
  },
  executor: { type: "shell", script: "echo 'hello world'", shell: "bash" },
  retries: 0,
  timeout: 30,
  bypass_concurrency: false,
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
  max_retries: 0,
  retry_delay_seconds: 0,
  on_failure_webhooks: [],
});

interface Props {
  selectedJob?: JobDefinition | null;
  onSubmit: (payload: JobPayload) => Promise<void> | void;
  onValidate: (payload: JobPayload) => Promise<ValidationResult | undefined> | ValidationResult | undefined;
  onManualRun: () => void;
  onAdhocRun: (payload: JobPayload) => void;
  submitting: boolean;
  validating: boolean;
  statusMessage?: string;
  onReset: () => void;
}

export function JobForm({
  selectedJob,
  onSubmit,
  onValidate,
  onManualRun,
  onAdhocRun,
  submitting,
  validating,
  statusMessage,
  onReset,
}: Props) {
  const { domain } = useActiveDomain();
  const [payload, setPayload] = useState<JobPayload>(() => createDefaultPayload());
  const [activeStep, setActiveStep] = useState(0);
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [provider, setProvider] = useState<"gemini" | "openai">("gemini");

  const workersQuery = useQuery({
    queryKey: ["workers", domain],
    queryFn: fetchWorkers,
    staleTime: 5000,
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", domain],
    queryFn: () => fetchJobs(),
    staleTime: 30000,
  });

  const allJobs = jobsQuery.data ?? [];

  const workerHints = useMemo(() => {
    const workers = workersQuery.data ?? [];
    const collect = (getter: (w: any) => string | string[] | undefined) => {
      const values = workers.flatMap((w) => {
        const v = getter(w);
        if (!v) return [];
        return Array.isArray(v) ? v : [v];
      });
      return Array.from(new Set(values.filter(Boolean))) as string[];
    };
    return {
      os: collect((w) => w.os),
      tags: collect((w) => w.tags),
      users: collect((w) => w.allowed_users),
      hostnames: collect((w) => w.hostname),
      subnets: collect((w) => w.subnet),
      deployments: collect((w) => w.deployment_type),
      pythonVersions: collect((w) => w.python_version),
      capabilities: collect((w) => w.capabilities),
      shells: collect((w) => w.shells),
    };
  }, [workersQuery.data]);

  const normalizeExecutor = (exec: JobDefinition["executor"]): JobPayload["executor"] => {
    if (exec.type !== "python") {
      return exec as JobPayload["executor"];
    }
    return {
      ...exec,
      environment: {
        ...createDefaultPythonEnvironment(),
        python_version: exec.environment?.python_version ?? exec.interpreter ?? "python3",
        ...exec.environment,
        requirements: exec.environment?.requirements ?? [],
      },
    } as JobPayload["executor"];
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const generated = await generateJob(prompt, provider);
      if (generated) {
        setPayload({
            ...generated,
            executor: normalizeExecutor(generated.executor)
        });
      }
    } catch (e) {
      console.error("Failed to generate job", e);
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => {
    if (selectedJob) {
      setPayload({
        name: selectedJob.name,
        user: selectedJob.user || "default",
        affinity: { ...createDefaultPayload().affinity, ...selectedJob.affinity },
        executor: normalizeExecutor(selectedJob.executor),
        retries: selectedJob.retries,
        timeout: selectedJob.timeout,
        bypass_concurrency: selectedJob.bypass_concurrency ?? false,
        // queue removed
        priority: (selectedJob as any).priority ?? 5,
        schedule: { ...createDefaultPayload().schedule, ...(selectedJob.schedule ?? {}) },
        completion: { ...createDefaultPayload().completion, ...(selectedJob.completion ?? {}) },
        tags: selectedJob.tags ?? [],
        depends_on: selectedJob.depends_on ?? [],
        max_retries: selectedJob.max_retries ?? 0,
        retry_delay_seconds: selectedJob.retry_delay_seconds ?? 0,
        on_failure_webhooks: selectedJob.on_failure_webhooks ?? [],
      });
    } else {
      setPayload(createDefaultPayload());
    }
    setActiveStep(0);
  }, [selectedJob]);

  const executor = payload.executor;
  const executorType = executor.type;
  const schedule = payload.schedule;
  const completion = payload.completion;
  const pythonEnv =
    executor.type === "python"
      ? { ...createDefaultPythonEnvironment(), ...(executor.environment as PythonEnvironment | undefined) }
      : null;

  const updatePayload = (field: keyof JobPayload, value: any) => {
    setPayload((prev) => ({ ...prev, [field]: value }));
  };

  const updateExecutor = (update: Record<string, unknown>) => {
    setPayload((prev) => ({ ...prev, executor: { ...prev.executor, ...update } as JobPayload["executor"] }));
  };

  const updateSchedule = (update: Record<string, unknown>) => {
    setPayload((prev) => ({ ...prev, schedule: { ...prev.schedule, ...update } }));
  };

  const updateCompletion = (update: Record<string, unknown>) => {
    setPayload((prev) => ({ ...prev, completion: { ...prev.completion, ...update } }));
  };

  const updatePythonEnv = (update: Partial<PythonEnvironment>) => {
    if (executor.type !== "python") {
      return;
    }
    const merged = {
      ...createDefaultPythonEnvironment(),
      ...(executor.environment as PythonEnvironment | undefined),
      ...update,
    };
    updateExecutor({ environment: merged });
  };

  const updateAffinity = (key: keyof typeof defaultAffinity, value: string[]) => {
    updatePayload("affinity", {
      ...payload.affinity,
      [key]: value,
    });
  };

  const parseList = (value: string) =>
    value
      .split(/\n|,/)
      .map((s) => s.trim())
      .filter(Boolean);

  const setCompletionList = (field: keyof JobPayload["completion"], value: string) => {
    updateCompletion({ [field]: parseList(value) });
  };

  const toInputValue = (iso?: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
  const fromInputValue = (value: string) => (value ? new Date(value).toISOString() : null);

  const handleValidateOnly = async () => onValidate(payload);

  const handleValidateThenSubmit = async () => {
    const validation = await onValidate(payload);
    if (!validation?.valid) {
      return;
    }
    const normalized = { ...payload, user: payload.user?.trim() || "default" };
    await onSubmit(normalized);
  };

  const executorTypeSelect = (
    <Form.Item label="Executor Type" required>
      <Select
        value={executorType}
        onChange={(nextType) => {
          const defaults: Record<string, any> = {
            python: createDefaultPythonExecutor(),
            shell: { type: "shell", script: "echo 'hello world'", shell: "bash" },
            batch: { type: "batch", script: "echo hello", shell: "cmd" },
            powershell: { type: "powershell", script: "Write-Host 'hello world'", shell: "pwsh" },
            sql: { type: "sql", dialect: "postgres", query: "SELECT 1;", connection_uri: "", database: "" },
            external: { type: "external", command: "/usr/bin/env" },
          };
          updateExecutor(defaults[nextType]);
        }}
        options={[
          { label: "Shell", value: "shell" },
          { label: "Batch", value: "batch" },
          { label: "PowerShell", value: "powershell" },
          { label: "Python", value: "python" },
          { label: "SQL / Database", value: "sql" },
          { label: "External Binary", value: "external" },
        ]}
      />
    </Form.Item>
  );

  const steps = [
    { key: "basics", title: "Basics", description: "Name, retries, timeout" },
    { key: "executor", title: "Executor", description: "Code & environment" },
    { key: "schedule", title: "Schedule", description: "When it should run" },
    { key: "affinity", title: "Placement", description: "Workers & affinity" },
    { key: "completion", title: "Completion", description: "Success signals" },
  ];

  const renderStepContent = (key: string) => {
    switch (key) {
      case "executor":
        return (
          <>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                {executorTypeSelect}
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Arguments">
                  <Input
                    value={(executor as any).args?.join(" ") ?? ""}
                    onChange={(e) => updateExecutor({ args: e.target.value.split(" ").filter(Boolean) })}
                    placeholder="--flag value"
                  />
                </Form.Item>
              </Col>
            </Row>

            {executor.type === "python" && (
              <>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item label="Interpreter">
                      <Select
                        mode="tags"
                        value={executor.interpreter ? [executor.interpreter] : []}
                        onChange={(val) => {
                          const arr = Array.isArray(val) ? val : [val];
                          updateExecutor({ interpreter: arr[arr.length - 1] });
                        }}
                        options={(workerHints.pythonVersions ?? []).map((v) => ({ label: v, value: v }))}
                        placeholder="python3, python3.11, uv"
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Python Version / Dist (uv friendly)">
                      <Select
                        mode="tags"
                        value={pythonEnv?.python_version ? [pythonEnv.python_version] : []}
                        onChange={(val) => {
                          const arr = Array.isArray(val) ? val : [val];
                          updatePythonEnv({ python_version: arr[arr.length - 1] });
                        }}
                        options={(workerHints.pythonVersions ?? []).map((v) => ({ label: v, value: v }))}
                        placeholder="3.11, 3.12, pypy3"
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Python Code Block">
                  <Input.TextArea
                    value={executor.code ?? ""}
                    onChange={(e) => updateExecutor({ code: e.target.value })}
                    autoSize={{ minRows: 8 }}
                    placeholder="# Multi-line Python supported"
                  />
                </Form.Item>
                {pythonEnv && (
                  <Row gutter={16}>
                    <Col xs={24} md={8}>
                      <Form.Item label="Environment Type">
                        <Select
                          value={pythonEnv.type}
                          onChange={(value) => updatePythonEnv({ type: value as PythonEnvironment["type"] })}
                          options={[
                            { label: "System", value: "system" },
                            { label: "Virtualenv", value: "venv" },
                            { label: "uv managed", value: "uv" },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item label="Virtualenv Path (optional)">
                        <Input
                          value={pythonEnv.venv_path ?? ""}
                          onChange={(e) => updatePythonEnv({ venv_path: e.target.value || null })}
                          placeholder="/opt/venvs/job"
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item label="Requirements File">
                        <Input
                          value={pythonEnv.requirements_file ?? ""}
                          onChange={(e) => updatePythonEnv({ requirements_file: e.target.value || null })}
                          placeholder="/workspace/requirements.txt"
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item label="Requirements (one per line)">
                        <Input.TextArea
                          value={(pythonEnv.requirements ?? []).join("\n")}
                          onChange={(e) => updatePythonEnv({ requirements: parseList(e.target.value) })}
                          autoSize
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item label="Working Directory">
                        <Input
                          value={executor.workdir ?? ""}
                          onChange={(e) => updateExecutor({ workdir: e.target.value || null })}
                          placeholder="/opt/jobs"
                        />
                      </Form.Item>
                    </Col>
                    {pythonEnv.type === "uv" && (
                      <Col span={24}>
                        <Alert
                          type="info"
                          showIcon
                          message="Workers should have uv installed. The requested Python version will be provisioned via uv if available."
                        />
                      </Col>
                    )}
                  </Row>
                )}
              </>
            )}

            {(executor.type === "shell" || executor.type === "batch") && (
              <>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item label="Shell">
                      <Input
                        value={executor.shell ?? (executor.type === "batch" ? "cmd" : "bash")}
                        onChange={(e) => updateExecutor({ shell: e.target.value })}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Working Directory">
                      <Input
                        value={executor.workdir ?? ""}
                        onChange={(e) => updateExecutor({ workdir: e.target.value || null })}
                        placeholder="/opt/jobs"
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Script / Code Block">
                  <Input.TextArea
                    value={executor.script ?? ""}
                    onChange={(e) => updateExecutor({ script: e.target.value })}
                    autoSize={{ minRows: 8 }}
                    placeholder="Multi-line shell or batch scripts supported"
                  />
                </Form.Item>
              </>
            )}

            {executor.type === "external" && (
              <>
                <Form.Item label="Command / Binary Path">
                  <Input value={executor.command ?? ""} onChange={(e) => updateExecutor({ command: e.target.value })} />
                </Form.Item>
                <Form.Item label="Working Directory">
                  <Input
                    value={executor.workdir ?? ""}
                    onChange={(e) => updateExecutor({ workdir: e.target.value || null })}
                    placeholder="/opt/jobs"
                  />
                </Form.Item>
              </>
            )}

            {executor.type === "powershell" && (
              <>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item label="Shell">
                      <Select
                        value={(executor as any).shell ?? "pwsh"}
                        onChange={(val) => updateExecutor({ shell: val })}
                        options={[
                          { label: "pwsh (cross-platform)", value: "pwsh" },
                          { label: "powershell (Windows)", value: "powershell" },
                        ]}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Working Directory">
                      <Input
                        value={executor.workdir ?? ""}
                        onChange={(e) => updateExecutor({ workdir: e.target.value || null })}
                        placeholder="/opt/jobs"
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="PowerShell Script">
                  <Input.TextArea
                    value={(executor as any).script ?? ""}
                    onChange={(e) => updateExecutor({ script: e.target.value })}
                    autoSize={{ minRows: 8 }}
                    placeholder="Write-Host 'Hello from PowerShell'"
                  />
                </Form.Item>
              </>
            )}

            {executor.type === "sql" && (
              <>
                <Row gutter={16}>
                  <Col xs={24} md={8}>
                    <Form.Item label="Dialect">
                      <Select
                        value={(executor as any).dialect ?? "postgres"}
                        onChange={(val) => updateExecutor({ dialect: val })}
                        options={[
                          { label: "PostgreSQL", value: "postgres" },
                          { label: "MySQL", value: "mysql" },
                          { label: "SQL Server", value: "mssql" },
                          { label: "Oracle", value: "oracle" },
                          { label: "MongoDB", value: "mongodb" },
                        ]}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item label="Database">
                      <Input
                        value={(executor as any).database ?? ""}
                        onChange={(e) => updateExecutor({ database: e.target.value })}
                        placeholder="mydb"
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item label="Credential Reference">
                      <Input
                        value={(executor as any).credential_ref ?? ""}
                        onChange={(e) => updateExecutor({ credential_ref: e.target.value || null })}
                        placeholder="stored credential name (optional)"
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Connection URI">
                  <Input
                    value={(executor as any).connection_uri ?? ""}
                    onChange={(e) => updateExecutor({ connection_uri: e.target.value })}
                    placeholder="postgresql://user:pass@host:5432/db"
                  />
                </Form.Item>
                <Form.Item label="SQL Query">
                  <Input.TextArea
                    value={(executor as any).query ?? ""}
                    onChange={(e) => updateExecutor({ query: e.target.value })}
                    autoSize={{ minRows: 8 }}
                    placeholder="SELECT * FROM table LIMIT 10;"
                  />
                </Form.Item>
                <Alert
                  type="info"
                  showIcon
                  message="Workers require sqlalchemy (relational) or pymongo (MongoDB) to be installed. Credentials can be stored encrypted via Admin > Credentials."
                  style={{ marginBottom: 12 }}
                />
              </>
            )}

            <Form.Item label="Environment Variables (KEY=VALUE per line)">
              <Input.TextArea
                value={
                  executor.env
                    ? Object.entries(executor.env)
                        .map(([k, v]) => `${k}=${v}`)
                        .join("\n")
                    : ""
                }
                onChange={(e) => {
                  const envLines = e.target.value.split("\n");
                  const env: Record<string, string> = {};
                  envLines.forEach((line) => {
                    const [k, ...rest] = line.split("=");
                    if (k && rest.length) {
                      env[k.trim()] = rest.join("=").trim();
                    }
                  });
                  updateExecutor({ env });
                }}
                autoSize
              />
            </Form.Item>
            <Divider style={{ marginTop: 0 }} />
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Linux Impersonation User">
                  <Input
                    value={(executor as any).impersonate_user ?? ""}
                    onChange={(e) => updateExecutor({ impersonate_user: e.target.value || null })}
                    placeholder="svc_batch (optional)"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Kerberos Principal">
                  <Input
                    value={(executor as any).kerberos?.principal ?? ""}
                    onChange={(e) =>
                      updateExecutor({
                        kerberos: { ...((executor as any).kerberos ?? {}), principal: e.target.value },
                      })
                    }
                    placeholder="user@REALM"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Kerberos Keytab Path">
                  <Input
                    value={(executor as any).kerberos?.keytab ?? ""}
                    onChange={(e) =>
                      updateExecutor({
                        kerberos: { ...((executor as any).kerberos ?? {}), keytab: e.target.value },
                      })
                    }
                    placeholder="/etc/security/keytabs/user.keytab"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Kerberos Cache (optional)">
                  <Input
                    value={(executor as any).kerberos?.ccache ?? ""}
                    onChange={(e) =>
                      updateExecutor({
                        kerberos: { ...((executor as any).kerberos ?? {}), ccache: e.target.value || null },
                      })
                    }
                    placeholder="/tmp/krb5cc_hydra"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Typography.Text type="secondary">
              Linux workers only. If `impersonate_user` is set, worker runs command as `sudo -n -u &lt;user&gt;` and runs `kinit -kt` before job execution when Kerberos fields are provided.
            </Typography.Text>
          </>
        );
      case "schedule":
        return (
          <>
            <Row gutter={16} align="middle">
              <Col xs={24} md={8}>
                <Form.Item label="Mode">
                  <Select
                    value={schedule.mode}
                    onChange={(mode) => updateSchedule({ mode, next_run_at: null })}
                    options={[
                      { label: "Immediate", value: "immediate" },
                      { label: "Interval", value: "interval" },
                      { label: "Cron", value: "cron" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Enabled">
                  <Switch checked={schedule.enabled} onChange={(checked) => updateSchedule({ enabled: checked })} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Typography.Text type="secondary">
                  Next run:{" "}
                  {!schedule.enabled
                    ? "Disabled"
                    : schedule.next_run_at
                      ? new Date(schedule.next_run_at).toLocaleString()
                      : schedule.mode === "immediate"
                        ? "Immediately"
                        : "Pending"}
                </Typography.Text>
              </Col>
            </Row>
            {schedule.mode === "interval" && (
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="Interval (seconds)">
                    <InputNumber
                      min={1}
                      style={{ width: "100%" }}
                      value={schedule.interval_seconds ?? 300}
                      onChange={(value) => updateSchedule({ interval_seconds: Number(value) })}
                    />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {schedule.mode === "cron" && (
              <Row gutter={16}>
                <Col span={24}>
                  <Form.Item label="Cron Expression">
                    <Input value={schedule.cron ?? ""} onChange={(e) => updateSchedule({ cron: e.target.value })} placeholder="*/5 * * * *" />
                  </Form.Item>
                </Col>
              </Row>
            )}
            {(schedule.mode === "interval" || schedule.mode === "cron") && (
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="Start At">
                    <Input
                      type="datetime-local"
                      value={toInputValue(schedule.start_at)}
                      onChange={(e) => updateSchedule({ start_at: fromInputValue(e.target.value) })}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="End At">
                    <Input
                      type="datetime-local"
                      value={toInputValue(schedule.end_at)}
                      onChange={(e) => updateSchedule({ end_at: fromInputValue(e.target.value) })}
                    />
                  </Form.Item>
                </Col>
              </Row>
            )}
          </>
        );
      case "completion":
        return (
          <>
            <Row gutter={16}>
              <Col span={24}>
                <Form.Item label="Exit Codes">
                  <Input
                    value={completion.exit_codes.join(", ")}
                    onChange={(e) => {
                      const values = parseList(e.target.value)
                        .map((c) => Number(c))
                        .filter((n) => !Number.isNaN(n));
                      updateCompletion({ exit_codes: values.length ? values : [] });
                    }}
                    placeholder="0, 2"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Stdout must contain">
                  <Input.TextArea
                    value={completion.stdout_contains.join("\n")}
                    onChange={(e) => setCompletionList("stdout_contains", e.target.value)}
                    placeholder="ready"
                    autoSize
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Stdout must NOT contain">
                  <Input.TextArea
                    value={completion.stdout_not_contains.join("\n")}
                    onChange={(e) => setCompletionList("stdout_not_contains", e.target.value)}
                    placeholder="error"
                    autoSize
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Stderr must contain">
                  <Input.TextArea
                    value={completion.stderr_contains.join("\n")}
                    onChange={(e) => setCompletionList("stderr_contains", e.target.value)}
                    autoSize
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Stderr must NOT contain">
                  <Input.TextArea
                    value={completion.stderr_not_contains.join("\n")}
                    onChange={(e) => setCompletionList("stderr_not_contains", e.target.value)}
                    autoSize
                  />
                </Form.Item>
              </Col>
            </Row>
          </>
        );
      case "affinity":
        return (
          <>
            <Alert
              type="info"
              showIcon
              message="Use the worker-derived dropdowns to target specific pools. You can also type new values to create ad-hoc affinities."
              style={{ marginBottom: 12 }}
            />
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Target OS">
                  <Select
                    mode="tags"
                    value={payload.affinity.os}
                    onChange={(vals) => updateAffinity("os", vals)}
                    options={workerHints.os.map((v) => ({ label: v, value: v }))}
                    placeholder="linux, windows"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Tags">
                  <Select
                    mode="tags"
                    value={payload.affinity.tags}
                    onChange={(vals) => updateAffinity("tags", vals)}
                    options={workerHints.tags.map((v) => ({ label: v, value: v }))}
                    placeholder="gpu, python, ingest"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Allowed Users">
                  <Select
                    mode="tags"
                    value={payload.affinity.allowed_users}
                    onChange={(vals) => updateAffinity("allowed_users", vals)}
                    options={workerHints.users.map((v) => ({ label: v, value: v }))}
                    placeholder="alice, bob"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Hostnames">
                  <Select
                    mode="tags"
                    value={payload.affinity.hostnames ?? []}
                    onChange={(vals) => updateAffinity("hostnames", vals)}
                    options={workerHints.hostnames.map((v) => ({ label: v, value: v }))}
                    placeholder="worker-1, batch-2"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Subnets / CIDRs">
                  <Select
                    mode="tags"
                    value={payload.affinity.subnets ?? []}
                    onChange={(vals) => updateAffinity("subnets", vals)}
                    options={workerHints.subnets.map((v) => ({ label: v, value: v }))}
                    placeholder="10.0.1"
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Deployment Types">
                  <Select
                    mode="tags"
                    value={payload.affinity.deployment_types ?? []}
                    onChange={(vals) => updateAffinity("deployment_types", vals)}
                    options={workerHints.deployments.map((v) => ({ label: v, value: v }))}
                    placeholder="docker, kubernetes, bare-metal"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Required Executor Types">
                  <Select
                    mode="tags"
                    value={payload.affinity.executor_types ?? []}
                    onChange={(vals) => updateAffinity("executor_types", vals)}
                    options={workerHints.capabilities.map((v) => ({ label: v, value: v }))}
                    placeholder="shell, python, powershell, sql"
                  />
                </Form.Item>
              </Col>
            </Row>
          </>
        );
      case "basics":
      default:
        return (
          <>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Name" required>
                  <Input value={payload.name} onChange={(e) => updatePayload("name", e.target.value)} placeholder="batch-import" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Tags (comma-separated)">
                  <Select
                    mode="tags"
                    style={{ width: "100%" }}
                    placeholder="production, data-import, critical"
                    value={payload.tags ?? []}
                    onChange={(value) => updatePayload("tags", value)}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item label="Timeout (seconds)">
                  <InputNumber
                    min={0}
                    style={{ width: "100%" }}
                    value={payload.timeout}
                    onChange={(value) => updatePayload("timeout", Number(value))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Retries">
                  <InputNumber
                    min={0}
                    style={{ width: "100%" }}
                    value={payload.retries}
                    onChange={(value) => updatePayload("retries", Number(value))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Priority (higher runs first)">
                  <InputNumber
                    min={0}
                    max={100}
                    style={{ width: "100%" }}
                    value={payload.priority}
                    onChange={(value) => updatePayload("priority", Number(value))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Bypass Worker Concurrency Quota">
                  <Switch
                    checked={Boolean(payload.bypass_concurrency)}
                    onChange={(checked) => updatePayload("bypass_concurrency", checked)}
                  />
                </Form.Item>
                <Typography.Text type="secondary">
                  When enabled, this job can run beyond worker max concurrency lanes.
                </Typography.Text>
              </Col>
            </Row>
            <Divider orientation="left" plain>Advanced Retry &amp; Alerting</Divider>
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Max Scheduler Retries" tooltip="Scheduler-level retries after terminal failure (separate from worker retries above)">
                  <InputNumber
                    min={0}
                    style={{ width: "100%" }}
                    value={payload.max_retries ?? 0}
                    onChange={(value) => updatePayload("max_retries", Number(value))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Retry Delay (seconds)" tooltip="Seconds to wait before each scheduler retry">
                  <InputNumber
                    min={0}
                    style={{ width: "100%" }}
                    value={payload.retry_delay_seconds ?? 0}
                    onChange={(value) => updatePayload("retry_delay_seconds", Number(value))}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="Failure Webhook URLs (one per line)" tooltip="HTTP POST will be sent to these URLs on terminal failure">
              <Input.TextArea
                value={(payload.on_failure_webhooks ?? []).join("\n")}
                onChange={(e) => updatePayload("on_failure_webhooks", parseList(e.target.value))}
                placeholder="https://hooks.example.com/alert"
                autoSize={{ minRows: 2 }}
              />
            </Form.Item>
            <Divider orientation="left" plain>Job Dependencies</Divider>
            <Form.Item label="Depends On" tooltip="This job will be triggered automatically when all listed jobs succeed">
              <Select
                mode="multiple"
                style={{ width: "100%" }}
                placeholder="Select prerequisite jobs..."
                value={payload.depends_on ?? []}
                onChange={(value) => updatePayload("depends_on", value)}
                options={allJobs
                  .filter((j) => j._id !== (selectedJob?._id))
                  .map((j) => ({ label: `${j.name} (${j._id.slice(0, 8)})`, value: j._id }))}
                filterOption={(input, option) =>
                  (option?.label as string ?? "").toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>
          </>
        );
    }
  };

  const activeKey = steps[activeStep]?.key ?? "basics";

  return (
    <Form layout="vertical" onFinish={handleValidateThenSubmit}>
      {!selectedJob && (
        <Alert
            message="Magic Job Generator"
            description={
                <Space.Compact style={{ width: '100%' }}>
                    <Select 
                        value={provider} 
                        onChange={setProvider} 
                        options={[{label: 'Gemini', value: 'gemini'}, {label: 'OpenAI', value: 'openai'}]}
                        style={{ width: 100 }}
                    />
                    <Input 
                        placeholder="Describe your job (e.g., 'Run a backup script every Sunday at 2am')" 
                        value={prompt}
                        onChange={e => setPrompt(e.target.value)}
                        onPressEnter={handleGenerate}
                    />
                    <Button type="primary" loading={generating} onClick={handleGenerate}>Generate</Button>
                </Space.Compact>
            }
            type="info"
            showIcon
            style={{ marginBottom: 20 }}
        />
      )}
      <Steps
        current={activeStep}
        items={steps}
        onChange={setActiveStep}
        responsive
      />
      <Divider />
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {renderStepContent(activeKey)}
      </Space>
      <Divider />
      <Space wrap>
        {activeStep > 0 && (
          <Button onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}>
            Previous
          </Button>
        )}
        {activeStep < steps.length - 1 && (
          <Button type="primary" onClick={() => setActiveStep((prev) => Math.min(steps.length - 1, prev + 1))}>
            Next
          </Button>
        )}
        {activeStep === steps.length - 1 && (
          <Button type="primary" htmlType="submit" loading={submitting || validating}>
            {selectedJob ? "Validate & Update" : "Validate & Submit"}
          </Button>
        )}
        <Button onClick={handleValidateOnly} loading={validating}>
          Validate This Step
        </Button>
        {!selectedJob && (
          <Button
            onClick={() => {
              const normalized = { ...payload, user: payload.user?.trim() || "default" };
              onAdhocRun(normalized);
            }}
            disabled={submitting}
            type="dashed"
          >
            Run Adhoc
          </Button>
        )}
        {selectedJob && (
          <Button onClick={onManualRun} type="default">
            Run Now
          </Button>
        )}
        {selectedJob && (
          <Button onClick={onReset} danger>
            New Job
          </Button>
        )}
      </Space>
      {statusMessage && <Typography.Paragraph style={{ marginTop: "0.5rem" }}>{statusMessage}</Typography.Paragraph>}
    </Form>
  );
}
