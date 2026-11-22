import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { StatusChip } from "../ui.jsx";

const KIND = {
  public: ["공공", "tag-pub"],
  corp: ["기업", "tag-corp"],
  proof: ["결과물", "st-verify"],
  self: ["자습", "st-part"],
};
const SENIOR = new Set(["경력", "시니어"]); // 3년 이상 경력 공고
// 지원자가 많이 몰리는 대표 직무 3개로 한정 (모든 직무·기업을 조사할 수는 없어서)
const FAMILIES = ["AI·ML 엔지니어", "백엔드", "데이터 엔지니어·분석"];
const shortName = (n) => n.replace(/\((공개 자료 재구성|가상)\)/g, "").trim();
export const band = (v) => (v >= 70 ? "hi" : v >= 40 ? "mid" : "lo");
const BAND_LABEL = { hi: "높음", mid: "보통", lo: "부족" };
const reduceMotion = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

export default function Seeker({ companies, corpVersion, active, mode }) {
  const [personas, setPersonas] = useState([]);
  const [pid, setPid] = useState("");
  const [text, setText] = useState("");
  const [cid, setCid] = useState("S"); // 시연 기본: 첫 예시 지원자의 기본 회사와 같게
  const [hours, setHours] = useState(10); // 입력칸은 뺐다: 기간 표시('약 N주')에만 쓰는 기본값
  const [res, setRes] = useState(null);
  const [shown, setShown] = useState(0); // trace 진행 표시
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState(false);
  const [showSenior, setShowSenior] = useState(false);
  const [cFam, setCFam] = useState(""); // 목록에 없는 회사: 직군 · 이름 · 공고
  const [cName, setCName] = useState("");
  const [cPost, setCPost] = useState("");
  const pdfRef = useRef(null); // 마지막 PDF (재진단용)
  const timer = useRef(null);
  const seen = useRef(corpVersion);

  useEffect(() => {
    api.personas().then((ps) => {
      setPersonas(ps);
      if (ps[0]) pick(ps[0], ps);
    }).catch((e) => setErr(e.message));
    return () => clearInterval(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run({ instant = false, t = text, c = cid, h = hours, pdf = pdfRef.current } = {}) {
    setBusy(true); setErr(""); clearInterval(timer.current);
    const custom = c === "custom" ? { name: cName.trim() || "직접 입력한 회사", job_family: cFam || FAMILIES[1], posting_text: cPost } : undefined;
    try {
      const r = pdf ? await api.diagnosePdf(pdf, c, h, custom) : await api.diagnose({ resume_text: t, company_id: c, weekly_hours: h, custom });
      if (instant || reduceMotion()) { setRes(r); setShown(r.trace.length); }
      else {
        setShown(0); let i = 0;
        timer.current = setInterval(() => {
          i += 1; setShown(i);
          if (i >= r.trace.length) { clearInterval(timer.current); setRes(r); }
        }, 200);
        setRes((prev) => (prev ? { ...prev, trace: r.trace } : { trace: r.trace, pending: true }));
      }
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  function pick(p) {
    pdfRef.current = null;
    setPid(p.id); setText(p.resume); setCid(p.default_company);
    run({ instant: true, t: p.resume, c: p.default_company, pdf: null });
  }

  // 기업 콘솔에서 요구역량·트랙이 바뀌면 같은 입력으로 즉시 다시 진단
  useEffect(() => {
    if (seen.current !== corpVersion) {
      seen.current = corpVersion;
      if (res && !res.pending) run({ instant: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [corpVersion, active]);

  const onPdf = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    pdfRef.current = f; setPid("");
    run({ pdf: f });
  };

  const ready = res && !res.pending;
  const famOf = (id) => companies.find((c) => c.id === id)?.job_family;
  const isCustom = cid === "custom";
  const fam = isCustom ? (cFam || FAMILIES[1]) : (famOf(cid) || FAMILIES[0]);
  // 취준생 기준: 기본은 신입·주니어(연차 미상 포함) 공고만. 경력 공고는 켜야 보인다 (실무 근거 계산에는 항상 포함)
  const visible = (c) => showSenior || !SENIOR.has(c.level) || c.id === cid;
  const pool = companies.filter(visible);
  const families = FAMILIES.map((f) => [f, pool.filter((c) => c.job_family === f).length, companies.filter((c) => c.job_family === f).length])
    .filter(([, , all]) => all > 0);
  const customOk = !isCustom || cPost.trim().length >= 20;
  function pickCompany(id) {
    if (id === "custom") { setCFam(fam); setCid("custom"); return; } // 공고를 붙여 넣은 뒤 진단
    setCid(id); if (ready) run({ instant: true, c: id });
  }
  function pickFamily(f) {
    if (isCustom) { setCFam(f); return; }
    // 직군을 바꾸면: 이미 진단했으면 그 직군에서 준비도가 가장 높은 회사, 아니면 첫 회사
    const inFam = pool.filter((c) => c.job_family === f).map((c) => c.id);
    if (!inFam.length) { setCFam(f); setCid("custom"); return; } // 그 직군에 신입 공고가 없으면 직접 입력으로
    const best = ready ? res.others.filter((o) => inFam.includes(o.company_id)).sort((a, b) => b.readiness - a.readiness)[0]?.company_id : null;
    pickCompany(best || inFam[0]);
  }

  return (
    <section className={`view seeker ${ready ? "docked" : ""}`} aria-label="취준생 진단">
      <div className="seeker-main">
      <div className="panel bar-in">
        <div className="cell">
          <div className="step"><span className="n">1</span><h2>이력서</h2></div>
          <select aria-label="예시 지원자" value={pid} onChange={(e) => { const p = personas.find((x) => x.id === e.target.value); if (p) pick(p); }}>
            {!pid && <option value="">직접 입력 / PDF</option>}
            {personas.map((p) => <option key={p.id} value={p.id}>예시: {p.name} (가상)</option>)}
          </select>
          <div className="row">
            <button type="button" className="btn ghost sm" aria-expanded={edit} onClick={() => setEdit((v) => !v)}>{edit ? "이력서 닫기" : "내 이력서 붙여 넣기"}</button>
            <label className="btn ghost sm filebtn">PDF 올리기<input type="file" accept="application/pdf,.pdf" onChange={onPdf} /></label>
            {pdfRef.current && <span className="hint">{pdfRef.current.name}{ready && res.extracted_chars != null ? ` · ${res.extracted_chars}자` : ""}</span>}
          </div>
        </div>
        <div className="cell">
          <div className="step"><span className="n">2</span><h2>희망 직군</h2></div>
          <div className="pick2">
            <select aria-label="희망 직군" value={fam} onChange={(e) => pickFamily(e.target.value)}>
              {families.map(([f, n]) => <option key={f} value={f}>{f} ({n}곳)</option>)}
            </select>
            <select aria-label="이 직군의 회사" value={cid}
              onChange={(e) => (e.target.value === "__senior" ? setShowSenior((v) => !v) : pickCompany(e.target.value))}>
              {pool.filter((c) => c.job_family === fam).map((c) => <option key={c.id} value={c.id}>{shortName(c.name)} · {c.job_title || c.desc}{SENIOR.has(c.level) ? ` (${c.level})` : ""}</option>)}
              <option value="custom">＋ 목록에 없는 회사 (공고 붙여 넣기)</option>
              <option value="__senior">{showSenior ? "－ 경력 공고 숨기기" : "＋ 경력 공고도 보기"}</option>
            </select>
          </div>
          {isCustom && (
            <div className="custom-in">
              <input type="text" value={cName} maxLength={40} onChange={(e) => setCName(e.target.value)}
                placeholder="회사·직무 이름 (예: 삼성SDS 소프트웨어)" aria-label="회사 이름" />
              <textarea value={cPost} maxLength={8000} onChange={(e) => setCPost(e.target.value)}
                placeholder="공고의 자격요건·우대사항을 붙여 넣어 주세요" aria-label="공고" />
            </div>
          )}
        </div>
        <div className="cell go">
          <div className="step"><span className="n">3</span><h2>진단</h2></div>
          <button className="btn big" disabled={busy || (!text.trim() && !pdfRef.current) || !customOk} onClick={() => run()}>
            {busy ? "진단 중…" : "내 준비도 진단하기"}
          </button>
          <p className="notice">채용 합불 판단에 쓰이지 않고, 이력서 원문은 저장하지 않아요.</p>
        </div>
        {edit && (
          <textarea className="resume" value={text} onChange={(e) => { setText(e.target.value); setPid(""); pdfRef.current = null; }}
            placeholder="프로젝트·인턴·교육·보유기술을 한 줄씩 적어 주세요" aria-label="이력서" />
        )}
        {busy && mode === "bedrock" && <p className="hint full">AI가 이력서를 읽는 중이에요 · 보통 10초 안팎</p>}
        {err && <p className="err full">{err}</p>}
      </div>

      {ready ? <Result r={res} shown={shown} onPick={pickCompany} showSenior={showSenior} />
        : res?.trace ? <div className="panel"><h2>AI가 분석하는 중…</h2><Trace res={res} shown={shown} /></div>
        : <div className="panel"><p className="empty">{busy ? "진단 중…" : "위에서 이력서를 넣고 ‘내 준비도 진단하기’를 눌러 주세요."}</p></div>}
      </div>
      {/* 학습 코치: 오른쪽에 붙어서 스크롤해도 따라온다 */}
      {ready && <aside className="coach-dock" aria-label="학습 코치"><Coach r={res} /></aside>}
    </section>
  );
}

function HowPanel({ res, shown }) {
  return (
    <details className="panel how">
      <summary><b>AI가 어떻게 판단했나요?</b> <span className="hint">찾은 스킬 {res.skills_found.length}개 · 실행 단계 {res.trace.length}개{res.usage ? ` · 모델 호출 ${res.usage.calls}회` : ""}</span></summary>
      <h3>이력서에서 찾은 스킬</h3>
      <div className="row">
        {res.skills_found.length ? res.skills_found.map((s) => (
          <span key={s.skill_id} title={`${s.evidence}
정규화: ${HOW[s.how] || s.how}`}><StatusChip status={s.status}>{s.name} · {s.status_label}</StatusChip></span>
        )) : <span className="hint">인식된 스킬이 없습니다</span>}
      </div>
      <h3>실행 단계 <span className="hint">({res.mode === "bedrock" ? "Bedrock" : "규칙 엔진"}{res.usage ? ` · 토큰 ${res.usage.input_tokens + res.usage.output_tokens}` : ""})</span></h3>
      <Trace res={res} shown={shown} />
      <h3>점수 계산식 (규칙)</h3>
      <div className="formula">{res.formula}</div>
    </details>
  );
}

function Trace({ res, shown }) {
  return (
    <>
      {res.fallbacks?.length > 0 && <p className="warn" role="status">일부 단계가 규칙 방식으로 대체됨: {res.fallbacks.join(" / ")}</p>}
      <ol className="trace">
        {res.trace.map((t, i) => (
          <li key={t.name} className={i < shown ? "done" : ""}>
            <span className="dot" />
            <div><b>{t.name}</b><small>{t.tool} · {t.ms}ms{t.detail ? ` · ${t.detail}` : ""}</small>
              {t.calls?.length > 0 && <small className="calls">{t.calls.map((c) => `${c.model} ${(c.ms / 1000).toFixed(1)}s${c.kind !== "embed" && c.in ? ` · ${c.in}→${c.out} tok` : ""}`).join("  |  ")}</small>}
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

const COACH_Q = ["하나만 먼저 한다면 뭐부터 할까요?", "이 회사는 이 기술을 실제로 어떤 업무에 써요?", "시장 수요가 큰 갭은 뭐예요?"];
const TOOL_LABEL = {
  get_company_criteria: "기업 기준 조회", search_courses: "과정 검색", market_stats: "시장 통계",
  company_docs: "기업 문서(KB) 검색", readiness_after: "준비도 계산(규칙)",
};

function Coach({ r }) {
  const [q, setQ] = useState("");
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  // 진단 대상이 바뀌면 대화를 비운다
  const key = r.company.id + ":" + r.skills_found.map((s) => s.skill_id + s.status).join(",");
  useEffect(() => { setLog([]); setErr(""); }, [key]);
  const logRef = useRef(null);
  useEffect(() => { const el = logRef.current; if (el) el.scrollTop = el.scrollHeight; }, [log, busy]); // 새 답이 오면 아래로

  async function ask(question) {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true); setErr("");
    try {
      // 이력서 원문이 아니라 스킬 상태 코드만 보낸다
      const statuses = Object.fromEntries(r.skills_found.map((s) => [s.skill_id, s.status]));
      const a = await api.coach(r.company.id, text, statuses);
      setLog((l) => [...l, { q: text, a }]); setQ("");
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="panel coach card">
      <div className="coach-top">
        <h2>학습 코치에게 묻기</h2>
        <p className="hint">{shortName(r.company.name)} 기준으로 답해요. 회사 기준·교육과정·시장 통계·회사 문서를 AI가 직접 찾아보고, 실제 있는 과정만 추천해요.</p>
      </div>
      <div className="coach-log" ref={logRef}>
        {log.length === 0 && !busy && (
          <div className="coach-empty">
            <p className="hint">이런 걸 물어볼 수 있어요</p>
            {COACH_Q.map((x) => <button key={x} className="btn ghost sm" disabled={busy} onClick={() => ask(x)}>{x}</button>)}
          </div>
        )}
      {log.map(({ q: qq, a }, i) => (
        <div className="turn" key={i}>
          <p className="q">{qq}</p>
          <p className="a">{a.answer.split(/(\[C:[^\]]+\])/).map((x, j) => /^\[C:/.test(x) ? <sup key={j} className="hint">과정</sup> : x)}</p>
          {a.courses.length > 0 && (
            <ul className="coach-courses">
              {a.courses.map((c) => (
                <li key={c.id}>{c.link && /^https:\/\/(www|hrd)\.work24\.go\.kr\//.test(c.link)
                  ? <a href={c.link} target="_blank" rel="noopener noreferrer">{c.title}</a> : c.title} · {c.provider} · {c.hours}시간</li>
              ))}
            </ul>
          )}
          {a.fallbacks.length > 0 && <p className="warn" role="status">{a.fallbacks.join(" / ")}</p>}
          <details>
            <summary className="hint">도구 호출 {a.tool_calls.length}회 · {a.mode === "bedrock" ? "Bedrock이 도구 선택" : "규칙 플래너가 도구 선택"}{a.usage ? ` · 모델 호출 ${a.usage.calls}회 · 토큰 ${a.usage.tokens}` : ""}</summary>
            <ol className="trace">
              {a.tool_calls.map((t, k) => <li key={k} className="done"><span className="dot" /><div><b>{TOOL_LABEL[t.tool] ?? t.tool}</b><small>{t.summary} · {t.ms}ms</small></div></li>)}
            </ol>
          </details>
        </div>
      ))}
        {busy && <p className="hint coach-wait">AI가 도구를 골라 찾아보는 중…</p>}
        {err && <p className="err">{err}</p>}
      </div>
      <form className="coach-in" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input value={q} maxLength={300} onChange={(e) => setQ(e.target.value)} placeholder="예: Docker는 어떤 과정부터 들으면 돼요?" aria-label="코치에게 질문" />
        <button className="btn" disabled={busy || !q.trim()}>{busy ? "…" : "묻기"}</button>
      </form>
    </div>
  );
}

const EV_TYPE = { corp: "기업 기준", market: "시장", resume: "이력서", posting: "공고 문장", plan: "경로 효과(계산)" };
const HOW = { dict: "별칭 사전", "dict-std": "LLM 표준명 → 사전", llm: "임베딩 후보 → LLM 선택", "dict-rule": "사전 + 규칙 판정(안전망)" };

const VERDICT_CLS = { fit: "own", partial: "part", far: "miss" };

function ProjectFit({ pf, company }) {
  const top = pf.units.slice(0, 3);
  return (
    <div className="panel card pfc">
      <div className="ch" title="“그 경험이 해당 부서에 필요한 경험이었는지가 중요하다” — 현업 인사 담당자">
        <h2><span className="cn">4</span>내 프로젝트</h2><StatusChip status={VERDICT_CLS[pf.verdict]}>{pf.verdict_label}</StatusChip></div>
      <div className={`big-n b-${band(pf.best_fit)}`}><span className="num">{pf.best_fit}</span><small>점 · 이 부서 실무에 가장 맞는 경험</small></div>
      {top.length > 0 ? (
        <ul className="pf">
          {top.map((u, i) => (
            <li key={i} title={u.matched.map((m) => m.name).concat(u.domain.length ? [`도메인: ${u.domain.join(", ")}`] : []).join(" · ")}>
              <div className="pf-t">{u.text.replace(/^[-·•\s]+/, "")}</div>
              <div className={`pf-bar b-${band(u.fit)}`} aria-hidden="true"><i style={{ width: `${u.fit}%` }} /></div>
              <span className="num">{u.fit}</span>
            </li>
          ))}
        </ul>
      ) : <p className="empty">이 부서 기준과 겹치는 경험이 없어요.</p>}
      {pf.mini_project && (
        <div className="mini">
          <small>추천 미니 프로젝트</small>
          <div>{pf.mini_project.skills.join(" + ")}로 {pf.domain_label || "이 부서"} 주제 하나</div>
        </div>
      )}
    </div>
  );
}

function verdict(apply, work) {
  if (apply >= 80 && work >= 80) return "지원도, 입사 후 실무도 준비가 잘 돼 있어요. 남은 갭만 다듬으면 돼요.";
  if (apply >= 70) return work < apply ? "서류 문턱은 거의 넘었어요. 이제 입사 후 실무에 쓰는 역량을 채우면 돼요." : "서류 문턱은 거의 넘었어요. 남은 필수 역량만 채우면 돼요.";
  if (apply >= 40) return "지원 기준의 필수 역량부터 채우면 서류 문턱을 넘을 수 있어요.";
  return "이 회사 기준과는 아직 거리가 있어요. 아래 순서대로 하나씩 채워 보세요.";
}

const isWork24 = (st) => st.link && /^https:\/\/(www|hrd)\.work24\.go\.kr\//.test(st.link) && st.kind === "public";

// 자습 단계용 공식 문서 (과정명을 지어내지 않도록, 고용24 과정이 아닌 단계에만 공식 문서 주소를 단다)
const DOCS = {
  git: "https://git-scm.com/doc", docker: "https://docs.docker.com/", kubernetes: "https://kubernetes.io/docs/home/",
  airflow: "https://airflow.apache.org/docs/", aws: "https://docs.aws.amazon.com/", aws_s3: "https://docs.aws.amazon.com/s3/",
  amazon_bedrock: "https://docs.aws.amazon.com/bedrock/", python: "https://docs.python.org/3/", pytorch: "https://pytorch.org/docs/stable/",
  spark: "https://spark.apache.org/docs/latest/", kafka: "https://kafka.apache.org/documentation/",
  terraform: "https://developer.hashicorp.com/terraform/docs", redis: "https://redis.io/docs/", mysql: "https://dev.mysql.com/doc/",
  postgresql: "https://www.postgresql.org/docs/", spring: "https://spring.io/guides", react: "https://react.dev/learn",
  fastapi: "https://fastapi.tiangolo.com/", grafana: "https://grafana.com/docs/", prometheus: "https://prometheus.io/docs/",
  mlflow: "https://mlflow.org/docs/latest/", huggingface: "https://huggingface.co/docs", helm: "https://helm.sh/docs/",
  argocd: "https://argo-cd.readthedocs.io/", github_actions: "https://docs.github.com/actions",
};

/** 단계 → 바로 갈 곳: 고용24 과정이면 수강 페이지, 자습이면 공식 문서 */
function linkFor(st) {
  if (!st) return null;
  if (isWork24(st)) return { href: st.link, label: "고용24 과정 보기" };
  if (st.kind === "self" && DOCS[st.skill_id]) return { href: DOCS[st.skill_id], label: "공식 문서 열기" };
  return null;
}

function Roadmap({ r }) {
  const p = r.path;
  const [sel, setSel] = useState(0);
  const MAX = 10;  // 노드가 많으면 이름이 잘려서 앞 10단계만 보여준다
  const shown = p.steps.slice(0, MAX);
  const rest = p.steps.length - shown.length;
  const st = shown[Math.min(sel, shown.length - 1)];
  const nApply = shown.filter((x) => x.tier === "apply").length;
  const nWork = shown.length - nApply;
  return (
    <div className="panel card road">
      <div className="ch"><h2><span className="cn">3</span>할 일 순서</h2><span className="hint">{p.steps.length}단계 · 약 {p.weeks}주</span></div>
      <div className="lanes" style={{ gridTemplateColumns: `${nApply}fr ${nWork}fr` }}>
        {nApply > 0 && <span className="lane apply">① 서류 문턱</span>}
        {nWork > 0 && <span className="lane work">② 입사 후 실무</span>}
      </div>
      <ol className="nodes" style={{ gridTemplateColumns: `repeat(${shown.length}, minmax(0,1fr))` }}>
        {shown.map((x, i) => (
          <li key={i} className={`${x.tier} ${i === sel ? "on" : ""}`}>
            <button type="button" onClick={() => setSel(i)} aria-pressed={i === sel}>
              <span className="dot">{i + 1}</span>
              <span className="lbl"><mark>{(x.covers || [x.skill]).join(", ")}</mark></span>
              <span className="sub">{x.hours}시간</span>
            </button>
          </li>
        ))}
      </ol>
      {st && (
        <div className="node-detail">
          <div className="t">{st.title} <span className={`chip ${KIND[st.kind][1]}`}>{KIND[st.kind][0]}</span></div>
          <p className="meta">{st.hours}시간{st.gain && <> · 끝내면 지원 <b className={`c-${band(st.gain.apply_after ?? 0)}`}>{st.gain.apply_after ?? "-"}</b> · 실무 <b className={`c-${band(st.gain.readiness_after)}`}>{st.gain.readiness_after}</b>점</>}</p>
          <p className="w">{st.why.replace(/\s*\[E\d+\]/g, "")}</p>
          {linkFor(st) && <a className="btn go-link" href={linkFor(st).href} target="_blank" rel="noopener noreferrer">{linkFor(st).label} ↗</a>}
        </div>
      )}
      {rest > 0 && (
        <details className="rest">
          <summary>이후 {rest}단계 더 보기</summary>
          <ol className="rest-l" start={MAX + 1}>
            {p.steps.slice(MAX).map((x, i) => {
              const lk = linkFor(x);
              return (
                <li key={i}><b>{(x.covers || [x.skill]).join(", ")}</b>
                  <span className="hint"> · {lk ? <a href={lk.href} target="_blank" rel="noopener noreferrer">{x.title} ↗</a> : x.title} · {x.hours}시간</span></li>
              );
            })}
          </ol>
        </details>
      )}
    </div>
  );
}

/* 목록에 없는 회사: ① 비슷한 직군 회사들의 실무 근거  ② AI 예측(참고, 점수 미반영)  ③ 한계 → 통합 플랫폼 */
function CustomPanel({ r }) {
  const c = r.custom, pred = c.prediction;
  return (
    <div className="panel card custom">
      <div className="ch">
        <h2>AI 예측 · {r.company.name}은 실무에서 이런 기술을 쓸 것 같아요 <em className="tag-ref">참고 · 점수 미반영</em></h2>
      </div>
      <div className="cust-grid">
        <div className="pred">
          <ol className="pred-l">
            {pred.items.map((x) => (
              <li key={x.skill_id}>
                <div><b>{x.name}</b> <span className={`chip ${x.status === "own" ? "st-own" : x.status === "miss" ? "st-miss" : "st-part"}`}>{x.status_label}</span></div>
                <small>{x.reason}</small>
              </li>
            ))}
          </ol>
          <p className="hint">{pred.mode === "bedrock" ? "Claude(Bedrock)가 공고와 직군 통계 후보 안에서만 골랐어요." : "직군 통계로 고른 규칙 예측이에요."}</p>
        </div>
        <div className="platform-note">
            <b>정확한 실무 기준은 기업만 알아요.</b> {r.company.name}이 SkillBridge에 실무 기준을 등록하면, 추정이 아니라 실제 기준으로 진단돼요.
            그래서 SkillBridge는 취준생·기업·기관이 함께 쓰는 통합 플랫폼이에요.
        </div>
      </div>
    </div>
  );
}

/* 결론 ①·② 카드: 같은 모양으로 '점수 · 부족한 것(+근거/첫 과정) · 이미 있는 것' */
function stepFor(r, sid, name) {
  return r.path.steps.find((st) => st.skill_id === sid || (st.covers || []).includes(name));
}

function ApplyCard({ r }) {
  const rows = r.matrix.filter((m) => m.weight_apply != null);
  const gaps = rows.filter((m) => m.status !== "own").sort((a, b) => b.weight_apply - a.weight_apply);
  const have = rows.filter((m) => m.status === "own");
  return (
    <div className="panel card concl">
      <div className="ch"><h2><span className="cn">1</span>서류 <small>공고 기준</small></h2>
        {r.company.apply_none ? <span className="big num muted">—</span>
          : <span className={`big num c-${band(r.readiness_apply)}`}>{r.readiness_apply}<small>점</small></span>}</div>
      {r.company.apply_none ? (
        <p className="ok-line neutral">{r.company.apply_verified
          ? <>공식 상세 공고에도 <b>기술 요구가 없어요</b>. 서류 뒤 <b>코딩·CS 테스트</b>(알고리즘·자료구조·DB·네트워크·OS)로 봐요.</>
          : <>확인한 공고 본문에는 기술 요구가 없었어요 (직무별 상세는 미확인). 서류 뒤 <b>코딩·CS 테스트</b>로 봐요.</>}<br />
          오른쪽 <b>실무</b>로 무엇을 준비할지 보세요.</p>
      ) : gaps.length ? (
        <ul className="cl">
          {gaps.slice(0, 5).map((m) => {
            const st = stepFor(r, m.skill_id, m.name);
            const lk = linkFor(st);
            return (
              <li key={m.skill_id}>
                <div className="cl-h"><b>{m.name}</b>{m.weight_apply === 2 && <span className="w">필수</span>}
                  <GapStatus m={m} />
                  {/* 회색 보조 정보는 커서를 올렸을 때만 이름 옆에 띄운다 */}
                  {(st || m.bridge?.reason) && <span className="cl-tip">
                    {m.bridge?.reason && <span className="tip-why">{m.bridge.reason}</span>}
                    {st && (lk ? <a href={lk.href} target="_blank" rel="noopener noreferrer" className="cl-link">{st.title} ↗</a> : st.title)}</span>}</div>
              </li>
            );
          })}
        </ul>
      ) : <p className="ok-line">공고 요구는 모두 갖췄어요.</p>}
      {have.length > 0 && <div className="have"><small>이미 있어요</small>{have.map((m) => <span key={m.skill_id} className="chip st-own">{m.name}</span>)}</div>}
    </div>
  );
}

function WorkCard({ r }) {
  const rows = r.matrix.filter((m) => m.weight_apply == null);
  const gaps = rows.filter((m) => m.status !== "own").sort((a, b) => (b.weight_work || 0) - (a.weight_work || 0));
  const have = rows.filter((m) => m.status === "own");
  const ev = r.work_evidence || {};
  return (
    <div className="panel card concl work">
      <div className="ch"><h2><span className="cn">2</span>실무 <small>면접부터 보는 역량 · 공고엔 없어요{r.company.custom ? " · 직군 추정" : ""}</small></h2>
        <span className={`big num c-${band(r.readiness)}`}>{r.readiness}<small>점</small></span></div>
      {gaps.length ? (
        <ul className="cl">
          {gaps.slice(0, 5).map((m) => {
            const e = ev[m.skill_id] || {};
            const tip = e.quote ? `“${e.quote}”${e.from ? ` · ${e.from}` : ""}` : "";
            return (
              <li key={m.skill_id} title={tip}>
                <div className="cl-h"><b>{m.name}</b>
                  <GapStatus m={m} />
                  {(e.from || e.family_used > 0 || m.bridge?.reason) && <span className="cl-tip">
                    {m.bridge?.reason && <span className="tip-why">{m.bridge.reason}</span>}
                    {e.family_n > 0 && e.family_used > 0 && <>같은 직군 {e.family_n}곳 중 {e.family_used}곳이 실무에서 써요</>}
                    {e.family_n > 0 && e.family_used > 0 && e.from && " · "}
                    {e.url ? <a className="cl-link" href={e.url} target="_blank" rel="noopener noreferrer">{srcLabel(e.from)} ↗</a>
                      : e.from && srcLabel(e.from)}</span>}</div>
              </li>
            );
          })}
        </ul>
      ) : <p className="ok-line">공고 밖 실무 기술도 모두 갖췄어요.</p>}
      {have.length > 0 && <div className="have"><small>이미 있어요</small>{have.map((m) => <span key={m.skill_id} className="chip st-own">{m.name}</span>)}</div>}
    </div>
  );
}

// 부족한 기술의 상태 칩: 이름은 없지만 비슷한 도구·이력서 경험으로 연결되면 그걸 먼저 보여 준다 (인정은 0.5까지)
function GapStatus({ m }) {
  if (m.bridge) return <span className={`chip bridge ${m.bridge.type}`}>{m.bridge.label}</span>;
  return m.status !== "miss" ? <StatusChip status={m.status}>{m.status_label}</StatusChip> : null;
}

const WEIGHT_TXT = { 2: "필수", 1: "우대" };
// 실무 근거 출처는 종류 하나로만 보여준다 (예: '현업 필수' → 현업 인터뷰, '토스증권 ML · 기술 블로그' → 기술 블로그)
function srcLabel(from = "") {
  for (const k of ["기술 블로그", "직무 소개", "현직자 인터뷰", "채용설명회", "발표", "고객 사례", "인터뷰"]) if (from.includes(k)) return k;
  if (from.startsWith("현업")) return "현업 인터뷰";
  return "근거";
}

function Result({ r, shown, onPick, showSenior }) {
  return (
    <div className="dash">
      <div className="verdict-line">
        <span className="who">{shortName(r.company.name)} · {r.company.job_title || r.company.desc}</span>
        <h2>{r.company.apply_none
          ? (r.readiness >= 70 ? "실무 역량은 잘 갖췄어요. 코딩·CS 테스트만 준비하면 돼요." : "서류는 코딩·CS 테스트로 보고, 입사하면 쓰는 역량부터 채워 보세요.")
          : verdict(r.readiness_apply, r.readiness)}</h2>
      </div>

      <ApplyCard r={r} />
      <WorkCard r={r} />
      {r.custom && <CustomPanel r={r} />}
      {r.path.steps.length > 0 && <Roadmap r={r} />}
      <OthersPanel r={r} onPick={onPick} showSenior={showSenior} />
      {r.project_fit && <ProjectFit pf={r.project_fit} company={r.company} />}
    </div>
  );
}

function OthersPanel({ r, onPick, showSenior }) {
  const fam = r.company.job_family || r.others.find((o) => o.current)?.job_family;
  const list = r.others.filter((o) => o.job_family === fam && (showSenior || o.current || !SENIOR.has(o.level)));
  const custom = r.company.custom;
  return (
    <div className="panel card othc">
      <div className="ch"><h2>{custom ? "이런 기업도 있어요" : "같은 직군 다른 회사"}</h2></div>
      {list.length <= 1 && <p className="hint">신입 공고가 아직 적어요. 회사 목록에서 ‘경력 공고도 보기’를 켜 보세요.</p>}
      <ul className="others">
        {list.map((o) => (
          <li key={o.company_id} className={`${o.current ? "cur" : ""} b-${band(o.readiness)}`} title={o.first_task ? `첫 할 일: ${o.first_task}` : "갭 없음"}
            onClick={() => !o.current && onPick(o.company_id)} role="button" tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && !o.current && onPick(o.company_id)}>
            <span className="nm">{shortName(o.name)}{o.level && o.level !== "미상" && <em className={`lv ${SENIOR.has(o.level) ? "sr" : ""}`}>{o.level}</em>}</span>
            <span className="tr"><i style={{ width: `${o.readiness}%` }} /></span>
            <span className={`num c-${band(o.readiness)}`}>{o.readiness}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
