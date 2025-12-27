const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type TokenMap = Record<string, string>;

const TOKEN_MAP_KEY = "hydra_token_map";
const ACTIVE_DOMAIN_KEY = "hydra_domain";

function readTokenMap(): TokenMap {
  try {
    const raw = localStorage.getItem(TOKEN_MAP_KEY);
    return raw ? (JSON.parse(raw) as TokenMap) : {};
  } catch {
    return {};
  }
}

function writeTokenMap(map: TokenMap) {
  localStorage.setItem(TOKEN_MAP_KEY, JSON.stringify(map));
}

export function setTokenForDomain(domain: string, token: string) {
  const map = readTokenMap();
  map[domain] = token;
  writeTokenMap(map);
}

export function getTokenForDomain(domain: string): string | undefined {
  return readTokenMap()[domain];
}

export function hasTokenForDomain(domain: string): boolean {
  return Boolean(getTokenForDomain(domain));
}

export function getAdminToken(): string | undefined {
  return readTokenMap()["admin"];
}

export function hasAnyToken(): boolean {
  const map = readTokenMap();
  return Object.keys(map).length > 0;
}

export function forgetToken(domain?: string) {
  if (!domain) {
    localStorage.removeItem(TOKEN_MAP_KEY);
    return;
  }
  const map = readTokenMap();
  delete map[domain];
  writeTokenMap(map);
}

export function setActiveDomain(domain: string) {
  localStorage.setItem(ACTIVE_DOMAIN_KEY, domain);
}

export function getActiveDomain(): string {
  return localStorage.getItem(ACTIVE_DOMAIN_KEY) || "prod";
}

type TokenContext =
  | { token: string; activeDomain: string; source: "domain" | "admin" }
  | { token?: undefined; activeDomain: string; source: "none" };

export function getTokenContext(domain?: string): TokenContext {
  const map = readTokenMap();
  const activeDomain = domain || getActiveDomain();
  if (map[activeDomain]) {
    return { token: map[activeDomain], activeDomain, source: "domain" };
  }
  if (map["admin"]) {
    return { token: map["admin"], activeDomain, source: "admin" };
  }
  return { activeDomain, source: "none" };
}

export function getEffectiveToken(domain?: string): string | undefined {
  return getTokenContext(domain).token;
}

export function withTempToken<T>(token: string | undefined, fn: () => Promise<T>): Promise<T> {
  const currentDomain = getActiveDomain();
  const map = readTokenMap();
  const prev = map[currentDomain];
  if (token) {
    map[currentDomain] = token;
    writeTokenMap(map);
  }
  return fn().finally(() => {
    if (prev) {
      setTokenForDomain(currentDomain, prev);
    }
  });
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail ?? res.statusText);
  }
  return res.json();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const { token, activeDomain, source } = getTokenContext();
  if (token) {
    headers.set("x-api-key", token);
  }
  const url = new URL(path, API_BASE);
  if (source === "admin" && !url.searchParams.has("domain")) {
    url.searchParams.set("domain", activeDomain);
  }
  const res = await fetch(url.toString(), { ...init, headers });
  return handleResponse<T>(res);
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  delete: <T>(path: string) =>
    request<T>(path, {
      method: "DELETE",
    }),
};

export const streamUrl = () => {
  const { token, activeDomain, source } = getTokenContext();
  const url = new URL("/events/stream", API_BASE);
  if (token) {
    url.searchParams.set("token", token);
  }
  if (source === "admin" && !url.searchParams.has("domain")) {
    url.searchParams.set("domain", activeDomain);
  }
  return url.toString();
};
export const runStreamUrl = (runId: string) => {
  const { token, activeDomain, source } = getTokenContext();
  const url = new URL(`/runs/${runId}/stream`, API_BASE);
  if (token) {
    url.searchParams.set("token", token);
  }
  if (source === "admin" && !url.searchParams.has("domain")) {
    url.searchParams.set("domain", activeDomain);
  }
  return url.toString();
};
