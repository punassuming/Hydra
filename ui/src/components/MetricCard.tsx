import { Card, Statistic, Space, Tooltip } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  value: number | string;
  prefix?: ReactNode;
  suffix?: ReactNode;
  tooltip?: string;
  loading?: boolean;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  valueStyle?: React.CSSProperties;
}

export function MetricCard({
  title,
  value,
  prefix,
  suffix,
  tooltip,
  loading,
  trend,
  valueStyle,
}: MetricCardProps) {
  return (
    <Card loading={loading} hoverable style={{ height: "100%" }}>
      <Space direction="vertical" size="small" style={{ width: "100%" }}>
        <Space>
          {title}
          {tooltip && (
            <Tooltip title={tooltip}>
              <InfoCircleOutlined style={{ color: "#999" }} />
            </Tooltip>
          )}
        </Space>
        <Statistic
          value={value}
          prefix={prefix}
          suffix={suffix}
          valueStyle={valueStyle}
        />
        {trend && (
          <div style={{ fontSize: "12px", color: trend.isPositive ? "#52c41a" : "#f5222d" }}>
            {trend.isPositive ? "↑" : "↓"} {Math.abs(trend.value)}%
          </div>
        )}
      </Space>
    </Card>
  );
}
