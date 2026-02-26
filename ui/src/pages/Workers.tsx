import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, Col, Progress, Row, Space, Statistic, Table, Tag, Tooltip, Typography, Button } from "antd";
import { fetchWorkers } from "../api/jobs";
import { WorkerInfo } from "../types";
import { apiClient } from "../api/client";
import { useNavigate } from "react-router-dom";
import { useActiveDomain } from "../context/ActiveDomainContext";

function connectivityTag(status?: string) {
  const normalized = status === "online" ? "online" : "offline";
  return <Tag color={normalized === "online" ? "green" : "volcano"}>{normalized}</Tag>;
}

function dispatchTag(state?: string) {
  const normalized = state === "draining" ? "draining" : state === "online" ? "online" : "offline";
  const color = normalized === "online" ? "green" : normalized === "draining" ? "gold" : "default";
  return <Tag color={color}>{normalized}</Tag>;
}

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
      title: "Running Users",
      dataIndex: "running_users",
      key: "running_users",
      render: (users: string[]) => (users?.length ? users.join(", ") : "-"),
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
      title: "Load",
      key: "load",
      render: (_: unknown, record: WorkerInfo) => (
        <Tooltip title={`1m ${record.load_1m ?? "-"}, 5m ${record.load_5m ?? "-"}`}>
          <div>{record.load_1m != null ? `${record.load_1m.toFixed(2)}` : "-"} / {record.load_5m != null ? record.load_5m.toFixed(2) : "-"}</div>
        </Tooltip>
      ),
    },
    {
      title: "Saturation",
      key: "concurrency",
      render: (_: unknown, record: WorkerInfo) => {
        const max = Math.max(record.max_concurrency ?? 1, 1);
        const runningCount = record.current_running ?? 0;
        const percent = Math.round((runningCount / max) * 100);
        return (
        <Tooltip title={`Running ${runningCount} of ${max}${runningCount > max ? " (over quota via bypass jobs)" : ""}`}>
          <div>
            <div style={{ marginBottom: 4 }}>
              {runningCount}/{max}
            </div>
            <Progress
              percent={Math.min(percent, 100)}
              size="small"
              status={runningCount > max ? "exception" : "active"}
              showInfo={false}
            />
          </div>
        </Tooltip>
      )},
    },
    {
      title: "Last heartbeat",
      dataIndex: "last_heartbeat",
      key: "last_heartbeat",
      render: (value?: number) => (value ? new Date(value * 1000).toLocaleTimeString() : "-"),
    },
    {
      title: "Connectivity",
      key: "status",
      render: (_: unknown, record: WorkerInfo) => connectivityTag(record.connectivity_status ?? record.status),
    },
    {
      title: "Dispatch",
      key: "state",
      render: (_: unknown, record: WorkerInfo) => (
        <Space>
          {dispatchTag(record.dispatch_status ?? record.state)}
          <Button size="small" onClick={(e) => { e.stopPropagation(); setStateMutation.mutate({ workerId: record.worker_id, state: "online" }); }}>
            Online
          </Button>
          <Button size="small" onClick={(e) => { e.stopPropagation(); setStateMutation.mutate({ workerId: record.worker_id, state: "draining" }); }}>
            Drain
          </Button>
          <Button size="small" onClick={(e) => { e.stopPropagation(); setStateMutation.mutate({ workerId: record.worker_id, state: "offline" }); }}>
            Offline
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
  const online = workers.filter((w) => (w.connectivity_status ?? w.status) === "online").length;
  const totalCapacity = workers.reduce((sum, w) => sum + (w.max_concurrency ?? 0), 0);
  const running = workers.reduce((sum, w) => sum + (w.current_running ?? 0), 0);
  const avgMemory = workers.length
    ? workers.reduce((sum, w) => sum + (w.memory_rss_mb ?? 0), 0) / workers.length
    : 0;
  const avgLoad1m = workers.length
    ? workers.reduce((sum, w) => sum + (w.load_1m ?? 0), 0) / workers.length
    : 0;
  const overQuotaWorkers = workers.filter((w) => (w.current_running ?? 0) > (w.max_concurrency ?? 0)).length;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        Worker Capabilities
      </Typography.Title>
      <Typography.Text type="secondary">
        Inspect deployments, advertised runtimes, and placement hints to design new affinities.
      </Typography.Text>
      <Row gutter={16}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Workers Online" value={online} suffix={`/ ${workers.length}`} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Running Tasks" value={running} suffix={`/ ${totalCapacity}`} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Avg Memory RSS" value={avgMemory.toFixed(1)} suffix="MB" />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Avg Load (1m)" value={avgLoad1m.toFixed(2)} suffix={`| ${overQuotaWorkers} over quota`} />
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
