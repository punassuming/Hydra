import { Alert, Button, Select, Space, Spin, Typography } from "antd";
import { BugOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useState } from "react";
import { analyzeRun } from "../api/jobs";

interface FailureInsightProps {
  runId: string;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
  compact?: boolean;
}

export function FailureInsight({
  runId,
  stdout = "",
  stderr = "",
  exitCode = 1,
  compact = false,
}: FailureInsightProps) {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [provider, setProvider] = useState<"gemini" | "openai">("gemini");

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const res = await analyzeRun({
        run_id: runId,
        stdout,
        stderr,
        exit_code: exitCode,
        provider,
      });
      setAnalysis(res.analysis);
    } catch (e) {
      console.error(e);
      setAnalysis("Failed to analyze. Please try again.");
    } finally {
      setAnalyzing(false);
    }
  };

  if (analysis) {
    return (
      <Alert
        message={
          <Space>
            <BugOutlined />
            AI Failure Analysis ({provider.toUpperCase()})
          </Space>
        }
        description={
          <div>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: "13px",
                margin: 0,
              }}
            >
              {analysis}
            </pre>
            <Button
              type="link"
              size="small"
              onClick={() => setAnalysis(null)}
              style={{ paddingLeft: 0 }}
            >
              Clear Analysis
            </Button>
          </div>
        }
        type="warning"
        showIcon
        closable
        onClose={() => setAnalysis(null)}
        style={{ marginTop: 12 }}
      />
    );
  }

  return (
    <div style={{ marginTop: 12 }}>
      <Space>
        {!compact && (
          <Select
            value={provider}
            onChange={setProvider}
            options={[
              { label: "Gemini", value: "gemini" },
              { label: "OpenAI", value: "openai" },
            ]}
            style={{ width: 100 }}
          />
        )}
        <Button
          onClick={handleAnalyze}
          loading={analyzing}
          danger
          icon={analyzing ? <Spin size="small" /> : <ThunderboltOutlined />}
        >
          {analyzing ? "Analyzing..." : compact ? "Analyze" : "Analyze Failure"}
        </Button>
      </Space>
    </div>
  );
}
