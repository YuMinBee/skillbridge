import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Market from "./tabs/Market.jsx";
import Seeker from "./tabs/Seeker.jsx";
import Corp from "./tabs/Corp.jsx";
import Analyze from "./tabs/Analyze.jsx";
import Landing from "./tabs/Landing.jsx";

// 2026-11-17 전면 수정: 탭은 '역량 분석' 하나. 예전 화면은 주소(#seeker·#corp·#market)로만 열린다(코드 유지, 발표에서 안 씀)
// 11-21: 첫 화면은 소개(home). 공유 결과 주소(?job=)는 바로 분석 화면으로
const TABS = [["home", "소개", ""], ["analyze", "역량 분석", "취준생"]];
const OLD = ["seeker", "corp", "market"];
const hashTab = () => {
  const h = location.hash.slice(1);
  if (TABS.some(([k]) => k === h) || OLD.includes(h)) return h;
  return new URLSearchParams(location.search).get("job") ? "analyze" : "home";
};

export default function App() {
  const [tab, setTab] = useState(hashTab);
  const [meta, setMeta] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [corpVersion, setCorpVersion] = useState(0);
  const [toast, setToast] = useState("");
  const [sampleTick, setSampleTick] = useState(0);  // 소개 화면 '예시로 체험하기' → 분석 화면이 받아서 바로 시작
  const tt = useRef(null);

  const notify = useCallback((msg) => {
    setToast(msg); clearTimeout(tt.current); tt.current = setTimeout(() => setToast(""), 2400);
  }, []);

  useEffect(() => {
    // 역량 분석 탭은 meta 없이 돈다. 연결 문제는 분석을 시작할 때 그 화면에서 알린다(시작 화면에 빨간 배너를 띄우지 않음)
    api.meta().then(setMeta).catch(() => {});
    api.companies(true).then(setCompanies).catch(() => {});
    const onHash = () => setTab(hashTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (k) => { setTab(k); try { history.replaceState(null, "", "#" + k); } catch { /* noop */ } };

  return (
    <div className="wrap">
      <header className="top">
        {/* 11-22: 탭(소개·역량 분석)을 내림. 로고 = 소개로, 소개의 버튼 = 분석으로 */}
        <div className="brand">
          <h1><a href="#home" className="logo" onClick={(e) => { e.preventDefault(); go("home"); window.scrollTo(0, 0); }}>SkillBridge</a></h1>
        </div>
      </header>
      {tab === "home" && <Landing onStart={() => { go("analyze"); window.scrollTo(0, 0); }}
        onSample={() => { go("analyze"); window.scrollTo(0, 0); setSampleTick((n) => n + 1); }} />}
      <div hidden={tab !== "analyze"}><Analyze active={tab === "analyze"} sampleTick={sampleTick} /></div>
      <div hidden={tab !== "market"}>{tab === "market" && <Market />}</div>
      <div hidden={tab !== "seeker"}><Seeker companies={companies.filter((c) => c.listed !== false)} corpVersion={corpVersion} active={tab === "seeker"} mode={meta?.bedrock} /></div>
      <div hidden={tab !== "corp"}>
        <Corp companies={companies} corpVersion={corpVersion} active={tab === "corp"}
          onChanged={(msg) => { setCorpVersion((v) => v + 1); if (msg) notify(msg); }} />
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
