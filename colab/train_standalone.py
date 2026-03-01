import argparse
import json
import random
import re
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, get_linear_schedule_with_warmup
from tqdm.auto import tqdm

# --- 1. 自动挂载 Google Drive ---
try:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
except ImportError:
    pass

# --- 2. 显存与时间管理工具 ---
def autotune_batch_size(max_input_length):
    """根据 T4 显存自动适配，保命第一"""
    if not torch.cuda.is_available():
        return 1, 8
    free_gpu_mem = torch.cuda.mem_get_info()[0] / (1024**3)
    print(f"检测到可用显存: {free_gpu_mem:.2f} GB")
    
    # 针对 T4 (12GB) 的黄金配置
    if free_gpu_mem > 10:
        batch_size, grad_accum = 2, 4  # 等效 batch 8
    else:
        batch_size, grad_accum = 1, 8  # 等效 batch 8
    print(f">>> 自动配置: Batch={batch_size}, 梯度累积={grad_accum}")
    return batch_size, grad_accum

# --- 3. 数据解析逻辑 ---
def _extract_sections(text):
    sec = {"abstract": "", "intro": "", "full": str(text)}
    if not text or len(str(text)) < 20: return sec
    # 简易正则匹配摘要和引言
    abs_m = re.search(r"(?i)abstract[:\n](.*?)(?=\n\n|\n(?:\d|intro))", str(text), re.S)
    int_m = re.search(r"(?i)introduction[:\n](.*?)(?=\n\n|\n(?:\d|related|method))", str(text), re.S)
    if abs_m: sec["abstract"] = abs_m.group(1).strip()
    if int_m: sec["intro"] = int_m.group(1).strip()
    return sec

def load_data(data_dir, max_samples=20000):
    """从 Drive 加载数据，支持全量或部分"""
    data_dir = Path(data_dir)
    records = []
    files = list(data_dir.rglob("*.csv")) + list(data_dir.rglob("*.json*"))
    print(f"正在扫描文件，目标样本数: {'全部' if max_samples==0 else max_samples}")
    
    for path in files:
        try:
            if path.suffix == ".csv":
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
                for _, row in df.iterrows():
                    d = row.to_dict()
                    records.append({
                        "src": f"Title: {d.get('title','')}\n{d.get('abstract','')}",
                        "tgt": str(d.get('summary', d.get('key_takeaways', '')))
                    })
            else:
                with open(path, 'r') as f:
                    for line in f:
                        d = json.loads(line)
                        records.append({
                            "src": f"Title: {d.get('title','')}\n{d.get('abstract','')}",
                            "tgt": str(d.get('summary', ''))
                        })
            if max_samples > 0 and len(records) >= max_samples: break
        except: continue
    
    random.shuffle(records)
    return records[:max_samples] if max_samples > 0 else records

# --- 4. Dataset 类 ---
class PaperDataset(Dataset):
    def __init__(self, data, tokenizer, max_in=512, max_out=128):
        self.data = data
        self.tok = tokenizer
        self.max_in = max_in
        self.max_out = max_out

    def __len__(self): return len(self.data)

    def __getitem__(self, i):
        item = self.data[i]
        enc = self.tok(item["src"], max_length=self.max_in, truncation=True, padding="max_length", return_tensors="pt")
        dec = self.tok(item["tgt"], max_length=self.max_out, truncation=True, padding="max_length", return_tensors="pt")
        labels = dec["input_ids"].squeeze(0).clone()
        labels[labels == self.tok.pad_token_id] = -100
        return {"input_ids": enc["input_ids"].squeeze(0), "attention_mask": enc["attention_mask"].squeeze(0), "labels": labels}

# --- 5. 主训练循环 ---
def start_training(cfg):
    # 加载数据
    raw_data = load_data(cfg.data_dir, cfg.max_samples)
    split = int(len(raw_data) * 0.95)
    train_set = raw_data[:split]
    val_set = raw_data[split:]
    print(f"数据就绪: 训练集 {len(train_set)}, 验证集 {len(val_set)}")

    # 加载模型
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained("facebook/bart-large-cnn")
    model = AutoModelForSeq2SeqLM.from_pretrained("facebook/bart-large-cnn").to(device)

    # 自动适配 Batch Size
    bs, ga = autotune_batch_size(cfg.max_input_length)
    
    # 实时 Tokenize（大数据量下保 RAM 命）
    train_ds = PaperDataset(train_set, tokenizer, cfg.max_input_length, cfg.max_output_length)
    loader = DataLoader(train_ds, batch_size=bs, shuffle=True)

    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr)
    total_steps = (len(loader) * cfg.epochs) // ga
    sched = get_linear_schedule_with_warmup(opt, int(total_steps * 0.1), total_steps)

    out_path = Path(cfg.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f">>> 开始训练，每 500 步将自动保存一次进度到 Drive")
    model.train()
    for epoch in range(cfg.epochs):
        pbar = tqdm(loader, desc=f"Epoch {epoch+1}")
        for step, batch in enumerate(pbar):
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss / ga
            loss.backward()

            if (step + 1) % ga == 0:
                opt.step()
                sched.step()
                opt.zero_grad()
            
            pbar.set_postfix({"loss": f"{loss.item()*ga:.4f}"})

            # --- 自动存档逻辑 ---
            if (step + 1) % 500 == 0:
                ckpt_path = out_path / "checkpoint_latest"
                model.save_pretrained(ckpt_path)
                tokenizer.save_pretrained(ckpt_path)
                # 打印一行，避免被 tqdm 覆盖
                tqdm.write(f"步数 {step+1}: 进度已存档至 {ckpt_path}")

    # 最终保存
    model.save_pretrained(out_path)
    tokenizer.save_pretrained(out_path)
    print(f"--- 训练圆满完成！最终模型已存至: {out_path} ---")

# --- 6. 一键配置区 ---
if __name__ == "__main__":
    config = SimpleNamespace(
        # 【必须修改】你的数据在 Drive 里的哪个文件夹？
        data_dir="/content/drive/MyDrive/cs_data", 
        
        # 模型存到哪里？
        output_dir="/content/drive/MyDrive/bart_final_model",
        
        # 【保命设置】Colab 4小时限制建议设为 20000
        # 如果你想全量跑，设为 0，但记得盯着存档点
        max_samples=20000, 
        
        epochs=1,            # 先跑 1 轮看看效果
        max_input_length=512,
        max_output_length=128,
        lr=3e-5
    )
    
    start_training(config)