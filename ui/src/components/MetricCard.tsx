import { Card, Statistic, Space, Tooltip } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import { ReactNode } from "react";
import { useTheme } from "../theme";

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
  const { colors } = useTheme();
  
  return (
    <Card loading={loading} hoverable style={{ height: "100%" }}>
      <Space direction="vertical" size="small" style={{ width: "100%" }}>
        <Space>
          {title}
          {tooltip && (
            <Tooltip title={tooltip}>
              <InfoCircleOutlined style={{ color: colors.textDisabled }} />
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
          <div style={{ fontSize: "12px", color: trend.isPositive ? colors.success : colors.error }}>
            {trend.isPositive ? "↑" : "↓"} {Math.abs(trend.value)}%
          </div>
        )}
      </Space>
    </Card>
  );
}
