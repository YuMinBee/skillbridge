"""분석 결과(JSON) → 보고서 PDF. 화면의 'PDF로 저장'과 같은 내용을 파일로 만든다.

사용:  .venv\\Scripts\\python scripts\\report.py                 (eval/private의 가장 최근 mine_*.json)
      .venv\\Scripts\\python scripts\\report.py 결과.json
결과:  같은 폴더에 .html과 .pdf (Edge로 인쇄). 개인 자료라 eval/private는 커밋되지 않는다.
"""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIV = ROOT / "eval" / "private"
SLOT = [("S", "상황"), ("T", "과제"), ("A", "행동"), ("R", "결과")]
LEVEL = {"strong": "강점", "ok": "보통", "weak": "약함"}
KIND = {"resume": "내 문서", "posting": "공고", "posting_stats": "공고 집계", "course": "고용24 과정"}
e = html.escape

CSS = """
@page{size:A4;margin:16mm 14mm}
body{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#18202f;font-size:11.5px;line-height:1.55;margin:0}
h1{font-size:20px;margin:0 0 2px} h2{font-size:14px;margin:18px 0 8px;padding-bottom:4px;border-bottom:2px solid #3a5cf5}
.sub{color:#5a6478;font-size:11px;margin:0 0 12px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.card{border:1px solid #e1e6f0;border-radius:8px;padding:8px 10px}
.card b{display:block;font-size:18px} .card small{color:#5a6478}
.rank{margin:4px 0 0;padding:0;list-style:none;font-size:10.5px;color:#5a6478}
.exp{border:1px solid #e1e6f0;border-radius:8px;padding:8px 10px;margin-bottom:8px;break-inside:avoid}
.exp .h{display:flex;justify-content:space-between;font-weight:700}
.lv{font-size:10.5px;padding:1px 8px;border-radius:99px}
.strong{background:#dcf2e7;color:#1f8a5b}.ok{background:#fbeed6;color:#b26b00}.weak{background:#f8e1e1;color:#c23b3b}
table.slots{width:100%;border-collapse:collapse;margin-top:4px}
table.slots td{padding:3px 6px;vertical-align:top;border-top:1px solid #f1f4fb}
table.slots td.k{width:52px;font-weight:700;white-space:nowrap}
td.off{color:#9aa3b5}
.hint{color:#5a6478;font-size:10.5px;margin:4px 0 0}
ul.gaps{columns:2;margin:0;padding-left:18px} ol.reco{padding-left:18px} ol.reco li{margin-bottom:6px;break-inside:avoid}
ol.cites{font-size:10px;color:#5a6478;padding-left:20px} ol.cites li{margin-bottom:2px;word-break:break-all}
.foot{margin-top:16px;font-size:10px;color:#5a6478;border-top:1px solid #e1e6f0;padding-top:6px}
"""


