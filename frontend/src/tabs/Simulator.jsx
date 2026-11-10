import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

// 기업 기준 시뮬레이터: 요구역량을 바꾸면 우리 지원자 풀 중 '지원 가능선' 이상이 몇 %가 되는가.
// 저장하지 않고 계산만 한다. '이 기준 적용'을 눌러야 실제 요구역량이 바뀐다.
const W_LABEL = { 2: "필수", 1: "우대", 0: "제외" };

function Hist({ cur, scen, threshold }) {
  const max = Math.max(1, ...cur, ...scen);
  return (
    <div className="hist" role="img" aria-label={`준비도 분포. 지원 가능선 ${threshold}점`}>
      {cur.map((v, i) => (
        <div key={i} className={`hbin ${i * 10 >= threshold ? "pass" : ""}`} title={`${i * 10}~${i === 9 ? 100 : i * 10 + 9}점 · 현재 ${v}명 · 시나리오 ${scen[i]}명`}>
          <div className="hbars">
            <div className="hb cur" style={{ height: `${(v / max) * 100}%` }} />
            <div className="hb scen" style={{ height: `${(scen[i] / max) * 100}%` }} />
          </div>
          <span className="hx num">{i * 10}</span>
        </div>
      ))}
      <div className="hline" style={{ left: `${threshold}%` }}><span>지원 가능선 {threshold}점</span></div>
    </div>
  );
}

export default function Simulator({ company, onApply }) {
  const base = useMemo(() => {
    const ex = new Set(company.excluded || []);
    return Object.fromEntries(Object.entries(company.requirements).filter(([k, w]) => !ex.has(k) && (w === 1 || w === 2)));
  }, [company]);
  const names = useMemo(() => Object.fromEntries(company.requirements_view.map((r) => [r.skill_id, r.name])), [company]);
  const [scen, setScen] = useState(base);
  const [tracks, setTracks] = useState(false);
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { setScen(base); setTracks(false); }, [base]);
  useEffect(() => {
    let live = true;
    const reqs = Object.fromEntries(Object.entries(scen).filter(([, w]) => w > 0));
    if (!Object.keys(reqs).length) { setErr("필수 또는 우대 역량이 하나 이상 필요합니다"); return undefined; }
    const t = setTimeout(() => {
      api.simulate(company.tenant_id, reqs, tracks).then((x) => { if (live) { setR(x); setErr(""); } })
        .catch((e) => live && setErr(e.message));
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [scen, tracks, company.tenant_id]);

  const changed = JSON.stringify(scen) !== JSON.stringify(base);
  const setW = (sid, w) => setScen((s) => ({ ...s, [sid]: w }));

  return (
    <div className="panel">
      <h2>기준 시뮬레이터 <span className="hint">(저장하지 않고 미리 계산)</span></h2>
      <p className="hint">요구역량을 바꾸거나 우리 교육 트랙 이수를 가정하면, 지원자 풀 중 실무 준비도 {r?.threshold ?? 70}점 이상이 몇 %가 되는지 바로 계산합니다.
        취준생 진단과 같은 점수 공식을 씁니다.</p>
      {err && <p className="err">{err}</p>}
      {r && (
        <div className="sim">
          <div className="sim-hero">
            <div><small>지금 기준</small><span className="num big2">{r.current.share}%</span></div>
            <span className="arrow" aria-hidden="true">→</span>
            <div><small>시나리오</small><span className="num big2">{r.scenario.share}%</span></div>
            <span className={`delta num ${r.delta_pp > 0 ? "up" : r.delta_pp < 0 ? "down" : ""}`}>{r.delta_pp > 0 ? "+" : ""}{r.delta_pp}%p</span>
            <small className="hint">지원자 {r.n}명 기준{r.fake_included ? " (시연용 가상 기록 포함)" : ""}</small>
          </div>
          <ul className="legend"><li><i className="sw cur" />지금 기준</li><li><i className="sw scen" />시나리오</li></ul>
          <Hist cur={r.current.hist} scen={r.scenario.hist} threshold={r.threshold} />

          <h3>시나리오 기준</h3>
          <div className="sim-reqs">
            {Object.keys(base).map((sid) => (
              <div key={sid} className="sim-req">
                <span>{names[sid] ?? sid}</span>
                <div className="seg sm" role="group" aria-label={`${names[sid]} 가중치`}>
                  {[2, 1, 0].map((w) => (
                    <button key={w} aria-pressed={(scen[sid] ?? 0) === w} onClick={() => setW(sid, w)}>{W_LABEL[w]}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <label className="check"><input type="checkbox" checked={tracks} onChange={(e) => setTracks(e.target.checked)} />
            지원자가 우리 교육 트랙을 이수했다고 가정 {r.tracks_effect ? `(${r.tracks_effect.skills.join(", ")})` : "(등록된 트랙 없음)"}</label>

          <h3>한 가지만 바꾼다면</h3>
          <ol className="levers">
            {r.levers.map((l) => (
              <li key={l.skill_id}>
                <span>{l.name} <span className="hint">{l.change}</span></span>
                <span className={`num ${l.delta_pp > 0 ? "up" : ""}`}>{l.delta_pp > 0 ? "+" : ""}{l.delta_pp}%p</span>
                <button className="btn-ghost" onClick={() => setW(l.skill_id, l.change.startsWith("필수") ? 1 : 0)}>시나리오에 넣기</button>
              </li>
            ))}
            {r.tracks_effect && (
              <li className="track-lever">
                <span>기준은 그대로, <b>교육 트랙 이수</b></span>
                <span className={`num ${r.tracks_effect.delta_pp > 0 ? "up" : ""}`}>+{r.tracks_effect.delta_pp}%p</span>
                <button className="btn-ghost" onClick={() => { setScen(base); setTracks(true); }}>시나리오로 보기</button>
              </li>
            )}
          </ol>
          {r.tracks_effect && r.levers[0] && r.tracks_effect.delta_pp > r.levers[0].delta_pp && (
            <p className="insight">기준을 낮추는 것(최대 +{r.levers[0].delta_pp}%p)보다 <b>교육 트랙을 운영하는 것(+{r.tracks_effect.delta_pp}%p)</b>이 지원 가능한 인재를 더 많이 만듭니다.</p>
          )}
          <div className="row">
            <button className="btn" disabled={!changed} onClick={() => onApply(Object.fromEntries(Object.entries(scen).filter(([, w]) => w > 0)))}>이 기준 적용</button>
            <button className="btn-ghost" disabled={!changed && !tracks} onClick={() => { setScen(base); setTracks(false); }}>되돌리기</button>
          </div>
        </div>
      )}
    </div>
  );
}
