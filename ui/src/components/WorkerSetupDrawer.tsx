import { useState } from "react";
import { Button, Drawer, Radio, Space, Steps, Tag, Tooltip, Typography, Alert, Divider } from "antd";
import { CopyOutlined, CheckOutlined } from "@ant-design/icons";
import { useActiveDomain } from "../context/ActiveDomainContext";

const { Text, Paragraph, Title } = Typography;

type DeploymentMode = "docker" | "bare" | "windows" | "kubernetes";

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    if (!navigator.clipboard) {
      setCopied(false);
      return;
    }
    navigator.clipboard.writeText(code).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => {
        // Clipboard write failed (non-secure context, denied permission, etc.)
        // No-op — the user can still select and copy the text manually.
      }
    );
  };
  return (
    <div style={{ position: "relative", marginBottom: 8 }}>
      <pre
        style={{
          background: "rgba(0,0,0,0.06)",
          border: "1px solid rgba(0,0,0,0.1)",
          borderRadius: 6,
          padding: "10px 12px",
          paddingRight: 40,
          fontSize: 12,
          overflowX: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          margin: 0,
        }}
      >
        {code}
      </pre>
      <Tooltip title={copied ? "Copied!" : "Copy to clipboard"}>
        <Button
          size="small"
          aria-label="Copy command to clipboard"
          icon={copied ? <CheckOutlined /> : <CopyOutlined />}
          onClick={handleCopy}
          style={{ position: "absolute", top: 6, right: 6, opacity: 0.7 }}
        />
      </Tooltip>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  redisUrl?: string;
}

export function WorkerSetupDrawer({ open, onClose, redisUrl }: Props) {
  const { domain } = useActiveDomain();
  const [mode, setMode] = useState<DeploymentMode>("docker");

  const effectiveRedisUrl = redisUrl || "redis://<redis-host>:6379/0";
  const apiBase = (window as Window & { __HYDRA_API_BASE__?: string }).__HYDRA_API_BASE__ ||
    (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL ||
    "http://localhost:8000";

  const rotateAclCommand = `# Rotate token + Redis ACL credentials (run once, requires ADMIN_TOKEN)
ADMIN_TOKEN=<your-admin-token> ./scripts/start-domain-workers.sh ${domain || "prod"} 1`;

  const dockerCommand =
    `DOMAIN=${domain || "prod"} \\
API_TOKEN=<your-domain-token> \\
REDIS_PASSWORD=<your-redis-acl-password> \\
REDIS_URL=${effectiveRedisUrl} \\
docker compose -f docker-compose.worker.yml up -d --build --scale worker=2`;

  const bareCommand =
    `export DOMAIN=${domain || "prod"}
export API_TOKEN=<your-domain-token>
export REDIS_PASSWORD=<your-redis-acl-password>
export REDIS_URL=${effectiveRedisUrl}
python -m worker`;

  const windowsCommand =
    `# 1. Create runtime directory
New-Item -ItemType Directory -Force C:\\hydra-worker
New-Item -ItemType Directory -Force C:\\hydra-worker\\logs

# 2. Install worker
cd C:\\hydra-worker
uv venv .venv
uv pip install -e C:\\path\\to\\hydra

# 3. Write .env file
@"
DOMAIN=${domain || "prod"}
API_TOKEN=<your-domain-token>
REDIS_URL=${effectiveRedisUrl}
REDIS_PASSWORD=<your-redis-acl-password>
HYDRA_BOOTSTRAP_WORKING_DIR=C:\\hydra-worker
HYDRA_BOOTSTRAP_LOG_FILE=C:\\hydra-worker\\logs\\worker.log
PYTHONUNBUFFERED=1
"@ | Set-Content C:\\hydra-worker\\.env

# 4. Validate and install Task Scheduler watchdog
.venv\\Scripts\\python.exe -m worker bootstrap validate
.venv\\Scripts\\python.exe -m worker bootstrap install`;

  const k8sCommand =
    `# Create K8s secret and scale workers
WORKER_BACKEND=k8s \\
K8S_NAMESPACE=hydra \\
K8S_DEPLOYMENT=hydra-worker \\
ADMIN_TOKEN=<your-admin-token> \\
./scripts/start-domain-workers.sh ${domain || "prod"} 3`;

  const commandMap: Record<DeploymentMode, string> = {
    docker: dockerCommand,
    bare: bareCommand,
    windows: windowsCommand,
    kubernetes: k8sCommand,
  };

  return (
    <Drawer
      title="Connect a Worker"
      placement="right"
      width={600}
      open={open}
      onClose={onClose}
    >
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <div>
          <Title level={5} style={{ marginBottom: 4 }}>Step 1 — Get credentials</Title>
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            Workers need a domain token and Redis ACL password to connect. Use the
            script below (or go to <strong>Admin → Domains → Rotate ACL</strong>) to
            generate fresh credentials:
          </Paragraph>
          <CodeBlock code={rotateAclCommand} />
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 8 }}
            message={
              <span>
                Or rotate manually via the API:{" "}
                <Text code>POST {apiBase}/admin/domains/{domain || "prod"}/redis_acl/rotate</Text>
              </span>
            }
          />
        </div>

        <Divider style={{ margin: "4px 0" }} />

        <div>
          <Title level={5} style={{ marginBottom: 8 }}>Step 2 — Choose deployment mode</Title>
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value as DeploymentMode)}
            optionType="button"
            buttonStyle="solid"
            style={{ marginBottom: 16 }}
          >
            <Radio.Button value="docker">Docker</Radio.Button>
            <Radio.Button value="bare">Bare-metal / VM</Radio.Button>
            <Radio.Button value="windows">Windows</Radio.Button>
            <Radio.Button value="kubernetes">Kubernetes</Radio.Button>
          </Radio.Group>

          <CodeBlock code={commandMap[mode]} />

          {mode === "docker" && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              Add <Tag>--scale worker=N</Tag> to run N workers in parallel.
              Workers auto-restart on crash (<Text code>restart: unless-stopped</Text>).
            </Text>
          )}
          {mode === "bare" && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              Use a process supervisor (systemd, supervisord) to keep the worker alive.
              Set <Tag>WORKER_ID</Tag> to a unique value when running multiple workers on the same host.
            </Text>
          )}
          {mode === "windows" && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              The bootstrap installs a Task Scheduler watchdog that restarts the worker automatically.
              See <Text code>docs/windows-worker-bootstrap.md</Text> for a full guide.
            </Text>
          )}
          {mode === "kubernetes" && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              The script creates a K8s Secret and scales the Deployment.
              Manifests are in <Text code>deploy/k8s/worker-deployment.yaml</Text>.
            </Text>
          )}
        </div>

        <Divider style={{ margin: "4px 0" }} />

        <div>
          <Title level={5} style={{ marginBottom: 8 }}>Step 3 — Verify</Title>
          <Steps
            direction="vertical"
            size="small"
            items={[
              {
                title: "Worker comes online",
                description: "The worker should appear in this table within ~5 seconds of starting.",
                status: "process",
              },
              {
                title: "Connectivity status is green",
                description: "Check the Connectivity column — it turns green once the heartbeat is received.",
                status: "wait",
              },
              {
                title: "Run a test job",
                description: "Use Operate → New Job to dispatch a quick shell job to confirm end-to-end execution.",
                status: "wait",
              },
            ]}
          />
        </div>
      </Space>
    </Drawer>
  );
}
