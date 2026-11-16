import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Bars, StatusChip } from "../ui.jsx";

const KIND = {
  public: ["공공", "tag-pub"],
  corp: ["기업", "tag-corp"],
  proof: ["결과물", "st-verify"],
  self: ["자습", "st-part"],
};
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
      <div className="grid-side">
        <div className="panel input">
          <div className="step"><span className="n">1</span><h2>이력서 넣기</h2></div>
          <label className="fld">예시 지원자로 바로 해 보기
            <select value={pid} onChange={(e) => { const p = personas.find((x) => x.id === e.target.value); if (p) pick(p); }}>
              {!pid && <option value="">직접 입력 / PDF</option>}
              {personas.map((p) => <option key={p.id} value={p.id}>{p.name} (가상)</option>)}
            </select>
          </label>
          <label className="fld">또는 내 이력서 붙여 넣기
            <textarea value={text} onChange={(e) => { setText(e.target.value); setPid(""); pdfRef.current = null; }}
              placeholder="프로젝트·인턴·교육·보유기술을 한 줄씩 적어 주세요" />
          </label>
          <label className="fld file">PDF로 올리기
            <input type="file" accept="application/pdf,.pdf" onChange={onPdf} />
          </label>
          {pdfRef.current && <p className="hint">PDF: {pdfRef.current.name}{ready && res.extracted_chars != null ? ` · ${res.extracted_chars}자 읽음` : ""}</p>}

          <div className="step"><span className="n">2</span><h2>가고 싶은 회사</h2></div>
          <select aria-label="가고 싶은 회사" value={cid} onChange={(e) => { setCid(e.target.value); if (ready) run({ instant: true, c: e.target.value }); }}>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.desc}</option>)}
          </select>
          <label className="fld">일주일에 공부할 수 있는 시간
            <span className="inline"><input type="number" min={1} max={80} value={hours}
              onChange={(e) => setHours(Math.max(1, Math.min(80, +e.target.value || 1)))}
              onBlur={() => ready && run({ instant: true })} /> 시간</span>
          </label>

          <div className="step"><span className="n">3</span><h2>진단하기</h2></div>
          <button className="btn big" disabled={busy || (!text.trim() && !pdfRef.current)} onClick={() => run()}>
            {busy ? "진단 중…" : "내 준비도 진단하기"}
          </button>
          {busy && mode === "bedrock" && <p className="hint">AI가 이력서를 읽는 중이에요 · 보통 10초 안팎</p>}
          {err && <p className="err">{err}</p>}
          <p className="notice">결과는 나에게만 보이고 채용 합불 판단에 쓰이지 않아요. 이력서 원문은 저장하지 않아요.</p>
        </div>

        <div className="stack">
          {ready ? <Result r={res} />
            : res?.trace ? <div className="panel"><h2>AI가 분석하는 중…</h2><Trace res={res} shown={shown} /></div>
            : <div className="panel"><p className="empty">{busy ? "진단 중…" : "왼쪽에서 이력서를 넣고 ‘내 준비도 진단하기’를 눌러 주세요."}</p></div>}
          {ready && (
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
          )}
        </div>
      </div>
    </section>
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
    <div className="panel coach">
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
  return (
    <div className="panel">
      <h2>내 프로젝트가 이 부서에 맞나요?</h2>
      <blockquote className="quote">“프로젝트 경험은 필수인데, 그 경험이 해당 부서에 필요한 경험이었는지가 중요하다” <cite>현업 인사 담당자</cite></blockquote>
      <p className="hint">경험 하나하나가 {company.job_title || company.name} 기준을 몇 점어치 보여주는지 계산했어요{pf.domain_label ? ` · 부서 도메인: ${pf.domain_label}` : ""}.</p>
      <div className="row"><StatusChip status={VERDICT_CLS[pf.verdict]}>{pf.verdict_label}</StatusChip><span className="hint">가장 맞는 경험 <span className="num">{pf.best_fit}</span>점 · 경험 {pf.n_units}개</span></div>
      {pf.units.length > 0 ? (
        <ul className="pf">
          {pf.units.map((u, i) => (
            <li key={i}>
              <div className="pf-bar" aria-hidden="true"><i style={{ width: `${u.fit}%` }} /></div>
              <span className="num">{u.fit}</span>
              <div>
                <div>{u.text}</div>
                <div className="row">
                  {u.matched.map((m) => <StatusChip key={m.skill_id} status={m.status}>{m.name}</StatusChip>)}
                  {u.domain.length > 0 && <span className="chip">도메인 일치: {u.domain.join(", ")}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="empty">이 부서 기준과 겹치는 프로젝트·인턴·연구 경험이 없습니다.</p>}
      {pf.mini_project && (
        <div className="mini">
          <h4>추천: 이 부서에 맞는 미니 프로젝트 하나</h4>
          <div className="m">{pf.mini_project.skills.join(" + ")}를 써서 {pf.domain_label || "이 부서"} 주제로 작게 만들어 보세요.</div>
          {pf.mini_project.show.some((x) => !x.what.endsWith("결과 화면)")) && (
            <ul>{pf.mini_project.show.filter((x) => !x.what.endsWith("결과 화면)")).map((x, i) => <li key={i}><b>{x.skill}</b>: 현업이 본다고 한 것 “{x.what}”</li>)}</ul>
          )}
          <p className="hint">결과물에는 각 스킬을 실제로 쓴 흔적(코드·설정·결과 화면)을 남기고, 이력서에 프로젝트 한 줄로 적으세요.</p>
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

function Result({ r }) {
  const p = r.path, b = r.baseline;
  const first = p.steps[0];
  const tiers = [["apply", "① 서류 문턱 넘기 (지원 기준)"], ["work", "② 입사 후 실무 준비 (실무 기준)"]];
  return (
    <>
      <div className="panel summary">
        <p className="kicker">{r.company.name} · {r.company.job_title || r.company.desc}</p>
        <h2 className="headline">{verdict(r.readiness_apply, r.readiness)}</h2>
        <div className="scores">
          <div className="sc">
            <div className="ring" style={{ "--p": r.readiness_apply }}><span>{r.readiness_apply}</span></div>
            <div><b>지원 준비도</b><small>공고·필수 기준, 즉 입사 문턱을 얼마나 넘었나</small></div>
          </div>
          <div className="sc">
            <div className="ring alt" style={{ "--p": r.readiness }}><span>{r.readiness}</span></div>
            <div><b>실무 준비도</b><small>기업이 입사 후 실제로 쓰는 역량을 얼마나 갖췄나</small></div>
          </div>
        </div>
        {first ? (
          <div className="todo">
            <small>지금 할 일 1순위</small>
            <div className="todo-t">{first.title}</div>
            <div className="hint">{(first.covers || [first.skill]).join(", ")} · {first.hours}시간 · <span className={`chip ${KIND[first.kind][1]}`}>{KIND[first.kind][0]}</span>{first.gain?.apply_after != null ? ` · 끝내면 지원 준비도 ${first.gain.apply_after}점` : ""}</div>
          </div>
        ) : <div className="todo"><div className="todo-t">이 회사 기준으로 채울 갭이 없어요.</div></div>}
        {p.steps.length > 0 && <p className="hint">전체 {p.steps.length}단계 · {p.total_hours}시간 · 주 {p.weekly_hours}시간이면 약 {p.weeks}주. 점수는 규칙으로 계산하고, AI는 설명만 써요.</p>}
      </div>

      {p.steps.length > 0 && (
        <div className="panel">
          <h2>할 일 순서</h2>
          <p className="hint">서류 문턱(지원 기준)부터 넘고, 그다음 입사 후 실무 역량을 준비해요. 같은 단계 안에서는 시간 대비 효과가 큰 것부터예요.</p>
          {tiers.map(([tk, tl]) => {
            const steps = p.steps.map((st, i) => [st, i]).filter(([st]) => st.tier === tk);
            if (!steps.length) return null;
            return (
              <div key={tk} className="tier">
                <h3>{tl}</h3>
                <ol className="path">
                  {steps.map(([st, i]) => (
                    <li key={i} style={{ "--n": `"${i + 1}"` }}>
                      <div>
                        <div className="t">{st.link && /^https:\/\/(www|hrd)\.work24\.go\.kr\//.test(st.link) && st.kind === "public"
                          ? <a href={st.link} target="_blank" rel="noopener noreferrer">{st.title}</a> : st.title}{" "}
                          <span className={`chip ${KIND[st.kind][1]}`}>{KIND[st.kind][0]}</span></div>
                        <div className="m">{(st.covers || [st.skill]).join(", ")} · {st.weight_label} · {st.hours}시간{st.gain ? ` · 지원 ${st.gain.apply_after ?? "-"}점 · 실무 ${st.gain.readiness_after}점이 돼요` : ""}</div>
                        <details className="why-d"><summary>왜 이 순서인가요?</summary>
                          <div className="w">{st.why.split(/(\[E\d+\])/).map((x, j) => /^\[E\d+\]$/.test(x) ? <b key={j}>{x}</b> : x)}</div>
                          <div className="w">{st.meta}</div>
                        </details>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            );
          })}
          {p.market && <p className="hint">이 경로를 마치면 {r.company.region !== "미상" ? `${r.company.region} ` : ""}시장 공고 평균 적합도 {p.market.fit_before} → {p.market.fit_after}점 ({p.market.postings}건 기준)</p>}
          {Object.keys(r.evidence).length > 0 && (
            <details className="ev">
              <summary>근거 목록 {Object.keys(r.evidence).length}건 (설명은 이 목록만 인용해요)</summary>
              <ul>{Object.values(r.evidence).map((e) => <li key={e.id}><b>[{e.id}]</b> {EV_TYPE[e.type] ?? e.type} · {e.text}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {r.project_fit && <ProjectFit pf={r.project_fit} company={r.company} />}

      <Coach r={r} />

      <div className="panel">
        <h2>공고만 보고 준비하면 놓치는 것</h2>
        <div className="cmp">
          <div className="col">
            <h4>공고(지원 기준)만 볼 때 갭 · 준비도 <span className="num">{b.readiness_posting}</span></h4>
            <div className="row">{b.gaps_posting.length ? b.gaps_posting.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
          <div className="col">
            <h4>실무 기준까지 볼 때 갭 · 준비도 <span className="num">{b.readiness_company}</span></h4>
            <div className="row">{b.gaps_company.length ? b.gaps_company.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
        </div>
        <div className="diff">
          {b.missed.length > 0 && <div className="plus">공고엔 없지만 입사 후 필요한 것: {b.missed.join(", ")}</div>}
          {b.unnecessary.length > 0 && <div className="minus">지원할 때만 보는 것: {b.unnecessary.join(", ")}</div>}
        </div>
      </div>

      <details className="panel how">
        <summary><b>스킬별 상세 표</b> <span className="hint">{r.matrix.length}개 스킬 · 내 상태와 근거</span></summary>
        <div className="row">
          <StatusChip status="own" /><StatusChip status="part" /><StatusChip status="verify" /><StatusChip status="miss" />
        </div>
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

      <div className="panel">
        <h2>다른 회사라면?</h2>
        <p className="hint">같은 이력서도 회사마다 준비도와 첫 할 일이 달라요.</p>
        <Bars unit="" rows={r.others.map((o) => ({
          key: o.company_id, label: o.name.replace("(가상)", ""), value: o.readiness, cls: o.current ? "" : "alt",
          note: `${o.first_task ? `첫 할 일: ${o.first_task}` : "갭 없음"}${o.project_fit != null ? ` · 가장 맞는 경험 ${o.project_fit}점` : ""}`,
        }))} />
      </div>
    </>
  );
}
