import { apiClient } from "./client";

export interface DomainInfo {
  domain: string;
  display_name?: string;
  description?: string;
  token?: string;
  worker_redis_acl_user?: string;
  jobs_count?: number;
  runs_count?: number;
  workers_count?: number;
}

export interface WorkerRedisAclInfo {
  username: string;
  password: string;
  domain: string;
  keys: string[];
  channels: string[];
}

export const fetchDomains = () => apiClient.get<{ domains: DomainInfo[] }>("/admin/domains");
export const createDomain = (payload: DomainInfo) =>
  apiClient.post<DomainInfo & { worker_redis_acl?: WorkerRedisAclInfo }>("/admin/domains", payload);
export const updateDomain = (domain: string, payload: Partial<DomainInfo>) =>
  apiClient.put(`/admin/domains/${domain}`, payload);
export const rotateDomainToken = (domain: string) => apiClient.post<{ ok: boolean; domain: string; token: string }>(`/admin/domains/${domain}/token`, {});
export const rotateDomainWorkerRedisAcl = (domain: string) =>
  apiClient.post<{ ok: boolean; domain: string; worker_redis_acl: WorkerRedisAclInfo }>(
    `/admin/domains/${domain}/redis_acl/rotate`,
    {},
  );
export const deleteDomain = (domain: string) => apiClient.delete(`/admin/domains/${domain}`);
export const fetchTemplates = () => apiClient.get<{ templates: any[] }>("/admin/job_templates");
export const importTemplate = (templateId: string) => apiClient.post(`/admin/job_templates/${templateId}/import`, {});
