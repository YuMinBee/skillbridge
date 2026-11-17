"""BM25. 한글은 형태소 분석기 없이 2~3글자 n-gram, 영문·숫자는 단어 단위(소문자)."""
import math
import re
from collections import Counter

_WORD = re.compile(r"[가-힣]+|[A-Za-z][A-Za-z0-9+#.]*|\d+")


def tokens(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text):
        if w[0] >= "가":
            out += [w[i:i + n] for n in (2, 3) for i in range(len(w) - n + 1)] or [w]
        else:
            out.append(w.lower())
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(1, len(docs))
        df = Counter(t for c in self.tf for t in c)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        q = set(tokens(query))
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            for t in q & tf.keys():
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out
