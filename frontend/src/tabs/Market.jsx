import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Bars, Seg } from "../ui.jsx";
import SupplyMap from "./SupplyMap.jsx";
import Digital from "./Digital.jsx";
import Quality from "./Quality.jsx";

const LIVE = new Set(["public", "public_it"]);

export default function Market() {
  const [region, setRegion] = useState("dg");
  const [job, setJob] = useState("public");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [sup, setSup] = useState(null);
  const [dig, setDig] = useState(null);
  const [q, setQ] = useState(null);
  const isLive = LIVE.has(job);

  useEffect(() => { api.quality().then((x) => x.available && setQ(x)).catch(() => {}); }, []);

  useEffect(() => {
    let live = true;
    api.market(region, job).then((x) => { if (live) { setD(x); setErr(""); } }).catch((e) => live && setErr(e.message));
    if (LIVE.has(job)) {
      setSup(null);
      api.digital(region).then((x) => live && setDig(x)).catch(() => live && setDig(null));
    } else {
      setDig(null);
      api.supply(region, job).then((x) => live && setSup(x)).catch(() => live && setSup(null));
    }
    return () => { live = false; };
  }, [region, job]);

  return (
    <section className="view" aria-label="시장 분석">
      <p className="lead"><b>지역 교육기관·지자체용 화면이에요.</b> 채용공고가 요구하는 역량과 지역 교육과정 공급을 비교해서, 어디가 비어 있는지 보여줘요.</p>
      <p className="hint">{isLive
        ? "공공기관 채용공고(잡알리오 실공고)에서 스킬을 추출해 전 직무의 AI·데이터·디지털 역량 요구를 집계합니다."
        : "민간 AI·클라우드 직무는 라벨링한 가상 샘플 공고로 요구역량과 추세를 보여줍니다 (시연용)."}</p>
      <div className="row">
        <Seg label="지역" value={region} onChange={setRegion} options={[["dg", "대경권"], ["all", "전국"]]} />
        <Seg label="직무" value={job} onChange={setJob} options={[["public", "공공 전 직무 · 실공고"], ["public_it", "공공 정보통신 · 실공고"], ["ai", "AI 엔지니어 · 샘플"], ["cloud", "클라우드 · 샘플"]]} />
      </div>
      {err && <p className="err">{err}</p>}
      {d && (
        <div className="grid2">
          <div className="panel">
            <h2>공고 요구 빈도 상위 스킬</h2>
            <p className="hint">분석 공고 <span className="num">{d.n.toLocaleString()}</span>건 · {d.period} · 언급 비율(%)</p>
            <Bars rows={d.top.map((t) => ({ key: t.skill_id, label: t.name, value: Math.round(t.pct) }))} />
          </div>
          <div className="panel">
            <h2>급상승 스킬 <span className="hint">(직전 6개월 대비 언급 비율 변화)</span></h2>
            {d.rising_window && <p className="hint">최근 {d.rising_window.recent} vs 직전 {d.rising_window.prev}</p>}
            <div className="rise">
              {d.rising.length ? d.rising.map((r) => (
                <div key={r.skill_id}>
                  <span>{r.name} <span className="hint num">{r.prev_pct}% → {r.recent_pct}%</span></span>
                  <span className="up">+{r.delta_pp}%p</span>
                </div>
              )) : <p className="hint">상승한 스킬이 없습니다.</p>}
            </div>
            <h3>근거 공고 예시</h3>
            <ul className="evid">
              {d.evidence.map((e) => (
                <li key={e.posting_id + e.skill}>
                  <b>{e.skill}</b> · “{e.text}”
                  <small>{e.company} · {e.region} · {e.date} · {e.section} · {e.source}</small>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {isLive && dig?.available && <Digital data={dig} />}
      {!isLive && sup?.available && <SupplyMap data={sup} />}
      {q && <Quality q={q} />}
      {d && <p className="hint">데이터 출처: {d.source}.{d.live ? "" : " 숫자는 시연용입니다."}
        {d.engine?.name === "athena" && <> 집계: Amazon Athena (S3 curated/, {d.engine.ms}ms · {d.engine.scanned_mb}MB 스캔 · 로컬 계산과 {d.engine.match ? "일치" : "불일치"}).</>}</p>}
    </section>
  );
}
