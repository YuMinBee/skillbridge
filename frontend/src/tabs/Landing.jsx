// 첫 화면(소개). 숫자는 AGENTS.md '발표 숫자 확정'(eval/trust/report.md, test 60단락 × 5회)·report_retrieval.md·
// task_judge_result.json과 같게 둔다. 바뀌면 여기도 고친다. 웹 방식이 "지어낸다"고 쓰지 않는다(팀 규칙).
// 11-22 원칙: 히어로처럼 섹션마다 큰 문장 하나 + 큰 숫자/실제 화면 하나. 작은 글씨 카드를 늘리지 않는다.
import bridgePhoto from "../assets/hero-bridge.jpg";  // Unsplash 무료 라이선스 https://unsplash.com/photos/_a33bgpBCdg

const REPO = "https://github.com/YuMinBee/skillbridge/blob/main/eval/trust/";

// 누가 쓰나 (docs/DEMO_SCRIPT.md 대상: 대학 취업센터·부트캠프에서 상담 전에 돌리는 1차 진단)
const USE = [
  ["취업센터 · 부트캠프", "상담 전에 학생 자소서를 먼저 넣어 두면, 강점과 부족한 역량이 근거와 함께 정리돼 상담은 해석과 계획에 집중할 수 있습니다."],
  ["취준생 혼자서", "지원 전에 내 문서가 공고 기준으로 어디가 비어 있는지 보고, 바로 할 과제와 개강하는 과정을 고릅니다."],
  ["같은 기준으로", "같은 문서는 몇 번을 넣어도 같은 판정이 나옵니다. 학생마다, 상담사마다 기준이 흔들리지 않습니다."],
];

// 비교: 같은 Sonnet 4.6, test 60단락 × 5회. 웹 ②(잘 쓴 프롬프트)와 대비, 웹 ③은 각주로
const VS = [
  { k: "없는 근거를 있다고 한 비율", web: "29.1%", us: "2.1%", note: "웹 Claude에 잘 쓴 프롬프트로 물었을 때 → SkillBridge. 우리 기준까지 준 프롬프트도 6.7%" },
  { k: "같은 자소서 5번, 5번 모두 같은 판정", web: "86.7%", us: "100%", note: "웹 Claude에 잘 쓴 프롬프트로 물었을 때 → SkillBridge. 우리 기준까지 준 프롬프트도 88.3%" },
];

// 에이전트 단계 (backend/app/agents/supervisor.py 순서) — 한 줄씩만
const FLOW = [
  ["개인정보 가리기", "Bedrock Guardrails"],
  ["강점 진단", "원문 문장만 인용"],
  ["공고 기준 비교", "실제 공고 요구 문장"],
  ["과제 · 교육과정", "맞는 과정이 없으면 추천 안 함"],
  ["근거 검증", "어긋나면 코드가 지움"],
];

const CHECKS = [
  ["96.2%", "STAR 칸 정확도", "사람 2명이 따로 라벨링한 정답 기준 (κ 0.78)", "report.md"],
  ["0.824", "교육과정 검색 nDCG@5", "검색 방식 7가지 중 최고 · BM25 0.648", "report_retrieval.md"],
  ["0 / 16", "부적절한 추천 과제", "사람이 과제 16개를 직접 판정", "task_judge_result.json"],
];

const DATA = [["109", "민간 IT 공고", "기업 공식 채용 페이지 직접 수집 포함"], ["263", "공공기관 IT 공고", "잡알리오"], ["1,856", "고용24 교육과정", "앞으로 개강하는 과정만 추천"]];
const AWS = ["Amazon Bedrock · Claude Sonnet 4.6", "Cohere Embed v4", "Bedrock Guardrails", "AWS Lambda", "Amazon DynamoDB"];

