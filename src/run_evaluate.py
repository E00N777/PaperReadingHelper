"""
评估脚本：在测试集或自建 arXiv 测试集上计算 ROUGE、BERTScore，并支持人工抽样输出。
"""
import argparse
import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.cs_papersum import load_cs_papersum, split_train_val_test
from src.data.dataset import PaperContributionDataset
from src.model.summarizer import build_model_and_tokenizer, generate_contribution_summary
from src.evaluation.metrics import evaluate_summaries


def load_arxiv_test(arxiv_test_dir: str = "data/arxiv_test"):
    """加载自建 arXiv 测试集：目录下 expected 为人工摘要，或 jsonl 含 reference。"""
    path = Path(arxiv_test_dir)
    if not path.exists():
        return []
    records = []
    for f in path.glob("*.jsonl"):
        for line in open(f, "r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    for sub in path.iterdir():
        if sub.is_dir():
            ref_file = sub / "reference.txt"
            if ref_file.exists():
                rec = {"source_text": (sub / "paper.txt").read_text(encoding="utf-8") if (sub / "paper.txt").exists() else "", "contribution_summary": ref_file.read_text(encoding="utf-8")}
                if rec["source_text"] or rec["contribution_summary"]:
                    records.append(rec)
    return records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model_path", default="outputs/mode_abstract_intro")
    p.add_argument("--data_dir", default="data/cs_papersum")
    p.add_argument("--arxiv_test_dir", default="data/arxiv_test")
    p.add_argument("--use_arxiv_only", action="store_true")
    p.add_argument("--max_test", type=int, default=200)
    p.add_argument("--output", default="evaluation_results.json")
    p.add_argument("--sample_for_manual", type=int, default=10)
    args = p.parse_args()

    model_path = args.model_path
    if not Path(model_path).exists():
        model_path = model_path  # 使用 HuggingFace 模型名
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    model = model.to(device)

    if args.use_arxiv_only:
        test_records = load_arxiv_test(args.arxiv_test_dir)
    else:
        records = load_cs_papersum(data_dir=args.data_dir, max_samples=5000)
        if not records:
            test_records = load_arxiv_test(args.arxiv_test_dir)
        else:
            _, _, test_records = split_train_val_test(records, 0.9, 0.05, 0.05, seed=42)
    test_records = test_records[: args.max_test]
    if not test_records:
        print("No test data.")
        return

    refs = [r.get("contribution_summary", "") for r in test_records]
    sources = [r.get("source_text", "")[:16000] for r in test_records]
    preds = generate_contribution_summary(model, tokenizer, sources, device=device)

    results = evaluate_summaries(preds, refs)
    print("Metrics:", results)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"metrics": results, "num_samples": len(test_records)}, f, indent=2)

    # 人工抽样：输出若干条供人工评估
    sample_n = min(args.sample_for_manual, len(test_records))
    manual_path = Path(args.output).with_suffix(".manual_sample.jsonl")
    with open(manual_path, "w", encoding="utf-8") as f:
        for i in range(sample_n):
            f.write(json.dumps({"reference": refs[i], "prediction": preds[i], "title": test_records[i].get("title", "")}, ensure_ascii=False) + "\n")
    print("Manual sample written to", manual_path)


if __name__ == "__main__":
    main()
