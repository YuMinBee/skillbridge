// 품질: eval/run_eval.py 결과 (results.json). 한 줄 결론 → 단계별 표 4개.
// 숫자는 모두 정답셋 기준이며, 정답 1차 라벨이 AI 보조 초안이면 '잠정'으로 표시한다.
const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const f3 = (x) => (x == null ? "—" : x.toFixed(3));

function Stage({ rows, cols, emptyNote }) {
  return (
    <div className="tbl-wrap">
      <table>
        <thead><tr><th>단계</th>{cols.map(([k, label]) => <th key={k}>{label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.stage}>
              <td>{r.label}</td>
              {r.available
                ? cols.map(([k, , fmt]) => <td key={k} className="num">{fmt(r[k])}</td>)
                : <td colSpan={cols.length} className="hint">{emptyNote}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Quality({ q }) {
  const b = q.baseline.agg;
  const c = q.courses.agg;
  const ag = q.agreement;
  const pending = "Bedrock 실행 전 · eval-live로 측정";
  return (
    <div className="panel">
      <h2>품질 · 정답셋 평가 <span className="hint">({q.at} · eval/report.md)</span></h2>
      <div className="supply-head">
        <div className="hero">
          <span className="num big">{pct(b.company.gap_cov)}</span>
          <span>기업 기준 경로의 실제 갭 커버율</span>
          <small>공고 문구만 보면 {pct(b.posting.gap_cov)} · 불필요한 공부 {pct(b.posting.waste)}</small>
        </div>
        <p className="hint" style={{ margin: 0 }}>
          같은 합성 지원자 {q.baseline.n}명을 기업이 등록한 기준과 공고 문구만으로 각각 진단했습니다. 공고만 보면 {q.baseline.top_missed.slice(0, 3).map(([n]) => n).join("·")} 같은 실제 요구를 놓칩니다.
          {ag.available ? ` 라벨 일치도 κ=${ag.kappa.toFixed(2)}.` : " 정답 1차 라벨은 AI 보조 초안이라 팀원 2차 라벨 전까지 잠정치입니다."}
        </p>
      </div>

      <h3>공고 스킬 추출 · 잡알리오 실공고 {q.postings.n}건 (정답 {q.postings.n_labels}개)</h3>
      <Stage rows={q.postings.rows} emptyNote={pending}
        cols={[["p", "Precision", f3], ["r", "Recall", f3], ["f1", "F1", f3], ["req_acc", "필수/우대 일치", pct]]} />

      <h3>이력서 갭 탐지 · 합성 지원자 {q.gaps.n}명 (사전 밖 표기 {q.gaps.oov}/{q.gaps.mentions})</h3>
      <Stage rows={q.gaps.rows} emptyNote={pending}
        cols={[["gap_recall", "갭 recall", pct], ["false_gap", "오탐률", pct], ["status_acc", "상태 정확도", pct], ["oov_acc", "사전 밖 표기", pct]]} />

      <div className="grid2">
        <div>
          <h3>과정 추천 · 고용24 실카탈로그</h3>
          <div className="tbl-wrap"><table>
            <thead><tr><th>순위</th><th>Hit@3</th><th>nDCG@5</th><th>1순위 적합</th></tr></thead>
            <tbody>
              <tr><td>역량다리</td><td className="num">{pct(c.ours.hit3)}</td><td className="num">{f3(c.ours.ndcg5)}</td><td className="num">{pct(c.ours.p1)}</td></tr>
              <tr><td>카탈로그 순서</td><td className="num">{pct(c.catalog_order.hit3)}</td><td className="num">{f3(c.catalog_order.ndcg5)}</td><td className="num">{pct(c.catalog_order.p1)}</td></tr>
            </tbody>
          </table></div>
          <p className="hint">요구 스킬 {q.courses.skills}개 중 {q.courses.covered}개만 적합한 공공 과정이 있습니다. 나머지는 자습·기업 트랙으로 메웁니다.</p>
        </div>
        <div>
          <h3>공고만 본 추천 vs 기업 기준</h3>
          <div className="tbl-wrap"><table>
            <thead><tr><th>기준</th><th>상위 3단계 적중</th><th>갭 커버</th><th>불필요</th></tr></thead>
            <tbody>
              <tr><td>기업 기준</td><td className="num">{pct(b.company.hit3)}</td><td className="num">{pct(b.company.gap_cov)}</td><td className="num">{pct(b.company.waste)}</td></tr>
              <tr><td>공고 문구만</td><td className="num">{pct(b.posting.hit3)}</td><td className="num">{pct(b.posting.gap_cov)}</td><td className="num">{pct(b.posting.waste)}</td></tr>
            </tbody>
          </table></div>
        </div>
      </div>
    </div>
  );
}
