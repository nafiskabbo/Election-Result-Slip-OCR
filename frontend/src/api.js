const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export function apiUrl(path = "") {
  if (!path) return API_BASE;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${suffix}`;
}

const jsonHeaders = { "Content-Type": "application/json" };

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(apiUrl(path), { credentials: "omit", ...options });
  } catch {
    const hint = API_BASE
      ? `Cannot reach the API at ${API_BASE}. Confirm the Render service is live.`
      : "Cannot reach the API. On Vercel, set VITE_API_URL to your Render URL and redeploy.";
    throw new Error(hint);
  }
  const contentType = res.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = body?.detail || body?.message || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

export const api = {
  health: () => request("/api/health"),
  currentUser: () => request("/api/auth/current"),
  switchRole: (role) => request("/api/auth/switch", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ role }),
  }),
  listSlips: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const suffix = query.toString() ? `?${query}` : "";
    return request(`/api/slips${suffix}`);
  },
  getSlip: (id) => request(`/api/slips/${id}`),
  updateField: (id, field_name, new_value, reason) => request(`/api/slips/${id}/field`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify({ field_name, new_value, reason }),
  }),
  updateParty: (id, party_result_id, votes, reason) => request(`/api/slips/${id}/party`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify({ party_result_id, votes, reason }),
  }),
  approve: (id) => request(`/api/slips/${id}/approve`, { method: "POST" }),
  reject: (id, reason) => request(`/api/slips/${id}/reject`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ status: "rejected", reason }),
  }),
  flag: (id, reason) => request(`/api/slips/${id}/flag`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ status: "flagged", reason }),
  }),
  clearSlips: () => request("/api/slips", { method: "DELETE" }),
  upload: (files) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request("/api/upload", { method: "POST", body: form });
  },
  samplePacks: () => request("/api/upload/samples"),
  loadPack: (packId) => request(`/api/upload/samples/${packId}`, { method: "POST" }),
  rules: () => request("/api/rules"),
  updateRule: (code, payload) => request(`/api/rules/${code}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  evaluate: (id) => request(`/api/rules/evaluate/${id}`, { method: "POST" }),
  audit: (limit = 100) => request(`/api/audit?limit=${limit}`),
  slipAudit: (id) => request(`/api/audit/slip/${id}`),
  linkPage: (page_id, target_slip_id, reason) => request("/api/linking/link", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ page_id, target_slip_id, reason }),
  }),
  unlinkPage: (page_id, reason) => request("/api/linking/unlink", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ page_id, reason }),
  }),
};

export function fileUrl(path) {
  if (!path) return "";
  return apiUrl(path);
}

export function statusLabel(status) {
  return (status || "").replaceAll("_", " ");
}
