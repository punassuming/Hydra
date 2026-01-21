import { Tag } from "antd";
import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, ClockCircleOutlined } from "@ant-design/icons";

interface StatusBadgeProps {
  status: string;
  size?: "small" | "default" | "large";
}

export function StatusBadge({ status, size = "default" }: StatusBadgeProps) {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case "success":
        return { color: "success", icon: <CheckCircleOutlined />, text: "Success" };
      case "running":
        return { color: "processing", icon: <SyncOutlined spin />, text: "Running" };
      case "failed":
      case "error":
        return { color: "error", icon: <CloseCircleOutlined />, text: "Failed" };
      case "queued":
      case "pending":
        return { color: "default", icon: <ClockCircleOutlined />, text: "Queued" };
      default:
        return { color: "default", icon: null, text: status };
    }
  };

  const config = getStatusConfig(status);

  return (
    <Tag color={config.color} icon={config.icon} style={{ margin: 0 }}>
      {config.text}
    </Tag>
  );
}
