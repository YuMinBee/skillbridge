"""GitHub 공개 레포 README 읽기 (포트폴리오 대신). 토큰 없이 공개 API만 쓴다(시간당 60회).

입력: 아이디(YuMinBee), 프로필 주소(https://github.com/YuMinBee), 레포 주소(https://github.com/YuMinBee/Coma).
아이디면 포크가 아닌 공개 레포 중 최근에 push한 MAX_REPOS개의 README를 읽는다. 비공개 레포는 읽지 않는다.
"""
import json
import re
import urllib.request

MAX_REPOS = 5
MAX_README = 2_000
_IN = re.compile(r"^(?:https?://)?(?:www\.)?(?:github\.com/)?([A-Za-z0-9-]{1,39})(?:/([A-Za-z0-9._-]{1,100}))?/?$")
_UA = {"User-Agent": "skillbridge-analyzer", "Accept": "application/vnd.github+json"}


class GithubError(ValueError):
    pass


def parse(s: str) -> tuple[str, str | None]:
    m = _IN.match((s or "").strip())
    if not m:
        raise GithubError("GitHub 아이디나 주소를 확인해 주세요 (예: github.com/아이디)")
    return m.group(1), m.group(2)


def _get(url: str, raw: bool = False, opener=None):
    h = dict(_UA)
    if raw:
        h["Accept"] = "application/vnd.github.raw"
    req = urllib.request.Request(url, headers=h)
    with (opener or urllib.request.urlopen)(req, timeout=10) as r:
        body = r.read()
    return body.decode("utf-8", errors="replace") if raw else json.loads(body)


def _clean(md: str) -> str:
    md = re.sub(r"<[^>]+>", " ", md)                       # HTML 배지·이미지
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)           # 이미지
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)       # 링크는 글자만
    md = re.sub(r"```.*?```", " ", md, flags=re.S)         # 코드 블록
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def readmes(target: str, opener=None) -> list[dict]:
    """→ [{repo, url, description, text}]"""
    user, repo = parse(target)
    try:
        if repo:
            meta = [_get(f"https://api.github.com/repos/{user}/{repo}", opener=opener)]
        else:
            rs = _get(f"https://api.github.com/users/{user}/repos?per_page=100&sort=pushed", opener=opener)
            meta = [r for r in rs if not r.get("fork") and not r.get("private") and r["name"].lower() != user.lower()]
            meta = meta[:MAX_REPOS]
    except Exception as e:  # noqa: BLE001
        raise GithubError("GitHub에서 레포를 읽지 못했습니다 (아이디 확인 또는 잠시 뒤 다시)") from e
    out = []
    for m in meta:
        try:
            md = _get(f"https://api.github.com/repos/{m['full_name']}/readme", raw=True, opener=opener)
        except Exception:  # noqa: BLE001  README 없는 레포는 건너뛴다
            continue
        out.append({"repo": m["name"], "url": m.get("html_url"), "description": m.get("description") or "",
                    "text": _clean(md)[:MAX_README]})
    return out


def as_document(items: list[dict]) -> str:
    return "\n\n".join(f"[GitHub · {it['repo']}]\n{it['description']}\n{it['text']}".strip() for it in items)
