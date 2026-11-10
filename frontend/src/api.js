async function req(method, url, body, isForm = false) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body;
    else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  }
  const r = await fetch(url, opt);
  let data = null;
  try { data = await r.json(); } catch { /* 빈 응답 */ }
  if (!r.ok) {
    const d = data && data.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(", ") : `요청 실패 (${r.status})`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  meta: () => req("GET", "/api/meta"),
  market: (region, job) => req("GET", `/api/market?region=${region}&job=${job}`),
  digital: (region) => req("GET", `/api/digital?region=${region}`),
  supply: (region, job) => req("GET", `/api/supply?region=${region}&job=${job}`),
  skills: (region, job) => req("GET", `/api/skills?region=${region}&job=${job}`),
  quality: () => req("GET", "/api/quality"),
  personas: () => req("GET", "/api/personas"),
  diagnose: (body) => req("POST", "/api/diagnose", body),
  diagnosePdf: (file, companyId, hours) => {
    const f = new FormData();
    f.append("file", file); f.append("company_id", companyId); f.append("weekly_hours", String(hours));
    return req("POST", "/api/diagnose/pdf", f, true);
  },
  companies: () => req("GET", "/api/companies"),
  company: (id) => req("GET", `/api/companies/${id}`),
  putRequirements: (id, requirements) => req("PUT", `/api/companies/${id}/requirements`, { requirements }),
  putTracks: (id, tracks) => req("PUT", `/api/companies/${id}/tracks`, { tracks }),
  suggest: (id, text) => req("POST", `/api/companies/${id}/docs`, { text }),
  simulate: (id, requirements, assumeTracks) => req("POST", `/api/companies/${id}/simulate`, { requirements, assume_tracks: assumeTracks }),
  insights: (id) => req("GET", `/api/companies/${id}/insights`),
  reset: () => req("POST", "/api/reset"),
};
