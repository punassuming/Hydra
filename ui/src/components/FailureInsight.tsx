import { Alert, Button, Input, Select, Space, Spin, Typography } from "antd";
import { BugOutlined, ThunderboltOutlined, QuestionCircleOutlined } from "@ant-design/icons";
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
  const [analysisType, setAnalysisType] = useState<"failure" | "summary" | "errors" | "retry" | "custom">("failure");
  const [question, setQuestion] = useState("");

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const res = await analyzeRun({
        run_id: runId,
        stdout,
        stderr,
        exit_code: exitCode,
        provider,
        analysis_type: analysisType,
        question: analysisType === "custom" ? question : undefined,
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
            AI Log Assistant ({provider.toUpperCase()} · {analysisType})
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
      <Space direction="vertical" style={{ width: "100%" }} size={8}>
        <Space wrap>
          <Select
            value={provider}
            onChange={setProvider}
            options={[
              { label: "Gemini", value: "gemini" },
              { label: "OpenAI", value: "openai" },
            ]}
            style={{ width: 110 }}
          />
          <Select
            value={analysisType}
            onChange={(value) => setAnalysisType(value)}
            options={[
              { label: "Fix Failure", value: "failure" },
              { label: "Summarize", value: "summary" },
              { label: "Extract Errors", value: "errors" },
              { label: "Retry Tuning", value: "retry" },
              { label: "Custom", value: "custom" },
            ]}
            style={{ width: compact ? 150 : 190 }}
          />
          {analysisType === "custom" && (
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              prefix={<QuestionCircleOutlined />}
              placeholder="Ask about this run"
              style={{ width: compact ? 220 : 340 }}
            />
          )}
        </Space>
        <Button
          onClick={handleAnalyze}
          loading={analyzing}
          icon={analyzing ? <Spin size="small" /> : <ThunderboltOutlined />}
        >
          {analyzing ? "Analyzing..." : compact ? "Analyze Logs" : "Run AI Log Analysis"}
        </Button>
        {!compact && (
          <Typography.Text type="secondary">
            Use this assistant to summarize logs, extract root errors, and suggest retry/timeout tuning.
          </Typography.Text>
        )}
      </Space>
    </div>
  );
}
