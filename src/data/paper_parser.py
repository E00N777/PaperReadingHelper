"""
论文 PDF / 结构化文本解析：提取摘要、引言、结论等章节，用于不同输入模式的消融。
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def extract_sections_from_text(full_text: str) -> Dict[str, str]:
    """
    从纯文本中按常见标题抽取章节。
    返回 {"abstract": ..., "introduction": ..., "conclusion": ..., "full": ...}
    """
    sections = {"abstract": "", "introduction": "", "conclusion": "", "full": full_text}
    if not full_text or not full_text.strip():
        return sections

    # 常见节标题模式（不区分大小写）
    patterns = [
        (r"\b(?:abstract|summary)\b\s*[:\n]?", "abstract", r"(?:\n\n|\n(?=\d\.|\b(?:introduction|1\.)\b))"),
        (r"\b(?:introduction|intro)\b\s*[:\n]?", "introduction", r"(?:\n\n|\n(?=\d\.\s|\b(?:related|method|preliminary|2\.)\b))"),
        (r"\b(?:conclusion|conclusions|discussion)\b\s*[:\n]?", "conclusion", r"(?:\n\n|\n(?=\b(?:reference|acknowledgment|appendix)\b)|$)"),
    ]
    text = full_text
    for start_pat, key, end_pat in patterns:
        m = re.search(start_pat, text, re.I | re.DOTALL)
        if m:
            start = m.end()
            rest = text[start:]
            end_m = re.search(end_pat, rest, re.I | re.DOTALL)
            end = end_m.start() if end_m else len(rest)
            sections[key] = rest[:end].strip()[:8000]
    return sections


def extract_abstract_intro(full_text: str, max_chars: int = 8192) -> str:
    """
    仅抽取摘要 + 引言，用于消融实验「仅摘要+引言」输入。
    """
    sec = extract_sections_from_text(full_text)
    parts = [sec["abstract"], sec["introduction"]]
    combined = "\n\n".join(p for p in parts if p).strip()
    if not combined:
        combined = full_text[:max_chars]
    return combined[:max_chars]


def get_full_or_abstract_intro(
    full_text: str,
    mode: str = "abstract_intro",
    max_chars: int = 8192,
) -> str:
    """
    mode: "abstract_intro" 仅摘要+引言；"full" 全文（截断）。
    """
    if mode == "full":
        return full_text[:max_chars]
    return extract_abstract_intro(full_text, max_chars)


def parse_pdf_sections(pdf_path: str) -> Dict[str, str]:
    """
    从 PDF 路径解析出各章节文本（依赖 pdfplumber）。
    """
    try:
        import pdfplumber
    except ImportError:
        return {"full": "", "abstract": "", "introduction": "", "conclusion": ""}

    path = Path(pdf_path)
    if not path.exists():
        return {"full": "", "abstract": "", "introduction": "", "conclusion": ""}

    full_text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"
    return extract_sections_from_text(full_text)