def render(d: dict) -> str:
    r, cites = d["result"], {c["n"]: c for c in d.get("citations", [])}
    s, jf = r["strengths"], r.get("job_family") or {}
    strong = sum(1 for x in s if x["level"] == "strong")
    rank = "".join(f"<li>{i + 1}. {e(x['label'])} <b style='display:inline;font-size:11px'>{x['score']}</b></li>"
                   for i, x in enumerate(jf.get("ranking", [])))
    cost = d.get("cost") or {}
    out = [f"<!doctype html><meta charset='utf-8'><title>역량 분석 보고서</title><style>{CSS}</style>",
           "<h1>역량 분석 보고서</h1>",
           f"<p class='sub'>STAR(기업 역량면접 방식)로 경험을 판정하고, 공개 채용 공고 기준으로 부족한 역량과 보완 교육을 정리했습니다. "
           f"근거 {len(cites)}개 · 분석 {d.get('sec', '?')}초 · 비용 ${cost.get('usd', 0):.3f}</p>",
           "<div class='cards'>",
           f"<div class='card'><small>강점 경험</small><b>{strong} / {len(s)}</b></div>",
           f"<div class='card'><small>강점 직군</small><b>{e(jf.get('ranking', [{}])[0].get('label', '—'))}</b><ol class='rank'>{rank}</ol></div>",
           f"<div class='card'><small>준비도 · {e(jf.get('label', ''))}</small><b>{r['readiness'].get('apply') if r['readiness'].get('apply') is not None else '—'}</b><small>공개 공고 기준</small></div>",
           f"<div class='card'><small>보완할 역량</small><b>{len(r['gaps'])}</b><small>추천 {len(r['recommendations'])}개</small></div>",
           "</div>", "<h2>① 경험별 강점 (STAR)</h2>"]
    for x in s:
        rows = "".join(
            f"<tr><td class='k'>{k} {lab}</td>" + (f"<td>“{e(x['slots'][k]['quote'])}”</td>" if x["slots"][k]["present"] else "<td class='off'>없음</td>") + "</tr>"
            for k, lab in SLOT)
        out.append(f"<div class='exp'><div class='h'><span>{e(x['title'])}</span><span><span class='lv {x['level']}'>{LEVEL[x['level']]}</span> {x['score']} / 5</span></div>"
                   f"<table class='slots'>{rows}</table>" + (f"<p class='hint'>보완: {e(x['missing_hint'])}</p>" if x.get("missing_hint") else "") + "</div>")
    out.append("<h2>② 부족한 역량</h2><ul class='gaps'>")
    for g in r["gaps"]:
        out.append(f"<li>{e(g['name'])} · {e(g['status_label'])} ({'필수' if g.get('weight') == 2 else '우대'}) "
                   + "".join(f"[{n}]" for n in g.get("cites", [])) + "</li>")
    out.append("</ul><h2>③ 추천 과제와 교육</h2><ol class='reco'>")
    for x in r["recommendations"]:
        if x.get("abstained"):
            out.append(f"<li><b>추천하지 않음</b> — {e(x.get('abstain_reason') or '근거 없음')}</li>")
            continue
        c = x.get("course")
        course = f"<br>교육: {e(c['name'])} ({c['hours']}시간)" + (f" · {e(c['url'])}" if c.get("url") else "") if c else ""
        out.append(f"<li><b>{e(x['task'])}</b><br><span class='hint'>왜: {e(x['why'])} {''.join(f'[{n}]' for n in x.get('cites', []))}</span>{course}</li>")
    out.append("</ol><h2>근거</h2><ol class='cites'>")
    for n in sorted(cites):
        c = cites[n]
        out.append(f"<li value='{n}'>[{e(KIND.get(c['kind'], c['kind']))}] {e(c['title'])}"
                   + (f" — “{e(c['quote'])}”" if c.get("quote") else "") + (f" ({e(c['url'])})" if c.get("url") else "") + "</li>")
    v = d.get("verify") or {}
    out.append(f"</ol><p class='foot'>검증: {'통과' if v.get('passed') else '제거 ' + str(len(v.get('removed', []))) + '건'} "
               "(STAR 인용 ⊂ 원문 · 과정 ⊂ 고용24 카탈로그 · 추천마다 근거 1개 이상) · 점수는 규칙으로만 계산 · "
               "채용 합불 판단에 쓰지 않습니다 · 역량다리</p>")
    return "\n".join(out)


def to_pdf(html_path: Path) -> Path | None:
    edge = next((p for p in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if p and Path(p).exists()), None)
    if not edge:
        return None
    pdf = html_path.with_suffix(".pdf")
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    html_path.resolve().as_uri()], capture_output=True, timeout=60)
    return pdf if pdf.exists() else None


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else max(PRIV.glob("mine_*.json"), default=None)
    if not src:
        sys.exit("결과가 없습니다. 먼저 .\\tasks.ps1 mine")
    d = json.loads(Path(src).read_text(encoding="utf-8"))
    h = Path(src).with_name(Path(src).stem.replace("mine_", "report_") + ".html")
    h.write_text(render(d), encoding="utf-8")
    pdf = to_pdf(h)
    print(f"보고서: {pdf or h}")
    return pdf or h


if __name__ == "__main__":
    main()
