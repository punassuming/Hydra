import { useQuery } from "@tanstack/react-query";
import { Button, Card, Drawer, Row, Col, Tag, Spin, Typography, Space, Empty } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { fetchTemplates, JobPayload } from "../api/jobs";

const { Text, Title } = Typography;

const EXECUTOR_LABEL: Record<string, string> = {
  shell: "Shell",
  python: "Python",
  sql: "SQL",
  external: "External",
  http: "HTTP",
  sensor: "Sensor",
  batch: "Batch",
  powershell: "PowerShell",
};

const SCHEDULE_LABEL: Record<string, string> = {
  immediate: "Manual",
  cron: "Cron",
  interval: "Interval",
};

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (template: Partial<JobPayload>) => void;
}

export function TemplateDrawer({ open, onClose, onSelect }: Props) {
  const { data: templates, isLoading } = useQuery({
    queryKey: ["job-templates"],
    queryFn: fetchTemplates,
    staleTime: 60_000,
    enabled: open,
  });

  return (
    <Drawer
      title={
        <Space>
          <ThunderboltOutlined />
          <span>Start from Template</span>
        </Space>
      }
      placement="right"
      width={640}
      open={open}
      onClose={onClose}
    >
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        Choose a template to pre-populate the job form. You can customize every field before saving.
      </Text>

      {isLoading && (
        <div style={{ textAlign: "center", padding: 32 }}>
          <Spin size="large" />
        </div>
      )}

      {!isLoading && (!templates || templates.length === 0) && (
        <Empty description="No templates available" />
      )}

      <Row gutter={[12, 12]}>
        {(templates ?? []).map((tpl: any) => {
          const execType: string = tpl.executor?.type ?? "shell";
          const schedMode: string = tpl.schedule?.mode ?? "immediate";
          return (
            <Col xs={24} sm={12} key={tpl.id ?? tpl.name}>
              <Card
                size="small"
                hoverable
                style={{ height: "100%" }}
                actions={[
                  <Button
                    key="use"
                    type="link"
                    size="small"
                    onClick={() => {
                      const { id: _id, ...payload } = tpl as any;
                      onSelect(payload as Partial<JobPayload>);
                      onClose();
                    }}
                  >
                    Use template
                  </Button>,
                ]}
              >
                <Title level={5} style={{ marginBottom: 4, marginTop: 0 }}>
                  {tpl.name}
                </Title>
                <Space size={4} wrap style={{ marginBottom: 6 }}>
                  <Tag color="blue">{EXECUTOR_LABEL[execType] ?? execType}</Tag>
                  <Tag color="geekblue">{SCHEDULE_LABEL[schedMode] ?? schedMode}</Tag>
                  {tpl.schedule?.cron && <Tag color="cyan">{tpl.schedule.cron}</Tag>}
                  {(tpl.affinity?.tags ?? []).map((t: string) => (
                    <Tag key={t}>{t}</Tag>
                  ))}
                </Space>
                {tpl.executor?.script && (
                  <Text
                    type="secondary"
                    style={{ fontSize: 11, display: "block", fontFamily: "monospace", whiteSpace: "pre-wrap", wordBreak: "break-all" }}
                  >
                    {String(tpl.executor.script).slice(0, 80)}{String(tpl.executor.script).length > 80 ? "…" : ""}
                  </Text>
                )}
                {tpl.executor?.code && (
                  <Text
                    type="secondary"
                    style={{ fontSize: 11, display: "block", fontFamily: "monospace", whiteSpace: "pre-wrap", wordBreak: "break-all" }}
                  >
                    {String(tpl.executor.code).slice(0, 80)}{String(tpl.executor.code).length > 80 ? "…" : ""}
                  </Text>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
    </Drawer>
  );
}
