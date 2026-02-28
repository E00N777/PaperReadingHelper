"""
单篇论文贡献摘要生成入口。
用法：
  python run.py --input "Title: ... Abstract: ..." --output summary.txt
  python run.py --pdf path/to/paper.pdf --output summary.txt
"""
import argparse
from pathlib import Path

from src.model.summarizer import build_model_and_tokenizer, generate_contribution_summary
from src.data.paper_parser import parse_pdf_sections, extract_abstract_intro


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="", help="结构化文本（Title + Abstract + 可选 Conclusion）")
    p.add_argument("--pdf", default="", help="PDF 路径，将解析后作为输入")
    p.add_argument("--model_path", default="facebook/bart-large-cnn")
    p.add_argument("--output", default="")
    args = p.parse_args()

    if args.pdf:
        sections = parse_pdf_sections(args.pdf)
        source = sections.get("full") or (sections.get("abstract", "") + "\n\n" + sections.get("introduction", ""))
    else:
        source = args.input.strip()
    if not source:
        print("No input. Use --input or --pdf")
        return

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_path = args.model_path
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(device)
    preds = generate_contribution_summary(model, tokenizer, source[:16000], device=device)
    summary = preds[0] if preds else ""
    print(summary)
    if args.output:
        Path(args.output).write_text(summary, encoding="utf-8")
        print("Written to", args.output)


if __name__ == "__main__":
    main()
