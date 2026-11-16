"""같은 팀·부서 쌍의 블로그 원문을 받아 본문 텍스트만 남긴다 (데이터로만 다룸)."""
import glob, hashlib, json, re, sys
from html.parser import HTMLParser
from pathlib import Path
import httpx

REPO = Path(__file__).resolve().parents[2]  # 레포 루트
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)

class T(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"}
    def __init__(s):
        super().__init__(); s.d = 0; s.buf = []
    def handle_starttag(s, t, a):
        if t in s.SKIP: s.d += 1
        if t in ("p", "li", "h1", "h2", "h3", "h4", "pre", "br", "tr", "div"): s.buf.append("\n")
    def handle_endtag(s, t):
        if t in s.SKIP and s.d: s.d -= 1
    def handle_data(s, x):
        if not s.d: s.buf.append(x)

best = {}
for f in sorted(glob.glob(str(REPO / "research/public_companies/batch_*.json"))):
    for c in json.load(open(f, encoding="utf-8")): best[c["key"]] = c
pairs = {k: c for k, c in best.items() if c.get("match") in ("same_team", "same_dept")}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
idx = {}
for k, c in pairs.items():
    for u in sorted({w["url"] for w in c.get("work_sources", [])}):
        name = hashlib.sha1(u.encode()).hexdigest()[:10] + ".txt"
        try:
            r = httpx.get(u, headers=H, follow_redirects=True, timeout=30)
            p = T(); p.feed(r.text)
            txt = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\xa0]+", " ", "".join(p.buf))).strip()
            (OUT / name).write_text(txt, encoding="utf-8")
            # 조사 때 인용한 문장이 받은 본문에 있는지 = 본문을 제대로 받았는지
            qs = [w["quote"][:25] for w in c["work_sources"] if w["url"] == u]
            hit = sum(q in txt for q in qs)
            print(k, r.status_code, len(txt), f"quote {hit}/{len(qs)}", u[:60])
            idx.setdefault(k, []).append({"url": u, "file": name, "chars": len(txt), "quote_hit": hit, "quotes": len(qs)})
        except Exception as e:
            print(k, "ERR", type(e).__name__, u[:60])
json.dump(idx, open(OUT / "index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
