"""
自动评估：ROUGE-1/2/L，BERTScore。
"""
from typing import List, Dict, Optional

import numpy as np


def _ensure_list(s: str | List[str]) -> List[str]:
    if isinstance(s, str):
        return [s]
    return list(s)


def compute_rouge(
    predictions: List[str],
    references: List[str],
    use_stemmer: bool = True,
) -> Dict[str, float]:
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        return {"rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}

    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=use_stemmer)
    preds = _ensure_list(predictions)
    refs = _ensure_list(references)
    n = max(len(preds), len(refs), 1)
    if len(preds) < n:
        preds = preds + [""] * (n - len(preds))
    if len(refs) < n:
        refs = refs + [""] * (n - len(refs))

    agg = {"rouge1": [], "rouge2": [], "rougeL": []}
    for p, r in zip(preds, refs):
        s = scorer.score(r, p)
        for k in agg:
            agg[k].append(s[k].fmeasure)
    return {k: float(np.mean(v)) for k, v in agg.items()}


def compute_bertscore(
    predictions: List[str],
    references: List[str],
    model_type: str = "microsoft/deberta-xlarge-mnli",
    lang: str = "en",
) -> Dict[str, float]:
    try:
        from bert_score import score as bert_score_fn
    except ImportError:
        return {"bertscore_f1": 0.0, "bertscore_precision": 0.0, "bertscore_recall": 0.0}

    preds = _ensure_list(predictions)
    refs = _ensure_list(references)
    P, R, F1 = bert_score_fn(preds, refs, model_type=model_type, lang=lang, verbose=False)
    return {
        "bertscore_precision": float(P.mean()),
        "bertscore_recall": float(R.mean()),
        "bertscore_f1": float(F1.mean()),
    }


def evaluate_summaries(
    predictions: List[str],
    references: List[str],
    metrics: Optional[List[str]] = None,
    bertscore_model: str = "microsoft/deberta-xlarge-mnli",
) -> Dict[str, float]:
    if metrics is None:
        metrics = ["rouge1", "rouge2", "rougeL", "bertscore"]
    results = {}
    if any(m.startswith("rouge") for m in metrics):
        results.update(compute_rouge(predictions, references))
    if "bertscore" in metrics or "bertscore_f1" in str(metrics):
        results.update(compute_bertscore(predictions, references, model_type=bertscore_model))
    return results
