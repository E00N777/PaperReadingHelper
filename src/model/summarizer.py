"""
摘要模型封装：BART / LED，支持长文档截断与生成。
"""
from typing import Optional, List, Union

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline


def build_model_and_tokenizer(
    model_name: str = "facebook/bart-large-cnn",
    use_long_doc: bool = False,
    device: Optional[str] = None,
):
    long_doc_name = "allenai/led-base-16384"
    name = long_doc_name if use_long_doc else model_name
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSeq2SeqLM.from_pretrained(name)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    return model, tokenizer, device


def generate_contribution_summary(
    model,
    tokenizer,
    source_text: Union[str, List[str]],
    device: str = "cpu",
    max_length: int = 150,
    min_length: int = 30,
    num_beams: int = 4,
    do_sample: bool = False,
) -> List[str]:
    """批量或单条生成贡献摘要。"""
    if isinstance(source_text, str):
        source_text = [source_text]
    enc = tokenizer(
        source_text,
        max_length=4096,
        truncation=True,
        padding=True,
        return_tensors="pt",
    )
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_length=max_length,
            min_length=min_length,
            num_beams=num_beams,
            do_sample=do_sample,
            early_stopping=True,
        )
    return tokenizer.batch_decode(out, skip_special_tokens=True)
