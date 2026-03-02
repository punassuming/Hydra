import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Space, Typography, Button, Progress, Table, Tag, Modal, Tabs } from "antd";
import { fetchJobOverview, runJobNow, fetchHistory } from "../api/jobs";
import { JobRun } from "../types";
import { useActiveDomain } from "../context/ActiveDomainContext";
import { StatusBadge } from "../components/StatusBadge";
import { LogViewer } from "../components/LogViewer";
import { FailureInsight } from "../components/FailureInsight";
import { useTheme } from "../theme";
import {
  BarChartOutlined,
  HistoryOutlined,
} from "@ant-design/icons";

function StatusTab() {
  const queryClient = useQueryClient();
  const { domain } = useActiveDomain();
  const { colors } = useTheme();
  const overviewQuery = useQuery({ queryKey: ["job-overview", domain], queryFn: fetchJobOverview, refetchInterval: 5000 });

  const runNow = useMutation({
    mutationFn: (jobId: string) => runJobNow(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job-overview", domain] });
    },
  });

  const renderRunStrip = (runs: JobRun[] | undefined) => {
    const recent = (runs ?? []).slice(0, 10);
    if (!recent.length) return <Typography.Text type="secondary">No runs yet</Typography.Text>;
    const color = (status?: string) =>
      status === "success" ? colors.success : status === "running" ? colors.info : colors.warning;
    return (
      <Space size={6}>
        {recent.map((run, idx) => (
          <div
            key={run._id ?? idx}
            title={`${run.status} · ${run.start_ts ? new Date(run.start_ts).toLocaleString() : "n/a"}`}
            style={{
              width: 12,
              height: 12,
              borderRadius: 3,
              background: color(run.status),
              opacity: idx === 0 ? 1 : 0.7,
            }}
          />
        ))}
      </Space>
    );
  };

  const renderDurationSpark = (runs: JobRun[] | undefined) => {
    const durations = (runs ?? [])
      .map((r) => (typeof r.duration === "number" ? r.duration : null))
      .filter((d): d is number => d !== null);
    if (!durations.length) return <Typography.Text type="secondary">No duration data</Typography.Text>;
    const max = Math.max(...durations, 1);
    return (
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 40 }}>
        {durations.map((d, idx) => (
          <div
            key={`${d}-${idx}`}
            style={{
              width: 12,
              height: Math.max(6, (d / max) * 36),
              background: colors.primary,
              borderRadius: 4,
              opacity: 0.8,
            }}
            title={`~${d.toFixed(1)}s`}
          />
        ))}
      </div>
    );
  };

  return (
    <Card
      title="Job Status"
      extra={<Typography.Text type="secondary">Run health across all jobs. Use Operate to manage job definitions.</Typography.Text>}
    >
      <Table
        rowKey="job_id"
        loading={overviewQuery.isLoading}
        dataSource={overviewQuery.data ?? []}
        pagination={{ pageSize: 10 }}
        columns={[
          {
            title: "Job",
            dataIndex: "name",
            key: "name",
            render: (_: unknown, job) => {
              const last = job.last_run;
              return (
                <Space>
                  <Typography.Text strong>{job.name}</Typography.Text>
                  <Tag color="default">{job.schedule_mode === "immediate" ? "manual" : job.schedule_mode}</Tag>
                  {last && <StatusBadge status={last.status} />}
                </Space>
              );
            },
          },
          {
            title: "Success / Failed / Total / Queued",
            key: "counts",
            render: (_: unknown, job) => (
              <Space direction="vertical" size={4}>
                <div>
                  {job.success_runs} / {job.failed_runs} / {job.total_runs} / {job.queued_runs ?? 0}
                </div>
                <Progress
                  percent={job.total_runs ? Math.round((job.success_runs / job.total_runs) * 100) : 0}
                  size="small"
                  status="active"
                />
              </Space>
            ),
          },
          {
            title: "Recent Runs",
            key: "recent",
            render: (_: unknown, job) => renderRunStrip(job.recent_runs),
          },
          {
            title: "Durations",
            key: "durations",
            render: (_: unknown, job) => renderDurationSpark(job.recent_runs),
          },
          {
            title: "Last Run",
            key: "last",
            render: (_: unknown, job) => {
              const last = job.last_run as JobRun | undefined;
              if (!last) return "-";
              return (
                <Space direction="vertical" size={2}>
                  <div>{last.start_ts ? new Date(last.start_ts).toLocaleString() : "-"}</div>
                  {typeof last.duration === "number" && <div>{last.duration.toFixed(1)}s</div>}
                </Space>
              );
            },
          },
          {
            title: "",
            key: "actions",
            render: (_: unknown, job) => (
              <Button size="small" onClick={() => runNow.mutate(job.job_id)} loading={runNow.isPending}>
                Run Now
              </Button>
            ),
          },
        ]}
      />
    </Card>
  );
}

