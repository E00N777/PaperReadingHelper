# 基于深度学习的科技论文贡献总结自动生成

输入：人工智能领域学术论文的 **PDF 全文**或**结构化文本**。  
输出：该论文**核心贡献的简洁、连贯的段落式摘要**（3--5 句话）。

本仓库包含数据加载（CS-PaperSum）、模型训练与推理、自动评估（ROUGE、BERTScore）、消融实验脚本以及自建 arXiv 测试集流程，并附带技术报告与可复现说明。

---

## 环境要求

- **Python** 3.10+
- **PyTorch** 2.0+
- **CUDA**（可选，用于 GPU 训练与推理）

推荐使用虚拟环境：

```bash
cd e:\AI_test
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 数据集：CS-PaperSum

**下载教程与放置位置**请直接看：**[docs/CS-PaperSum下载与放置说明.md](docs/CS-PaperSum下载与放置说明.md)**。

简要说明：

1. **下载**：在 [CS-PaperSum GitHub](https://github.com/zihaohe123/CS-PaperSum) 的 README 中有 **Google Drive** 链接，用浏览器打开后下载数据集并解压。
2. **放置位置**：将解压后的**所有数据文件**（或包含数据的子文件夹）放到本项目的 **`data/cs_papersum/`** 目录下，例如：
   - `e:\AI_test\data\cs_papersum\`（直接放若干 `.json` / `.jsonl` / `.csv`），或
   - `e:\AI_test\data\cs_papersum\release\`（解压得到一个子文件夹时，把该文件夹放在 `cs_papersum` 下即可）。
3. 程序会**递归扫描** `data/cs_papersum` 下的 `*.json`、`*.jsonl`、`*.csv`，无需再改代码。

若未放置数据，训练脚本会提示 “No data found”；评估与消融可使用自建 arXiv 测试集（见下）。

---

## 快速开始

### 1. 训练（使用默认「摘要+引言」输入）

**本地训练：**

```bash
python src/run_train.py --data_dir data/cs_papersum --output_dir outputs
```

**在 Google Colab 上训练、再把模型下载到本地运行：** 见 **[docs/Colab训练与本地运行.md](docs/Colab训练与本地运行.md)**。用 `colab/train_standalone.py` 在 Colab 跑训练，保存到 Drive 后下载 `mode_abstract_intro` 到本地，用 `--model_path` 指向该目录即可做评估与推理。

- 使用全文输入：`--input_mode full`
- 限制样本数（调试）：`--max_samples 500`
- 更多参数：`--config config.yaml`，或直接传 `--epochs`、`--batch_size`、`--lr` 等

模型会保存到 `outputs/mode_abstract_intro`（或 `mode_full`）。

### 2. 评估（自动指标 + 人工抽样）

在 CS-PaperSum 测试集上评估：

```bash
python src/run_evaluate.py --model_path outputs/mode_abstract_intro --data_dir data/cs_papersum --output evaluation_results.json
```

仅在使用自建 arXiv 测试集时：

```bash
python src/run_evaluate.py --model_path outputs/mode_abstract_intro --use_arxiv_only --arxiv_test_dir data/arxiv_test --output evaluation_results.json
```

会生成：

- `evaluation_results.json`：ROUGE-1/2/L、BERTScore 等；
- `evaluation_results.manual_sample.jsonl`：若干条「参考 vs 模型预测」，供人工评估。

### 3. 消融实验

比较「输入章节」与「长文档截断」对指标的影响：

```bash
python src/run_ablation.py --model_path outputs/mode_abstract_intro --data_dir data/cs_papersum --output ablation_results.json
```

结果写入 `ablation_results.json`，包含例如 `input_mode_abstract_intro`、`input_mode_full`、`long_doc_max_2048`、`long_doc_max_8192` 等配置的 ROUGE/BERTScore。

---

## 自建小型测试集（arXiv）

用于**时效性**与**最终模型对比**评估：

1. 下载近期论文元数据与目录结构：

```bash
python scripts/download_arxiv_test.py --output_dir data/arxiv_test --num_papers 20 --category cs.AI
```

2. 在 `data/arxiv_test/paper_XX_<id>/` 下：
   - `paper.txt`：可替换为 PDF 转写的全文或保留脚本生成的 Title+Abstract；
   - `reference.txt`：**人工撰写**该论文的 3--5 句贡献摘要并保存。

3. 使用该测试集评估：

```bash
python src/run_evaluate.py --use_arxiv_only --arxiv_test_dir data/arxiv_test --output evaluation_arxiv.json
```

---

## 项目结构

```
e:\AI_test\
├── config.yaml              # 数据路径、模型、评估与消融配置
├── requirements.txt
├── README.md
├── report/
│   └── report.tex           # 技术报告（4--8 页，NeurIPS/ICLR 风格章节）
├── scripts/
│   └── download_arxiv_test.py   # 自建 arXiv 测试集
├── data/
│   ├── cs_papersum/         # 放置 CS-PaperSum 数据
│   └── arxiv_test/         # 自建测试集目录与各论文 reference.txt
└── src/
    ├── data/
    │   ├── cs_papersum.py   # CS-PaperSum 加载与划分
    │   ├── paper_parser.py  # PDF/文本章节解析（摘要、引言、结论）
    │   └── dataset.py       # PyTorch Dataset（支持 abstract_intro / full）
    ├── model/
    │   └── summarizer.py    # BART/LED 封装与生成
    ├── evaluation/
    │   └── metrics.py       # ROUGE、BERTScore
    ├── run_train.py         # 训练入口
    ├── run_evaluate.py      # 评估入口
    └── run_ablation.py      # 消融实验入口
