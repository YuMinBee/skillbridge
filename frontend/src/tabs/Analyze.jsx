// 역량 분석 (T4 · docs/pivot/T4_FRONTEND.md). 이력서 → job 접수 → 진행 상태 → ① 강점(STAR) ② 갭 ③ 추천 → 근거 패널 → 비용.
// job_id는 localStorage에 둔다: 탭을 닫았다 열어도 서버에서 끝난 결과를 이어서 본다.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { Seg, StatusChip } from "../ui.jsx";

const STAGE = {
  guard: "개인정보 가리기", star: "① 강점 진단 (STAR)", skills: "스킬 추출", retriever: "② 역량 기준 찾기",
  recommend: "③ 과제 추천", verifier: "근거 검증", cost: "비용 계산",
};
const SLOT = [["S", "상황"], ["T", "과제"], ["A", "행동"], ["R", "결과"]];
const LEVEL = { strong: ["강점", "st-own"], ok: ["보통", "st-part"], weak: ["약함", "st-miss"] };
const KIND = { resume: "내 이력서", posting: "공고", course: "고용24 과정", ncs_unit: "NCS 능력단위", ncs_basic: "NCS 직업기초능력" };
const KEY = "analyzeJob";
const EXAMPLE = `[프로젝트] 식당 예약 API
동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다. 저는 예약 API 설계를 맡았습니다. Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다. 그 결과 중복 예약이 월 12건에서 0건이 되었습니다.

[스터디] 데이터 분석
혁신적으로 스터디를 주도했습니다. 열정적으로 참여했습니다.

[프로젝트]
- Redis로 인기 상품 목록을 캐싱해 응답 속도를 개선함
- Docker로 서버를 컨테이너화하고 GitHub Actions로 CI/CD를 구성해 배포함
[보유기술] Java, Spring Boot, MySQL, Redis, Docker`;

const load = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
const save = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* noop */ } };
const usd = (v) => (v == null ? "—" : `$${v.toFixed(v < 0.01 ? 4 : 3)}`);

const QUESTIONS = [
  ["S", "상황", "어떤 문제나 불편이 있었나요?", "예) 동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다"],
  ["T", "과제", "그중 내가 맡은 일·목표는 무엇이었나요?", "예) 저는 예약 API 설계를 맡았습니다"],
  ["A", "행동", "내가 직접 한 일을 구체적으로 (도구·방법)", "예) Spring Boot로 API를 만들고 락으로 동시성 문제를 막았습니다"],
  ["R", "결과", "무엇이 바뀌었나요? 숫자가 있으면 좋아요", "예) 중복 예약이 월 12건에서 0건이 되었습니다"],
];
const blankExp = () => ({ title: "", S: "", T: "", A: "", R: "" });
const EXAMPLE_TPL = [
  { title: "식당 예약 API", S: "동아리 행사 예약을 엑셀로 받다 보니 중복 예약이 잦았습니다", T: "저는 예약 API 설계를 맡았습니다",
    A: "Spring Boot로 예약 API를 만들고 동시성 문제를 락으로 막았습니다", R: "중복 예약이 월 12건에서 0건이 되었습니다" },
  { title: "데이터 분석 스터디", S: "", T: "", A: "혁신적으로 스터디를 주도했습니다", R: "열심히 참여했습니다" },
];
const MODES = [["pdf", "이력서 PDF"], ["template", "템플릿으로 쓰기"], ["text", "글 붙여 넣기"]];