// 건너는 길: 예시 자소서(docs/pivot/captures/demo_resume.md)를 실제로 분석한 결과에서 발췌. 공고·과정 문장도 실제 결과 그대로
const CROSS = [
  {
    n: "01", t: "지금의 나", d: "자소서 속 경험을 STAR로 나누고, 칸마다 내 문장을 그대로 인용합니다.",
    card: (
      <div className="lp-pv-card">
        <div className="lp-pv-h"><b>동아리 장비 대여 시스템</b><span className="lp-chip ok">강점</span></div>
        <ul className="lp-star">
          <li><i>S</i><span>“한 학기에 장비 5개를 잃어버렸습니다”</span></li>
          <li><i>T</i><span>“대여·반납 기록을 남기는 백엔드를 맡았습니다”</span></li>
          <li><i>A</i><span>“Spring Boot와 MySQL로 대여 API를 만들고”</span></li>
          <li><i>R</i><span>“다음 학기에는 분실 장비가 0개였고”</span></li>
        </ul>
      </div>
    ),
  },
  {
    n: "02", t: "건너야 할 곳", d: "공고가 요구하는데 내 문서에 없는 역량을, 실제 공고 문장으로 짚습니다.",
    card: (
      <div className="lp-pv-card lp-pv-post">
        <span className="lp-chip warn">부족한 역량 · AWS</span>
        <p>“MSA 환경에서 서비스 설계 및 클라우드(AWS/GCP) 인프라 운영 경험이 있는 분”</p>
        <small>민간 백엔드 공고 45건 중 11건이 요구</small>
      </div>
    ),
  },
  {
    n: "03", t: "건너는 방법", d: "근거가 붙은 과제와, 앞으로 개강하는 고용24 실제 과정을 이어 드립니다.",
    card: (
      <div className="lp-pv-card lp-pv-course">
        <span className="lp-chip acc">고용24 과정</span>
        <b>AWS 활용 Spring 백엔드 개발자 실무 부트캠프</b>
        <small>2026-12-29 개강</small>
      </div>
    ),
  },
];

// 메뉴 바 링크: 주소(#)를 바꾸면 App이 화면을 다시 고르므로, 바꾸지 않고 그 섹션으로 부드럽게 스크롤
const jump = (id) => (e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); };

