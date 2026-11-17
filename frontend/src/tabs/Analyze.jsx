// 역량 분석 (T4 · docs/pivot/T4_FRONTEND.md). 자기소개서·포트폴리오 PDF → job 접수 → 진행 상태 → ① 강점(STAR) ② 갭 ③ 추천 → 근거 → 비용.
// job_id는 localStorage에 둔다: 탭을 닫았다 열어도 서버에서 끝난 결과를 이어서 본다.
// (글 붙여 넣기·STAR 템플릿 입력은 2026-11-17 화면에서 내림. API(/api/analyze)는 남아 있음)
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { Seg, StatusChip } from "../ui.jsx";

const STAGE = {
  collect: "GitHub 읽기", guard: "개인정보 가리기", star: "① 강점 진단 (STAR)", skills: "스킬 추출", retriever: "② 역량 기준 찾기",
  recommend: "③ 과제 추천", verifier: "근거 검증", cost: "비용 계산",
};
const SLOT = [["S", "상황"], ["T", "과제"], ["A", "행동"], ["R", "결과"]];
const LEVEL = { strong: ["강점", "st-own"], ok: ["보통", "st-part"], weak: ["약함", "st-miss"] };
const KIND = { resume: "내 문서", posting: "공고", posting_stats: "공고 집계", course: "고용24 과정", ncs_unit: "NCS 능력단위", ncs_basic: "NCS 직업기초능력" };
const KEY = "analyzeJob";

const load = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
const save = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* noop */ } };
const usd = (v) => (v == null ? "—" : `$${v.toFixed(v < 0.01 ? 4 : 3)}`);

const ACCEPT = ".pdf,.docx,.md,.txt,application/pdf";

function DocPick({ files, onPick }) {
  const add = (list) => onPick([...files, ...Array.from(list || [])].slice(0, 4));
  return (
    <div className="fld">
      <label className="fld pdfpick">자소서 · 포트폴리오 · CV · 노션 내보내기
        <input type="file" multiple accept={ACCEPT} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </label>
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

export default function Analyze({ active }) {
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

  const submit = async () => {
    setErr(""); setJob(null); setSel(null);
    try {
      const { job_id } = await api.analyzeDocs(files, github, family, posting, sector);
      save(job_id); setJobId(job_id);
    } catch (e) { setErr(e.message); }
  };

  const running = job && (job.status === "queued" || job.status === "running");
  const cites = useMemo(() => Object.fromEntries((job?.citations || []).map((c) => [c.n, c])), [job]);
  const res = job?.result;

  return (
    <section className="view">
      <div className="grid-side">
        <div className="panel no-print">
          <h2>어디에 지원하나요?</h2>
          <Seg label="지원 분야" value={sector} options={[["private", "민간 기업"], ["public", "공공기관"]]} onChange={setSector} />
          <h2>내 경험 넣기</h2>
          <DocPick files={files} onPick={setFiles} />
          <label className="fld">GitHub (선택)
            <input type="text" value={github} onChange={(e) => setGithub(e.target.value)} placeholder="아이디 또는 github.com/아이디/레포" maxLength={150} />
          </label>
          <p className="hint">PDF·Word·노션(md) 4개까지, 합쳐서 5MB · GitHub는 공개 레포 README만 읽습니다</p>
          <details>
            <summary className="hint">직군 (기본: 자동)</summary>
            <Seg label="직군" value={family} options={[["auto", "자동"], ...families]} onChange={setFamily} />
          </details>
          <details>
            <summary className="hint">지원할 공고 (선택)</summary>
            <textarea value={posting} onChange={(e) => setPosting(e.target.value)} rows={6} placeholder="자격요건·우대사항이 있는 공고 본문" />
          </details>
          <button className="btn" disabled={!sector || !(files.length || github.trim()) || running} onClick={submit}>
            {running ? "분석 중…" : "분석 시작"}
          </button>
          {err && <p className="err">{err}</p>}
          {job && <Progress job={job} />}
        </div>

        <div className="stack">
          {!job && <div className="panel"><p className="empty">자기소개서나 포트폴리오를 넣고 분석을 시작하세요</p></div>}
          {job?.status === "failed" && <p className="err">분석 실패: {job.error}</p>}
          {res && (
            <>
              <div className="row no-print">
                <button className="btn ghost sm" onClick={() => window.print()}>PDF로 저장</button>
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
      <p className="hint foot">채용 합불 판단에 쓰지 않습니다 · 파일과 이력서 원문은 저장하지 않습니다</p>
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
        </div>
      <div className="panel"><h3>강점 직군</h3><div className="big">{r.job_family?.ranking?.[0]?.label ?? "—"}</div>
        {r.job_family?.ranking && (
          <ol className="rank">{r.job_family.ranking.map((x) => <li key={x.id}><span>{x.label}</span><span className="num">{x.score}</span></li>)}</ol>
        )}</div>
      <div className="panel"><h3>준비도{r.job_family ? ` · ${r.sector?.label ?? ""} ${r.job_family.label}` : ""}</h3><div className="big num">{r.readiness.apply ?? "—"}</div>
        <p className="hint">공개 공고 기준</p></div>
      <div className="panel"><h3>이번 분석 비용</h3><div className="big num">{usd(job.cost?.usd)}</div>
        </div>
    </div>
  );
}

const Cite = ({ ns, onCite }) => (ns || []).map((n) => (
  <button key={n} className="cite" onClick={() => onCite(n)} aria-label={`근거 ${n} 보기`}>[{n}]</button>
));

function Strengths({ list, onCite }) {
  return (
    <div className="panel">
      <h2>① 강점 (STAR)</h2>
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
      <h2>② 부족한 역량</h2>
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
              <><b>추천하지 않음</b><p className="hint">{r.abstain_reason || "근거 없음"}</p></>
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
      ) : <p className="hint">0원 (규칙 엔진)</p>}
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
      ) : <p className="hint">[번호]를 누르면 근거가 보입니다</p>}
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
