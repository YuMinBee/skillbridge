// 역량 분석 (T4 · docs/pivot/T4_FRONTEND.md). 자기소개서·포트폴리오 PDF → job 접수 → 진행 상태 → ① 강점(STAR) ② 갭 ③ 추천 → 근거 → 비용.
// job_id는 localStorage에 둔다: 탭을 닫았다 열어도 서버에서 끝난 결과를 이어서 본다.
// (글 붙여 넣기·STAR 템플릿 입력은 2026-11-17 화면에서 내림. API(/api/analyze)는 남아 있음)
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { Seg, StatusChip } from "../ui.jsx";
import { SAMPLE, SAMPLE_NAME } from "../sample.js";
import { Award, FileDown, GraduationCap, LayoutDashboard, ListChecks, LogOut, RotateCcw, Route, ShieldCheck, Target } from "lucide-react";

// 왼쪽 바 메뉴 아이콘 (lucide-react)
const ICON = { overview: LayoutDashboard, path: Route, strengths: Award, gaps: Target, recos: ListChecks, courses: GraduationCap, log: ShieldCheck };

const STAGE = {
  collect: "GitHub 읽기", guard: "개인정보 가리기", star: "① 강점 진단 (STAR)", skills: "스킬 추출", retriever: "② 역량 기준 찾기",
  recommend: "③ 과제 추천", verifier: "근거 검증", cost: "비용 계산",
};
const SLOT = [["S", "상황"], ["T", "과제"], ["A", "행동"], ["R", "결과"]];
const LEVEL = { strong: ["강점", "st-own"], ok: ["보통", "st-part"], weak: ["약함", "st-miss"] };
const KIND = { resume: "내 문서", posting: "공고", posting_stats: "공고 집계", course: "고용24 과정", ncs_unit: "NCS 능력단위", ncs_basic: "NCS 직업기초능력" };
const KEY = "analyzeJob";

// 주소의 ?job=j_xxxx 가 있으면 그 결과를 연다(결과 공유·발표 캡처용). 없으면 이 브라우저의 마지막 분석
const load = () => {
  try {
    const q = new URLSearchParams(location.search).get("job");
    if (q && /^j_[0-9a-f]{12}$/.test(q)) return q;
    return localStorage.getItem(KEY) || "";
  } catch { return ""; }
};
const save = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* noop */ } };
const usd = (v) => (v == null ? "—" : `$${v.toFixed(v < 0.01 ? 4 : 3)}`);

// 단계마다 실제로 한 일 한 줄. 값은 supervisor.run()의 stage 행(progress)에 이미 남아 있다. 값이 없으면 표시하지 않는다
const said = (p) => {
  if (p.status !== "done") return null;
  switch (p.agent) {
    case "collect": return p.repos ? `공개 레포 ${p.repos.length}개 README 읽음` : null;
    // 정규식 가림은 접수 때 끝나서 여기 수(masked)에 안 들어간다(supervisor guard 단계 주석)
    case "guard": return p.masked != null ? `접수 때 정규식으로 1차 가림 · 이 단계에서 ${p.masked}곳 더 가림` : null;
    case "star": return p.mode === "bedrock" ? `Claude가 경험을 STAR로 나눔 · 원문에 없는 인용 ${p.dropped_quotes ?? 0}개 버림`
      : p.mode ? "규칙 엔진으로 STAR 나눔" : null;
    case "skills": return p.n_skills != null ? `내 문서에서 스킬 ${p.n_skills}개 인식` : null;
    case "retriever": return p.source ? `기준: ${p.source} · 요구 역량 ${p.n_requirements}개` : null;
    case "recommend": return p.tasks_asked != null
      ? `과제 ${p.tasks_asked}개 만들어 ${p.tasks_accepted}개 채택${p.tasks_rejected?.length ? ` · ${p.tasks_rejected.length}개 기각` : ""}`
      : p.impl || null;
    case "verifier": return p.removed != null ? (p.removed ? `검사 3가지 · 근거 없는 항목 ${p.removed}개 제거` : "검사 3가지 모두 통과") : null;
    default: return null;
  }
};
// trace의 호출 종류(bedrock.CallLog kind) → 화면 이름
const CALL = { guardrail: "개인정보 가리기 · Guardrails", star: "강점 진단(STAR)", extract: "스킬 추출", normalize: "스킬 이름 맞추기",
  link: "연결되는 경험 찾기", embed: "교육과정 검색 · 임베딩", task: "과제 구체화", explain: "설명", predict: "직군 예측" };
const callName = (k) => CALL[k.split(":")[0]] || k;

const ACCEPT = ".pdf,.docx,.md,.txt,application/pdf";

const EXTS = [".pdf", ".docx", ".md", ".txt"];

