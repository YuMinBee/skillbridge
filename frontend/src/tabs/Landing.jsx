// 첫 화면(소개). 숫자는 AGENTS.md '발표 숫자 확정'(eval/trust/report.md, test 60단락 × 5회)·report_retrieval.md·
// task_judge_result.json과 같게 둔다. 바뀌면 여기도 고친다. 웹 방식이 "지어낸다"고 쓰지 않는다(팀 규칙).
// 11-22 원칙: 히어로처럼 섹션마다 큰 문장 하나 + 큰 숫자/실제 화면 하나. 작은 글씨 카드를 늘리지 않는다.
import { useEffect, useRef, useState } from "react";
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
  { k: "자소서에 없는 내용을 있다고 한 비율", web: "29.1%", us: "2.1%", note: "Claude에 직접 물으면 프롬프트를 잘 써도 열 번에 세 번꼴 → SkillBridge는 백 번에 두 번꼴" },
  { k: "같은 자소서를 5번 넣었을 때 매번 같은 답", web: "86.7%", us: "100%", note: "Claude에 직접 물으면 프롬프트를 잘 써도 열 개 중 한 개꼴로 답이 바뀜 → SkillBridge는 매번 같은 답" },
];

// 에이전트 단계 (backend/app/agents/supervisor.py 순서) — 한 줄씩만
const FLOW = [
  ["개인정보 가리기", "이름·연락처부터 가림"],
  ["강점 진단", "내 문장을 그대로 인용"],
  ["공고 기준 비교", "실제 공고 문장과 비교"],
  ["과제 · 교육과정", "맞는 과정이 없으면 추천 안 함"],
  ["근거 검증", "어긋나면 코드가 지움"],
];

const CHECKS = [
  ["96.2%", "경험 정리 정확도", "사람 2명이 따로 만든 정답과 비교 (두 사람끼리는 89% 일치)", "report.md"],
  ["0.824", "교육과정 찾기 점수", "1점 만점 · 검색 방식 7가지 중 가장 높음 · 단순 단어 검색은 0.648", "report_retrieval.md"],
  ["0 / 16", "엉뚱한 추천 과제", "사람이 추천 과제 16개를 하나씩 직접 판정", "task_judge_result.json"],
];

const DATA = [["109", "민간 IT 공고", "기업 공식 채용 페이지 직접 수집 포함"], ["263", "공공기관 IT 공고", "잡알리오"], ["1,856", "고용24 교육과정", "앞으로 개강하는 과정만 추천"]];
const AWS = ["Amazon Bedrock · Claude Sonnet 4.6", "Cohere Embed v4", "Bedrock Guardrails", "AWS Lambda", "Amazon DynamoDB"];

// 건너는 길: 예시 자소서(docs/pivot/captures/demo_resume.md)를 실제로 분석한 결과에서 발췌. 공고·과정 문장도 실제 결과 그대로
const CROSS = [
  {
    n: "01", t: "지금의 나", d: "자소서 속 경험을 상황·과제·행동·결과(STAR) 네 칸으로 나누고, 칸마다 내 문장을 그대로 인용합니다.",
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

// 모션: 화면에 들어오면 한 번만. '애니메이션 줄이기'를 켠 사람에게는 바로 최종 상태
const calm = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// [data-reveal] 요소가 화면에 들어오면 .in을 붙인다(한 번만)
function useReveal(root) {
  useEffect(() => {
    const els = root.current ? [...root.current.querySelectorAll("[data-reveal]")] : [];
    if (calm() || !("IntersectionObserver" in window)) { els.forEach((e) => e.classList.add("in")); return undefined; }
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.2 });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [root]);
}

// 비교 숫자: 화면에 들어오면 웹 값에서 우리 값으로 세어 감 (예: 29.1 → 2.1)
function CountTo({ from, to }) {
  const ref = useRef(null);
  const dec = String(to).includes(".") ? 1 : 0;
  const [v, setV] = useState(calm() ? to : from);
  useEffect(() => {
    if (calm() || !ref.current || !("IntersectionObserver" in window)) { setV(to); return undefined; }
    let raf = 0;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now(), D = 1100;
      const step = (t) => { const k = Math.min(1, (t - t0) / D), ease = 1 - Math.pow(1 - k, 3); setV(from + (to - from) * ease); if (k < 1) raf = requestAnimationFrame(step); };
      raf = requestAnimationFrame(step);
    }, { threshold: 0.6 });
    io.observe(ref.current);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [from, to]);
  return <b ref={ref} className="num">{v.toFixed(dec)}%</b>;
}

export default function Landing({ onStart, onSample }) {
  const root = useRef(null);
  useReveal(root);
  return (
    <div className="lp" ref={root}>
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
            <li key={c.n} data-reveal>
              <div className="lp-cross-l"><span className="lp-cross-n">{c.n}</span><b>{c.t}</b><p>{c.d}</p></div>
              <div className="lp-cross-r">{c.card}</div>
            </li>
          ))}
        </ol>
        <p className="lp-x-foot">예시 자소서를 실제로 분석한 결과에서 발췌했습니다</p>
      </section>

      {/* 비교: 큰 숫자 대비 두 개 */}
      <section className="lp-x lp-x-light" id="compare">
        <h3 className="lp-x-title">Claude에게 그냥 묻는 것보다,<br />믿을 수 있습니다.</h3>
        <div className="lp-vs">
          {VS.map((v) => (
            <div className="lp-vs-i" key={v.k}>
              <p className="lp-vs-k">{v.k}</p>
              <div className="lp-vs-n"><s className="num">{v.web}</s><span aria-hidden="true">→</span><CountTo from={parseFloat(v.web)} to={parseFloat(v.us)} /></div>
            </div>
          ))}
        </div>
        <p className="lp-x-foot">같은 Claude Sonnet 4.6 모델로 자소서 60단락을 5번씩 비교 · 어떻게 물어도 차이가 우연이 아니었습니다(95% 신뢰구간) · <a href={REPO + "report.md"} target="_blank" rel="noreferrer">평가 기록</a></p>
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
        <p className="lp-x-foot">경험 정리 정확도는 우리 기준을 그대로 알려 준 프롬프트(94.7%)와 비슷한 수준입니다</p>
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
