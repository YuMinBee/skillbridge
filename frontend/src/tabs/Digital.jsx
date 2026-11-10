// 공공기관 전 직무의 디지털·AI 역량 요구 (잡알리오 실공고).
// 한 줄 결론(히어로) → 역량 묶음별 요구율 × 대경권 대면 교육 → 직무 분야별 요구율 → 근거 공고.
// 막대는 모두 한 계열(공고 요구율 %)이라 범례 없이 제목이 이름을 대신한다.
const ORDER = ["office", "it", "data", "ai"];

function Row({ label, pct, max, right, title }) {
  return (
    <li title={title}>
      <span className="nm">{label}</span>
      <div className="track"><div className="fill" style={{ width: `${max ? (pct / max) * 100 : 0}%` }} /></div>
      <span className="v num">{pct}%</span>
      <span className="st">{right}</span>
    </li>
  );
}

const seats = (n) => (n == null ? <span className="hint">미집계</span>
  : n > 0 ? <span className="num">{n.toLocaleString()}명</span> : <span className="bad-t">대면 0</span>);

export default function Digital({ data }) {
  const o = data.overall;
  const gmax = Math.max(...ORDER.map((g) => o.groups[g]), 1);
  const fields = data.by_field.slice(0, 12);
  const fmax = Math.max(...fields.map((f) => f.digital), 1);
  const smax = Math.max(...data.top_skills.map((t) => t.pct), 1);
  const gs = data.group_supply;

  return (
    <div className="panel">
      <h2>공공기관 전 직무의 디지털·AI 역량 요구 <span className="hint">({data.region} · {data.period})</span></h2>
      <div className="supply-head">
        <div className="hero">
          <span className="num big">{o.digital}%</span>
          <span>공고가 디지털 역량을 명시</span>
          <small>그중 AI {o.groups.ai}% · 전국 {data.nation.digital}%</small>
        </div>
        <p className="hint" style={{ margin: 0 }}>
          디지털 역량을 적은 공고 {o.n_digital.toLocaleString()}건 중 <b>{o.cert_only}%</b>는 실무 역량 없이 <b>자격증만</b> 요구합니다.
          IT가 아닌 직무에서도 {data.non_it.digital}%가 디지털 역량을 적습니다. 공고 본문(자격요건·우대조건)만 본 하한값입니다.
        </p>
      </div>

      <h3>역량 묶음별 요구율 · 대경권 대면 교육</h3>
      <ol className="supply-list">
        {ORDER.map((g) => (
          <Row key={g} label={data.labels[g]} pct={o.groups[g]} max={gmax}
            right={g === "ai" && gs.ai.ai_use_dg
              ? <span title="챗GPT 활용 등 사무 과정 포함">{seats(gs[g]["대경권"])} <span className="hint">(활용 {gs.ai.ai_use_dg.toLocaleString()})</span></span>
              : seats(gs[g]["대경권"])} />
        ))}
      </ol>
      <p className="hint">오른쪽: 그 역량을 배울 대경권 대면 훈련 정원(4개월 개강분, 스킬별 합이라 중복 가능). 사무 디지털 교육은 많고 데이터·IT 자격 교육은 거의 없습니다.</p>

      <div className="grid2">
        <div>
          <h3>직무 분야(NCS)별 디지털 역량 명시율</h3>
          <ol className="supply-list compact">
            {fields.map((f) => (
              <Row key={f.field} label={f.field} pct={f.digital} max={fmax}
                title={ORDER.map((g) => `${data.labels[g]} ${f.groups[g]}%`).join(" · ")}
                right={<span className="hint num">{f.n.toLocaleString()}건</span>} />
            ))}
          </ol>
          <p className="hint">공고 {data.min_field}건 이상인 분야. 한 공고가 여러 분야에 걸칠 수 있습니다.</p>
        </div>
        <div>
          <h3>많이 요구하는 디지털 역량</h3>
          <ol className="supply-list compact">
            {data.top_skills.map((t) => (
              <Row key={t.skill_id} label={t.name} pct={t.pct} max={smax} title={t.category} right={seats(t.dg_seats)} />
            ))}
          </ol>
          <h3>근거 공고</h3>
          <ul className="evid">
            {data.examples.map((e) => (
              <li key={e.group}>
                <b>{e.group} · {e.skill}</b> · “{e.text}”
                <small>{e.company} · {e.date} · {e.url ? <a href={e.url.startsWith("http") ? e.url : `https://${e.url}`} target="_blank" rel="noreferrer">원문</a> : "잡알리오"}</small>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="hint">출처: {data.source}. 교육 공급: 고용24 훈련과정 전수 수집.</p>
    </div>
  );
}
