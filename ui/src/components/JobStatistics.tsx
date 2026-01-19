import { useQuery } from "@tanstack/react-query";
import { fetchJobStatistics } from "../api/jobs";
import { Card, Statistic, Row, Col, Progress, Tag, Space } from "antd";
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined, 
  SyncOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  TagsOutlined
} from "@ant-design/icons";
import { useActiveDomain } from "../context/ActiveDomainContext";

export function JobStatistics() {
  const { domain } = useActiveDomain();
  const { data, isLoading } = useQuery({
    queryKey: ["job-statistics", domain],
    queryFn: fetchJobStatistics,
    refetchInterval: 10000,
  });

  if (isLoading || !data) {
    return <Card title="Statistics" loading={isLoading} bordered={false} />;
  }

  const successRate = data.success_rate.toFixed(1);
  const failureRate = data.total_runs > 0 ? ((data.failed_runs / data.total_runs) * 100).toFixed(1) : "0.0";

  return (
    <Card title="System Statistics" bordered={false}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Statistic
            title="Total Jobs"
            value={data.total_jobs}
            prefix={<ClockCircleOutlined />}
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Statistic
            title="Enabled Jobs"
            value={data.enabled_jobs}
            prefix={<PlayCircleOutlined style={{ color: "#52c41a" }} />}
            valueStyle={{ color: "#52c41a" }}
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Statistic
            title="Disabled Jobs"
            value={data.disabled_jobs}
            prefix={<PauseCircleOutlined />}
            valueStyle={{ color: "#999" }}
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Statistic
            title="Running Now"
            value={data.running_runs}
            prefix={<SyncOutlined spin={data.running_runs > 0} />}
            valueStyle={{ color: "#1890ff" }}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" title="Success Rate">
            <Progress
              type="circle"
              percent={parseFloat(successRate)}
              format={() => `${successRate}%`}
              strokeColor={{
                "0%": "#108ee9",
                "100%": "#87d068",
              }}
            />
            <div style={{ marginTop: 16, textAlign: "center" }}>
              <Space>
                <CheckCircleOutlined style={{ color: "#52c41a" }} />
                <span>{data.success_runs} successes</span>
              </Space>
              <br />
              <Space>
                <CloseCircleOutlined style={{ color: "#ff4d4f" }} />
                <span>{data.failed_runs} failures</span>
              </Space>
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card size="small" title="Schedule Types">
            <Statistic
              title="Cron Jobs"
              value={data.schedule_breakdown.cron}
              valueStyle={{ fontSize: 20 }}
            />
            <Statistic
              title="Interval Jobs"
              value={data.schedule_breakdown.interval}
              valueStyle={{ fontSize: 20 }}
            />
            <Statistic
              title="Immediate Jobs"
              value={data.schedule_breakdown.immediate}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} md={8}>
          <Card size="small" title="Available Tags">
            <div style={{ maxHeight: 200, overflowY: "auto" }}>
              {data.available_tags.length > 0 ? (
                <Space wrap>
                  {data.available_tags.map((tag) => (
                    <Tag key={tag} icon={<TagsOutlined />} color="blue">
                      {tag}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <span style={{ color: "#999" }}>No tags defined</span>
              )}
            </div>
          </Card>
        </Col>
      </Row>
    </Card>
  );
}
