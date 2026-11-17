// 방문자 샌드박스 ID: 기업 콘솔에서 바꾼 기준은 이 방문자에게만 보인다 (24시간 유지).
// 저장이 막힌 브라우저면 이 페이지를 연 동안만 쓰는 ID로 동작한다.
const SANDBOX = (() => {
  const make = () => "v-" + Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");
  try {
    let id = localStorage.getItem("sandbox");
    if (!id || !/^[A-Za-z0-9_-]{8,40}$/.test(id)) { id = make(); localStorage.setItem("sandbox", id); }
    return id;
  } catch { return make(); }
})();

// 시연 키: 발표자는 주소 뒤에 ?demo=키 를 한 번 붙여 열면 이 브라우저에 저장되고 주소에서는 지워진다.
// 키가 없는 공개 방문자는 규칙 엔진으로 돈다 (Bedrock 비용 0).
const DEMO = (() => {
  try {
    const u = new URL(location.href), k = u.searchParams.get("demo");
    if (k !== null) {
      if (k) localStorage.setItem("demoKey", k); else localStorage.removeItem("demoKey");
      u.searchParams.delete("demo"); history.replaceState(null, "", u.toString());
    }
    return localStorage.getItem("demoKey") || "";
  } catch { return ""; }
})();

async function req(method, url, body, isForm = false) {
  const opt = { method, headers: { "X-Sandbox": SANDBOX } };
  if (DEMO) opt.headers["X-Demo-Key"] = DEMO;
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
  diagnosePdf: (file, companyId, hours, custom) => {
    const f = new FormData();
    f.append("file", file); f.append("company_id", companyId); f.append("weekly_hours", String(hours));
    if (custom) { f.append("custom_name", custom.name); f.append("custom_family", custom.job_family); f.append("custom_posting", custom.posting_text); }
    return req("POST", "/api/diagnose/pdf", f, true);
  },
  companies: (all = false) => req("GET", `/api/companies${all ? "?all=1" : ""}`),
  company: (id) => req("GET", `/api/companies/${id}`),
  putRequirements: (id, requirements) => req("PUT", `/api/companies/${id}/requirements`, { requirements }),
  putTracks: (id, tracks) => req("PUT", `/api/companies/${id}/tracks`, { tracks }),
  suggest: (id, text) => req("POST", `/api/companies/${id}/docs`, { text }),
  simulate: (id, requirements, assumeTracks) => req("POST", `/api/companies/${id}/simulate`, { requirements, assume_tracks: assumeTracks }),
  insights: (id) => req("GET", `/api/companies/${id}/insights`),
  reset: () => req("POST", "/api/reset"),
  families: () => req("GET", "/api/families"),
  analyze: (body) => req("POST", "/api/analyze", body),
  analyzePdf: (file, family, posting) => {
    const f = new FormData();
    f.append("file", file); f.append("job_family", family || "auto");
    if (posting) f.append("posting", posting);
    return req("POST", "/api/analyze/pdf", f, true);
  },
  job: (id) => req("GET", `/api/jobs/${encodeURIComponent(id)}`),
  coach: (companyId, question, statuses) => req("POST", "/api/coach", { company_id: companyId, question, statuses }),
};
