import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { StatusChip } from "../ui.jsx";

const KIND = {
  public: ["공공", "tag-pub"],
  corp: ["기업", "tag-corp"],
  proof: ["결과물", "st-verify"],
  self: ["자습", "st-part"],
};
export const band = (v) => (v >= 70 ? "hi" : v >= 40 ? "mid" : "lo");
const BAND_LABEL = { hi: "높음", mid: "보통", lo: "부족" };
const reduceMotion = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

export default function Seeker({ companies, corpVersion, active, mode }) {
  const [personas, setPersonas] = useState([]);
  const [pid, setPid] = useState("");
  const [text, setText] = useState("");
  const [cid, setCid] = useState("A");
  const [hours, setHours] = useState(15);
  const [res, setRes] = useState(null);
  const [shown, setShown] = useState(0); // trace 진행 표시
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState(false);
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
    try {
      const r = pdf ? await api.diagnosePdf(pdf, c, h) : await api.diagnose({ resume_text: t, company_id: c, weekly_hours: h });
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
    setPid(p.id); setText(p.resume); setCid(p.default_company); setHours(p.weekly_hours);
    run({ instant: true, t: p.resume, c: p.default_company, h: p.weekly_hours, pdf: null });
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

  return (
    <section className="view" aria-label="취준생 진단">
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
          <div className="step"><span className="n">2</span><h2>가고 싶은 회사</h2></div>
          <select aria-label="가고 싶은 회사" value={cid} onChange={(e) => { setCid(e.target.value); if (ready) run({ instant: true, c: e.target.value }); }}>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.desc}</option>)}
          </select>
          <label className="fld"><span className="inline">주당 공부 <input type="number" min={1} max={80} value={hours}
            onChange={(e) => setHours(Math.max(1, Math.min(80, +e.target.value || 1)))}
            onBlur={() => ready && run({ instant: true })} /> 시간</span></label>
        </div>
        <div className="cell go">
          <div className="step"><span className="n">3</span><h2>진단</h2></div>
          <button className="btn big" disabled={busy || (!text.trim() && !pdfRef.current)} onClick={() => run()}>
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

      {ready ? <Result r={res} shown={shown} />
        : res?.trace ? <div className="panel"><h2>AI가 분석하는 중…</h2><Trace res={res} shown={shown} /></div>
        : <div className="panel"><p className="empty">{busy ? "진단 중…" : "위에서 이력서를 넣고 ‘내 준비도 진단하기’를 눌러 주세요."}</p></div>}
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
      <h2>학습 코치에게 묻기</h2>
      <p className="hint">궁금한 걸 물어보세요. AI가 회사 기준·교육과정·시장 통계·회사 문서를 직접 찾아보고 답해요. 실제 있는 과정만 추천해요.</p>
      <div className="row">
        {COACH_Q.map((x) => <button key={x} className="btn ghost sm" disabled={busy} onClick={() => ask(x)}>{x}</button>)}
      </div>
      <form className="coach-in" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input value={q} maxLength={300} onChange={(e) => setQ(e.target.value)} placeholder="예: Docker는 어떤 과정부터 들으면 돼요?" aria-label="코치에게 질문" />
        <button className="btn" disabled={busy || !q.trim()}>{busy ? "생각 중…" : "묻기"}</button>
      </form>
      {err && <p className="err">{err}</p>}
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
      <div className="ch"><h2>내 프로젝트 적합도</h2><StatusChip status={VERDICT_CLS[pf.verdict]}>{pf.verdict_label}</StatusChip></div>
      <div className={`big-n b-${band(pf.best_fit)}`}><span className="num">{pf.best_fit}</span><small>/100 · 가장 맞는 경험</small></div>
      <p className="hint">경험 {pf.n_units}개를 {company.job_title || company.name} 기준으로 채점{pf.domain_label ? ` · 도메인: ${pf.domain_label}` : ""}</p>
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
      <blockquote className="quote">“그 경험이 해당 부서에 필요한 경험이었는지가 중요하다” <cite>현업 인사 담당자</cite></blockquote>
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