export default function Analyze({ active }) {
  const [families, setFamilies] = useState([["backend", "백엔드"], ["ai_ml", "AI·ML"], ["data", "데이터"]]);
  const [family, setFamily] = useState("auto");
  const [mode, setMode] = useState("pdf");
  const [file, setFile] = useState(null);
  const [exps, setExps] = useState([blankExp()]);
  const [skills, setSkills] = useState("");
  const [resume, setResume] = useState("");
  const [posting, setPosting] = useState("");
  const [jobId, setJobId] = useState(load);
  const [job, setJob] = useState(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState(null);
  const timer = useRef(null);

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

  const ready = mode === "pdf" ? !!file : mode === "template" ? exps.some((e) => e.S || e.T || e.A || e.R) : resume.trim().length >= 20;

  const submit = async () => {
    setErr(""); setJob(null); setSel(null);
    try {
      const base = { job_family: family, posting: posting || null };
      const { job_id } = mode === "pdf" ? await api.analyzePdf(file, family, posting)
        : mode === "template" ? await api.analyze({ ...base, experiences: exps, skills })
          : await api.analyze({ ...base, resume });
      save(job_id); setJobId(job_id);
    } catch (e) { setErr(e.message); }
  };

  const setExp = (i, k, v) => setExps((xs) => xs.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  const running = job && (job.status === "queued" || job.status === "running");
  const cites = useMemo(() => Object.fromEntries((job?.citations || []).map((c) => [c.n, c])), [job]);
  const res = job?.result;

  return (
    <section className="view">
      <p className="lead">
        이력서를 넣으면 <b>기업 역량면접 방식(STAR)</b>으로 경험의 강점을 보고, 공개 공고 기준과 비교해 <b>근거가 붙은 과제</b>를 추천합니다.
        모든 판정에는 출처가 붙고, 근거를 확인하지 못하면 추천하지 않습니다. 채용 합불 판단에 쓰지 않습니다.
      </p>
      <div className="grid-side">
        <div className="panel no-print">
          <h2>내 경험 넣기</h2>
          <Seg label="입력 방식" value={mode} options={MODES} onChange={setMode} />
          {mode === "pdf" && (
            <>
              <input type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <p className="hint">글자를 읽기만 하고 파일은 저장하지 않습니다. 이름·연락처는 자동으로 가립니다.
                이력서가 없으면 <button className="linkbtn" onClick={() => setMode("template")}>템플릿으로 쓰기</button>.</p>
            </>
          )}
          {mode === "template" && (
            <div className="tpl">
              <p className="hint">경험 하나에 네 칸입니다. 기업 역량면접(STAR)과 같은 순서라 자소서·면접 답변으로도 쓸 수 있어요.</p>
              {exps.map((e, i) => (
                <fieldset key={i} className="tpl-exp">
                  <legend>경험 {i + 1}</legend>
                  <input type="text" value={e.title} onChange={(ev) => setExp(i, "title", ev.target.value)}
                    placeholder="경험 이름 (예: 팀 프로젝트 · 식당 예약 API)" maxLength={60} />
                  {QUESTIONS.map(([k, l, q, ph]) => (
                    <label key={k} className="fld"><span><b className="num">{k}</b> {l} · {q}</span>
                      <textarea rows={2} value={e[k]} onChange={(ev) => setExp(i, k, ev.target.value)} placeholder={ph} maxLength={k === "A" ? 1000 : 600} />
                    </label>
                  ))}
                  {exps.length > 1 && <button className="btn ghost sm" onClick={() => setExps((xs) => xs.filter((_, j) => j !== i))}>이 경험 빼기</button>}
                </fieldset>
              ))}
              <div className="row">
                {exps.length < 8 && <button className="btn ghost sm" onClick={() => setExps((xs) => [...xs, blankExp()])}>+ 경험 추가</button>}
                <button className="btn ghost sm" onClick={() => { setExps(EXAMPLE_TPL); setSkills("Java, Spring Boot, MySQL, Redis"); }}>예시 채우기</button>
              </div>
              <label className="fld">가진 기술 (쉼표로)
                <input type="text" value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="Java, Spring Boot, MySQL" maxLength={500} />
              </label>
            </div>
          )}
          {mode === "text" && (
            <>
              <textarea value={resume} onChange={(e) => setResume(e.target.value)} rows={12}
                placeholder="경험을 문단이나 글머리표로 붙여 넣으세요. 이름·연락처는 자동으로 가립니다." />
              <div className="row">
                <button className="btn ghost sm" onClick={() => setResume(EXAMPLE)}>예시 넣기</button>
                <span className="hint">{resume.length.toLocaleString()}자</span>
              </div>
            </>
          )}
          <details>
            <summary className="hint">직군 직접 고르기 (기본: 이력서 스킬로 자동 추정)</summary>
            <Seg label="직군" value={family} options={[["auto", "자동"], ...families]} onChange={setFamily} />
          </details>
          <details>
            <summary className="hint">지원할 공고 붙여 넣기 (선택) · 없으면 같은 직군 공개 공고(민간 + 잡알리오) 기준</summary>
            <textarea value={posting} onChange={(e) => setPosting(e.target.value)} rows={6} placeholder="자격요건·우대사항이 있는 공고 본문" />
          </details>
          <button className="btn" disabled={!ready || running} onClick={submit}>
            {running ? "분석 중…" : "분석 시작"}
          </button>
          {err && <p className="err">{err}</p>}
          {job && <Progress job={job} />}
        </div>

        <div className="stack">
          {!job && <div className="panel"><p className="empty">왼쪽에 이력서를 넣고 분석을 시작하세요. 창을 닫아도 서버에서 계속 분석합니다.</p></div>}
          {job?.status === "failed" && <p className="err">분석 실패: {job.error}</p>}
          {res && (
            <>
              <div className="row no-print">
                <button className="btn ghost sm" onClick={() => window.print()}>PDF로 저장</button>
                <span className="hint">브라우저 인쇄 창에서 'PDF로 저장'을 고르세요. 분석 결과와 근거 목록이 함께 들어갑니다.</span>
              </div>
              <Summary job={job} />
              <div className="an-main">
                <div className="stack">
                  <Strengths list={res.strengths} onCite={setSel} />
                  <Gaps list={res.gaps} onCite={setSel} />
                  <Recos list={res.recommendations} onCite={setSel} />
                  <Cost job={job} />
                </div>
                <Evidence c={sel ? cites[sel] : null} total={job.citations.length} verify={job.verify} />
              </div>
              <CiteList list={job.citations} />
            </>
          )}
        </div>
      </div>
    </section>
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
          {p.note && <small className="hint">{p.note}</small>}
        </li>
      ))}
    </ol>
  );
}

