import { apiClient } from "./client";
import {
  JobDefinition,
  JobRun,
  WorkerInfo,
  ScheduleConfig,
  CompletionCriteria,
  JobOverview,
  JobGridData,
  JobGanttData,
  JobGraphData,
} from "../types";

export interface JobPayload {
  name: string;
  user: string;
  priority: number;
  affinity: JobDefinition["affinity"];
  executor: JobDefinition["executor"];
  retries: number;
  timeout: number;
  schedule: ScheduleConfig;
  completion: CompletionCriteria;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  next_run_at?: string | null;
}

export const fetchJobs = () => apiClient.get<JobDefinition[]>("/jobs/");
export const fetchJob = (jobId: string) => apiClient.get<JobDefinition>(`/jobs/${jobId}`);
export const fetchWorkers = () => apiClient.get<WorkerInfo[]>("/workers/");
export const fetchWorker = (workerId: string) => apiClient.get<WorkerInfo>(`/workers/${workerId}`);
export const fetchJobRuns = (jobId: string) => apiClient.get<JobRun[]>(`/jobs/${jobId}/runs`);
export const fetchJobOverview = () => apiClient.get<JobOverview[]>("/overview/jobs");
export const fetchHistory = () => apiClient.get<JobRun[]>("/history/");
export const fetchJobGrid = (jobId: string) => apiClient.get<JobGridData>(`/jobs/${jobId}/grid`);
export const fetchJobGantt = (jobId: string) => apiClient.get<JobGanttData>(`/jobs/${jobId}/gantt`);
export const fetchJobGraph = (jobId: string) => apiClient.get<JobGraphData>(`/jobs/${jobId}/graph`);
export const createJob = (payload: JobPayload) => apiClient.post<JobDefinition>("/jobs/", payload);
export const updateJob = (jobId: string, payload: Partial<JobPayload>) =>
  apiClient.put<JobDefinition>(`/jobs/${jobId}`, payload);
export const patchJob = (jobId: string, payload: Partial<JobPayload>) =>
  apiClient.patch<JobDefinition>(`/jobs/${jobId}`, payload);
export const deleteJob = (jobId: string) => apiClient.delete<{ ok: boolean; job_id: string }>(`/jobs/${jobId}`);
export const pauseJob = (jobId: string) => apiClient.post<{ ok: boolean; job_id: string; status: string }>(`/jobs/${jobId}/pause`, {});
export const resumeJob = (jobId: string) => apiClient.post<{ ok: boolean; job_id: string; status: string }>(`/jobs/${jobId}/resume`, {});
export const validateJob = (payload: JobPayload) => apiClient.post<ValidationResult>("/jobs/validate", payload);
export const validateJobById = (jobId: string) => apiClient.post<ValidationResult>(`/jobs/${jobId}/validate`, {});
export const runJobNow = (jobId: string) => apiClient.post<{ job_id: string; queued: boolean }>(`/jobs/${jobId}/run`, {});
export const runAdhocJob = (payload: JobPayload) => apiClient.post<JobDefinition>("/jobs/adhoc", payload);
export const createJobsBulk = (payload: JobPayload[]) => apiClient.post<JobDefinition[]>("/jobs/bulk", payload);

export const fetchRuns = (params?: { job_id?: string; status?: string; limit?: number; skip?: number }) => {
  const query = new URLSearchParams();
  if (params?.job_id) query.append("job_id", params.job_id);
  if (params?.status) query.append("status", params.status);
  if (params?.limit) query.append("limit", params.limit.toString());
  if (params?.skip) query.append("skip", params.skip.toString());
  return apiClient.get<{ runs: JobRun[]; total: number; limit: number; skip: number }>(`/runs/?${query.toString()}`);
};
export const fetchRun = (runId: string) => apiClient.get<JobRun>(`/runs/${runId}`);
export const deleteRun = (runId: string) => apiClient.delete<{ ok: boolean; run_id: string }>(`/runs/${runId}`);

export const fetchStatsOverview = () => apiClient.get<{
  domains: Array<{
    domain: string;
    jobs_count: number;
    runs_count: number;
    success_count: number;
    failed_count: number;
    running_count: number;
    workers_count: number;
    pending_count: number;
    active_jobs: number;
  }>;
  total_jobs: number;
  total_runs: number;
  total_workers: number;
  total_pending: number;
  total_running: number;
}>("/stats/overview");

export const generateJob = (prompt: string, provider: "gemini" | "openai" = "gemini", model?: string) => 
    apiClient.post<JobPayload>("/ai/generate_job", { prompt, provider, model });

export const analyzeRun = (payload: { run_id: string; stdout: string; stderr: string; exit_code: number; provider?: "gemini" | "openai"; model?: string }) => 
    apiClient.post<{ analysis: string }>("/ai/analyze_run", { provider: "gemini", ...payload });



