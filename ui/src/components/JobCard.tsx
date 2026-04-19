import { Card, Space, Typography, Tag, Button, Tooltip } from "antd";
import { Link } from "react-router-dom";
import {
  PlayCircleOutlined,
  EditOutlined,
  CopyOutlined,
  ClockCircleOutlined,
  UserOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { JobDefinition } from "../types";
import { StatusBadge } from "./StatusBadge";
import { useTheme } from "../theme";

interface JobCardProps {
  job: JobDefinition;
  onRun?: () => void;
  onEdit?: () => void;
  onClone?: () => void;
  selected?: boolean;
  compact?: boolean;
}

export function JobCard({ job, onRun, onEdit, onClone, selected, compact = false }: JobCardProps) {
  const { colors } = useTheme();
  const nextRun = job.schedule?.next_run_at
    ? new Date(job.schedule.next_run_at).toLocaleString()
    : job.schedule?.mode === "immediate"
      ? "Manual"
      : "N/A";

  return (
    <Card
      hoverable
      style={{
        borderColor: selected ? colors.info : undefined,
        borderWidth: selected ? 2 : 1,
      }}
      bodyStyle={{ padding: compact ? 16 : 24 }}
      actions={
        compact
          ? undefined
          : [
              <Tooltip title="Run Now" key="run">
                <PlayCircleOutlined onClick={onRun} />
              </Tooltip>,
              <Tooltip title="Edit" key="edit">
                <EditOutlined onClick={onEdit} />
              </Tooltip>,
              <Tooltip title="Duplicate" key="clone">
                <CopyOutlined onClick={onClone} />
              </Tooltip>,
            ]
      }
    >
      <Space direction="vertical" size="small" style={{ width: "100%" }}>
        <Space style={{ justifyContent: "space-between", width: "100%" }}>
          <Link to={`/jobs/${job._id}`}>
            <Typography.Text strong style={{ fontSize: 16 }}>
              {job.name}
            </Typography.Text>
          </Link>
          {job.schedule?.enabled === false && <Tag color="warning">Disabled</Tag>}
        </Space>

        {!compact && (
          <>
            <Space size="small" wrap>
              <Tag icon={<ThunderboltOutlined />} color="blue">
                {job.executor.type}
              </Tag>
              <Tag color="geekblue">Priority: {job.priority}</Tag>
              {job.user && (
                <Tag icon={<UserOutlined />} color="default">
                  {job.user}
                </Tag>
              )}
            </Space>

            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <ClockCircleOutlined /> Schedule: {job.schedule?.mode === "immediate" ? "manual" : job.schedule?.mode}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Next Run: {nextRun}
              </Typography.Text>
            </Space>

            {job.affinity && Object.keys(job.affinity).length > 0 && (
              <div>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Affinity: {JSON.stringify(job.affinity)}
                </Typography.Text>
              </div>
            )}
          </>
        )}
      </Space>
    </Card>
  );
}
