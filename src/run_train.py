"""
训练脚本：在 CS-PaperSum 上训练贡献摘要模型。
支持不同 input_mode 与 long_doc_strategy（用于消融）。
"""
import argparse
import os
import sys
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader
from transformers import get_linear_schedule_with_warmup
from tqdm import tqdm

# 将项目根加入 path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.cs_papersum import load_cs_papersum, split_train_val_test
from src.data.dataset import PaperContributionDataset, PreTokenizedDataset
from src.model.summarizer import build_model_and_tokenizer


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--data_dir", default="data/cs_papersum")
    p.add_argument("--output_dir", default="outputs")
    p.add_argument("--input_mode", choices=["abstract_intro", "full"], default="abstract_intro")
    p.add_argument("--max_samples", type=int, default=None)
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--batch_size", type=int, default=None)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--no_pre_tokenize", action="store_true", help="不预 tokenize，训练时实时编码（CPU 负载高）")
    return p.parse_args()


def main():
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    data_cfg = cfg.get("data", {})
    model_cfg = cfg.get("model", {})
    data_dir = args.data_dir or data_cfg.get("cs_papersum_dir", "data/cs_papersum")
    max_input = data_cfg.get("max_input_length", 512)
    max_output = data_cfg.get("max_output_length", 150)
    train_r = data_cfg.get("train_ratio", 0.9)
    val_r = data_cfg.get("val_ratio", 0.05)
    test_r = data_cfg.get("test_ratio", 0.05)

    max_samples = args.max_samples if args.max_samples is not None else data_cfg.get("max_samples", 3000)
    records = load_cs_papersum(data_dir=data_dir, max_samples=max_samples)
    if not records:
        print("No data found. Please download CS-PaperSum and put under", data_dir)
        return
    train_rec, val_rec, test_rec = split_train_val_test(records, train_r, val_r, test_r, seed=cfg.get("project", {}).get("seed", 42))

    model_name = model_cfg.get("name", "facebook/bart-large-cnn")
    use_long = model_cfg.get("use_long_doc", False)
    model, tokenizer, device = build_model_and_tokenizer(model_name, use_long_doc=use_long)
    raw_train_ds = PaperContributionDataset(
        train_rec,
        tokenizer,
        max_input_length=max_input,
        max_output_length=max_output,
        input_mode=args.input_mode,
    )
    raw_val_ds = PaperContributionDataset(
        val_rec, tokenizer, max_input_length=max_input, max_output_length=max_output, input_mode=args.input_mode
    )

    if not args.no_pre_tokenize:
        print("Pre-tokenizing dataset to reduce CPU load during training...")
        train_ds = PreTokenizedDataset([
            raw_train_ds[i] for i in tqdm(range(len(raw_train_ds)), desc="Train tokenize", leave=False)
        ])
        val_ds = PreTokenizedDataset([
            raw_val_ds[i] for i in tqdm(range(len(raw_val_ds)), desc="Val tokenize", leave=False)
        ])
        print("Pre-tokenize done. Training will use cached tensors (low CPU).")
    else:
        train_ds = raw_train_ds
        val_ds = raw_val_ds

    batch_size = args.batch_size or model_cfg.get("batch_size", 1)
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=0,
        pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, num_workers=0,
        pin_memory=False,
    )

    num_epochs = args.epochs or model_cfg.get("num_epochs", 3)
    lr = args.lr or model_cfg.get("learning_rate", 5e-5)
    warmup_ratio = model_cfg.get("warmup_ratio", 0.1)
    grad_accum = model_cfg.get("gradient_accumulation_steps", 2)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    total_steps = len(train_loader) * num_epochs // grad_accum
    sched = get_linear_schedule_with_warmup(opt, num_warmup_steps=int(total_steps * warmup_ratio), num_training_steps=total_steps)

    out_dir = Path(args.output_dir) / f"mode_{args.input_mode}"
    out_dir.mkdir(parents=True, exist_ok=True)

    model.train()
    total_steps_per_epoch = len(train_loader)
    for epoch in range(num_epochs):
        total_loss = 0.0
        running_loss = 0.0
        pbar = tqdm(
            train_loader,
            desc=f"Epoch {epoch+1}/{num_epochs}",
            unit="batch",
            leave=True,
            ncols=100,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] loss={postfix}",
        )
        for step, batch in enumerate(pbar):
            batch = {k: v.to(device, non_blocking=False) for k, v in batch.items()}
            loss = model(**batch).loss
            (loss / grad_accum).backward()
            loss_val = loss.item()
            total_loss += loss_val
            running_loss = 0.95 * running_loss + 0.05 * loss_val if step > 0 else loss_val
            pbar.set_postfix_str(f"{running_loss:.4f}")
            if (step + 1) % grad_accum == 0:
                opt.step()
                sched.step()
                opt.zero_grad()
            if step % 200 == 0 and step > 0 and torch.cuda.is_available():
                torch.cuda.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        avg_loss = total_loss / total_steps_per_epoch
        print(f"Epoch {epoch+1}/{num_epochs} done, avg loss: {avg_loss:.4f}")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print("Saved to", out_dir)


if __name__ == "__main__":
    main()