function DocPick({ files, onPick }) {
  const [over, setOver] = useState(false);
  const [skipped, setSkipped] = useState([]);
  const add = (list) => {
    const all = Array.from(list || []);
    const ok = all.filter((f) => EXTS.some((e) => f.name.toLowerCase().endsWith(e)));
    setSkipped(all.filter((f) => !ok.includes(f)).map((f) => f.name));
    onPick([...files, ...ok].slice(0, 4));
  };
  const drop = {
    onDragOver: (e) => { e.preventDefault(); setOver(true); },
    onDragLeave: () => setOver(false),
    onDrop: (e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); },
  };
  return (
    <div className="fld">
      <label className="fld q pdfpick"><span className="qt">자기소개서 · 포트폴리오 · 이력서 등 (필수)</span>
        <span className={over ? "filepick over" : "filepick"} {...drop}>
          <input type="file" multiple accept={ACCEPT} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          <span className="filebtn">파일 선택</span>
          <span className="hint">{files.length ? `${files.length}개 선택됨` : "선택된 파일 없음"} (파일은 4개까지, 합쳐서 5MB)</span>
        </span>
      </label>
      <p className="hint">올릴 수 있는 파일: .pdf, .docx, .md, .txt</p>
      {skipped.length > 0 && <p className="err">올릴 수 없는 형식이라 뺐어요: {skipped.join(", ")}</p>}
      {files.length > 0 && (
        <ul className="doclist">
          {files.map((f, i) => (
            <li key={i}><span>{f.name}</span><span className="hint num">{(f.size / 1024 / 1024).toFixed(1)}MB</span>
              <button className="linkbtn" onClick={() => onPick(files.filter((_, j) => j !== i))} aria-label={`${f.name} 빼기`}>빼기</button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Analyze({ active, sampleTick = 0 }) {
  const [families, setFamilies] = useState([["backend", "백엔드"], ["ai_ml", "AI·ML"], ["data", "데이터"]]);
  const [family, setFamily] = useState("auto");
  const [sector, setSector] = useState("");  // 처음에 반드시 고른다: 민간과 공공은 요구가 달라 섞지 않는다
  const [files, setFiles] = useState([]);
  const [github, setGithub] = useState("");
  const [posting, setPosting] = useState("");
  const [jobId, setJobId] = useState(load);
  const [job, setJob] = useState(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState(null);
  const [pane, setPane] = useState("overview");
  const timer = useRef(null);
  useEffect(() => setPane("overview"), [jobId]);  // 새 분석이면 Overview부터

  useEffect(() => { api.families().then((f) => setFamilies(f.map((x) => [x.id, x.label]))).catch(() => {}); }, []);

  useEffect(() => {
    clearTimeout(timer.current);
    if (!jobId || !active) return undefined;
    let stop = false;
    const tick = async () => {
      try {
        const j = await api.job(jobId);
        if (stop) return;
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer.current = setTimeout(tick, 1500);
      } catch (e) {
        if (!stop) { setErr(e.message); setJobId(""); save(""); }
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer.current); };
  }, [jobId, active]);

  // 예시로 체험하기: 합성 자소서를 파일로 만들어 민간·자동 직군으로 바로 분석 (입력 칸에도 그대로 보이게 채운다)
  const trySample = async () => {
    const f = new File([SAMPLE], SAMPLE_NAME, { type: "text/markdown" });
    setFiles([f]); setSector("private"); setGithub(""); setPosting(""); setFamily("auto");
    setErr(""); setJob(null); setSel(null); setPane("overview");
    try {
      const { job_id } = await api.analyzeDocs([f], "", "auto", "", "private");
      save(job_id); setJobId(job_id);
    } catch (e) { setErr(e.message); }
  };
  useEffect(() => { if (sampleTick) trySample(); }, [sampleTick]);  // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    setErr(""); setJob(null); setSel(null);
    const mb = files.reduce((s, f) => s + f.size, 0) / 1024 / 1024;
    if (mb > 5) {  // 5MB를 넘으면 서버에 닿기 전에 막혀(함수 URL 상한) 아무 안내가 없으므로 여기서 먼저 알린다
      setErr(`문서가 합쳐서 ${mb.toFixed(1)}MB예요. 5MB 이하로 줄여 주세요 (PDF는 '최소 크기'로 다시 저장하면 대개 줄어요).`);
      return;
    }
    try {
      const { job_id } = await api.analyzeDocs(files, github, family, posting, sector);
      save(job_id); setJobId(job_id);
    } catch (e) { setErr(e.message); }
  };

  const running = job && (job.status === "queued" || job.status === "running");
  const cites = useMemo(() => Object.fromEntries((job?.citations || []).map((c) => [c.n, c])), [job]);
  const res = job?.result;
  // 다시 분석: 결과를 닫고 입력 화면으로 (입력값은 남겨 둔다)
  const again = () => { clearTimeout(timer.current); setJob(null); setJobId(""); save(""); setSel(null); setErr(""); };
  const inputLine = [files.map((f) => f.name).join(", "), github.trim() && `GitHub ${github.trim()}`,
    res?.sector?.label, res?.job_family && `${res.job_family.label}${res.job_family.inferred ? "(자동)" : ""}`].filter(Boolean).join(" · ");

  // 화면 3단계: ① 입력(가운데 카드 하나) → ② 분석 중(진행 단계가 하나씩 완료) → ③ 결과 대시보드(왼쪽 바 · 결과 · 근거)
  if (!job) {
    return (
      <section className="view">
        <div className="panel an-intake">
          <div><h2>내 역량 분석하기</h2><p className="hint">문서 하나면 됩니다. 강점, 부족한 역량, 추천 과제와 교육과정을 근거와 함께 보여 드려요</p></div>
          <label className="fld q"><span className="qt">어디에 지원하나요? (필수)</span>
            <Seg label="지원 분야" value={sector} options={[["private", "민간 기업"], ["public", "공공기관"]]} onChange={setSector} full />
          </label>
          <DocPick files={files} onPick={setFiles} />
          <details className="an-more">
            <summary>더 정확하게 (선택) · 지원할 공고 · GitHub · 직군</summary>
            <label className="fld q"><span className="qt">지원할 공고</span>
              <textarea value={posting} onChange={(e) => setPosting(e.target.value)} rows={5} placeholder="공고에서 자격요건, 우대사항, 주요 업무 부분을 복사해서 넣어주세요. 넣지 않으면 수집한 공고 전체가 기준입니다" />
            </label>
            <div className="fld">
              <label className="fld q"><span className="qt">GitHub</span>
                <input type="text" value={github} onChange={(e) => setGithub(e.target.value)} placeholder="아이디 또는 github.com/아이디/레포" maxLength={150} />
              </label>
              <p className="hint">공개 레포 README만 읽습니다</p>
            </div>
            <label className="fld q"><span className="qt">직군 (기본: 자동)</span>
              <Seg label="직군" value={family} options={[["auto", "자동"], ...families]} onChange={setFamily} />
            </label>
          </details>
          <div className="an-go">
            <button className="btn" disabled={!sector || !(files.length || github.trim())} onClick={submit}>분석 시작</button>
            <button className="btn ghost" onClick={trySample}>예시로 체험하기</button>
          </div>
          <p className="hint">{!sector ? "지원 분야를 먼저 골라 주세요 · " : ""}예시는 실존 인물이 아닌 합성 자소서(백엔드 지망, 경험 4개)입니다</p>
          {err && <p className="err">{err}</p>}
        </div>
        <p className="hint foot">채용 합불 판단에 쓰지 않습니다 · 파일과 이력서 원문은 저장하지 않습니다</p>
      </section>
    );
  }

  if (!res) {
    return (
      <section className="view">
        <div className="panel an-intake an-running" aria-busy={running}>
          <div><h2>{job.status === "failed" ? "분석하지 못했어요" : "에이전트가 분석하고 있어요"}</h2>
            <p className="hint">{inputLine || "내 문서"} · 창을 닫아도 서버에서 계속 돌고, 다시 열면 이어서 보여 드려요</p></div>
          <Progress job={job} />
          {job.status === "failed" && <><p className="err">{job.error}</p><button className="btn" onClick={again}>다시 시도</button></>}
        </div>
      </section>
    );
  }

  const nCourse = res.recommendations.filter((r) => r.course).length;
  const go = (k) => { setPane(k); window.scrollTo(0, 0); };
  // 나가기: 로그인이 없으므로 '로그아웃' 대신, 이 브라우저에 저장된 결과를 닫고 소개 화면으로 (App이 hashchange를 듣는다)
  const exit = () => { again(); location.hash = "home"; };
  const navBtn = ([k, l, n]) => (
    <button key={k} role="tab" id={`tab-${k}`} aria-controls={`pane-${k}`} aria-selected={pane === k} onClick={() => go(k)}>
      <span className="nav-l">{(() => { const I = ICON[k]; return I ? <I size={18} strokeWidth={1.8} aria-hidden="true" /> : null; })()}{l}</span>{n != null && <span className="num">{n}</span>}</button>
  );
  return (
    <section className="view">
      <div className="an-dash">
        <aside className="panel an-side no-print">
          <div className="an-input">
            <span className="pm-av" aria-hidden="true">나</span>
            <div><b>{res.sector?.label} {res.job_family?.label}</b><small className="hint">{[files.map((f) => f.name).join(", "), github.trim() && `GitHub ${github.trim()}`].filter(Boolean).join(" · ") || "공유된 분석 결과"}</small></div>
          </div>
          <nav role="tablist" aria-label="분석 결과" aria-orientation="vertical">
            {navBtn(["overview", "Overview", null])}
            {navBtn(["path", "내 학습 경로", null])}
            <hr />
            {[["strengths", "강점", res.strengths.length], ["gaps", "부족한 역량", res.gaps.length],
              ["recos", "추천 과제", res.recommendations.length], ["courses", "교육과정", nCourse]].map(navBtn)}
            <hr />
            {navBtn(["log", "작업 기록 · 검증", null])}
          </nav>
          <div className="an-side-foot">
            <button className="side-act" onClick={again}><RotateCcw size={17} strokeWidth={1.8} aria-hidden="true" />다시 분석</button>
            <button className="side-act" onClick={() => window.print()}><FileDown size={17} strokeWidth={1.8} aria-hidden="true" />PDF로 저장</button>
            <button className="side-act out" onClick={exit} title="이 브라우저에 저장된 분석 결과를 닫고 소개 화면으로 갑니다"><LogOut size={17} strokeWidth={1.8} aria-hidden="true" />나가기</button>
          </div>
        </aside>
        <div className="stack an-panes">
          <div className="an-pane" role="tabpanel" id="pane-overview" aria-labelledby="tab-overview" hidden={pane !== "overview"}><Overview job={job} go={go} /></div>
          <div className="an-pane" role="tabpanel" id="pane-path" aria-labelledby="tab-path" hidden={pane !== "path"}><PathMap res={res} onCite={setSel} /></div>
          <div className="an-pane" role="tabpanel" id="pane-strengths" aria-labelledby="tab-strengths" hidden={pane !== "strengths"}><Strengths list={res.strengths} onCite={setSel} /></div>
          <div className="an-pane" role="tabpanel" id="pane-gaps" aria-labelledby="tab-gaps" hidden={pane !== "gaps"}><Gaps list={res.gaps} onCite={setSel} /></div>
          <div className="an-pane" role="tabpanel" id="pane-recos" aria-labelledby="tab-recos" hidden={pane !== "recos"}><Recos list={res.recommendations} gaps={res.gaps} onCite={setSel} /></div>
          <div className="an-pane" role="tabpanel" id="pane-courses" aria-labelledby="tab-courses" hidden={pane !== "courses"}><Courses res={res} onCite={setSel} /></div>
          {/* 작업 기록·비용은 인쇄(PDF)에 넣지 않는다: an-pane이 아니라 인쇄 때 펼쳐지지 않음 */}
          <div className="no-print" role="tabpanel" id="pane-log" aria-labelledby="tab-log" hidden={pane !== "log"}><Log job={job} /></div>
        </div>
      </div>
      {sel != null && cites[sel] && <Evidence c={cites[sel]} n={sel} onClose={() => setSel(null)} />}
      <CiteList list={job.citations} />
      <p className="hint foot">채용 합불 판단에 쓰지 않습니다 · 파일과 이력서 원문은 저장하지 않습니다</p>
    </section>
  );
}

// 준비도 게이지: 270° 호, 값만큼 색칠
function Gauge({ v }) {
  const r = 70, c = 2 * Math.PI * r, arc = c * 0.75, val = v == null ? 0 : Math.max(0, Math.min(100, v));
  const col = val >= 70 ? "var(--ok)" : val >= 40 ? "var(--warn)" : "var(--accent)";
  return (
    <svg className="ov-gauge" viewBox="0 0 180 180" role="img" aria-label={`준비도 ${v ?? "없음"} / 100`}>
      <circle cx="90" cy="90" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="14" strokeLinecap="round" strokeDasharray={`${arc} ${c}`} transform="rotate(135 90 90)" />
      <circle cx="90" cy="90" r={r} fill="none" stroke={col} strokeWidth="14" strokeLinecap="round" strokeDasharray={`${(arc * val) / 100} ${c}`} transform="rotate(135 90 90)" />
      <text x="90" y="92" textAnchor="middle" className="ov-g-v">{v ?? "—"}</text>
      <text x="90" y="116" textAnchor="middle" className="ov-g-l">준비도 / 100</text>
    </svg>
  );
}

// Overview: 목표 · 강점 직군 · 준비도 게이지 · 다음 할 일 체크리스트 · 강점 경험 표 (레퍼런스: Dribbble 'Job Portal - Career Dashboard')
function Overview({ job, go }) {
  const r = job.result;
  const [done, setDone] = useState([]);  // 체크는 이 화면에서만(저장 안 함)
  const src = job.progress?.find((p) => p.agent === "retriever")?.source;
  const must = r.gaps.filter((g) => g.weight === 2).length;
  const todo = r.recommendations.filter((x) => !x.abstained).slice(0, 4);
  const pct = todo.length ? Math.round((done.length / todo.length) * 100) : 0;
  const strong = r.strengths.filter((e) => e.level === "strong").length;
  const filled = (e) => Object.values(e.slots).filter((s) => s.present).length;
  return (
    <div className="ov">
      <div className="panel ov-goal">
        <h3>목표</h3>
        <p className="ov-big"><span className="hint">지원 준비 중</span> {r.sector?.label} {r.job_family?.label}</p>
        <div className="row">
          {r.job_family?.inferred && <span className="chip">직군 자동 판단</span>}
          {src && <span className="chip">{src.replace(/^.*?(공고|공공기관)/, "$1")}</span>}
        </div>
      </div>
      <div className="panel ov-fam">
        <h3>강점 직군</h3>
        <div className="row">
          {(r.job_family?.ranking || []).map((x, i) => (
            <span key={x.id} className={`chip ${i === 0 ? "tag-pub" : ""}`}>{x.label} <b className="num">{x.score}</b></span>
          ))}
        </div>
      </div>
      <div className="panel ov-ready">
        <h3>준비도 <small className="hint">· 공개 공고 기준</small></h3>
        <Gauge v={r.readiness?.apply} />
        <div className="ov-stats">
          <button onClick={() => go("strengths")}><b className="num">{strong}<small>/{r.strengths.length}</small></b><span><i className="ov-dot ok" />강점 경험</span></button>
          <button onClick={() => go("gaps")}><b className="num">{must}</b><span><i className="ov-dot bad" />부족 · 필수</span></button>
          <button onClick={() => go("gaps")}><b className="num">{r.gaps.length - must}</b><span><i className="ov-dot pref" />부족 · 우대</span></button>
          <button onClick={() => go("courses")}><b className="num">{r.recommendations.filter((x) => x.course).length}</b><span><i className="ov-dot acc" />추천 과정</span></button>
          <button onClick={() => go("log")}><b>{job.verify?.passed ? "통과" : `${job.verify?.removed?.length ?? 0}개 제거`}</b><span><i className="ov-dot ok" />근거 검증</span></button>
          <button onClick={() => go("log")}><b className="num">{usd(job.cost?.usd)}</b><span><i className="ov-dot idle" />분석 비용</span></button>
        </div>
      </div>
      <div className="panel ov-road">
        <div className="ov-h"><h3>다음 할 일</h3><span className="hint num">{done.length} / {todo.length} 완료</span></div>
        <div className="ov-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
        <ul className="ov-tasks">
          {todo.map((x) => (
            <li key={x.rank}>
              <label><input type="checkbox" checked={done.includes(x.rank)} onChange={(e) => setDone((d) => (e.target.checked ? [...d, x.rank] : d.filter((n) => n !== x.rank)))} />
                <span><b>{x.task}</b>{x.course && <small className="hint">고용24 · {x.course.name}{x.course.start ? ` · ${x.course.start} 개강` : ""}</small>}</span></label>
            </li>
          ))}
        </ul>
        <button className="btn ghost sm ov-more" onClick={() => go("recos")}>추천 과제 전체 보기 →</button>
      </div>
      <div className="panel ov-list">
        <div className="ov-h"><h3>내 경험 진단</h3><button className="linkbtn" onClick={() => go("strengths")}>STAR 자세히 →</button></div>
        <table>
          <thead><tr><th>#</th><th>경험</th><th>판정</th><th>STAR 칸</th></tr></thead>
          <tbody>
            {r.strengths.map((e, i) => {
              const [lab, cls] = LEVEL[e.level];
              return <tr key={e.exp_id}><td className="num">{i + 1}</td><td>{e.title}</td><td><span className={`chip ${cls}`}>{lab}</span></td><td className="num">{filled(e)} / 4</td></tr>;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ④ 교육과정: 추천 과제에 붙은 고용24 과정만 모아서. 맞는 과정이 없다고 판단한 역량도 이유와 함께 보여 준다
function Courses({ res, onCite }) {
  const name = (t) => res.gaps.find((g) => g.id === t)?.name || "역량";
  const have = res.recommendations.filter((r) => r.course);
  const none = res.recommendations.filter((r) => !r.course && r.course_note);
  return (
    <div className="panel an-sec sec-acc">
      <SecHead n="4" title="교육과정" sub="부족한 역량을 채울 수 있는 고용24 실제 과정이에요. 앞으로 개강하는 과정만, 맞는 과정이 없으면 추천하지 않습니다" count={have.length ? `${have.length}개` : null} />
      {!have.length && <p className="empty">이번 분석에서는 추천할 과정이 없어요. 추천 과제의 결과물 과제를 먼저 해 보세요.</p>}
      <ul className="an-courses">
        {have.map((r) => {
          const c = r.course;  // 과정 근거는 cites 맨 끝(supervisor _fallback_recommend: g["cites"] + cn)
          return (
            <li key={r.rank}>
              <span className="pm-t t-course">고용24</span>
              <b>{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.name}</a> : c.name}</b>
              <span className="hint">{c.start ? `${c.start} 개강` : ""}{c.hours ? `${c.start ? " · " : ""}${c.hours}시간` : ""}</span>
              <span>채우는 역량: <b>{name(r.target)}</b> {r.cites?.length > 0 && <Cite ns={r.cites.slice(-1)} onCite={onCite} />}</span>
            </li>
          );
        })}
      </ul>
      {none.length > 0 && (
        <div className="gap-grp"><h3>맞는 과정이 없던 역량</h3>
          <ul className="hint">{none.map((r) => <li key={r.rank}>{name(r.target)}: {r.course_note}</li>)}</ul></div>
      )}
    </div>
  );
}

function Progress({ job }) {
  const rows = job.progress?.length ? job.progress : Object.keys(STAGE).map((a) => ({ agent: a, status: "queued" }));
  return (
    <ol className="an-prog" aria-live="polite">
      {rows.map((p) => (
        <li key={p.agent} className={`s-${p.status}`}>
          <span className="dot" aria-hidden="true" />
          <span>{STAGE[p.agent] || p.agent}</span>
          <span className="num hint">{p.ms != null ? `${(p.ms / 1000).toFixed(1)}s` : ""}</span>
          {said(p) && <small className="said">{said(p)}</small>}
          {p.note && <small className="hint">{p.note}</small>}
        </li>
      ))}
    </ol>
  );
}

const Cite = ({ ns, onCite }) => (ns || []).map((n) => (
  <button key={n} className="cite" onClick={() => onCite(n)} aria-label={`근거 ${n} 보기`}>[{n}]</button>
));

function Strengths({ list, onCite }) {
  return (
    <div className="panel an-sec sec-ok">
      <SecHead n="1" title="강점 (STAR)" sub="내 문서의 경험을 상황·과제·행동·결과로 나눠 봤어요" count={list.length ? `${list.length}개 경험` : null} />
      {!list.length && <p className="empty">경험 단락을 찾지 못했습니다.</p>}
      {list.map((e) => {
        const [lab, cls] = LEVEL[e.level];
        return (
          <div key={e.exp_id} className="card star">
            <div className="ch"><b>{e.title}</b><span className="row"><span className={`chip ${cls}`}>{lab}</span><span className="num hint">{e.score} / 5</span></span></div>
            <div className="slots">
              {SLOT.map(([k, l]) => {
                const s = e.slots[k];
                return (
                  <div key={k} className={`slot ${s.present ? "on" : "off"}`}>
                    <span className="sk">{k}<small>{l}</small></span>
                    {s.present ? <span>“{s.quote}” {s.cite && <Cite ns={[s.cite]} onCite={onCite} />}</span> : <span className="hint">없음</span>}
                  </div>
                );
              })}
            </div>
            {e.missing_hint && <p className="hint">보완: {e.missing_hint}</p>}
          </div>
        );
      })}
    </div>
  );
}

function SecHead({ n, title, sub, count }) {
  return (
    <div className="sec-head">
      <span className="sec-n">{n}</span>
      <div><h2>{title}{count && <small className="hint"> · {count}</small>}</h2><p className="hint">{sub}</p></div>
    </div>
  );
}

function Gaps({ list, onCite }) {
  const groups = [["필수", list.filter((g) => g.weight === 2)], ["우대", list.filter((g) => g.weight !== 2)]];
  return (
    <div className="panel an-sec sec-bad">
      <SecHead n="2" title="부족한 역량" sub="공고에서 요구하지만 내 문서에서는 잘 보이지 않는 역량이에요" count={list.length ? `${list.length}개` : null} />
      {!list.length ? <p className="hint">기준에 비어 있는 역량이 없습니다.</p> : groups.map(([lab, gs]) => gs.length > 0 && (
        <div key={lab} className="gap-grp">
          <h3>{lab} <span className="num">{gs.length}</span></h3>
          <ul className="an-gaps">
            {gs.map((g) => (
              <li key={g.id}><b>{g.name}</b>
                <span className="row"><StatusChip status={g.status}>{g.status_label}</StatusChip><Cite ns={g.cites} onCite={onCite} /></span></li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// 학습 경로 지도: 나 → 추천 과제(부족 역량 · 고용24 과정) 리본. 하나를 고르면 노란 카드에 이유·근거·과정, 아래 줄에 경로 요약
function PathMap({ res, onCite }) {
  const items = res.recommendations.filter((r) => !r.abstained);
  const [pick, setPick] = useState(0);
  if (!items.length) return null;
  const cur = items[Math.min(pick, items.length - 1)];
  const gap = (t) => res.gaps.find((g) => g.id === t);
  const label = (r) => (r.target?.startsWith("star:") ? "강점 경험 보완" : gap(r.target)?.name || "과제");
  const tag = (r) => (r.target?.startsWith("star:") ? ["STAR 보완", "t-star"] : gap(r.target)?.weight === 2 ? ["필수", "t-must"] : ["우대", "t-pref"]);
  const fam = res.job_family?.label || "";
  const n = items.length, H = n * 100, mid = H / 2;
  return (
    <div className="panel pm">
      <div className="pm-head">
        <div><h2>내 학습 경로</h2><p className="hint">지금의 나에서 {res.sector?.label ?? ""} {fam} 지원까지, 부족한 역량을 채우는 길이에요</p></div>
      </div>
      <div className="pm-map" style={{ "--rows": n }}>
        <svg className="pm-ribbons" viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <defs><linearGradient id="pm-g" x1="0" x2="1"><stop offset="0" stopColor="#7fb2ff" /><stop offset="1" stopColor="#5b4cf0" /></linearGradient></defs>
          {items.map((r, i) => {
            const y = i * 100 + 50;
            return <path key={r.rank} d={`M0 ${mid} C 45 ${mid}, 55 ${y}, 100 ${y}`} className={i === pick ? "on" : ""} vectorEffect="non-scaling-stroke" />;
          })}
        </svg>
        <div className="pm-me">
          <span className="pm-av" aria-hidden="true">나</span>
          <b>지금의 나</b>
          <small className="hint">목표</small>
          <span>{res.sector?.label} {fam} 지원</span>
          <div className="pm-me-k"><span>준비도</span><b className="num">{res.readiness?.apply ?? "—"}</b></div>
        </div>
        <ol className="pm-dest">
          {items.map((r, i) => {
            const [t, c] = tag(r);
            return (
              <li key={r.rank}>
                <button className={i === pick ? "on" : ""} aria-pressed={i === pick} onClick={() => setPick(i)}>
                  <b>{label(r)}</b>
                  <span className="pm-tags"><span className={`pm-t ${c}`}>{t}</span>{r.course && <span className="pm-t t-course">고용24 과정</span>}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <div className="pm-note">
          <dl>
            <dt>할 일</dt><dd>{cur.task}</dd>
            <dt>왜</dt><dd>{cur.why} <Cite ns={cur.cites} onCite={onCite} /></dd>
            {cur.task_basis && <><dt>근거</dt><dd>공고 “{cur.task_basis.posting}”</dd></>}
            <dt>교육과정</dt><dd>{cur.course ? <>{cur.course.url ? <a href={cur.course.url} target="_blank" rel="noreferrer">{cur.course.name}</a> : cur.course.name}{cur.course.start ? ` · ${cur.course.start} 개강` : ""}</> : (cur.course_note || "과정 대신 결과물 과제")}</dd>
          </dl>
        </div>
      </div>
      <div className="pm-bar">
        <span>나 → <b>{label(cur)}</b>{cur.course ? <> → {cur.course.name}</> : null} → {res.sector?.label} {fam} 지원</span>
        {cur.cites?.[0] && <button className="btn sm" onClick={() => onCite(cur.cites[0])}>근거 보기</button>}
      </div>
    </div>
  );
}

function Recos({ list, gaps = [], onCite }) {
  const forLabel = (t) => {
    if (!t) return null;
    if (t.startsWith("star:")) return "강점 경험 보완";
    const g = gaps.find((x) => x.id === t);
    return g ? `${g.name} 채우기` : null;
  };
  return (
    <div className="panel an-sec sec-acc">
      <SecHead n="3" title="추천 과제" sub="부족한 역량을 채우려고 혼자 해 볼 만한 과제와 교육과정이에요" count={list.length ? `${list.length}개` : null} />
      <ol className="an-recos">
        {list.map((r) => (
          <li key={r.rank} className={r.abstained ? "abst" : ""}>
            <span className="reco-n num">{r.rank}</span>
            <div className="reco-body">
              {r.abstained ? (
                <><b>추천하지 않음</b><p className="hint">{r.abstain_reason || "근거 없음"}</p></>
              ) : (
                <>
                  {forLabel(r.target) && <span className="chip tag-pub reco-for">{forLabel(r.target)}</span>}
                  <b className="reco-task">{r.task}</b>
                  <dl className="reco-meta">
                    <dt>왜</dt><dd>{r.why} <Cite ns={r.cites} onCite={onCite} /></dd>
                    {r.task_basis && <><dt>근거</dt><dd>공고 “{r.task_basis.posting}”{r.task_basis.resume ? <> · 내 자소서 “{r.task_basis.resume}”</> : null}</dd></>}
                    {r.course && <><dt>교육과정</dt><dd>{r.course.url ? <a href={r.course.url} target="_blank" rel="noreferrer">{r.course.name}</a> : r.course.name}{r.course.start ? ` · ${r.course.start} 개강` : r.course.hours ? ` · ${r.course.hours}시간` : ""}</dd></>}
                    {!r.course && r.course_note && <><dt>교육과정</dt><dd>{r.course_note}</dd></>}
                  </dl>
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// 작업 기록: 에이전트가 단계마다 한 일 → 검증 → Bedrock 호출 → 비용
function Log({ job }) {
  const rows = (job.progress || []).filter((p) => p.agent !== "cost");
  const v = job.verify;
  const trace = job.trace || [];
  return (
    <div className="stack">
      <div className="panel">
        <h2>에이전트가 한 일</h2>
        <p className="hint">순서는 고정이고, 단계마다 결과를 다음 단계가 받아 씁니다. 한 단계가 실패해도 그 단계만 규칙으로 대신합니다.</p>
        <ol className="an-log">
          {rows.map((p) => (
            <li key={p.agent} className={`s-${p.status}`}>
              <b>{STAGE[p.agent] || p.agent}</b><span className="num hint">{p.ms != null ? `${(p.ms / 1000).toFixed(1)}s` : ""}</span>
              {said(p) && <p>{said(p)}</p>}
              {p.note && <p className="hint">{p.note}</p>}
              {p.tasks_rejected?.length > 0 && <ul className="hint">{p.tasks_rejected.map((t) => <li key={t}>기각: {t}</li>)}</ul>}
            </li>
          ))}
        </ol>
      </div>
      {v && (
        <div className="panel">
          <h2>검증 {v.passed ? <small className="chip st-own">통과</small> : <small className="chip st-miss">{v.removed.length}개 제거</small>}</h2>
          <p className="hint">결과를 보여 주기 전에 아래를 코드로 검사하고, 어긋난 항목은 지웁니다.</p>
          <ul className="an-checks">{v.checks.map((x) => <li key={x}>✓ {x}</li>)}</ul>
          {v.removed.length > 0 && <ul className="hint">{v.removed.map((x) => <li key={x}>제거: {x}</li>)}</ul>}
        </div>
      )}
      <div className="panel">
        <h2>Bedrock 호출 <small className="hint num">{trace.length}회</small></h2>
        {trace.length ? (
          <ul className="an-trace num">
            {trace.map((t, i) => <li key={i}><span>{callName(t.agent)}</span><span className="hint">{t.model}</span><span>{(t.ms / 1000).toFixed(1)}s</span><span className="hint">{t.in || t.out ? `${t.in.toLocaleString()} → ${t.out.toLocaleString()} 토큰` : ""}</span></li>)}
          </ul>
        ) : <p className="hint">이번 분석은 Bedrock을 부르지 않았습니다 (규칙 엔진 또는 저장된 결과)</p>}
      </div>
      <Cost job={job} />
    </div>
  );
}

function Cost({ job }) {
  const c = job.cost;
  if (!c) return null;
  const rows = Object.entries(c.by_agent || {}).filter(([, v]) => v > 0);
  const max = Math.max(...rows.map(([, v]) => v), 1e-9);
  return (
    <div className="panel">
      <h2>비용 <small className="hint num">{usd(c.usd)}</small></h2>
      <p className="hint num">입력 {c.input_tokens.toLocaleString()} · 출력 {c.output_tokens.toLocaleString()} 토큰 · Bedrock 호출 {c.calls}회 · {usd(c.usd)} (예산 {usd(c.budget_usd)})</p>
      {rows.length ? (
        <div className="bars">
          {rows.map(([a, v]) => (
            <div key={a} className="bar"><span>{STAGE[a] || a}</span>
              <div className="track"><div className="fill" style={{ width: `${(v / max) * 100}%` }} /></div><span className="v num">{usd(v)}</span></div>
          ))}
        </div>
      ) : <p className="hint">0원 (규칙 엔진)</p>}
    </div>
  );
}

// 근거: [번호]를 누를 때만 오른쪽에서 열리는 패널. Esc·바깥 클릭·닫기로 닫는다 (검증 결과는 '작업 기록 · 검증'에)
function Evidence({ c, n, onClose }) {
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="ev-scrim no-print" onClick={onClose} aria-hidden="true" />
      <aside className="panel an-ev ev-sheet no-print" role="dialog" aria-label={`근거 ${n}`}>
        <div className="ev-h"><h2>근거 <span className="num hint">[{n}]</span></h2><button className="ev-x" onClick={onClose} aria-label="근거 닫기">✕</button></div>
        <span className="chip tag-pub">{KIND[c.kind] || c.kind}</span>
        <b>{c.title}</b>
        {c.quote && <blockquote>{c.quote}</blockquote>}
        {c.url && <a href={c.url} target="_blank" rel="noreferrer">원문 열기</a>}
      </aside>
    </>
  );
}

// 인쇄(PDF)용 근거 목록: 화면에서는 숨기고 인쇄할 때만 보인다
function CiteList({ list }) {
  return (
    <div className="panel print-only">
      <h2>근거 목록</h2>
      <ol className="hint">
        {list.map((c) => (
          <li key={c.n} value={c.n}>[{KIND[c.kind] || c.kind}] {c.title}{c.quote ? ` — “${c.quote}”` : ""}{c.url ? ` (${c.url})` : ""}</li>
        ))}
      </ol>
      <p className="hint">SkillBridge · STAR(기업 역량면접 방식) 기준 · 점수는 규칙으로 계산 · 채용 합불 판단에 쓰지 않음</p>
    </div>
  );
}
