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
        <div className="panel">
          <h2>내 프로필</h2>
          <label className="fld">예시 지원자 (가상)
            <select value={pid} onChange={(e) => { const p = personas.find((x) => x.id === e.target.value); if (p) pick(p); }}>
              {!pid && <option value="">직접 입력 / PDF</option>}
              {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="fld">이력서 텍스트
            <textarea value={text} onChange={(e) => { setText(e.target.value); setPid(""); pdfRef.current = null; }}
              placeholder="경력·프로젝트·교육·보유기술을 붙여 넣으세요" />
          </label>
          <label className="fld">또는 PDF 업로드
            <input type="file" accept="application/pdf,.pdf" onChange={onPdf} />
          </label>
          {pdfRef.current && <p className="hint">PDF: {pdfRef.current.name}{ready && res.extracted_chars != null ? ` · ${res.extracted_chars}자 추출` : ""}</p>}
          <label className="fld">목표 기업
            <select value={cid} onChange={(e) => { setCid(e.target.value); if (ready) run({ instant: true, c: e.target.value }); }}>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.desc}</option>)}
            </select>
          </label>
          <label className="fld">주당 학습 가능 시간
            <input type="number" min={1} max={80} value={hours}
              onChange={(e) => setHours(Math.max(1, Math.min(80, +e.target.value || 1)))}
              onBlur={() => ready && run({ instant: true })} />
          </label>
          <button className="btn" disabled={busy || (!text.trim() && !pdfRef.current)} onClick={() => run()}>
            {busy ? "진단 중…" : "진단 실행"}
          </button>
          {busy && mode === "bedrock" && <p className="hint">Bedrock 호출 중 · 보통 10초 안팎 걸려요</p>}
          {err && <p className="err">{err}</p>}
          {ready && (
            <div>
              <h3>추출된 스킬</h3>
              <div className="row" style={{ marginTop: 6 }}>
                {res.skills_found.length ? res.skills_found.map((s) => (
                  <span key={s.skill_id} title={`${s.evidence}
정규화: ${HOW[s.how] || s.how}`}><StatusChip status={s.status}>{s.name} · {s.status_label}</StatusChip></span>
                )) : <span className="hint">인식된 스킬이 없습니다</span>}
              </div>
            </div>
          )}
          {res?.trace && (
            <div>
              <h3>에이전트 실행 단계 <span className="hint">({res.mode === "bedrock" ? "Bedrock" : "목업"} 모드{res.usage ? ` · 호출 ${res.usage.calls}회 · 토큰 ${res.usage.input_tokens + res.usage.output_tokens}` : ""})</span></h3>
              {res.fallbacks?.length > 0 && (
                <p className="warn" role="status">일부 단계가 규칙 방식으로 대체됨: {res.fallbacks.join(" / ")}</p>
              )}
              <ol className="trace" style={{ marginTop: 6 }}>
                {res.trace.map((t, i) => (
                  <li key={t.name} className={i < shown ? "done" : ""}>
                    <span className="dot" />
                    <div><b>{t.name}</b><small>{t.tool} · {t.ms}ms{t.detail ? ` · ${t.detail}` : ""}</small>
                      {t.calls?.length > 0 && <small className="calls">{t.calls.map((c) => `${c.model} ${(c.ms / 1000).toFixed(1)}s${c.kind !== "embed" && c.in ? ` · ${c.in}→${c.out} tok` : ""}`).join("  |  ")}</small>}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <p className="notice">개인 진단 결과는 본인에게만 보이며 채용 합불 판단에 쓰이지 않습니다. 이력서 원문은 저장하지 않고, 기업에는 갭 스킬의 익명 집계만 제공합니다.</p>
        </div>

        <div className="stack">{ready ? <Result r={res} /> : <div className="panel"><p className="empty">{busy ? "진단 중…" : "왼쪽에서 진단을 실행하세요."}</p></div>}</div>
      </div>
    </section>
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
      <p className="hint">에이전트가 필요한 도구(기업 기준 · 과정 검색 · 시장 통계 · {r.company.name} 문서 · 준비도 계산)를 골라 근거를 모은 뒤 답합니다. 과정은 카탈로그에 있는 것만, 점수는 규칙 계산값만 씁니다. 이력서 원문은 보내지 않습니다.</p>
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

function Result({ r }) {
  const p = r.path, b = r.baseline;
  return (
    <>
      <div className="panel">
        <div className="score">
          <div className="ring-cap"><div className="ring" style={{ "--p": r.readiness_apply }}><span>{r.readiness_apply}</span></div><small>① 지원</small></div>
          <div className="ring-cap"><div className="ring alt" style={{ "--p": r.readiness }}><span>{r.readiness}</span></div><small>② 실무</small></div>
          <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
            <h2>{r.company.name} · 지원 준비도 {r.readiness_apply} / 실무 준비도 {r.readiness}</h2>
            <p className="hint">지원 준비도는 공고에 적힌 입사 문턱, 실무 준비도는 기업이 등록한 '입사 후 실제로 쓰는 역량' 기준입니다. 점수는 규칙으로 계산하고, LLM은 설명만 합니다.</p>
            <div className="formula">{r.formula}</div>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>역량 갭 매트릭스</h2>
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
      </div>

      <div className="panel">
        <h2>맞춤 학습경로</h2>
        <p className="hint">
          {p.steps.length
            ? `① 지원 기준(공고) 갭으로 먼저 입사 문턱을 넘고, ② 실무 기준(기업 등록) 갭으로 입사 후 쓸 역량을 준비합니다. 각 단계 안에서는 시간당 효과가 큰 순서입니다. 총 ${p.total_hours}시간 (공공 ${p.hours_by_kind.public} · 기업 ${p.hours_by_kind.corp} · 결과물 ${p.hours_by_kind.proof}${p.hours_by_kind.self ? ` · 자습 ${p.hours_by_kind.self}` : ""}) · 주 ${p.weekly_hours}시간 기준 약 ${p.weeks}주.`
            : "이 기업 기준 갭이 없습니다."}
        </p>
        {p.market && (
          <div className="fit-row">
            <div><small>지원 준비도</small><span className="num">{p.apply_before ?? r.readiness_apply} → {p.apply_after ?? r.readiness_apply}점</span></div>
            <div><small>실무 준비도</small><span className="num">{p.work_before ?? r.readiness} → {p.work_after ?? r.readiness}점</span></div>
            <div><small>시장 공고 평균 적합도 ({p.market.postings}건)</small><span className="num">{p.market.fit_before} → {p.market.fit_after}점</span></div>
            <div><small>{p.market.threshold}점 넘는 공고</small><span className="num">{p.market.qualified_before}% → {p.market.qualified_after}%</span></div>
          </div>
        )}
        <ol className="path">
          {p.steps.map((s, i) => (
            <li key={i}>
              <div>
                <div className="t">{s.link && /^https:\/\/(www|hrd)\.work24\.go\.kr\//.test(s.link) && s.kind === "public"
                  ? <a href={s.link} target="_blank" rel="noopener noreferrer">{s.title}</a> : s.title}{" "}
                  <span className={`chip ${KIND[s.kind][1]}`}>{KIND[s.kind][0]}</span>{" "}
                  <span className="chip">{s.tier === "apply" ? "① 지원" : "② 실무"}</span></div>
                <div className="m">{(s.covers || [s.skill]).join(", ")} · {s.tier_label} {s.weight_label} 갭 · {s.hours}시간 · {s.meta}</div>
                {s.gain && <div className="gain">{s.gain.apply_after != null && <span className="num">지원 +{s.gain.apply} → {s.gain.apply_after}</span>}<span className="num">실무 +{s.gain.readiness} → {s.gain.readiness_after}</span><span className="num">시장 적합도 +{s.gain.market_fit}</span><span className="num hint">시간당 {s.gain.per_hour}</span></div>}
                <div className="w">{s.why.split(/(\[E\d+\])/).map((x, j) => /^\[E\d+\]$/.test(x) ? <b key={j}>{x}</b> : x)}</div>
              </div>
            </li>
          ))}
        </ol>
        {Object.keys(r.evidence).length > 0 && (
          <details className="ev">
            <summary>근거 목록 ({Object.keys(r.evidence).length}건) — 설명은 이 목록만 인용합니다</summary>
            <ul>{Object.values(r.evidence).map((e) => <li key={e.id}><b>[{e.id}]</b> {EV_TYPE[e.type] ?? e.type} · {e.text}</li>)}</ul>
          </details>
        )}
      </div>

      <Coach r={r} />

      <div className="panel">
        <h2>지원 기준(공고) vs 실무 기준(기업)</h2>
        <p className="hint">공고는 입사 문턱을 알려줍니다. 기업이 등록한 실무 기준은 입사 후 실제로 쓰는 역량입니다. 공고만 보고 준비하면 오른쪽 갭은 입사 후에 메워야 합니다.</p>
        <div className="cmp">
          <div className="col">
            <h4>① 지원 기준 (공고) · 준비도 <span className="num">{b.readiness_posting}</span></h4>
            <div className="row">{b.gaps_posting.length ? b.gaps_posting.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
          <div className="col">
            <h4>② 실무 기준 (기업 등록) · 준비도 <span className="num">{b.readiness_company}</span></h4>
            <div className="row">{b.gaps_company.length ? b.gaps_company.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
        </div>
        <div className="diff">
          {b.missed.length > 0 && <div className="plus">공고엔 없지만 입사 후 필요한 것: {b.missed.join(", ")}</div>}
          {b.unnecessary.length > 0 && <div className="minus">지원할 때만 보는 것 (실무 기준엔 없음): {b.unnecessary.join(", ")}</div>}
          <div className="hint">학습경로는 두 기준의 갭을 모두 다룹니다 (지원 먼저 → 실무).</div>
        </div>
      </div>

      <div className="panel">
        <h2>다른 기업과 비교</h2>
        <p className="hint">같은 프로필이 기업마다 다른 준비도와 첫 학습 과제를 받습니다.</p>
        <Bars unit="" rows={r.others.map((o) => ({
          key: o.company_id, label: o.name.replace("(가상)", ""), value: o.readiness, cls: o.current ? "" : "alt",
          note: o.first_task ? `첫 과제: ${o.first_task}` : "갭 없음",
        }))} />
      </div>
    </>
  );
}
