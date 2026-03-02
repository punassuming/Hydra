import { apiClient } from "./client";
import type { WorkerRedisAclInfo, CredentialPayload, CredentialRef } from "./admin";

export interface DomainSettings {
  domain: string;
  display_name?: string;
  description?: string;
  worker_redis_acl_user?: string;
}

export const fetchMyDomainSettings = () => apiClient.get<DomainSettings>("/domain/settings");
export const updateMyDomainSettings = (payload: Partial<DomainSettings>) =>
  apiClient.put<{ ok: boolean; domain: string; display_name?: string; description?: string }>("/domain/settings", payload);
export const rotateMyDomainToken = () =>
  apiClient.post<{ ok: boolean; domain: string; token: string }>("/domain/token/rotate", {});
export const rotateMyDomainWorkerRedisAcl = () =>
  apiClient.post<{ ok: boolean; domain: string; worker_redis_acl: WorkerRedisAclInfo }>("/domain/redis_acl/rotate", {});

export const fetchMyCredentials = () => apiClient.get<{ credentials: CredentialRef[] }>("/credentials/");
export const createMyCredential = (payload: CredentialPayload) =>
  apiClient.post<{ ok: boolean; name: string; domain: string }>("/credentials/", payload);
export const updateMyCredential = (name: string, payload: CredentialPayload) =>
  apiClient.put<{ ok: boolean; name: string; domain: string }>(`/credentials/${name}`, payload);
export const deleteMyCredential = (name: string) => apiClient.delete(`/credentials/${name}`);

