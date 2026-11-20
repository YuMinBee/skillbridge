"""배포 주소 끝까지 점검 (2026-11-20). 입력 형식마다, 이상한 입력마다 깨지지 않고 이유를 알려 주는지 본다.

python scripts/smoke_deploy.py [주소]     → eval/smoke_deploy.md (표)
- 입력 파일은 모두 이 스크립트가 만드는 합성 문서(개인 자료 없음). Bedrock 호출은 정상 입력 몇 개뿐(약 $0.2).
"""
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = (sys.argv[1] if len(sys.argv) > 1 else "https://fazwtcf7omav34gdiahcgvds3m0zyafv.lambda-url.ap-northeast-2.on.aws").rstrip("/")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
DEMO = (ROOT / "docs" / "pivot" / "captures" / "demo_resume.md").read_text(encoding="utf-8").split("---", 1)[1].strip()
EN = ("Library checkout system. Our club lost five devices a semester because loans were tracked in a chat room. "
      "I owned the backend. I built a loan API with Spring Boot and MySQL and added a scheduler that emails a reminder "
      "one day before the due date. The next semester we lost zero devices, and 60 members still use it.")


def docx_bytes(text):
    from docx import Document
    d = Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    b = io.BytesIO(); d.save(b); return b.getvalue()


def blank_pdf():
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(595, 842)
    b = io.BytesIO(); w.write(b); return b.getvalue()


def multipart(files, fields):
    bd = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, data, ctype in files:
        out.write(f"--{bd}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
        out.write(data); out.write(b"\r\n")
    out.write(f"--{bd}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={bd}"


def post(path, body, ctype):
    req = urllib.request.Request(URL + path, data=body, headers={"Content-Type": ctype}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def wait(job_id, limit=240):
    t0 = time.time()
    while time.time() - t0 < limit:
        with urllib.request.urlopen(f"{URL}/api/jobs/{job_id}", timeout=30) as r:
            j = json.loads(r.read())
        if j["status"] not in ("queued", "running"):
            return j, time.time() - t0
        time.sleep(4)
    return {"status": "timeout"}, limit


def run_case(name, files=None, fields=None, json_body=None, expect="done"):
    fields = {"sector": "private", "job_family": "auto", **(fields or {})}
    if json_body is not None:
        code, resp = post("/api/analyze", json.dumps(json_body).encode(), "application/json")
    else:
        body, ctype = multipart(files or [], fields)
        code, resp = post("/api/analyze/docs", body, ctype)
    if code != 200 or "job_id" not in resp:
        msg = resp.get("detail") if isinstance(resp, dict) else resp
        return {"case": name, "expect": expect, "got": f"HTTP {code}", "detail": str(msg)[:120], "ok": expect == "reject"}
    j, sec = wait(resp["job_id"])
    r = j.get("result") or {}
    st = r.get("strengths") or []
    detail = (f"경험 {len(st)} · 강함 {sum(e['level'] == 'strong' for e in st)} · 직군 {(r.get('job_family') or {}).get('label')} · "
              f"추천 {len(r.get('recommendations') or [])} · {sec:.0f}초 · ${(j.get('cost') or {}).get('usd', 0):.3f}")
    if j.get("status") != "done":
        detail = f"{j.get('status')}: {j.get('error', '')}"[:120]
    if expect == "done":
        ok = j.get("status") == "done"
    else:  # 거절: 접수에서 4xx이거나, 작업이 이유와 함께 실패
        ok = j.get("status") == "failed" and bool(j.get("error"))
    return {"case": name, "expect": expect, "got": j.get("status"), "detail": detail, "ok": ok}


def main():
    cases = [
        ("Word(.docx) 자소서", dict(files=[("자소서.docx", docx_bytes(DEMO), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])),
        ("노션 내보내기(.md)", dict(files=[("notion.md", ("# 지원 동기와 역량\n\n" + DEMO).encode(), "text/markdown")])),
        ("텍스트(.txt) + GitHub 링크", dict(files=[("a.txt", DEMO.encode(), "text/plain")], fields={"github": "https://github.com/octocat"})),
        ("여러 파일 동시(2개)", dict(files=[("a.txt", DEMO.split("3.")[0].encode(), "text/plain"), ("b.md", ("3." + DEMO.split("3.", 1)[1]).encode(), "text/markdown")])),
        ("같은 문서 다시(캐시)", dict(files=[("자소서.docx", docx_bytes(DEMO), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])),
        ("공공기관 선택", dict(files=[("a.txt", DEMO.encode(), "text/plain")], fields={"sector": "public"})),
        ("영어 자소서", dict(files=[("en.txt", EN.encode(), "text/plain")], expect="done")),
        ("경험 없는 글(기술 목록만)", dict(files=[("skills.txt", "[보유 기술] Java, Python\n[자격증] 없음".encode(), "text/plain")], expect="done")),
        ("빈 파일", dict(files=[("empty.txt", b"", "text/plain")], expect="reject")),
        ("글자 없는 PDF(이미지·스캔)", dict(files=[("scan.pdf", blank_pdf(), "application/pdf")], expect="reject")),
        ("5MB 넘는 파일", dict(files=[("big.txt", ("가" * 2_000_000).encode(), "text/plain")], expect="reject")),
        ("지원 안 하는 형식(.hwp)", dict(files=[("a.hwp", b"HWP Document File", "application/octet-stream")], expect="reject")),
        ("파일 5개(상한 4)", dict(files=[(f"{i}.txt", DEMO.encode(), "text/plain") for i in range(5)], expect="reject")),
        ("없는 GitHub 아이디만", dict(files=[], fields={"github": "this-user-should-not-exist-kosa06-zz"}, expect="reject")),
    ]
    rows = []
    for name, kw in cases:
        r = run_case(name, **kw)
        time.sleep(8)  # IP당 분당 8회 상한 안쪽으로
        rows.append(r)
        print(("✓" if r["ok"] else "✗"), name, "|", r["got"], "|", r["detail"])
    md = ["# 배포 주소 점검", "", f"{time.strftime('%Y-%m-%d %H:%M')} · {URL}", "",
          "| 입력 | 기대 | 결과 | 내용 | 통과 |", "|---|---|---|---|---|"]
    md += [f"| {r['case']} | {'분석 완료' if r['expect'] == 'done' else '거절 + 이유'} | {r['got']} | {r['detail']} | {'✓' if r['ok'] else '✗'} |" for r in rows]
    md += ["", f"통과 {sum(r['ok'] for r in rows)}/{len(rows)}. 입력은 모두 합성 문서."]
    (ROOT / "eval" / "smoke_deploy.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
