"""2계층 스킬 사전의 아래층: canonical 스킬 + 별칭 정확 매칭.

- 긴 별칭부터 매칭하고, 이미 잡힌 구간과 겹치는 짧은 별칭은 버린다
  (예: '자바스크립트' 안의 '자바', 'AWS SageMaker' 안의 'AWS').
- 영문 별칭은 앞뒤가 영숫자가 아닐 때만 인정한다 ('Java' ≠ 'JavaScript').
- 3글자 이하 영문 별칭(SQL, RAG, ROS …)은 대소문자를 구분한다.
"""
import csv
import re
from functools import lru_cache

from .config import SKILLS_CSV

_ASCII_ALNUM = re.compile(r"[A-Za-z0-9]")
# 대소문자로만 다른 이름이 있는 별칭: 'React'(프론트엔드) ≠ 'ReAct'(에이전트 기법)
_CASE_SENSITIVE = {"React"}


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


class SkillDict:
    def __init__(self, path=SKILLS_CSV):
        self.skills: dict[str, dict] = {}
        entries: list[tuple[str, str]] = []
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sid = r["skill_id"]
                self.skills[sid] = {"id": sid, "name": r["canonical"], "category": r["category"],
                                    "ncs_unit": r.get("ncs_unit", "")}
                aliases = [x.strip() for x in (r["aliases_ko"] + "|" + r["aliases_en"]).split("|") if x.strip()]
                self.skills[sid]["aliases"] = aliases
                names = {r["canonical"], *aliases}
                entries += [(n, sid) for n in names]
        entries.sort(key=lambda e: -len(e[0]))
        self._patterns = []
        for name, sid in entries:
            pre = r"(?<![A-Za-z0-9])" if _ASCII_ALNUM.match(name[0]) else ""
            post = r"(?![A-Za-z0-9])" if _ASCII_ALNUM.match(name[-1]) else ""
            if len(name) == 1:  # 'R'이 'R&D'에 걸리지 않게
                post = r"(?![A-Za-z0-9&])"
            flags = 0 if (_is_ascii(name) and len(name) <= 3) or name in _CASE_SENSITIVE else re.IGNORECASE
            self._patterns.append((re.compile(pre + re.escape(name) + post, flags), sid))

    def name(self, sid: str) -> str:
        return self.skills.get(sid, {}).get("name", sid)

    def exists(self, sid: str) -> bool:
        return sid in self.skills

    def find(self, text: str) -> list[dict]:
        """텍스트에서 스킬 언급을 찾는다. [{skill_id, mention, start, end}] (등장 순)"""
        taken = bytearray(len(text))
        found = []
        for pat, sid in self._patterns:
            for m in pat.finditer(text):
                s, e = m.span()
                if any(taken[s:e]):
                    continue
                taken[s:e] = b"\x01" * (e - s)
                found.append({"skill_id": sid, "mention": m.group(0), "start": s, "end": e})
        found.sort(key=lambda x: x["start"])
        return found


@lru_cache(maxsize=1)
def get_dict() -> SkillDict:
    return SkillDict()


_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            out += [s.strip() for s in _SENT_SPLIT.split(line) if s.strip()]
    return out