function Summary({ job }) {
  const r = job.result, s = r.strengths;
  const strong = s.filter((e) => e.level === "strong").length;
  return (
    <div className="an-sum">
      <div className="panel"><h3>강점 경험</h3><div className="big num">{strong}<small> / {s.length}</small></div>
        <p className="hint">STAR 4칸이 원문으로 확인된 경험</p></div>
      <div className="panel"><h3>지원 준비도{r.job_family ? ` · ${r.job_family.label}` : ""}</h3><div className="big num">{r.readiness.apply ?? "—"}</div>
        <p className="hint">{r.job_family?.inferred ? "직군은 스킬로 자동 추정 · " : ""}공개 공고 기준 · 규칙 계산</p></div>
      <div className="panel"><h3>실무 준비도</h3><div className="big num">{r.readiness.practice ?? "—"}</div>
        <p className="hint">{r.readiness.practice == null ? "NCS 기준 연결 준비 중" : "NCS 기준"}</p></div>
      <div className="panel"><h3>이번 분석 비용</h3><div className="big num">{usd(job.cost?.usd)}</div>
        <p className="hint">{job.mode === "bedrock" ? "Bedrock" : "규칙 엔진(0원)"} · 근거 {job.citations.length}개</p></div>
    </div>
  );
}

const Cite = ({ ns, onCite }) => (ns || []).map((n) => (
  <button key={n} className="cite" onClick={() => onCite(n)} aria-label={`근거 ${n} 보기`}>[{n}]</button>
));

function Strengths({ list, onCite }) {
  return (
    <div className="panel">
      <h2>① 경험별 강점 (STAR)</h2>
      <p className="hint">칸마다 이력서 원문 문장을 그대로 붙였습니다. 원문에서 찾지 못한 칸은 비워 둡니다. 점수는 규칙(칸 4 + 수치 0.5 + 내 역할 0.5)으로만 냅니다.</p>
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

function Gaps({ list, onCite }) {
  return (
    <div className="panel">
      <h2>② 기준 대비 갭</h2>
      {!list.length ? <p className="hint">기준에 비어 있는 역량이 없습니다.</p> : (
        <ul className="an-gaps">
          {list.map((g) => (
            <li key={g.id}><span>{g.name}</span> {g.weight === 2 ? <small className="hint">필수</small> : <small className="hint">우대</small>}
              <StatusChip status={g.status}>{g.status_label}</StatusChip> <Cite ns={g.cites} onCite={onCite} /></li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Recos({ list, onCite }) {
  return (
    <div className="panel">
      <h2>③ 추천 과제</h2>
      <ol className="an-recos">
        {list.map((r) => (
          <li key={r.rank} className={r.abstained ? "abst" : ""}>
            {r.abstained ? (
              <><b>추천하지 않음</b><p className="hint">{r.abstain_reason || "근거를 확인하지 못했습니다."} 근거 없는 추천은 내보내지 않습니다.</p></>
            ) : (
              <>
                <p><b>{r.task}</b></p>
                <p className="hint">왜: {r.why} <Cite ns={r.cites} onCite={onCite} /></p>
                {r.course && <p className="hint">과정: {r.course.url ? <a href={r.course.url} target="_blank" rel="noreferrer">{r.course.name}</a> : r.course.name} · {r.course.hours}시간</p>}
              </>
            )}
          </li>
        ))}
      </ol>
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
      <h2>비용</h2>
      <p className="hint num">입력 {c.input_tokens.toLocaleString()} · 출력 {c.output_tokens.toLocaleString()} 토큰 · Bedrock 호출 {c.calls}회 · {usd(c.usd)} (예산 {usd(c.budget_usd)})</p>
      {rows.length ? (
        <div className="bars">
          {rows.map(([a, v]) => (
            <div key={a} className="bar"><span>{STAGE[a] || a}</span>
              <div className="track"><div className="fill" style={{ width: `${(v / max) * 100}%` }} /></div><span className="v num">{usd(v)}</span></div>
          ))}
        </div>
      ) : <p className="hint">규칙 엔진으로 돌아 Bedrock 비용이 없습니다.</p>}
    </div>
  );
}

function Evidence({ c, total, verify }) {
  return (
    <aside className="panel an-ev">
      <h2>근거</h2>
      {c ? (
        <>
          <span className="chip tag-pub">{KIND[c.kind] || c.kind}</span>
          <b>{c.title}</b>
          {c.quote && <blockquote>{c.quote}</blockquote>}
          {c.url && <a href={c.url} target="_blank" rel="noreferrer">원문 열기</a>}
        </>
      ) : <p className="hint">[번호]를 누르면 그 판정의 근거 원문이 여기에 뜹니다. 근거 {total}개.</p>}
      {verify && (
        <div className="hint">
          <b>검증</b> {verify.passed ? "✓ 통과" : `· ${verify.removed.length}개 제거`}
          <ul>{verify.checks.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      )}
    </aside>
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
      <p className="hint">역량다리 · STAR(기업 역량면접 방식) 기준 · 점수는 규칙으로 계산 · 채용 합불 판단에 쓰지 않음</p>
    </div>
  );
}
