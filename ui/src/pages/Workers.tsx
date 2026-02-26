import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Col, Row, Space, Statistic, Table, Tag, Tooltip, Typography, Button } from "antd";
import { fetchWorkers } from "../api/jobs";
import { WorkerInfo } from "../types";
import { apiClient } from "../api/client";
import { useNavigate } from "react-router-dom";
import { useActiveDomain } from "../context/ActiveDomainContext";

export function WorkersPage() {
  const queryClient = useQueryClient();
  const { domain } = useActiveDomain();
  const { data, isLoading } = useQuery({ queryKey: ["workers", domain], queryFn: fetchWorkers, refetchInterval: 5000 });
  const navigate = useNavigate();
  const setStateMutation = useMutation({
    mutationFn: ({ workerId, state }: { workerId: string; state: string }) =>
      apiClient.post(`/workers/${workerId}/state`, { state }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workers", domain] }),
  });

  const columns = [
    { title: "ID", dataIndex: "worker_id", key: "worker_id" },
    { title: "Domain", dataIndex: "domain", key: "domain" },
    { title: "Host", dataIndex: "hostname", key: "hostname" },
    { title: "IP", dataIndex: "ip", key: "ip" },
    { title: "OS", dataIndex: "os", key: "os" },
    { title: "Deploy", dataIndex: "deployment_type", key: "deployment_type" },
    { title: "Subnet", dataIndex: "subnet", key: "subnet" },
    {
      title: "Tags",
      dataIndex: "tags",
      key: "tags",
      render: (tags: string[]) => (tags?.length ? tags.map((tag) => <Tag key={tag}>{tag}</Tag>) : "-"),
    },
    {
      title: "Affinity Users",
      dataIndex: "allowed_users",
      key: "allowed_users",
      render: (users: string[]) => (users?.length ? users.join(", ") : "any"),
    },
    {
      title: "Runtime",
      key: "runtime",
      render: (_: unknown, record: WorkerInfo) => (
        <Space size={4} direction="vertical">
          <div>Python: {record.python_version ?? "-"}</div>
          <div>CPU: {record.cpu_count ?? "-"}</div>
          <div>User: {record.run_user ?? "-"}</div>
        </Space>
      ),
    },
    {
      title: "Memory (30m)",
      key: "memory",
      render: (_: unknown, record: WorkerInfo) => {
        const current = record.memory_rss_mb;
        const max30 = record.memory_rss_mb_max_30m;
        if (current == null && max30 == null) return "-";
        return (
          <Tooltip title={`Current ${current?.toFixed(1) ?? "-"} MB, 30m max ${max30?.toFixed(1) ?? "-"} MB`}>
            <div>
              {current?.toFixed(1) ?? "-"} MB
              {max30 != null ? ` / ${max30.toFixed(1)} MB max` : ""}
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: "Processes (30m)",
      key: "process_count",
      render: (_: unknown, record: WorkerInfo) => {
        const current = record.process_count;
        const max30 = record.process_count_max_30m;
        if (current == null && max30 == null) return "-";
        return (
          <Tooltip title={`Current ${current ?? "-"} processes, 30m max ${max30 ?? "-"}`}>
            <div>
              {current ?? "-"}
              {max30 != null ? ` / ${max30} max` : ""}
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: "Concurrency",
      key: "concurrency",
      render: (_: unknown, record: WorkerInfo) => (
        <Tooltip title={`Running ${record.current_running} of ${record.max_concurrency}`}>
          <div>
            {record.current_running}/{record.max_concurrency}
          </div>
        </Tooltip>
      ),
    },
    {
      title: "Last heartbeat",
      dataIndex: "last_heartbeat",
      key: "last_heartbeat",
      render: (value?: number) => (value ? new Date(value).toLocaleTimeString() : "-"),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => <Tag color={status === "online" ? "green" : "volcano"}>{status}</Tag>,
    },
    {
      title: "State",
      key: "state",
      render: (_: unknown, record: WorkerInfo) => (
        <Space>
          <Tag>{record.state ?? "online"}</Tag>
          <Button size="small" onClick={() => setStateMutation.mutate({ workerId: record.worker_id, state: "online" })}>
            Online
          </Button>
          <Button size="small" onClick={() => setStateMutation.mutate({ workerId: record.worker_id, state: "draining" })}>
            Drain
          </Button>
          <Button size="small" danger onClick={() => setStateMutation.mutate({ workerId: record.worker_id, state: "disabled" })}>
            Disable
          </Button>
        </Space>
      ),
    },
    {
      title: "Running Jobs",
      dataIndex: "running_jobs",
      key: "running_jobs",
      render: (jobs: string[]) => (jobs?.length ? jobs.length : 0),
    },
  ];
  const workers = data ?? [];
  const online = workers.filter((w) => w.status === "online").length;
  const totalCapacity = workers.reduce((sum, w) => sum + (w.max_concurrency ?? 0), 0);
  const running = workers.reduce((sum, w) => sum + (w.current_running ?? 0), 0);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        Worker Capabilities
      </Typography.Title>
      <Typography.Text type="secondary">
        Inspect deployments, advertised runtimes, and placement hints to design new affinities.
      </Typography.Text>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="Workers Online" value={online} suffix={`/ ${workers.length}`} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="Running Tasks" value={running} suffix={`/ ${totalCapacity}`} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="Unique Tags" value={new Set(workers.flatMap((w) => w.tags ?? [])).size} />
          </Card>
        </Col>
      </Row>
      <Card>
        <Table
          dataSource={workers.map((w) => ({ ...w, key: w.worker_id }))}
          columns={columns}
          loading={isLoading}
          pagination={{ pageSize: 10 }}
          size="small"
          onRow={(record) => ({
            onClick: () => navigate(`/workers/${record.worker_id}`),
            style: { cursor: "pointer" },
          })}
        />
      </Card>
    </Space>
  );
}