function Roadmap({ r }) {
  const p = r.path;
  const [sel, setSel] = useState(0);
  const st = p.steps[Math.min(sel, p.steps.length - 1)];
  const nApply = p.steps.filter((x) => x.tier === "apply").length;
  const nWork = p.steps.length - nApply;
  return (
    <div className="panel card road">
      <div className="ch"><h2>할 일 로드맵</h2><span className="hint">{p.steps.length}단계 · {p.total_hours}시간 · 주 {p.weekly_hours}시간이면 약 {p.weeks}주</span></div>
      <div className="lanes" style={{ gridTemplateColumns: `${nApply}fr ${nWork}fr` }}>
        {nApply > 0 && <span className="lane apply">① 서류 문턱</span>}
        {nWork > 0 && <span className="lane work">② 입사 후 실무</span>}
      </div>
      <ol className="nodes" style={{ gridTemplateColumns: `repeat(${p.steps.length}, minmax(0,1fr))` }}>
        {p.steps.map((x, i) => (
          <li key={i} className={`${x.tier} ${i === sel ? "on" : ""}`} style={{ "--t": p.steps.length > 1 ? i / (p.steps.length - 1) : 0 }}>
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
          <div className="t">{isWork24(st) ? <a href={st.link} target="_blank" rel="noopener noreferrer">{st.title} <span aria-hidden="true">↗</span></a> : st.title}
            {" "}<span className={`chip ${KIND[st.kind][1]}`}>{KIND[st.kind][0]}</span></div>
          <div className="kv">
            <div><small>채우는 부족 역량</small><b><mark>{(st.covers || [st.skill]).join(", ")}</mark></b></div>
            <div><small>구분</small><b>{st.weight_label}</b></div>
            <div><small>시간</small><b className="num">{st.hours}시간</b></div>
            {st.gain && <div><small>끝내면</small><b>지원 <span className={`num c-${band(st.gain.apply_after ?? 0)}`}>{st.gain.apply_after ?? "-"}</span> · 실무 <span className={`num c-${band(st.gain.readiness_after)}`}>{st.gain.readiness_after}</span></b></div>}
          </div>
          <p className="w">{st.why.split(/(\[E\d+\])/).map((x, j) => /^\[E\d+\]$/.test(x) ? <b key={j}>{x}</b> : x)}</p>
        </div>
      )}
      <div className="foot">
        {p.market && <span className="hint">경로를 마치면 {r.company.region !== "미상" ? `${r.company.region} ` : ""}시장 공고 적합도 {p.market.fit_before} → <b>{p.market.fit_after}</b>점 ({p.market.postings}건)</span>}
        {Object.keys(r.evidence).length > 0 && (
          <details className="ev">
            <summary>근거 {Object.keys(r.evidence).length}건</summary>
            <ul>{Object.values(r.evidence).map((e) => <li key={e.id}><b>[{e.id}]</b> {EV_TYPE[e.type] ?? e.type} · {e.text}</li>)}</ul>
          </details>
        )}
      </div>
    </div>
  );
}

function Result({ r, shown }) {
  const p = r.path, b = r.baseline;
  const first = p.steps[0];
  return (
    <div className="dash">
      <div className="panel hero">
        <div className="h-msg">
          <p className="kicker">{r.company.name} · {r.company.job_title || r.company.desc}</p>
          <h2 className="headline">{verdict(r.readiness_apply, r.readiness)}</h2>
          <p className="hint">점수는 규칙으로 계산하고, AI는 근거를 인용해 설명만 해요.</p>
          <p className="legend"><i className="b-hi" />70+ 높음 <i className="b-mid" />40~69 보통 <i className="b-lo" />40 미만 · 부족한 역량</p>
        </div>
        <div className="sc">
          <div className={`ring b-${band(r.readiness_apply)}`} style={{ "--p": r.readiness_apply }}><span>{r.readiness_apply}</span></div>
          <div><b>지원 준비도 <em className={`bt b-${band(r.readiness_apply)}`}>{BAND_LABEL[band(r.readiness_apply)]}</em></b><small>입사 문턱(공고·필수)</small></div>
        </div>
        <div className="sc">
          <div className={`ring b-${band(r.readiness)}`} style={{ "--p": r.readiness }}><span>{r.readiness}</span></div>
          <div><b>실무 준비도 <em className={`bt b-${band(r.readiness)}`}>{BAND_LABEL[band(r.readiness)]}</em></b><small>입사 후 실제로 쓰는 역량</small></div>
        </div>
        <div className="todo">
          <small>지금 할 일 1순위</small>
          {first ? <>
            <div className="todo-t">{first.title}</div>
            <div className="hint"><mark>{(first.covers || [first.skill]).join(", ")}</mark> · {first.hours}시간{first.gain?.apply_after != null ? ` · 끝내면 지원 ${first.gain.apply_after}점` : ""}</div>
          </> : <div className="todo-t">채울 갭이 없어요</div>}
        </div>
      </div>

      {p.steps.length > 0 && <Roadmap r={r} />}
      {r.project_fit && <ProjectFit pf={r.project_fit} company={r.company} />}

      <div className="panel card gapc">
        <div className="ch"><h2>공고만 보면 놓치는 것</h2></div>
        <div className="vs">
          <div><small>공고만 볼 때 준비도</small><span className={`num c-${band(b.readiness_posting)}`}>{b.readiness_posting}</span></div>
          <span className="arrow">→</span>
          <div><small>실무 기준까지 보면</small><span className={`num c-${band(b.readiness_company)}`}>{b.readiness_company}</span></div>
        </div>
        {b.missed.length > 0 && <div className="grp"><small className="plus">공고엔 없지만 입사 후 필요</small><div className="row">{b.missed.map((x) => <span key={x} className="chip gap">{x}</span>)}</div></div>}
        {b.unnecessary.length > 0 && <div className="grp"><small className="minus">지원할 때만 보는 것</small><div className="row">{b.unnecessary.map((x) => <span key={x} className="chip">{x}</span>)}</div></div>}
      </div>
      <OthersPanel r={r} />

      <Coach r={r} />

      <details className="panel how">
        <summary><b>스킬별 상세 표</b> <span className="hint">{r.matrix.length}개 스킬 · 내 상태와 근거</span></summary>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>스킬</th><th>기준</th><th>구분</th><th>내 상태</th><th>근거</th></tr></thead>
            <tbody>
              {r.matrix.map((m) => (
                <tr key={m.skill_id}>
                  <td>{m.name}</td><td>{m.tier_label}</td><td>{m.weight_label}</td>
                  <td><StatusChip status={m.status}>{m.status_label}</StatusChip></td>
                  <td><span className="why">{m.evidence}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <HowPanel res={r} shown={shown} />
    </div>
  );
}

function OthersPanel({ r }) {
  return (
    <div className="panel card othc">
      <div className="ch"><h2>다른 회사라면?</h2><span className="hint">같은 이력서, 회사별 실무 준비도</span></div>
      <ul className="others">
        {r.others.map((o) => (
          <li key={o.company_id} className={`${o.current ? "cur" : ""} b-${band(o.readiness)}`} title={o.first_task ? `첫 할 일: ${o.first_task}` : "갭 없음"}>
            <span className="nm">{o.name.replace("(가상)", "")}</span>
            <span className="tr"><i style={{ width: `${o.readiness}%` }} /></span>
            <span className={`num c-${band(o.readiness)}`}>{o.readiness}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
