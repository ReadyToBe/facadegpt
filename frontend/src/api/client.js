export const API_ORIGIN = import.meta.env.VITE_API_ORIGIN || (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);
const API_BASE = `${API_ORIGIN}/api`;
const USER_ID_STORAGE_KEY = "facadegpt.localUserId";
let cachedUserId = "";

function createLocalUserId() {
  if (globalThis.crypto?.randomUUID) return `local:${globalThis.crypto.randomUUID()}`;
  const random = Math.random().toString(36).slice(2);
  return `local:${Date.now().toString(36)}-${random}`;
}

export function getFacadeGPTUserId() {
  if (cachedUserId) return cachedUserId;
  try {
    const stored = window.localStorage.getItem(USER_ID_STORAGE_KEY);
    if (stored) {
      cachedUserId = stored;
      return cachedUserId;
    }
    cachedUserId = createLocalUserId();
    window.localStorage.setItem(USER_ID_STORAGE_KEY, cachedUserId);
    return cachedUserId;
  } catch {
    cachedUserId = createLocalUserId();
    return cachedUserId;
  }
}

export function assetUrl(url) {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  return `${API_ORIGIN}${url}`;
}

async function request(path, options = {}) {
  const { headers, ...fetchOptions } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      "X-FacadeGPT-User-Id": getFacadeGPTUserId(),
      ...(headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await res.text();
    throw new Error(`Expected JSON from API but received ${contentType || "an unknown content type"}: ${text.slice(0, 120)}`);
  }
  return res.json();
}

export const api = {
  listProjects: () => request("/projects"),
  createProject: (name) => request("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  deleteProject: (id) => request(`/projects/${id}`, { method: "DELETE" }),
  getProject: (id) => request(`/projects/${id}`),
  getProjectMessages: (id) => request(`/projects/${id}/messages`),
  chatProject: (id, message) => request(`/projects/${id}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  getProjectSchemes: (id) => request(`/projects/${id}/schemes`),
  parseDemand: (id, natural_language) => request(`/projects/${id}/parse-demand`, { method: "POST", body: JSON.stringify({ natural_language }) }),
  updateWeights: (id, weights) => request(`/projects/${id}/weights`, { method: "PUT", body: JSON.stringify(weights) }),
  generateSchemes: (id, payload) => request(`/projects/${id}/generate-schemes`, { method: "POST", body: JSON.stringify(payload) }),
  getScheme: (id) => request(`/schemes/${id}`),
  deleteScheme: (id) => request(`/schemes/${id}`, { method: "DELETE" }),
  getFeedback: (id) => request(`/schemes/${id}/teaching-feedback`),
  getSchemeRenders: (id) => request(`/schemes/${id}/renders`),
  getViews: () => request("/render/view-options"),
  getRenderStyles: () => request("/render/style-options"),
  renderScheme: (id, payload) => request(`/schemes/${id}/render`, { method: "POST", body: JSON.stringify(payload) }),
  getLab: () => request("/lab"),
  evaluateLab: (params, orientation = "南") => request("/lab/evaluate", { method: "POST", body: JSON.stringify({ params, orientation }) }),
  getKnowledgeStatus: () => request("/knowledge/status"),
  rebuildKnowledge: () => request("/knowledge/rebuild", { method: "POST", body: JSON.stringify({ use_api_embeddings: true }) }),
};
