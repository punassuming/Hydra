import { useMemo, useState } from "react";
import { Typography, Space, Tabs, Input, Button, Segmented, Table, Tag, Tooltip, message } from "antd";
import { CodeOutlined, BugOutlined, SearchOutlined, CopyOutlined, ExpandOutlined, CompressOutlined } from "@ant-design/icons";
import { useTheme } from "../theme";

interface LogViewerProps {
  stdout?: string;
  stderr?: string;
  maxHeight?: number;
  showTabs?: boolean;
}

interface ParsedLogLine {
  line: number;
  timestamp?: string;
  level?: string;
  message: string;
  fields?: string;
  raw: string;
}

const LEVEL_COLORS: Record<string, string> = {
  trace: "default",
  debug: "processing",
  info: "success",
  warn: "warning",
  warning: "warning",
  error: "error",
  fatal: "error",
  critical: "error",
};

function escapeRegExp(input: string) {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderHighlighted(text: string, query: string) {
  if (!query) return text;
  const regex = new RegExp(`(${escapeRegExp(query)})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, idx) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <mark key={`${part}-${idx}`} style={{ padding: 0, background: "#fde68a", color: "#111827" }}>
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function parseLogLine(raw: string, line: number): ParsedLogLine {
  const trimmed = raw.trim();
  if (!trimmed) return { line, message: "", raw };

  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      const timestamp =
        String(parsed.timestamp ?? parsed.ts ?? parsed.time ?? parsed["@timestamp"] ?? "") || undefined;
      const level = String(parsed.level ?? parsed.severity ?? parsed.log_level ?? "") || undefined;
      const message = String(parsed.message ?? parsed.msg ?? parsed.event ?? parsed.text ?? trimmed);
      const fields = Object.entries(parsed)
        .filter(([k]) => !["timestamp", "ts", "time", "@timestamp", "level", "severity", "log_level", "message", "msg", "event", "text"].includes(k))
        .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
        .join(" ");
      return { line, timestamp, level, message, fields: fields || undefined, raw };
    } catch {
      // fall back to plain parsing
    }
  }

  const tsLevelPattern =
    /^\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+([A-Za-z]+)\s+(.*)$/;
  const tsMatch = raw.match(tsLevelPattern);
  if (tsMatch) {
    return {
      line,
      timestamp: tsMatch[1],
      level: tsMatch[2],
      message: tsMatch[3],
      raw,
    };
  }

  const levelPattern = /^\s*\[?(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\]?\s*[:|-]?\s*(.*)$/i;
  const lvlMatch = raw.match(levelPattern);
  if (lvlMatch) {
    return {
      line,
      level: lvlMatch[1],
      message: lvlMatch[2] || raw,
      raw,
    };
  }

  return { line, message: raw, raw };
}

function LogPane({
  title,
  text,
  maxHeight,
  background,
}: {
  title: string;
  text?: string;
  maxHeight: number;
  background: string;
}) {
  const { colors } = useTheme();
  const [messageApi, contextHolder] = message.useMessage();
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [viewMode, setViewMode] = useState<"raw" | "parsed">("raw");

  const parsed = useMemo(() => {
    const lines = (text ?? "").split(/\r?\n/);
    const parsedLines = lines.map((line, idx) => parseLogLine(line, idx + 1));
    if (!search.trim()) return parsedLines;
    const q = search.toLowerCase();
    return parsedLines.filter((row) => row.raw.toLowerCase().includes(q));
  }, [text, search]);

  const filteredRawText = useMemo(() => parsed.map((p) => p.raw).join("\n"), [parsed]);
  const effectiveMaxHeight = expanded ? 640 : maxHeight;

  const logStyle: React.CSSProperties = {
    background,
    color: colors.logText,
    padding: 16,
    borderRadius: 6,
    border: `1px solid ${colors.borderLight}`,
    maxHeight: effectiveMaxHeight,
    overflow: "auto",
    fontFamily: "'SFMono-Regular', 'Consolas', 'Menlo', monospace",
    fontSize: "13px",
    lineHeight: "1.55",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  };

  const copyText = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      messageApi.success(`Copied ${label}`);
    } catch {
      messageApi.error(`Could not copy ${label}`);
    }
  };

  const parsedColumns = [
    {
      title: "#",
      dataIndex: "line",
      key: "line",
      width: 70,
      render: (value: number) => <Typography.Text type="secondary">{value}</Typography.Text>,
    },
    {
      title: "Time",
      dataIndex: "timestamp",
      key: "timestamp",
      width: 220,
      render: (value?: string) => <Typography.Text>{value || "-"}</Typography.Text>,
    },
    {
      title: "Level",
      dataIndex: "level",
      key: "level",
      width: 110,
      render: (value?: string) =>
        value ? <Tag color={LEVEL_COLORS[value.toLowerCase()] || "default"}>{value.toUpperCase()}</Tag> : <Typography.Text>-</Typography.Text>,
    },
    {
      title: "Message",
      dataIndex: "message",
      key: "message",
      render: (value: string) => (
        <Typography.Text style={{ fontFamily: "'SFMono-Regular', 'Consolas', 'Menlo', monospace" }}>
          {renderHighlighted(value, search)}
        </Typography.Text>
      ),
    },
    {
      title: "Fields",
      dataIndex: "fields",
      key: "fields",
      render: (value?: string) =>
        value ? (
          <Tooltip title={value}>
            <Typography.Text ellipsis style={{ maxWidth: 260, display: "inline-block" }}>
              {renderHighlighted(value, search)}
            </Typography.Text>
          </Tooltip>
        ) : (
          "-"
        ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size={10}>
      {contextHolder}
      <Space wrap style={{ width: "100%", justifyContent: "space-between", display: "flex" }}>
        <Typography.Text strong>{title}</Typography.Text>
        <Space wrap>
          <Input
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs"
            prefix={<SearchOutlined />}
            style={{ width: 220 }}
          />
          <Segmented
            size="small"
            options={[
              { label: "Raw", value: "raw" },
              { label: "Parsed", value: "parsed" },
            ]}
            value={viewMode}
            onChange={(value) => setViewMode(value as "raw" | "parsed")}
          />
          <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(text || "", `${title.toLowerCase()} log`)}>
            Copy
          </Button>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copyText(filteredRawText, `${title.toLowerCase()} filtered log`)}
            disabled={!search.trim()}
          >
            Copy Filtered
          </Button>
          <Button
            size="small"
            icon={expanded ? <CompressOutlined /> : <ExpandOutlined />}
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? "Collapse" : "Expand"}
          </Button>
        </Space>
      </Space>
      {viewMode === "parsed" ? (
        <Table
          rowKey="line"
          dataSource={parsed}
          columns={parsedColumns}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ y: effectiveMaxHeight }}
          expandable={{
            expandedRowRender: (record: ParsedLogLine) => (
              <pre style={{ ...logStyle, margin: 0, maxHeight: 180, overflow: "auto" }}>{record.raw || "(empty line)"}</pre>
            ),
            rowExpandable: () => true,
          }}
        />
      ) : (
        <div style={logStyle}>
          {(parsed.length ? parsed : [{ line: 1, message: "(no output)", raw: "(no output)" }]).map((row) => (
            <div key={row.line}>
              <Typography.Text style={{ color: colors.logText, fontFamily: "'SFMono-Regular', 'Consolas', 'Menlo', monospace" }}>
                {renderHighlighted(row.raw, search)}
              </Typography.Text>
            </div>
          ))}
        </div>
      )}
    </Space>
  );
}

export function LogViewer({ stdout, stderr, maxHeight = 300, showTabs = true }: LogViewerProps) {
  const { colors } = useTheme();

  if (!showTabs) {
    return (
      <Space direction="vertical" style={{ width: "100%" }}>
        {stdout && (
          <LogPane title="Standard Output" text={stdout || "(no output)"} maxHeight={maxHeight} background={colors.logBg} />
        )}
        {stderr && (
          <LogPane title="Standard Error" text={stderr || "(no errors)"} maxHeight={maxHeight} background={colors.logErrorBg} />
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
      children: <LogPane title="Standard Output" text={stdout || "(no output)"} maxHeight={maxHeight} background={colors.logBg} />,
    },
    {
      key: "stderr",
      label: (
        <span>
          <BugOutlined /> Errors
        </span>
      ),
      children: <LogPane title="Standard Error" text={stderr || "(no errors)"} maxHeight={maxHeight} background={colors.logErrorBg} />,
    },
  ];

  return <Tabs defaultActiveKey="stdout" items={items} tabBarStyle={{ marginBottom: 8 }} />;
}
