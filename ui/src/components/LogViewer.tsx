import { Typography, Space, Divider, Tabs } from "antd";
import { CodeOutlined, BugOutlined } from "@ant-design/icons";

interface LogViewerProps {
  stdout?: string;
  stderr?: string;
  maxHeight?: number;
  showTabs?: boolean;
}

export function LogViewer({ stdout, stderr, maxHeight = 300, showTabs = true }: LogViewerProps) {
  const logStyle: React.CSSProperties = {
    background: "#1e1e1e",
    color: "#d4d4d4",
    padding: 16,
    borderRadius: 6,
    maxHeight,
    overflow: "auto",
    fontFamily: "'Courier New', monospace",
    fontSize: "13px",
    lineHeight: "1.6",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  };

  if (!showTabs) {
    return (
      <Space direction="vertical" style={{ width: "100%" }}>
        {stdout && (
          <>
            <Typography.Text strong>
              <CodeOutlined /> Standard Output
            </Typography.Text>
            <pre style={logStyle}>{stdout || "(no output)"}</pre>
          </>
        )}
        {stderr && (
          <>
            <Typography.Text strong type="danger">
              <BugOutlined /> Standard Error
            </Typography.Text>
            <pre style={{ ...logStyle, background: "#2e1e1e" }}>
              {stderr || "(no errors)"}
            </pre>
          </>
        )}
      </Space>
    );
  }

  const items = [
    {
      key: "stdout",
      label: (
        <span>
          <CodeOutlined /> Output
        </span>
      ),
      children: <pre style={logStyle}>{stdout || "(no output)"}</pre>,
    },
    {
      key: "stderr",
      label: (
        <span>
          <BugOutlined /> Errors
        </span>
      ),
      children: (
        <pre style={{ ...logStyle, background: "#2e1e1e" }}>
          {stderr || "(no errors)"}
        </pre>
      ),
    },
  ];

  return <Tabs defaultActiveKey="stdout" items={items} />;
}
