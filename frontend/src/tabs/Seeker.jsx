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

const EV_TYPE = { corp: "기업 기준", market: "시장", resume: "이력서", posting: "공고 문장", plan: "경로 효과(계산)" };
const HOW = { dict: "별칭 사전", "dict-std": "LLM 표준명 → 사전", llm: "임베딩 후보 → LLM 선택", "dict-rule": "사전 + 규칙 판정(안전망)" };

function Result({ r }) {
  const p = r.path, b = r.baseline;
  return (
    <>
      <div className="panel">
        <div className="score">
          <div className="ring" style={{ "--p": r.readiness }}><span>{r.readiness}</span></div>
          <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
            <h2>{r.company.name} 기준 준비도</h2>
            <p className="hint">점수는 규칙으로 계산하고, LLM은 설명만 합니다. 같은 입력이면 항상 같은 점수가 나옵니다.</p>
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
            <thead><tr><th>스킬</th><th>구분</th><th>내 상태</th><th>근거</th></tr></thead>
            <tbody>
              {r.matrix.map((m) => (
                <tr key={m.skill_id}>
                  <td>{m.name}</td><td>{m.weight_label}</td>
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
            ? `${p.optimized ? "시간당 효과(기업 준비도 + 시장 공고 적합도 상승)가 큰 단계부터 배치했습니다." : "필수 갭부터, 공공 과정으로 기초를 채우고 기업 트랙으로 마무리합니다."} 총 ${p.total_hours}시간 (공공 ${p.hours_by_kind.public} · 기업 ${p.hours_by_kind.corp} · 결과물 ${p.hours_by_kind.proof}${p.hours_by_kind.self ? ` · 자습 ${p.hours_by_kind.self}` : ""}) · 주 ${p.weekly_hours}시간 기준 약 ${p.weeks}주.`
            : "이 기업 기준 갭이 없습니다."}
        </p>
        {p.market && (
          <div className="fit-row">
            <div><small>기업 준비도</small><span className="num">{r.readiness} → {p.steps.length ? p.steps[p.steps.length - 1].gain.readiness_after : r.readiness}점</span></div>
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
                  <span className={`chip ${KIND[s.kind][1]}`}>{KIND[s.kind][0]}</span></div>
                <div className="m">{(s.covers || [s.skill]).join(", ")} · {s.weight_label} 갭 · {s.hours}시간 · {s.meta}</div>
                {s.gain && <div className="gain"><span className="num">준비도 +{s.gain.readiness} → {s.gain.readiness_after}</span><span className="num">시장 적합도 +{s.gain.market_fit}</span><span className="num hint">시간당 {s.gain.per_hour}</span></div>}
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

      <div className="panel">
        <h2>공고만 본 추천 vs 기업 기준 추천</h2>
        <p className="hint">일반 개인 에이전트는 공고 문구만 봅니다. 기업이 등록한 요구역량을 쓰면 갭이 이렇게 달라집니다.</p>
        <div className="cmp">
          <div className="col">
            <h4>공고 문구만 사용 · 준비도 <span className="num">{b.readiness_posting}</span></h4>
            <div className="row">{b.gaps_posting.length ? b.gaps_posting.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
          <div className="col">
            <h4>기업 등록 기준 사용 · 준비도 <span className="num">{b.readiness_company}</span></h4>
            <div className="row">{b.gaps_company.length ? b.gaps_company.map((g) => <StatusChip key={g.skill_id} status={g.status}>{g.name}</StatusChip>) : <span className="hint">갭 없음</span>}</div>
          </div>
        </div>
        <div className="diff">
          {b.missed.length > 0 && <div className="plus">공고만 봤으면 놓쳤을 갭: {b.missed.join(", ")}</div>}
          {b.unnecessary.length > 0 && <div className="minus">공고만 봤으면 불필요하게 공부했을 것: {b.unnecessary.join(", ")}</div>}
          <div className="hint">공고 기준 준비도 {b.readiness_posting} → 기업 기준 준비도 {b.readiness_company}</div>
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
