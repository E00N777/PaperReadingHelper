"""
消融实验：比较 (1) 长文档处理策略 (2) 输入章节（仅摘要+引言 vs 全文）对 ROUGE/BERTScore 的影响。
"""
import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.cs_papersum import load_cs_papersum, split_train_val_test
from src.model.summarizer import build_model_and_tokenizer, generate_contribution_summary
from src.evaluation.metrics import evaluate_summaries
from src.data.paper_parser import get_full_or_abstract_intro


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model_path", default="outputs/mode_abstract_intro")
    p.add_argument("--data_dir", default="data/cs_papersum")
    p.add_argument("--max_val", type=int, default=300)
    p.add_argument("--output", default="ablation_results.json")
    args = p.parse_args()

    records = load_cs_papersum(data_dir=args.data_dir, max_samples=2000)
    if not records:
        print("No data. Download CS-PaperSum to", args.data_dir)
        return
    _, val_rec, _ = split_train_val_test(records, 0.9, 0.05, 0.05, seed=42)
    val_rec = val_rec[: args.max_val]
    refs = [r.get("contribution_summary", "") for r in val_rec]

    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        model_path = Path(args.model_path)
        if model_path.exists():
            tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            model = AutoModelForSeq2SeqLM.from_pretrained(str(model_path))
        else:
            model, tokenizer, _ = build_model_and_tokenizer("facebook/bart-large-cnn")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
    except Exception as e:
        print("Model load failed:", e)
        return

    results = {}

    # 消融 1：输入章节
    for mode in ["abstract_intro", "full"]:
        sources = [get_full_or_abstract_intro(r.get("source_text", ""), mode=mode, max_chars=16000) for r in val_rec]
        preds = generate_contribution_summary(model, tokenizer, sources, device=device)
        results[f"input_mode_{mode}"] = evaluate_summaries(preds, refs)

    # 消融 2：长文档策略（此处仅比较同一模型下 truncate 与更短截断的效果，作为 proxy）
    for max_chars in [2048, 8192]:
        sources = [get_full_or_abstract_intro(r.get("source_text", ""), mode="full", max_chars=max_chars) for r in val_rec]
        preds = generate_contribution_summary(model, tokenizer, sources, device=device)
        results[f"long_doc_max_{max_chars}"] = evaluate_summaries(preds, refs)

    print("Ablation results:", json.dumps(results, indent=2))
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Saved to", args.output)


if __name__ == "__main__":
    main()
