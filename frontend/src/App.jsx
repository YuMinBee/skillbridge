import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Market from "./tabs/Market.jsx";
import Seeker from "./tabs/Seeker.jsx";
import Corp from "./tabs/Corp.jsx";
import Analyze from "./tabs/Analyze.jsx";

// 2026-11-17 전면 수정: 탭은 '역량 분석' 하나. 예전 화면은 주소(#seeker·#corp·#market)로만 열린다(코드 유지, 발표에서 안 씀)
const TABS = [["analyze", "역량 분석", "취준생"]];
const OLD = ["seeker", "corp", "market"];
const hashTab = () => { const h = location.hash.slice(1); return TABS.some(([k]) => k === h) || OLD.includes(h) ? h : "analyze"; };

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
    api.companies(true).then(setCompanies).catch(() => {});
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
          <p>내 경험의 강점을 <b>STAR</b>로 진단하고, <b>근거가 붙은</b> 과제를 추천합니다.</p>
          <div className="tools">
            {meta && (
              <>
                <span className={`mode ${meta.bedrock === "bedrock" ? "live" : ""}`} title="Bedrock 호출 모드">
                  {meta.bedrock === "bedrock" ? "AI 연결됨 · Bedrock" : meta.public_mock ? "규칙 엔진 · 공개" : "규칙 엔진(오프라인)"}
                </span>
                <span className={`mode ${meta.sources?.courses === "live" && meta.sources?.market === "live" ? "live" : ""}`}
                  title="공고(잡알리오)·교육과정(고용24)은 실데이터 · 기업 A·B·C와 예시 지원자는 가상 · D는 공개 자료 재구성 · E~H는 현업 청취 기준">
                  {meta.sources?.courses === "live" && meta.sources?.market === "live" ? "공고·과정 실데이터" : "샘플 데이터"}
                </span>
              </>
            )}
            <button className="btn ghost sm" onClick={toggleTheme} aria-label="라이트/다크 전환">테마</button>
            <button className="btn ghost sm" onClick={reset}>초기화</button>
          </div>
        </div>
        <nav className="tabs" role="tablist" aria-label="화면 전환">
          {TABS.map(([k, l, who]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => go(k)}>{l} <small>{who}</small></button>
          ))}
        </nav>
      </header>
      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}
      <div hidden={tab !== "analyze"}><Analyze active={tab === "analyze"} /></div>
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
