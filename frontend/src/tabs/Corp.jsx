import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Bars } from "../ui.jsx";
import Simulator from "./Simulator.jsx";

const LEVEL_CLS = { ok: "st-own", warn: "st-part", bad: "st-miss" };
const EMPTY_TRACK = { skill: "", title: "", hours: 8, benefit: "" };

export default function Corp({ companies, corpVersion, active, onChanged }) {
  const [cid, setCid] = useState("A");
  const [c, setC] = useState(null);
  const [skills, setSkills] = useState([]);
  const [ins, setIns] = useState(null);
  const [err, setErr] = useState("");
  const [nt, setNt] = useState(EMPTY_TRACK);
  const [doc, setDoc] = useState("");
  const [sugg, setSugg] = useState(null);

  const load = async (id = cid) => {
    try {
      const comp = await api.company(id);
      setC(comp);
      const [sk, ii] = await Promise.all([
        api.skills(comp.region === "대경권" ? "dg" : "all", comp.job), api.insights(id)]);
      setSkills(sk); setIns(ii); setErr("");
    } catch (e) { setErr(e.message); }
  };

  useEffect(() => { if (active) load(cid); /* eslint-disable-next-line */ }, [cid, corpVersion, active]);
  useEffect(() => { setSugg(null); setDoc(""); setNt(EMPTY_TRACK); }, [cid]);

  const saveReqs = async (reqs, msg) => {
    try { setC(await api.putRequirements(cid, reqs)); onChanged(msg); }
    catch (e) { setErr(e.message); }
  };
  const setWeight = (sid, w) => {
    const reqs = { ...c.requirements };
    if (w === 0) delete reqs[sid]; else reqs[sid] = w;
    const name = c.requirements_view.find((x) => x.skill_id === sid)?.name ?? sid;
    saveReqs(reqs, `${name}: ${w === 2 ? "필수" : w === 1 ? "우대" : "제외"}로 저장했습니다. 취준생 진단에 반영됩니다.`);
  };
  const addSkill = (sid, w = 1) => {
    if (!sid) return;
    const name = skills.find((s) => s.id === sid)?.name ?? sid;
    saveReqs({ ...c.requirements, [sid]: w }, `${name}을(를) ${w === 2 ? "필수" : "우대"} 역량으로 추가했습니다.`);
  };

  const saveTracks = async (tracks, msg) => {
    try {
      setC(await api.putTracks(cid, tracks.map(({ id, skills, title, hours, benefit }) => ({ id, skills, title, hours, benefit }))));
      onChanged(msg);
    } catch (e) { setErr(e.message); }
  };
  const addTrack = () => {
    if (!nt.skill || !nt.title.trim()) { setErr("트랙의 대상 스킬과 제목을 입력하세요"); return; }
    const used = new Set(c.tracks.map((t) => t.id));
    let n = c.tracks.length + 1; while (used.has(`${cid}-T${n}`)) n += 1;
    saveTracks([...c.tracks, { id: `${cid}-T${n}`, skills: [nt.skill], title: nt.title, hours: +nt.hours || 1, benefit: nt.benefit }],
      "교육 트랙을 등록했습니다.");
    setNt(EMPTY_TRACK);
  };

  const onDocFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 200_000) { setErr("텍스트 파일은 200KB 이하로 올려 주세요"); return; }
    f.text().then(setDoc);
  };
  const suggest = async () => {
    try { setSugg(await api.suggest(cid, doc)); setErr(""); } catch (e) { setErr(e.message); }
  };

  const inReq = new Set(c ? Object.keys(c.requirements) : []);

  return (
    <section className="view" aria-label="기업 콘솔">
      <p className="lead"><b>기업 담당자용 화면이에요.</b> 공고에 다 못 쓴 '입사 후 실제로 쓰는 역량'을 등록하면, 취준생 진단의 실무 준비도와 학습 순서에 바로 반영돼요. 기준을 바꿨을 때 지원자 풀이 어떻게 달라지는지도 미리 볼 수 있어요.</p>
      <div className="row">
        <label className="fld" style={{ minWidth: 260 }}>기업
          <select value={cid} onChange={(e) => setCid(e.target.value)}>
            {companies.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.desc}</option>)}
          </select>
        </label>
      </div>
      {err && <p className="err">{err}</p>}
      {c && (
        <>
          <div className="grid2">
            <div className="panel">
              <h2>입사 후 실무에 필요한 역량</h2>
              <p className="hint">공고에는 입사 문턱만 적어도 됩니다. 여기에는 입사 후 실제로 쓰는 역량을 필수·우대로 등록하세요(시장 빈도: {c.market_scope}). 취준생 진단의 실무 준비도와 학습경로 ② 단계에 바로 반영됩니다. 시연용이라 바꾼 기준은 이 브라우저에만 적용되고(24시간), 원본과 다른 방문자 화면은 그대로입니다.</p>
              {c.data_note && <p className="warn" role="note">{c.data_note}</p>}
              <div className="weights">
                {c.requirements_view.map((r) => (
                  <div className="w" key={r.skill_id}>
                    <span>{r.name}{c.sources?.[r.skill_id] && (c.sources[r.skill_id].url ? (
                      <a className="src" href={c.sources[r.skill_id].url} target="_blank" rel="noopener noreferrer"
                        title={`${c.sources[r.skill_id].from}: “${c.sources[r.skill_id].quote}”`}> [{c.sources[r.skill_id].from}]</a>) : (
                      <span className="src" title={`${c.sources[r.skill_id].from}: “${c.sources[r.skill_id].quote}”`}> [{c.sources[r.skill_id].from}]</span>))}</span>
                    <span className="v num" title="시장 언급률">{r.market_pct}%</span>
                    <select aria-label={`${r.name} 구분`} value={r.weight} onChange={(e) => setWeight(r.skill_id, +e.target.value)}
                      disabled={r.weight > 0 && c.requirements_view.length === 1}>
                      <option value={2}>필수</option><option value={1}>우대</option><option value={0}>제외</option>
                    </select>
                  </div>
                ))}
                <select aria-label="역량 추가" value="" onChange={(e) => addSkill(e.target.value)}>
                  <option value="">역량 추가… (시장 언급률 순)</option>
                  {skills.filter((s) => !inReq.has(s.id)).map((s) => <option key={s.id} value={s.id}>{s.name} (시장 {s.market_pct}%)</option>)}
                </select>
              </div>
            </div>

            <div className="panel">
              <h2>우리 교육 트랙</h2>
              <p className="hint">기업이 내놓는 교육입니다. 해당 갭이 있는 취준생에게 추천됩니다.</p>
              <ol className="path">
                {c.tracks.map((t) => (
                  <li key={t.id}>
                    <div>
                      <div className="t">{t.title}
                        <button className="btn ghost sm" onClick={() => saveTracks(c.tracks.filter((x) => x.id !== t.id), "교육 트랙을 삭제했습니다.")}>삭제</button>
                      </div>
                      <div className="m">{t.skill_names.join(", ")} 갭 대상 · {t.hours}시간{t.benefit ? ` · ${t.benefit}` : ""}</div>
                    </div>
                  </li>
                ))}
              </ol>
              {!c.tracks.length && <p className="hint">등록된 트랙이 없습니다.</p>}
              <h3>트랙 추가</h3>
              <div className="track-form">
                <select aria-label="대상 스킬" value={nt.skill} onChange={(e) => setNt({ ...nt, skill: e.target.value })}>
                  <option value="">대상 스킬</option>
                  {c.requirements_view.map((r) => <option key={r.skill_id} value={r.skill_id}>{r.name}</option>)}
                </select>
                <input type="number" min={1} max={200} aria-label="시간" value={nt.hours} onChange={(e) => setNt({ ...nt, hours: e.target.value })} />
                <input className="full" type="text" placeholder="트랙 제목" maxLength={80} value={nt.title} onChange={(e) => setNt({ ...nt, title: e.target.value })} />
                <input className="full" type="text" placeholder="혜택 문구 (예: 이수 시 서류 우대)" maxLength={80} value={nt.benefit} onChange={(e) => setNt({ ...nt, benefit: e.target.value })} />
                <button className="btn ghost full" onClick={addTrack}>트랙 등록</button>
              </div>
            </div>
          </div>

          <div className="grid2">
            <div className="panel">
              <h2>지원 희망자가 가장 많이 막히는 역량</h2>
              {ins && <>
                <p className="hint">진단 {ins.sessions}건 · 해당 역량이 부족·없음인 비율 (익명 집계{ins.fake_included ? ", 시연용 가상 기록 포함" : ""})</p>
                <Bars cls="bad" rows={ins.blocked.map((x) => ({ key: x.skill_id, label: x.name, value: x.pct }))} />
              </>}
            </div>
            <div className="panel">
              <h2>우리 공고 vs 시장</h2>
              <p className="hint">시장({ins?.market_scope}) 대비 우리 요구가 드문 역량은 지원자 풀을 줄입니다. 공공 단기과정(160시간 이하)이 없는 역량은 지원자가 스스로 채우기 어려워 기업 트랙이 필요합니다{ins?.courses_source === "live" ? " (고용24 훈련과정 기준)" : " (샘플 카탈로그 기준)"}.</p>
              <div className="tbl-wrap">
                <table>
                  <thead><tr><th>스킬</th><th>우리</th><th>시장 언급률</th><th>공공 단기과정</th><th>판단</th></tr></thead>
                  <tbody>
                    {ins?.vs_market.map((v) => (
                      <tr key={v.skill_id}>
                        <td>{v.name}</td><td style={{ whiteSpace: "nowrap" }}>{v.weight === 2 ? "필수" : "우대"}</td>
                        <td className="num">{v.market_pct}%</td>
                        <td>{v.course_gap
                          ? <span className={`chip ${v.has_track ? "st-own" : "st-miss"}`}>{v.has_track ? "없음 · 우리 트랙이 보완" : "없음 · 트랙 필요"}</span>
                          : <span className="num">{v.public_courses}개</span>}</td>
                        <td><span className={`chip ${LEVEL_CLS[v.level]}`} style={{ whiteSpace: "normal" }}>{v.judge}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <Simulator company={c} onApply={(reqs) => saveReqs(reqs, "시뮬레이터 기준을 적용했습니다. 취준생 진단에 반영됩니다.")} />

          <div className="panel">
            <h2>기업 자료로 실무 역량 초안 만들기</h2>
            <p className="hint">실제 쓰는 기술은 공고보다 기술 블로그·온보딩 문서·스택 설명에 흩어져 있습니다. 붙여 넣거나 .md/.txt 파일을 올리면 실무 역량 후보를 제안하고, 우리 회사 문서(지식베이스)에서 근거 문단을 붙입니다.</p>
            <textarea value={doc} onChange={(e) => setDoc(e.target.value)} placeholder="예: 서비스는 EKS 위의 Kubernetes로 운영하고 Terraform으로 인프라를 관리합니다…" style={{ minHeight: 110 }} />
            <div className="row">
              <input type="file" accept=".md,.txt,text/plain,text/markdown" onChange={onDocFile} />
              <button className="btn" disabled={!doc.trim()} onClick={suggest}>요구역량 초안 제안</button>
            </div>
            {sugg && (
              <div className="sugg">
                {!sugg.suggestions.length && <p className="hint">인식된 스킬이 없습니다.</p>}
                {sugg.kb && <p className="hint">근거: {sugg.kb}</p>}
                {sugg.suggestions.map((s) => (
                  <div className="s" key={s.skill_id}>
                    <span>{s.name} <span className="hint">· 언급 {s.mentions}회 · 시장 {s.market_pct}%{s.already ? ` · 현재 ${s.already === 2 ? "필수" : "우대"}` : ""}</span>
                      {s.kb_evidence && <small className="kb-ev" title={`우리 회사 문서 · ${s.kb_evidence.source}`}>“{s.kb_evidence.text}” <span className="hint">— {s.kb_evidence.source}</span></small>}</span>
                    <span className="row">
                      <button className="btn ghost sm" disabled={s.already === 2} onClick={() => addSkill(s.skill_id, 2)}>필수로{s.suggested_weight === 2 ? " (추천)" : ""}</button>
                      <button className="btn ghost sm" disabled={s.already === 1} onClick={() => addSkill(s.skill_id, 1)}>우대로{s.suggested_weight === 1 ? " (추천)" : ""}</button>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="notice">개인 진단 결과는 본인에게만 보이고, 기업에는 익명 집계만 제공합니다. 채용 합불 판단에 쓰지 않습니다.</p>
        </>
      )}
    </section>
  );
}
