import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJobOverview } from "../api/jobs";
import { Card, Table, Tag, Modal, Typography, Space, Tooltip } from "antd";
import { JobOverview as JobOverviewType } from "../types";
import { Link } from "react-router-dom";
import { useActiveDomain } from "../context/ActiveDomainContext";
import { LogViewer } from "./LogViewer";
import { FailureInsight } from "./FailureInsight";

export function JobOverview() {
  const { domain } = useActiveDomain();
  const { data, isLoading } = useQuery({
    queryKey: ["job-overview", domain],
    queryFn: fetchJobOverview,
    refetchInterval: 5000,
  });

  const [logModal, setLogModal] = useState<{ visible: boolean; run?: JobOverviewType["last_run"]; jobName?: string }>({
    visible: false,
  });

  const rows = useMemo(
    () => (data ?? []).map((item) => ({ ...item, key: item.job_id })),
    [data],
  );

  const columns = [
    {
      title: "Job",
      dataIndex: "name",
      key: "name",
      render: (_: unknown, record: JobOverviewType) => <Link to={`/jobs/${record.job_id}`}>{record.name}</Link>,
    },
    {
      title: "Tags",
      dataIndex: "tags",
      key: "tags",
      render: (tags: string[]) => (
        <>
          {tags && tags.length > 0 ? (
            tags.map((tag) => <Tag key={tag} color="blue">{tag}</Tag>)
          ) : (
            <Typography.Text type="secondary">-</Typography.Text>
          )}
        </>
      ),
    },
    {
      title: "Schedule",
      dataIndex: "schedule_mode",
      key: "schedule_mode",
      render: (mode: string) => <Tag>{mode}</Tag>,
    },
    { title: "Total Runs", dataIndex: "total_runs", key: "total_runs" },
    {
      title: "Success",
      dataIndex: "success_runs",
      key: "success_runs",
      render: (value: number, record: JobOverviewType) => (
        <Typography.Text type={value > 0 ? "success" : undefined}>{value}</Typography.Text>
      ),
    },
    {
      title: "Failed",
      dataIndex: "failed_runs",
      key: "failed_runs",
      render: (value: number, record: JobOverviewType) => (
        <Tooltip title={record.last_failure_reason || "No recent failures"}>
          <Typography.Text type={value > 0 ? "danger" : undefined}>{value}</Typography.Text>
        </Tooltip>
      ),
    },
    { title: "Queued", dataIndex: "queued_runs", key: "queued_runs" },
    {
      title: "Avg Duration",
      dataIndex: "avg_duration_seconds",
      key: "avg_duration_seconds",
      render: (duration: number | null) => {
        if (!duration) return "-";
        if (duration < 60) return `${duration.toFixed(1)}s`;
        if (duration < 3600) return `${(duration / 60).toFixed(1)}m`;
        return `${(duration / 3600).toFixed(1)}h`;
      },
    },
    {
      title: "Last Run",
      key: "last_run",
      render: (_: unknown, record: JobOverviewType) =>
        record.last_run ? new Date(record.last_run.start_ts || record.last_run.scheduled_ts || "").toLocaleString() : "-",
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, record: JobOverviewType) => (
        <Typography.Link
          onClick={() =>
            setLogModal({
              visible: true,
              run: record.last_run,
              jobName: record.name,
            })
          }
          disabled={!record.last_run}
        >
          View Logs
        </Typography.Link>
      ),
    },
  ];

  return (
    <>
      <Card title="Job Overview" bordered={false}>
        <Table dataSource={rows} columns={columns} loading={isLoading} pagination={{ pageSize: 10 }} size="small" />
      </Card>
      <Modal
        open={logModal.visible}
        title={`Logs - ${logModal.jobName ?? ""}`}
        onCancel={() => setLogModal({ visible: false })}
        footer={null}
        width={800}
      >
        {logModal.run ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text strong>Status: {logModal.run.status}</Typography.Text>
            <LogViewer
              stdout={logModal.run.stdout_tail ?? logModal.run.stdout ?? ""}
              stderr={logModal.run.stderr_tail ?? logModal.run.stderr ?? ""}
              maxHeight={360}
            />
            <FailureInsight
              runId={logModal.run._id}
              stdout={logModal.run.stdout ?? ""}
              stderr={logModal.run.stderr ?? ""}
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