function HistoryTab() {
  const { domain } = useActiveDomain();
  const { data, isLoading } = useQuery({
    queryKey: ["history", domain],
    queryFn: fetchHistory,
    refetchInterval: 5000,
  });
  const [logModal, setLogModal] = useState<{ visible: boolean; run?: JobRun }>({ visible: false });

  const columns = [
    { title: "Job", dataIndex: "job_id", key: "job_id" },
    { title: "User", dataIndex: "user", key: "user" },
    { title: "Domain", dataIndex: "domain", key: "domain", render: (value?: string) => value ?? "prod" },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => <StatusBadge status={status} />,
    },
    { title: "Worker", dataIndex: "worker_id", key: "worker_id" },
    {
      title: "Started",
      dataIndex: "start_ts",
      key: "start_ts",
      render: (value?: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
    {
      title: "Finished",
      dataIndex: "end_ts",
      key: "end_ts",
      render: (value?: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
    {
      title: "Logs",
      key: "logs",
      render: (_: unknown, record: JobRun) => (
        <Typography.Link onClick={() => setLogModal({ visible: true, run: record })}>View Logs</Typography.Link>
      ),
    },
  ];

  const runs = (data ?? []).map((run) => ({ ...run, key: run._id }));

  return (
    <>
      <Card
        title="Run History"
        extra={<Typography.Text type="secondary">All runs across jobs. Click logs to inspect output.</Typography.Text>}
      >
        <Table dataSource={runs} columns={columns} loading={isLoading} size="small" pagination={{ pageSize: 10 }} />
      </Card>
      <Modal open={logModal.visible} onCancel={() => setLogModal({ visible: false })} footer={null} width={1000} title="Run Logs">
        {logModal.run ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <StatusBadge status={logModal.run.status} />
              <Typography.Text type="secondary">Run ID: {logModal.run._id}</Typography.Text>
              {logModal.run.worker_id && <Typography.Text type="secondary">Worker: {logModal.run.worker_id}</Typography.Text>}
            </Space>
            <Typography.Text>
              Started: {logModal.run.start_ts ? new Date(logModal.run.start_ts).toLocaleString() : "-"} · 
              Finished: {logModal.run.end_ts ? new Date(logModal.run.end_ts).toLocaleString() : "-"} · 
              Duration: {typeof logModal.run.duration === "number" ? `${logModal.run.duration.toFixed(1)}s` : "-"}
            </Typography.Text>
            <LogViewer
              stdout={logModal.run.stdout_tail ?? logModal.run.stdout}
              stderr={logModal.run.stderr_tail ?? logModal.run.stderr}
              maxHeight={400}
            />
            <FailureInsight
              runId={logModal.run._id}
              stdout={logModal.run.stdout || ""}
              stderr={logModal.run.stderr || ""}
              exitCode={logModal.run.returncode || 1}
            />
          </Space>
        ) : (
          <Typography.Text type="secondary">No logs available.</Typography.Text>
        )}
      </Modal>
    </>
  );
}

export function ObservePage() {
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Tabs
        defaultActiveKey="status"
        items={[
          {
            key: "status",
            label: (
              <span>
                <BarChartOutlined /> Status
              </span>
            ),
            children: <StatusTab />,
          },
          {
            key: "history",
            label: (
              <span>
                <HistoryOutlined /> History
              </span>
            ),
            children: <HistoryTab />,
          },
        ]}
      />
    </Space>
  );
}
