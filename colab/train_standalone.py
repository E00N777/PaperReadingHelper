"""
Google Colab 用单文件训练脚本（不依赖项目结构）。
用法：在 Colab 中挂载 Drive，将数据放在 DATA_DIR，运行后模型保存到 OUTPUT_DIR。
本地可把 OUTPUT_DIR 下载后，用 --model_path 指向该目录做评估/推理。
"""
import argparse
import random
from pathlib import Path

import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, get_linear_schedule_with_warmup
from tqdm import tqdm


# ---------- 数据加载（与 src/data/cs_papersum 一致）----------
def _normalize_contribution(summary):
    if isinstance(summary, str):
        return summary.strip()
    if isinstance(summary, dict):
        parts = []
        for key in ("Key Takeaways", "key_takeaways", "contributions", "summary"):
            if key in summary and summary[key]:
                v = summary[key]
                parts.extend(v if isinstance(v, list) else [str(v)])
        text = " ".join(p[:200] for p in parts[:6] if isinstance(p, str) and len(p) > 10)
        return text[:800] if text else str(summary)
    return str(summary)


def _paper_to_record(paper, summary_key="summary"):
    title = paper.get("title", paper.get("Title", ""))
    abstract = paper.get("abstract", paper.get("Abstract", ""))
    conclusion = paper.get("conclusion", paper.get("Conclusion", ""))
    if not title and not abstract:
        return None
    source_parts = [f"Title: {title}", f"Abstract: {abstract}"]
    if conclusion:
        source_parts.append(f"Conclusion: {conclusion}")
    source_text = "\n\n".join(source_parts)
    summary = paper.get(summary_key) or paper.get("Key Takeaways") or paper.get("key_takeaways")
    if summary is None:
        for k in ("contributions", "contribution_summary", "takeaways"):
            if k in paper and paper[k]:
                summary = paper[k]
                break
    contribution_summary = _normalize_contribution(summary) if summary else abstract[:500] if abstract else ""
    if not contribution_summary and not abstract:
        return None
    return {
        "source_text": source_text,
        "contribution_summary": contribution_summary,
        "title": title,
    }


def load_cs_papersum(data_dir, max_samples=None):
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return []
    records = []
    for path in data_dir.rglob("*"):
        if path.is_dir() or path.suffix.lower() != ".csv":
            continue
        try:
            nrows = int(max_samples * 1.2 + 1000) if max_samples else None
            df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip", nrows=nrows)
            for _, row in df.iterrows():
                r = _paper_to_record(row.to_dict())
                if r:
                    records.append(r)
                if max_samples and len(records) >= max_samples:
                    break
        except Exception as e:
            print(f"Skip {path}: {e}")
        if max_samples and len(records) >= max_samples:
            break
    return records[:max_samples] if max_samples else records


def split_train_val_test(records, train_r=0.9, val_r=0.05, test_r=0.05, seed=42):
    random.seed(seed)
    idx = list(range(len(records)))
    random.shuffle(idx)
    n = len(idx)
    t, v = int(n * train_r), int(n * val_r)
    train = [records[i] for i in idx[:t]]
    val = [records[i] for i in idx[t : t + v]]
    test = [records[i] for i in idx[t + v : t + v + int(n * test_r)]]
    return train, val, test


# ---------- Dataset ----------
def get_source(text, mode="abstract_intro", max_chars=2048):
    if mode == "full":
        return text[:max_chars]
    return text[:max_chars]


class SimpleDataset(Dataset):
    def __init__(self, records, tokenizer, max_in=512, max_out=128, mode="abstract_intro"):
        self.records = records
        self.tok = tokenizer
        self.max_in = max_in
        self.max_out = max_out
        self.mode = mode

    def __len__(self):
        return len(self.records)

    def __getitem__(self, i):
        r = self.records[i]
        src = get_source(r["source_text"], self.mode, self.max_in * 4)
        tgt = r["contribution_summary"]
        enc = self.tok(src, max_length=self.max_in, truncation=True, padding="max_length", return_tensors="pt")
        dec = self.tok(tgt, max_length=self.max_out, truncation=True, padding="max_length", return_tensors="pt")
        labels = dec["input_ids"].squeeze(0).clone()
        pad_id = self.tok.pad_token_id
        if pad_id is not None:
            labels[labels == pad_id] = -100
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": labels,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_dir", default="/content/drive/MyDrive/colab_data/cs_papersum")
    p.add_argument("--output_dir", default="/content/drive/MyDrive/colab_outputs")
    p.add_argument("--max_samples", type=int, default=10000)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch_size", type=int, default=4)
    p.add_argument("--max_input_length", type=int, default=512)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--no_pre_tokenize", action="store_true")
    args = p.parse_args()

    print("Loading data...")
    records = load_cs_papersum(args.data_dir, max_samples=args.max_samples)
    if not records:
        print("No data. Put CS-PaperSum CSV under", args.data_dir)
        return
    train_rec, val_rec, _ = split_train_val_test(records, 0.9, 0.05, 0.05, 42)
    print(f"Train: {len(train_rec)}, Val: {len(val_rec)}")

    print("Loading model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained("facebook/bart-large-cnn")
    model = AutoModelForSeq2SeqLM.from_pretrained("facebook/bart-large-cnn").to(device)

    train_ds = SimpleDataset(train_rec, tokenizer, args.max_input_length, 128, "abstract_intro")
    val_ds = SimpleDataset(val_rec, tokenizer, args.max_input_length, 128, "abstract_intro")

    if not args.no_pre_tokenize:
        print("Pre-tokenizing...")
        train_ds = [train_ds[i] for i in tqdm(range(len(train_ds)), desc="Train")]
        val_ds = [val_ds[i] for i in tqdm(range(len(val_ds)), desc="Val")]
        class CachedDataset(Dataset):
            def __init__(self, data): self.data = data
            def __len__(self): return len(self.data)
            def __getitem__(self, i): return self.data[i]
        train_ds = CachedDataset(train_ds)
        val_ds = CachedDataset(val_ds)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    total_steps = len(train_loader) * args.epochs
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * total_steps), total_steps)

    out_dir = Path(args.output_dir) / "mode_abstract_intro"
    out_dir.mkdir(parents=True, exist_ok=True)

    model.train()
    for epoch in range(args.epochs):
        total_loss = 0.0
        for step, batch in enumerate(tqdm(train_loader, desc=f"Epoch {epoch+1}/{args.epochs}")):
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss
            loss.backward()
            total_loss += loss.item()
            opt.step()
            sched.step()
            opt.zero_grad()
        print(f"Epoch {epoch+1} avg loss: {total_loss/len(train_loader):.4f}")

    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print("Saved to", out_dir)
    print("Download this folder to your PC, then use: python src/run_evaluate.py --model_path <path-to-this-folder>")


if __name__ == "__main__":
    main()
