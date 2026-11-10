export const STATUS_CLS = { own: "st-own", part: "st-part", verify: "st-verify", miss: "st-miss" };
export const STATUS_LABEL = { own: "보유", part: "부분", verify: "검증 필요", miss: "없음" };

export function Bars({ rows, cls = "", unit = "%" }) {
  if (!rows.length) return <p className="empty">데이터 없음</p>;
  const max = Math.max(100, ...rows.map((r) => r.value));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.key}>
          <div className="bar">
            <span title={r.label}>{r.label}</span>
            <div className="track"><div className={`fill ${r.cls ?? cls}`} style={{ width: `${(r.value / max) * 100}%` }} /></div>
            <span className="v num">{r.value}{unit}</span>
          </div>
          {r.note && <div className="hint" style={{ marginTop: 2 }}>{r.note}</div>}
        </div>
      ))}
    </div>
  );
}

export function StatusChip({ status, children }) {
  return <span className={`chip ${STATUS_CLS[status]}`}>{children ?? STATUS_LABEL[status]}</span>;
}

export function Seg({ label, value, options, onChange }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}
