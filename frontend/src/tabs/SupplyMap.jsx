// 교육 공급 공백: 시장 수요 순으로 스킬을 나열하고, 지역 대면 교육 공급 상태를 옆에 붙인다.
// 공급이 0인 스킬이 대부분이라 산점도는 바닥에 점이 몰려 읽히지 않는다 → 수요 막대 + 상태 표시가 맞는 형태.
// 상태는 색 + 모양 + 글자로 구분 (있음 ●, 원격만 ◆, 공백 ○).
const ST = {
  "있음": { cls: "pt-ok", label: "지역 대면 과정 있음" },
  "원격만": { cls: "pt-warn", label: "원격 과정만" },
  "공백": { cls: "pt-bad", label: "공백 · 과정 없음" },
};

function Mark({ status, r = 5 }) {
  const s = r * 2 + 4, c = s / 2;
  return (
    <svg width={s} height={s} aria-hidden="true" style={{ flex: "none" }}>
      {status === "원격만" && <path className={`pt ${ST[status].cls}`} d={`M${c} ${c - r - 1}L${c + r + 1} ${c}L${c} ${c + r + 1}L${c - r - 1} ${c}Z`} />}
      {status === "공백" && <circle className="pt pt-ring" cx={c} cy={c} r={r} />}
      {status === "있음" && <circle className={`pt ${ST[status].cls}`} cx={c} cy={c} r={r} />}
    </svg>
  );
}

const TOP = 14;

export default function SupplyMap({ data }) {
  const pts = data.points.slice(0, TOP);
  const max = Math.max(...pts.map((p) => p.demand_pct), 1);
  const h = data.headline;
  const nGap = data.points.filter((p) => p.status !== "있음").length;

  return (
    <div className="panel">
      <h2>교육 공급 공백 <span className="hint">({data.region} · {data.job})</span></h2>
      <div className="supply-head">
        <div className="hero">
          <span className="num big">{h.dg_share}%</span>
          <span>대경권 대면 훈련 정원 중 IT·AI 과정 비중</span>
          <small>수도권 {h.capital_share}% · 약 {h.ratio}배 차이</small>
        </div>
        <p className="hint" style={{ margin: 0 }}>
          수요 상위 {data.points.length}개 스킬 중 <b>{nGap}개</b>는 {data.supply_scope}이 없습니다.
          수요는 큰데 가까이에서 배울 곳이 없는 역량이 기업 교육 트랙이 필요한 자리입니다.
        </p>
      </div>
      <ul className="legend" aria-label="범례">
        {Object.entries(ST).map(([k, v]) => <li key={k}><Mark status={k} r={4} />{v.label}</li>)}
      </ul>
      <ol className="supply-list">
        {pts.map((p) => (
          <li key={p.skill_id} title={p.example || ""}>
            <span className="nm">{p.name}</span>
            <div className="track"><div className="fill" style={{ width: `${(p.demand_pct / max) * 100}%` }} /></div>
            <span className="v num">{p.demand_pct}%</span>
            <span className="st"><Mark status={p.status} />
              {p.status === "있음" ? <span className="num">{p.seats.toLocaleString()}명</span>
                : p.status === "원격만" ? <span>원격 {p.online_rounds}회차</span> : <span className="bad-t">공백</span>}
            </span>
          </li>
        ))}
      </ol>
      <p className="hint">
        막대: 시장 수요(공고 언급률) · 오른쪽: {data.supply_scope} 정원. 공급은 {data.source.supply}.
        원격 과정은 명목 정원(500·1000)이 많아 지역 정원에서 빼고 회차 수로만 셉니다(검색어당 100건 상한이라 최소값). 수요: {data.source.demand}.
      </p>
    </div>
  );
}
