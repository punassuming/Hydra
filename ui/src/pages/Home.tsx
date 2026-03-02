import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Row, Col, Card, Typography, Space, Button, Modal, Divider, Tabs } from "antd";
import { JobForm } from "../components/JobForm";
import { JobList } from "../components/JobList";
import { JobRuns } from "../components/JobRuns";
import { EventsFeed } from "../components/EventsFeed";
import { JobOverview } from "../components/JobOverview";
import { JobStatistics } from "../components/JobStatistics";
import { useSchedulerEvents } from "../hooks/useEvents";
import { createJob, fetchJobs, JobPayload, runAdhocJob, runJobNow, updateJob, validateJob } from "../api/jobs";
import { WorkersMini } from "../components/WorkersMini";
import { useActiveDomain } from "../context/ActiveDomainContext";
import { JobsDashboard } from "../components/JobsDashboard";
import { DashboardOutlined, UnorderedListOutlined } from "@ant-design/icons";

export function HomePage() {
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>();
  const [validating, setValidating] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const events = useSchedulerEvents();
  const { domain } = useActiveDomain();
  useEffect(() => {
    setSelectedJobId(null);
    setStatusMessage(undefined);
  }, [domain]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", domain],
    queryFn: () => fetchJobs(),
    refetchInterval: 5000,
  });

  const jobs = jobsQuery.data ?? [];
  const selectedJob = jobs.find((j) => j._id === selectedJobId);

  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", domain] });
      setSelectedJobId(data._id);
      setStatusMessage("Job created and queued");
      setModalVisible(false);
    },
    onError: (err: Error) => setStatusMessage(err.message),
  });

  const updateMutation = useMutation({
    mutationFn: (payload: JobPayload) => updateJob(selectedJobId!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs", domain] });
      setStatusMessage("Job updated");
      setModalVisible(false);
    },
    onError: (err: Error) => setStatusMessage(err.message),
  });

  const manualRunMutation = useMutation({
    mutationFn: (jobId: string) => runJobNow(jobId),
    onSuccess: () => setStatusMessage("Manual run queued"),
    onError: (err: Error) => setStatusMessage(err.message),
  });

  const adhocMutation = useMutation({
    mutationFn: runAdhocJob,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", domain] });
      setSelectedJobId(data._id);
      setStatusMessage("Adhoc job queued");
      setModalVisible(false);
    },
    onError: (err: Error) => setStatusMessage(err.message),
  });

  const handleSubmit = (payload: JobPayload) => {
    setStatusMessage("Saving job…");
    if (selectedJobId) {
      updateMutation.mutate(payload);
    } else {
      createMutation.mutate(payload);
    }
  };

  const handleValidate = async (payload: JobPayload) => {
    setValidating(true);
    setStatusMessage("Validating…");
    try {
      const result = await validateJob(payload);
      if (result.valid) {
        const next = result.next_run_at ? ` – next run ${new Date(result.next_run_at).toLocaleString()}` : "";
        setStatusMessage(`Validation passed${next}`);
      } else {
        setStatusMessage(result.errors.join(", "));
      }
      return result;
    } catch (err) {
      setStatusMessage((err as Error).message);
      return undefined;
    } finally {
      setValidating(false);
    }
  };

  const handleManualRun = () => {
    if (selectedJobId) {
      manualRunMutation.mutate(selectedJobId);
    }
  };

  const handleAdhocRun = (payload: JobPayload) => {
    setStatusMessage(undefined);
    adhocMutation.mutate(payload);
  };

  const resetSelection = () => {
    setSelectedJobId(null);
    setStatusMessage(undefined);
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Row justify="space-between" align="middle" gutter={[16, 16]}>
          <Col xs={24} md={16}>
            <Typography.Title level={3} style={{ marginBottom: 8 }}>
              Hydra Jobs Control Plane
            </Typography.Title>
            <Typography.Text type="secondary">
              Submit, schedule, and inspect jobs across heterogeneous workers with queue/affinity aware placement.
            </Typography.Text>
          </Col>
          <Col xs={24} md={8} style={{ textAlign: "right" }}>
            <Space wrap>
              <Button type="primary" onClick={() => setModalVisible(true)}>
                New Job
              </Button>
              <Button disabled={!selectedJob} onClick={() => setModalVisible(true)}>
                Edit Selected
              </Button>
              {selectedJob && (
                <Button onClick={handleManualRun}>Run Selected</Button>
              )}
            </Space>
          </Col>
        </Row>
        {statusMessage && (
          <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0 }}>{statusMessage}</Typography.Paragraph>
        )}
      </Card>

      <Tabs
        defaultActiveKey="dashboard"
        items={[
          {
            key: "dashboard",
            label: (
              <span>
                <DashboardOutlined /> Dashboard
              </span>
            ),
            children: <JobsDashboard />,
          },
          {
            key: "jobs",
            label: (
              <span>
                <UnorderedListOutlined /> Jobs List
              </span>
            ),
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Card id="job-list" title="Jobs">
                  <JobList
                    jobs={jobs}
                    loading={jobsQuery.isLoading}
                    selectedId={selectedJobId}
                    onSelect={(job) => setSelectedJobId(job._id)}
                    onEdit={() => setModalVisible(true)}
                  />
                </Card>

                <JobStatistics />

                <JobOverview />

                <WorkersMini />
              </Space>
            ),
          },
        ]}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card id="job-history" title="Job History">
            <JobRuns jobId={selectedJobId} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card id="events" title="Events">
            <EventsFeed events={events} />
          </Card>
        </Col>
      </Row>

      <Modal
        title={selectedJob ? `Edit Job – ${selectedJob.name}` : "Create Job"}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          resetSelection();
        }}
        footer={null}
        width={980}
        destroyOnClose
      >
        <JobForm
          selectedJob={selectedJob}
          onSubmit={handleSubmit}
          onValidate={handleValidate}
          onManualRun={handleManualRun}
          onAdhocRun={handleAdhocRun}
          submitting={createMutation.isPending || updateMutation.isPending}
          validating={validating}
          statusMessage={statusMessage}
          onReset={resetSelection}
          onCancel={() => {
            setModalVisible(false);
            resetSelection();
          }}
        />
        <Divider />
        <Typography.Text type="secondary">
          Jobs are persisted immediately. Closing this dialog will not discard saved changes.
        </Typography.Text>
      </Modal>
    </Space>
  );
}
