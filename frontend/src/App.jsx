import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Market from "./tabs/Market.jsx";
import Seeker from "./tabs/Seeker.jsx";
import Corp from "./tabs/Corp.jsx";

const TABS = [["market", "① 시장 분석"], ["seeker", "② 취준생 진단"], ["corp", "③ 기업 콘솔"]];
const hashTab = () => { const h = location.hash.slice(1); return TABS.some(([k]) => k === h) ? h : "market"; };

export default function App() {
  const [tab, setTab] = useState(hashTab);
  const [meta, setMeta] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [corpVersion, setCorpVersion] = useState(0);
  const [toast, setToast] = useState("");
  const [err, setErr] = useState("");
  const tt = useRef(null);

  const notify = useCallback((msg) => {
    setToast(msg); clearTimeout(tt.current); tt.current = setTimeout(() => setToast(""), 2400);
  }, []);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setErr("API 서버에 연결하지 못했습니다. 백엔드(포트 8010)가 켜져 있는지 확인하세요."));
    api.companies().then(setCompanies).catch(() => {});
    const onHash = () => setTab(hashTab());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (k) => { setTab(k); try { history.replaceState(null, "", "#" + k); } catch { /* noop */ } };

  const toggleTheme = () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch { /* noop */ }
  };

  const reset = async () => {
    if (!confirm("내가 바꾼 기업 설정을 처음 상태로 되돌릴까요? (다른 방문자에게는 영향 없음)")) return;
    try { await api.reset(); setCorpVersion((v) => v + 1); notify("기업 설정을 처음 상태로 되돌렸습니다."); }
    catch (e) { notify(e.message); }
  };

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <h1>역량다리</h1>
          <p>AI·클라우드 채용시장 분석 → 기업 교육 트랙 → 취준생 맞춤 학습경로 (Amazon Bedrock 에이전트)</p>
          <span className="sample">{meta?.sources?.market === "live" ? "실데이터 · 기업·지원자는 가상" : "가상 데이터 데모"}</span>
          <div className="tools">
            {meta && (
              <>
                <span className={`mode ${meta.bedrock === "bedrock" ? "live" : ""}`} title="Bedrock 호출 모드">
                  {meta.bedrock === "bedrock" ? "BEDROCK" : meta.public_mock ? "규칙 엔진 · 공개" : "MOCK"}
                </span>
                <span className={`mode ${meta.sources?.courses === "live" ? "live" : ""}`} title={meta.sources?.courses === "live" ? "교육과정: 고용24 훈련과정 API 실데이터" : "교육과정: 가상 샘플"}>과정 {meta.sources?.courses === "live" ? "LIVE" : "SAMPLE"}</span>
                <span className={`mode ${meta.sources?.market === "live" ? "live" : ""}`} title={meta.sources?.market === "live" ? "시장: 실제 공고 + 가상 샘플 보충" : "시장: 가상 공고 샘플"}>시장 {meta.sources?.market === "live" ? "LIVE+SAMPLE" : "SAMPLE"}</span>
              </>
            )}
            <button className="btn ghost sm" onClick={toggleTheme} aria-label="라이트/다크 전환">테마</button>
            <button className="btn ghost sm" onClick={reset}>초기화</button>
          </div>
        </div>
        <nav className="tabs" role="tablist" aria-label="화면 전환">
          {TABS.map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => go(k)}>{l}</button>
          ))}
        </nav>
      </header>
      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}
      <div hidden={tab !== "market"}><Market /></div>
      <div hidden={tab !== "seeker"}><Seeker companies={companies} corpVersion={corpVersion} active={tab === "seeker"} mode={meta?.bedrock} /></div>
      <div hidden={tab !== "corp"}>
        <Corp companies={companies} corpVersion={corpVersion} active={tab === "corp"}
          onChanged={(msg) => { setCorpVersion((v) => v + 1); if (msg) notify(msg); }} />
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
