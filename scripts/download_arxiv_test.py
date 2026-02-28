"""
自建小型测试集：从 arXiv 下载 10–20 篇最新 AI 论文，并生成人工摘要模板目录。
使用方式：
  1. 运行脚本下载元数据与 PDF 链接；
  2. 手动下载 PDF 或使用提供的摘要+标题作为 paper.txt；
  3. 在每篇论文目录下创建 reference.txt，写入人工撰写的 3–5 句贡献摘要。
"""
import argparse
import json
import os
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output_dir", default="data/arxiv_test")
    p.add_argument("--num_papers", type=int, default=15)
    p.add_argument("--category", default="cs.AI")
    args = p.parse_args()

    try:
        import arxiv
    except ImportError:
        print("Install: pip install arxiv -i https://pypi.tuna.tsinghua.edu.cn/simple")
        return

    client = arxiv.Client()
    search = arxiv.Search(query=f"cat:{args.category}", max_results=args.num_papers, sort_by=arxiv.SortCriterion.SubmittedDate)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    entries = []
    for i, result in enumerate(client.results(search)):
        short_id = (result.entry_id or "").split("/abs/")[-1].replace("/", "") or str(i)
        d = out / f"paper_{i:02d}_{short_id}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "title": result.title,
            "summary": result.summary,
            "pdf_url": result.pdf_url,
            "arxiv_id": result.entry_id,
            "published": str(result.published),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        # 用 arXiv 摘要作为 paper 内容占位，用户可替换为全文
        (d / "paper.txt").write_text(f"Title: {result.title}\n\nAbstract: {result.summary}", encoding="utf-8")
        (d / "reference.txt").write_text(
            "# 请在此文件写入该论文的核心贡献摘要（3-5 句话），保存后用于评估。\n",
            encoding="utf-8",
        )
        entries.append({"dir": str(d), "title": result.title, "arxiv_id": result.entry_id})

    (out / "index.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries), encoding="utf-8")
    print(f"Created {len(entries)} paper dirs under {out}. Fill reference.txt with human contribution summaries for evaluation.")


if __name__ == "__main__":
    main()
