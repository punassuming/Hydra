import { Button, Card, Table, Tag, Space, Segmented, Row, Col } from "antd";
import { Link } from "react-router-dom";
import { JobDefinition } from "../types";
import { JobCard } from "./JobCard";
import { useState } from "react";
import { AppstoreOutlined, UnorderedListOutlined } from "@ant-design/icons";

interface Props {
  jobs?: JobDefinition[];
  onSelect: (job: JobDefinition) => void;
  selectedId?: string | null;
  loading?: boolean;
  onEdit?: () => void;
  onRun?: (jobId: string) => void;
}

export function JobList({ jobs, onSelect, selectedId, loading, onEdit, onRun }: Props) {
  const [viewMode, setViewMode] = useState<"table" | "card">("table");
  
  const dataSource = (jobs ?? []).map((job) => ({ ...job, key: job._id }));
  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (_: unknown, record: JobDefinition) => <Link to={`/jobs/${record._id}`}>{record.name}</Link>,
    },
    { title: "Domain", dataIndex: "domain", key: "domain", render: (value?: string) => value ?? "prod" },
    { title: "User", dataIndex: "user", key: "user" },
    {
      title: "Executor",
      key: "executor",
      render: (_: unknown, record: JobDefinition) => <Tag color="geekblue">{record.executor.type}</Tag>,
    },
    { title: "Priority", dataIndex: "priority", key: "priority" },
    {
      title: "Schedule",
      key: "schedule",
      render: (_: unknown, record: JobDefinition) => (
        <div>
          <strong>{record.schedule.mode === "immediate" ? "manual" : record.schedule.mode}</strong>
          <br />
          <small>
            {!record.schedule.enabled
              ? "disabled"
              : record.schedule.next_run_at
                ? new Date(record.schedule.next_run_at).toLocaleString()
                : record.schedule.mode === "immediate"
                  ? "manual"
                  : "pending"}
          </small>
        </div>
      ),
    },
    { title: "Retries", dataIndex: "retries", key: "retries" },
    {
      title: "Updated",
      dataIndex: "updated_at",
      key: "updated_at",
      render: (value: string) => new Date(value).toLocaleString(),
    },
  ];

  return (
    <Card 
      title={
        <Space style={{ justifyContent: "space-between", width: "100%", flexWrap: "wrap" }}>
          <span>Jobs</span>
          <Segmented
            value={viewMode}
            onChange={(value) => setViewMode(value as "table" | "card")}
            options={[
              { label: "Table", value: "table", icon: <UnorderedListOutlined /> },
              { label: "Cards", value: "card", icon: <AppstoreOutlined /> },
            ]}
          />
        </Space>
      }
      bordered={false}
      loading={loading}
    >
      {viewMode === "table" ? (
        <Table
          dataSource={dataSource}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
          rowClassName={(record) => (record._id === selectedId ? "job-row-selected" : "job-row")}
          onRow={(record) => ({
            onClick: () => onSelect(record),
            onDoubleClick: () => {
              onSelect(record);
              onEdit?.();
            },
            style: { cursor: "pointer" },
          })}
          scroll={{ x: 800 }}
        />
      ) : (
        <Row gutter={[16, 16]}>
          {dataSource.map((job) => (
            <Col xs={24} sm={12} md={8} lg={6} key={job._id}>
              <div onClick={() => onSelect(job)}>
                <JobCard
                  job={job}
                  selected={job._id === selectedId}
                  onEdit={() => {
                    onSelect(job);
                    onEdit?.();
                  }}
                  onRun={() => {
                    onSelect(job);
                    onRun?.(job._id);
                  }}
                />
              </div>
            </Col>
          ))}
        </Row>
      )}
    </Card>
  );
}
