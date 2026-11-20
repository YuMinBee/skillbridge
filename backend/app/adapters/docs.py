"""올린 문서에서 글자만 뽑는다. 파일은 저장하지 않는다.

PDF(자소서·포트폴리오·CV), Word(.docx 자소서), Markdown/텍스트(노션 '내보내기'). 스캔 이미지 PDF는 글자가 없어서 읽지 못한다.
"""
import io
import re

MAX_DOC_CHARS = 10_000   # 문서 하나에서 읽는 글자 수 상한 (Bedrock 입력 비용 상한)
EXT = (".pdf", ".docx", ".md", ".txt")


class DocError(ValueError):
    pass


def kind_of(filename: str) -> str:
    n = (filename or "").lower()
    for e in EXT:
        if n.endswith(e):
            return e[1:]
    raise DocError("PDF·Word(docx)·노션 내보내기(md·txt)만 올릴 수 있습니다")


def text_of(filename: str, raw: bytes) -> str:
    k = kind_of(filename)
    try:
        if k == "pdf":
            from pypdf import PdfReader
            t = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)
        elif k == "docx":
            import docx
            d = docx.Document(io.BytesIO(raw))
            rows = [p.text for p in d.paragraphs]
            for tb in d.tables:  # 자소서 양식은 표 안에 답을 쓰는 경우가 많다
                for r in tb.rows:
                    rows.append(" | ".join(dict.fromkeys(c.text.strip() for c in r.cells if c.text.strip())))
            t = "\n".join(rows)
        else:
            t = raw.decode("utf-8-sig", errors="replace")
            t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)  # 노션 내보내기의 이미지 링크
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DocError(f"{filename}을(를) 읽지 못했습니다") from e
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:MAX_DOC_CHARS]
