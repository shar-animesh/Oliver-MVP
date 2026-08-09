const BASE = "/api/v1";

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  createSubmission: (data) =>
    request("/submissions", { method: "POST", body: JSON.stringify(data) }),

  listSubmissions: () => request("/submissions"),

  getSubmission: (id) => request(`/submissions/${id}`),

  assess: (id) => request(`/assess/${id}`, { method: "POST" }),

  // Direct URL to the downloadable structured report (server sets attachment headers)
  reportUrl: (id) => `${BASE}/submissions/${id}/report`,

  cadence: (id) => request(`/submissions/${id}/cadence`),
  advance: (id) => request(`/submissions/${id}/advance`, { method: "POST" }),
  deliver: (id) => request(`/submissions/${id}/deliver`, { method: "POST" }),
  audit: () => request(`/audit`),
};
