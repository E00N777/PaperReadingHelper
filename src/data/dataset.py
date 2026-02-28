"""
PyTorch Dataset：支持不同输入模式（abstract_intro / full）与长文档截断策略。
预 tokenize 后可用 PreTokenizedDataset 降低训练时 CPU 负载。
"""
from typing import List, Dict, Optional, Any

import torch
from torch.utils.data import Dataset

from .paper_parser import get_full_or_abstract_intro


class PreTokenizedDataset(Dataset):
    """仅做索引，不调用 tokenizer，用于预 tokenize 后的数据以减轻 CPU 负载。"""
    def __init__(self, cached_items: List[Dict[str, torch.Tensor]]):
        self.cached_items = cached_items

    def __len__(self) -> int:
        return len(self.cached_items)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        return self.cached_items[idx]


class PaperContributionDataset(Dataset):
    def __init__(
        self,
        records: List[Dict[str, str]],
        tokenizer,
        max_input_length: int = 512,
        max_output_length: int = 150,
        input_mode: str = "abstract_intro",
        long_doc_strategy: str = "truncate",
    ):
        self.records = records
        self.tokenizer = tokenizer
        self.max_input_length = max_input_length
        self.max_output_length = max_output_length
        self.input_mode = input_mode
        self.long_doc_strategy = long_doc_strategy

    def __len__(self) -> int:
        return len(self.records)

    def _get_source_text(self, rec: Dict) -> str:
        source = rec.get("source_text", "")
        return get_full_or_abstract_intro(
            source,
            mode=self.input_mode,
            max_chars=self.max_input_length * 4,
        )

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        rec = self.records[idx]
        source = self._get_source_text(rec)
        target = rec.get("contribution_summary", "")

        if self.long_doc_strategy == "truncate":
            enc = self.tokenizer(
                source,
                max_length=self.max_input_length,
                truncation=True,
                padding="max_length",
                return_tensors="pt",
            )
        else:
            enc = self.tokenizer(
                source,
                max_length=self.max_input_length,
                truncation=True,
                padding="max_length",
                return_tensors="pt",
            )

        dec = self.tokenizer(
            target,
            max_length=self.max_output_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )
        labels = dec["input_ids"].squeeze(0).clone()
        labels[labels == self.tokenizer.pad_token_id] = -100

        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": labels,
        }
