// 첫 화면(소개). 숫자는 AGENTS.md '발표 숫자 확정'(eval/trust/report.md, test 60단락 × 5회)·report_retrieval.md·
// task_judge_result.json과 같게 둔다. 바뀌면 여기도 고친다. 웹 방식이 "지어낸다"고 쓰지 않는다(팀 규칙).
const REPO = "https://github.com/YuMinBee/skillbridge/blob/main/eval/trust/";

// 비교 막대: 같은 Sonnet 4.6, test 60단락 × 5회
const COMPARE = [
  {
    title: "없는 근거를 있다고 한 비율", note: "낮을수록 좋음",
    rows: [["웹 Claude · 그냥 묻기", 35.5], ["웹 Claude · 잘 쓴 프롬프트", 29.1], ["웹 Claude · 우리 기준까지 준 프롬프트", 6.7], ["SkillBridge", 2.1]],
  },
  {
    title: "같은 자소서 5번 → 5번 모두 같은 판정", note: "높을수록 좋음",
    rows: [["웹 Claude · 그냥 묻기", 61.7], ["웹 Claude · 잘 쓴 프롬프트", 86.7], ["웹 Claude · 우리 기준까지 준 프롬프트", 88.3], ["SkillBridge", 100]],
  },
];

// 에이전트 단계 (backend/app/agents/supervisor.py 순서)
const FLOW = [
  ["개인정보 가리기", "정규식과 Bedrock Guardrails로 이름·연락처·주소를 먼저 가립니다"],
  ["강점 진단", "경험을 STAR로 나누고 칸마다 원문 문장을 그대로 인용합니다. 원문에 없는 인용은 버립니다"],
  ["공고 기준 비교", "지원 분야 실제 공고의 요구 문장과 비교해 부족한 역량을 찾습니다"],
  ["과제 · 교육과정", "공고 근거가 붙은 과제와 고용24 실제 과정을 고릅니다. 맞는 과정이 없으면 추천하지 않습니다"],
  ["근거 검증", "인용이 원문에 있는지, 과정이 카탈로그에 있는지 코드로 확인하고 어긋나면 지웁니다"],
];

const CHECKS = [
  ["96.2%", "STAR 칸 정확도", "자소서 60단락 × 5회. 정답은 사람 2명이 따로 라벨링(κ 0.78). '우리 기준까지 준 프롬프트'(94.7%)와는 차이가 유의하지 않습니다.", "report.md"],
  ["0.824", "교육과정 검색 nDCG@5", "질의 40개로 검색 방식 7가지를 비교해 Cohere Embed v4를 골랐습니다(키워드 검색 BM25 0.648). 유사도 0.35 미만이면 추천하지 않습니다.", "report_retrieval.md"],
  ["0 / 16", "부적절한 추천 과제", "실제로 나온 과제 16개를 사람이 '1~2주 안에 혼자 할 수 있고 결과물이 남는가'로 판정했습니다. 적절 11 · 애매 5.", "task_judge_result.json"],
];

const DATA = [["109", "민간 IT 공고", "기업 공식 채용 페이지 직접 수집 포함"], ["263", "공공기관 IT 공고", "잡알리오"], ["1,856", "고용24 교육과정", "앞으로 개강하는 과정만 추천"]];
const AWS = ["Amazon Bedrock · Claude Sonnet 4.6", "Cohere Embed v4", "Bedrock Guardrails", "AWS Lambda", "Amazon DynamoDB"];

// 히어로 오른쪽: 예시 자소서(docs/pivot/captures/demo_resume.md)를 실제로 분석한 결과에서 발췌. 공고·과정 문장도 실제 결과 그대로
function Preview() {
  return (
    <div className="lp-pv" aria-label="예시 자소서 분석 결과 발췌">
      <div className="lp-pv-card lp-pv-main">
        <div className="lp-pv-h"><b>동아리 장비 대여 시스템</b><span className="lp-chip ok">STAR 4칸</span></div>
        <ul className="lp-star">
          <li><i>S</i><span>“한 학기에 장비 5개를 잃어버렸습니다”</span></li>
          <li><i>T</i><span>“대여·반납 기록을 남기는 백엔드를 맡았습니다”</span></li>
          <li><i>A</i><span>“Spring Boot와 MySQL로 대여 API를 만들고”</span></li>
          <li><i>R</i><span>“다음 학기에는 분실 장비가 0개였고”</span></li>
        </ul>
        <p className="lp-pv-src"><span className="lp-dot ok" />네 칸 모두 내 자소서 원문 그대로</p>
      </div>
      <div className="lp-pv-card lp-pv-post">
        <span className="lp-chip warn">부족한 역량 · AWS</span>
        <p>“MSA 환경에서 서비스 설계 및 클라우드(AWS/GCP) 인프라 운영 경험이 있는 분”</p>
        <small>민간 백엔드 공고 45건 중 11건이 요구</small>
      </div>
      <div className="lp-pv-card lp-pv-course">
        <span className="lp-chip acc">고용24 과정</span>
        <b>AWS 활용 Spring 백엔드 개발자 실무 부트캠프</b>
        <small>2026-12-29 개강</small>
      </div>
    </div>
  );
}

