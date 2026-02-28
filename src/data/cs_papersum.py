"""
CS-PaperSum 数据集加载与预处理。
数据集：https://github.com/zihaohe123/CS-PaperSum
Google Drive 下载后放置于 data/cs_papersum/
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any, Iterator

import pandas as pd


def _normalize_contribution(summary: Any) -> str:
    """将 CS-PaperSum 的结构化摘要转为 3-5 句的段落式贡献摘要。"""
    if isinstance(summary, str):
        return summary.strip()
    if isinstance(summary, dict):
        parts = []
        for key in ("Key Takeaways", "key_takeaways", "contributions", "summary"):
            if key in summary and summary[key]:
                v = summary[key]
                if isinstance(v, list):
                    parts.extend(v)
                else:
                    parts.append(str(v))
        if not parts:
            return str(summary)
        # 合并为连贯段落（取前几条作为句子）
        text = " ".join(p[:200] for p in parts[:6] if isinstance(p, str) and len(p) > 10)
        return text[:800] if text else str(summary)
    return str(summary)


def _load_json_or_jsonl(path: Path) -> List[Dict]:
    items = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read().strip()
    if not raw:
        return []
    if raw.startswith("["):
        items = json.loads(raw)
    else:
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items if isinstance(items, list) else [items]


def _paper_to_record(paper: Dict, summary_key: str = "summary") -> Optional[Dict[str, str]]:
    """单条论文转为统一格式：source_text, contribution_summary, meta."""
    title = paper.get("title", paper.get("Title", ""))
    abstract = paper.get("abstract", paper.get("Abstract", ""))
    conclusion = paper.get("conclusion", paper.get("Conclusion", ""))
    full_text = paper.get("full_text", paper.get("content", ""))

    if not title and not abstract:
        return None

    # 输入：优先 title + abstract + conclusion（与 CS-PaperSum 生成设定一致）
    source_parts = [f"Title: {title}", f"Abstract: {abstract}"]
    if conclusion:
        source_parts.append(f"Conclusion: {conclusion}")
    source_text = "\n\n".join(source_parts)
    if full_text and len(source_text) < 500:
        source_text = full_text[:16000]  # 截断

    # 贡献摘要目标
    summary = paper.get(summary_key) or paper.get("key_takeaways") or paper.get("Key Takeaways")
    if summary is None:
        for k in ("contributions", "contribution_summary", "takeaways"):
            if k in paper and paper[k]:
                summary = paper[k]
                break
    contribution_summary = _normalize_contribution(summary) if summary else ""

    if not contribution_summary and not abstract:
        return None

    return {
        "source_text": source_text,
        "contribution_summary": contribution_summary or abstract[:500],
        "title": title,
        "abstract": abstract,
        "conclusion": conclusion,
        "meta": {k: v for k, v in paper.items() if k not in ("abstract", "conclusion", "full_text", "content", summary_key, "key_takeaways", "Key Takeaways", "contributions", "contribution_summary", "takeaways")},
    }


def load_cs_papersum(
    data_dir: str = "data/cs_papersum",
    summary_key: str = "summary",
    max_samples: Optional[int] = None,
    file_glob: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    从本地目录加载 CS-PaperSum 数据。
    支持：.json / .jsonl / .csv（含 All_capped_keywords.csv 等）。
    """
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return []

    if file_glob is None:
        file_glob = "*"
    records = []
    for path in data_dir.rglob(file_glob):
        if path.is_dir() or path.suffix.lower() not in (".json", ".jsonl", ".csv"):
            continue
        try:
            if path.suffix.lower() == ".csv":
                # 大 CSV 可用 max_samples 限制读取行数以节省内存
                nrows = (int(max_samples * 1.2) + 1000) if max_samples else None
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip", nrows=nrows)
                for _, row in df.iterrows():
                    paper = row.to_dict()
                    r = _paper_to_record(paper, summary_key)
                    if r:
                        records.append(r)
            else:
                items = _load_json_or_jsonl(path)
                for paper in items:
                    r = _paper_to_record(paper, summary_key)
                    if r:
                        records.append(r)
        except Exception as e:
            print(f"Skip {path}: {e}")
            continue
        if max_samples and len(records) >= max_samples:
            break
    if max_samples:
        records = records[:max_samples]
    return records


def split_train_val_test(
    records: List[Dict],
    train_ratio: float = 0.9,
    val_ratio: float = 0.05,
    test_ratio: float = 0.05,
    seed: int = 42,
) -> tuple:
    """按比例划分训练/验证/测试集。"""
    import random
    random.seed(seed)
    indices = list(range(len(records)))
    random.shuffle(indices)
    n = len(indices)
    t = int(n * train_ratio)
    v = int(n * val_ratio)
    train_idx = indices[:t]
    val_idx = indices[t : t + v]
    test_idx = indices[t + v : t + v + int(n * test_ratio)]
    return (
        [records[i] for i in train_idx],
        [records[i] for i in val_idx],
        [records[i] for i in test_idx],
    )
