import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, Space, Typography, Tabs, Button, Tag, Descriptions, message, Modal, Input, Form } from "antd";
import { JobRuns } from "../components/JobRuns";
import { JobGridView } from "../components/JobGridView";
import { JobGanttView } from "../components/JobGanttView";
import { JobGraphView } from "../components/JobGraphView";
import { fetchJob, fetchJobRuns, runJobNow, killRun } from "../api/jobs";
import { useActiveDomain } from "../context/ActiveDomainContext";

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem("hydra_job_detail_tab") || "overview");
  const { domain } = useActiveDomain();
  const [paramsModalVisible, setParamsModalVisible] = useState(false);
  const [paramsText, setParamsText] = useState("");

  const jobQuery = useQuery({
    queryKey: ["job", domain, jobId],
    queryFn: () => fetchJob(jobId!),
    enabled: Boolean(jobId),
  });

  const runsQuery = useQuery({
    queryKey: ["job-runs", domain, jobId],
    queryFn: () => fetchJobRuns(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: 5000,
  });

  const parseParams = (text: string): Record<string, string> => {
    const result: Record<string, string> = {};
    text.split("\n").filter((line) => line.trim()).forEach((line) => {
      const [k, ...rest] = line.split("=");
      if (k?.trim() && rest.length) result[k.trim()] = rest.join("=").trim();
    });
    return result;
  };

  const manualRun = useMutation({
    mutationFn: ({ id, params }: { id: string; params?: Record<string, string> }) => runJobNow(id, params),
    onSuccess: () => {
      messageApi.success("Run queued");
      queryClient.invalidateQueries({ queryKey: ["job-runs", domain, jobId] });
      queryClient.invalidateQueries({ queryKey: ["job-grid", domain, jobId] });
      queryClient.invalidateQueries({ queryKey: ["job-gantt", domain, jobId] });
      queryClient.invalidateQueries({ queryKey: ["job-graph", domain, jobId] });
    },
  });

  const killMutation = useMutation({
    mutationFn: (runId: string) => killRun(runId),
    onSuccess: () => {
      messageApi.success("Kill signal sent");
      queryClient.invalidateQueries({ queryKey: ["job-runs", domain, jobId] });
    },
    onError: () => messageApi.error("Failed to send kill signal"),
  });

  const handleRunNow = () => {
    setParamsModalVisible(true);
  };

  const handleRunWithParams = () => {
    const params = parseParams(paramsText);
    manualRun.mutate({ id: job!._id, params: Object.keys(params).length ? params : undefined });
    setParamsModalVisible(false);
    setParamsText("");
  };

  const job = jobQuery.data;

  useEffect(() => {
    localStorage.setItem("hydra_job_detail_tab", activeTab);
  }, [activeTab]);

  const runningRuns = (runsQuery.data ?? []).filter((r) => r.status === "running");

  const tabItems = useMemo(() => {
    if (!job) return [];
    return [
      {
        key: "overview",
        label: "Overview",
        children: (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="Job ID">{job._id}</Descriptions.Item>
            <Descriptions.Item label="Name">{job.name}</Descriptions.Item>
            <Descriptions.Item label="User">{job.user}</Descriptions.Item>
            <Descriptions.Item label="Executor">{job.executor.type}</Descriptions.Item>
            <Descriptions.Item label="Bypass Concurrency">
              {job.bypass_concurrency ? "enabled" : "disabled"}
            </Descriptions.Item>
            <Descriptions.Item label="Schedule Mode">{job.schedule.mode}</Descriptions.Item>
            <Descriptions.Item label="Retries">{job.retries}</Descriptions.Item>
            <Descriptions.Item label="Timeout">{job.timeout}s</Descriptions.Item>
            {(job.max_retries ?? 0) > 0 && (
              <Descriptions.Item label="Max Scheduler Retries">{job.max_retries} (delay: {job.retry_delay_seconds ?? 0}s)</Descriptions.Item>
            )}
            {(job.depends_on ?? []).length > 0 && (
              <Descriptions.Item label="Depends On">{(job.depends_on ?? []).join(", ")}</Descriptions.Item>
            )}
            {(job.on_failure_webhooks ?? []).length > 0 && (
              <Descriptions.Item label="Failure Webhooks">{(job.on_failure_webhooks ?? []).join(", ")}</Descriptions.Item>
            )}
          </Descriptions>
        ),
      },
      {
        key: "grid",
        label: "Grid",
        children: jobId ? <JobGridView jobId={jobId} /> : null,
      },
      {
        key: "runs",
        label: "Runs",
        children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            {runningRuns.length > 0 && (
              <Space wrap>
                {runningRuns.map((run) => (
                  <Button
                    key={run._id}
                    danger
                    size="small"
                    onClick={() => killMutation.mutate(run._id)}
                    loading={killMutation.isPending}
                  >
                    Stop run {run._id.slice(0, 8)}
                  </Button>
                ))}
              </Space>
            )}
            <JobRuns jobId={jobId} runs={runsQuery.data ?? []} loading={runsQuery.isLoading} onKillRun={(runId) => killMutation.mutate(runId)} />
          </Space>
        ),
      },
      {
        key: "gantt",
        label: "Gantt",
        children: jobId ? <JobGanttView jobId={jobId} /> : null,
      },
      {
        key: "graph",
        label: "Graph",
        children: jobId ? <JobGraphView jobId={jobId} /> : null,
      },
      {
        key: "code",
        label: "Code",
        children: (
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>
            {job.executor.type === "python" ? job.executor.code : job.executor.type === "shell" ? job.executor.script : "No inline code"}
          </Typography.Paragraph>
        ),
      },
    ];
  }, [job, jobId, runsQuery.data, runsQuery.isLoading, runningRuns, killMutation]);

  if (!jobId) {
    return <Typography.Text>Select a job from the jobs list.</Typography.Text>;
  }

  if (jobQuery.isLoading) {
    return <Typography.Text>Loading job…</Typography.Text>;
  }

  if (!job) {
    return <Typography.Text>Job not found.</Typography.Text>;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      {contextHolder}
      <Card>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space align="center" wrap>
            <Typography.Title level={3} style={{ marginBottom: 0 }}>
              {job.name}
            </Typography.Title>
            <Tag color="blue">{job.executor.type}</Tag>
            <Tag color={job.schedule.enabled ? "green" : "default"}>{job.schedule.mode}</Tag>
          </Space>
          <Space>
            <Button onClick={handleRunNow} loading={manualRun.isPending}>Run Now</Button>
            <Button onClick={() => navigate("/")}>Back to Jobs</Button>
          </Space>
        </Space>
      </Card>
      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />
      <Modal
        open={paramsModalVisible}
        title="Run with Parameters"
        onOk={handleRunWithParams}
        onCancel={() => { setParamsModalVisible(false); setParamsText(""); }}
        okText="Run"
      >
        <Form layout="vertical">
          <Form.Item
            label="Runtime Parameters (KEY=VALUE, one per line)"
            extra="These will be injected as environment variables into the job process."
          >
            <Input.TextArea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              placeholder={"MY_PARAM=hello\nANOTHER=world"}
              autoSize={{ minRows: 4 }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