export default function Landing({ onStart, onSample }) {
  return (
    <div className="lp">
      <section className="lp-hero">
        <div className="lp-hero-l">
          <p className="lp-eyebrow">KOSA × AWS AI 부트캠프 06팀 · Amazon Bedrock</p>
          <h2>같은 Claude,<br />다른 신뢰도.</h2>
          <p className="lp-lead">자소서를 넣으면 강점은 <mark className="hl-ok">내 문장</mark>으로, 부족한 역량은 <mark className="hl-warn">실제 공고 문장</mark>으로,
            다음 할 일은 <mark className="hl-acc">고용24 실제 과정</mark>으로 근거를 붙여 보여 드립니다.</p>
          <div className="lp-cta">
            <button className="btn lp-btn" onClick={onStart}>내 역량 분석하기</button>
            <button className="btn ghost lp-btn" onClick={onSample}>예시로 체험하기</button>
          </div>
          <p className="lp-trust">회원가입 없음 · 이력서 원문은 저장하지 않음 · 채용 합불 판단에 쓰지 않음</p>
        </div>
        <Preview />
      </section>

      <section className="lp-sec">
        <div className="lp-sec-h">
          <p className="lp-eyebrow">웹 Claude와 비교</p>
          <h3>프롬프트를 잘 써도 여기까지입니다</h3>
          <p className="lp-muted">같은 Claude Sonnet 4.6에 같은 자소서 60단락을 5번씩 넣었습니다. 웹 방식은 3가지로 물었습니다.</p>
        </div>
        <div className="lp-compare">
          {COMPARE.map((c) => (
            <figure className="lp-chart" key={c.title}>
              <figcaption><b>{c.title}</b><span>{c.note}</span></figcaption>
              {c.rows.map(([k, v]) => (
                <div className={`lp-bar ${k === "SkillBridge" ? "us" : ""}`} key={k}>
                  <span className="lp-bar-k">{k}</span>
                  <span className="lp-bar-t"><i style={{ width: `${v}%` }} /></span>
                  <span className="lp-bar-v num">{v}%</span>
                </div>
              ))}
            </figure>
          ))}
        </div>
        <p className="lp-foot">95% 신뢰구간으로 비교했고, 두 지표 모두 세 가지 웹 방식과 차이가 유의합니다 · <a href={REPO + "report.md"} target="_blank" rel="noreferrer">평가 기록</a></p>
      </section>

      <section className="lp-sec">
        <div className="lp-sec-h">
          <p className="lp-eyebrow">어떻게 동작하나</p>
          <h3>다섯 단계가 순서대로, 매번 같은 방식으로</h3>
          <p className="lp-muted">AWS 안에서 단계마다 한 가지 일만 합니다. 한 단계가 실패해도 그 단계만 규칙으로 대신합니다.</p>
        </div>
        <ol className="lp-flow">
          {FLOW.map(([t, d], i) => (
            <li key={t}><span className="lp-flow-n num">{String(i + 1).padStart(2, "0")}</span><b>{t}</b><p>{d}</p></li>
          ))}
        </ol>
      </section>

      <section className="lp-sec">
        <div className="lp-sec-h">
          <p className="lp-eyebrow">검증</p>
          <h3>숫자는 사람이 확인했습니다</h3>
        </div>
        <div className="lp-checks">
          {CHECKS.map(([v, k, d, f]) => (
            <article key={k}>
              <div className="lp-check-v num">{v}</div>
              <b>{k}</b>
              <p>{d}</p>
              <a href={REPO + f} target="_blank" rel="noreferrer">평가 기록 보기 →</a>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-sec lp-data">
        <div className="lp-data-n">
          {DATA.map(([v, k, d]) => (
            <div key={k}><div className="num">{v}</div><b>{k}</b><small>{d}</small></div>
          ))}
        </div>
        <ul className="lp-aws" aria-label="사용한 AWS 서비스">{AWS.map((a) => <li key={a}>{a}</li>)}</ul>
      </section>

      <section className="lp-end">
        <h3>내 자소서에는 어떤 근거가 있을까요?</h3>
        <p>문서 하나면 됩니다. 결과는 학습 방향을 잡는 참고용입니다.</p>
        <div className="lp-cta">
          <button className="btn lp-btn lp-btn-inv" onClick={onStart}>지금 분석 시작</button>
          <button className="btn lp-btn lp-btn-line" onClick={onSample}>예시로 체험하기</button>
        </div>
      </section>
    </div>
  );
}