export default function Landing({ onStart, onSample }) {
  return (
    <div className="lp">
      {/* 히어로: 화면 전체 사진(물 위를 가로지르는 다리) + 유리 메뉴 바 + 왼쪽 아래 제목 */}
      <section className="lp-hero" style={{ "--hero-img": `url(${bridgePhoto})` }}>
        <nav className="lp-nav" aria-label="소개 메뉴">
          <a className="lp-nav-logo" href="#home">SkillBridge</a>
          <div className="lp-nav-links">
            {[["cross", "건너는 길"], ["compare", "비교"], ["flow", "동작 방식"], ["verify", "검증"]].map(([id, t]) => <a key={id} href={`#${id}`} onClick={jump(id)}>{t}</a>)}
          </div>
          <div className="lp-nav-act">
            <button className="lp-pill line" onClick={onSample}>예시로 체험하기</button>
            <button className="lp-pill" onClick={onStart}>분석 시작</button>
          </div>
        </nav>
        <div className="lp-hero-l">
          <h2>원하는 일까지,<br />다리가 되어 드릴게요.</h2>
          <div className="lp-hero-row">
            <p className="lp-lead">내 자소서 속 강점에서 출발해, 공고가 요구하는데 비어 있는 역량을 실제 공고 문장으로 짚고, 그 사이를 건널 과제와 고용24 과정까지 이어 드립니다.</p>
            <button className="lp-go" onClick={onStart}>내 역량 분석하기<span aria-hidden="true">↗</span></button>
          </div>
        </div>
      </section>

      {/* 건너는 길: 큰 번호 + 한 문장 | 실제 결과 카드, 세 줄 */}
      <section className="lp-x lp-x-dark" id="cross" style={{ "--hero-img": `url(${bridgePhoto})` }}>
        <h3 className="lp-x-title">세 걸음이면<br />건너갑니다.</h3>
        <ol className="lp-cross">
          {CROSS.map((c) => (
            <li key={c.n}>
              <div className="lp-cross-l"><span className="lp-cross-n">{c.n}</span><b>{c.t}</b><p>{c.d}</p></div>
              <div className="lp-cross-r">{c.card}</div>
            </li>
          ))}
        </ol>
        <p className="lp-x-foot">예시 자소서를 실제로 분석한 결과에서 발췌했습니다</p>
      </section>

      {/* 비교: 큰 숫자 대비 두 개 */}
      <section className="lp-x lp-x-light" id="compare">
        <h3 className="lp-x-title">같은 Claude,<br />다른 신뢰도.</h3>
        <div className="lp-vs">
          {VS.map((v) => (
            <div className="lp-vs-i" key={v.k}>
              <p className="lp-vs-k">{v.k}</p>
              <div className="lp-vs-n"><s className="num">{v.web}</s><span aria-hidden="true">→</span><b className="num">{v.us}</b></div>
              <p className="lp-vs-note">{v.note}</p>
            </div>
          ))}
        </div>
        <p className="lp-x-foot">같은 Claude Sonnet 4.6 · 자소서 60단락 × 5회 · 95% 신뢰구간으로 세 가지 웹 방식 모두와 차이가 유의 · <a href={REPO + "report.md"} target="_blank" rel="noreferrer">평가 기록</a></p>
      </section>

      {/* 동작 방식: 큰 단어 다섯 개를 한 줄로 */}
      <section className="lp-x lp-x-dark" id="flow">
        <h3 className="lp-x-title">다섯 단계, 매번<br />같은 방식으로.</h3>
        <ol className="lp-steps5">
          {FLOW.map(([t, d], i) => (
            <li key={t}><span className="num">{String(i + 1).padStart(2, "0")}</span><b>{t}</b><small>{d}</small></li>
          ))}
        </ol>
        <p className="lp-x-foot">모두 AWS 안에서 · 한 단계가 실패해도 그 단계만 규칙으로 대신합니다</p>
      </section>

      {/* 검증: 큰 숫자 세 개 */}
      <section className="lp-x lp-x-light" id="verify">
        <h3 className="lp-x-title">숫자는<br />사람이 확인했습니다.</h3>
        <div className="lp-big3">
          {CHECKS.map(([v, k, d, f]) => (
            <a key={k} href={REPO + f} target="_blank" rel="noreferrer">
              <span className="num">{v}</span><b>{k}</b><small>{d}</small><em>평가 기록 →</em>
            </a>
          ))}
        </div>
        <p className="lp-x-foot">STAR 정확도는 '우리 기준까지 준 프롬프트'(94.7%)와는 차이가 유의하지 않습니다</p>
      </section>

      {/* 이렇게 씁니다: 큰 문장 + 세 칸 */}
      <section className="lp-x lp-x-dark" id="use">
        <h3 className="lp-x-title">상담 전에 먼저 돌리는<br />1차 진단.</h3>
        <ol className="lp-steps5 lp-use3">
          {USE.map(([t, d], i) => (
            <li key={t}><span className="num">{String(i + 1).padStart(2, "0")}</span><b>{t}</b><small>{d}</small></li>
          ))}
        </ol>
      </section>

      {/* 데이터: 큰 숫자 세 개 + AWS */}
      <section className="lp-x lp-x-light" id="data">
        <h3 className="lp-x-title">실제 공고와<br />실제 과정으로만.</h3>
        <div className="lp-big3 lp-big3-acc">
          {DATA.map(([v, k, d]) => (
            <div key={k}><span className="num">{v}</span><b>{k}</b><small>{d}</small></div>
          ))}
        </div>
        <ul className="lp-aws" aria-label="사용한 AWS 서비스">{AWS.map((x) => <li key={x}>{x}</li>)}</ul>
      </section>

      <section className="lp-end">
        <h3>어디서부터 건너야 할지, 지금 확인해 보세요</h3>
        <div className="lp-cta">
          <button className="btn lp-btn lp-btn-inv" onClick={onStart}>지금 분석 시작</button>
          <button className="btn lp-btn lp-btn-line" onClick={onSample}>예시로 체험하기</button>
        </div>
      </section>
    </div>
  );
}