```

---

## 技术报告

- **位置**：`report/report.tex`
- **内容**：引言、相关工作、方法、实验（含消融）、分析与结论；可按 NeurIPS/ICLR 模板替换为官方 class 与 style 后编译为 4--8 页 PDF。
- 编译示例（需 LaTeX 环境）：

```bash
cd report
pdflatex report.tex
```

---

## 配置说明（config.yaml）

- **data.cs_papersum_dir**：CS-PaperSum 解压路径。
- **data.arxiv_test_dir**：自建 arXiv 测试集路径。
- **model.name**：主模型（如 BART）；**model.use_long_doc**：是否使用 LED。
- **model.batch_size / learning_rate / num_epochs**：训练超参。
- **evaluation.metrics**：评估指标列表。
- **ablation**：消融用的长文档策略与输入章节列表（与 run_ablation 逻辑对应）。

---

## 复现清单

1. **环境**：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -i https://pypi.tuna.tsinghua.edu.cn/simple`（建议 Python 3.10+、PyTorch 2.0+；`-i` 为国内源，可改用阿里云 `https://mirrors.aliyun.com/pypi/simple/` 等）。
2. **数据**：将 CS-PaperSum 放入 `data/cs_papersum/`。
3. **训练**：`python src/run_train.py --data_dir data/cs_papersum --output_dir outputs`。
4. **评估**：`python src/run_evaluate.py --model_path outputs/mode_abstract_intro`。
5. **消融**：`python src/run_ablation.py --model_path outputs/mode_abstract_intro`。
6. **自建测试集**：运行 `scripts/download_arxiv_test.py`，填写各目录下 `reference.txt` 后使用 `--use_arxiv_only` 评估。

若你本地未下载 CS-PaperSum，仍可运行 arXiv 测试集评估与消融（消融会使用已加载的少量样本或需先准备少量 JSON 数据）。

---

## 参考文献与数据来源

- **CS-PaperSum**：https://github.com/zihaohe123/CS-PaperSum  
- **论文**：CS-PaperSum: A Large-Scale Dataset of AI-Generated Summaries for Scientific Papers (2025).
