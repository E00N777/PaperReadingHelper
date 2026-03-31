# DeepLint

DeepLint is an LLM-augmented static analysis prototype for C and C++ projects. It combines a tree-sitter based structural front-end with bug-specific extractors and two LLM reasoning stages:

1. intra-procedural data-flow extraction
2. path validation

At the moment, the repository focuses on two scan modes:

- `metascan`: export structural metadata about the codebase
- `dfbscan`: bug-oriented data-flow scanning for `MLK`, `NPD`, and `UAF`

## Quick Start

```bash
python3 src/repoaudit.py \
  --scan-type dfbscan \
  --project-path /path/to/your/project \
  --language Cpp \
  --bug-type UAF \
  --model-name <your-model-name> \
  --temperature 0.5 \
  --call-depth 3 \
  --max-neural-workers 8 \
  --max-symbolic-workers 30
```

Results are written under `result/`, and logs are written under `log/`.

## Repository Layout

```text
src/
  repoaudit.py                     CLI entry point
  agent/
    metascan.py                    structural metadata export
    dfbscan.py                     bug-oriented scan orchestration
    memory_agent.py                prompt memory and compact context builder
  tstool/
    analyzer/
      TS_analyzer.py               shared tree-sitter utilities
      Cpp_TS_analyzer.py           C/C++ parser and function extractor
    dfbscan_extractor/
      Cpp/
        Cpp_MLK_extractor.py       memory leak source/sink extraction
        Cpp_NPD_extractor.py       null dereference source/sink extraction
        Cpp_UAF_extractor.py       use-after-free source/sink extraction
  llmtool/
    dfbscan/
      intra_dataflow_analyzer.py   LLM-based per-function propagation analysis
      path_validator.py            LLM-based final bug-path validation
  memory/
    syntactic/                     functions, values, APIs
    semantic/                      scan state objects
    report/                        final bug report objects
```

## High-Level Architecture

### 1. CLI and Scan Dispatch

`src/repoaudit.py` is the main entry point.

It is responsible for:

- validating CLI arguments
- recursively loading source files into memory
- building a `Cpp_TSAnalyzer`
- dispatching to `MetaScanAgent` or `DFBScanAgent`

This means all later stages work on an in-memory snapshot of the target project.

### 2. Tree-Sitter Front-End

`src/tstool/analyzer/TS_analyzer.py` and `src/tstool/analyzer/Cpp_TS_analyzer.py` build the structural model of the codebase:

- functions
- parameters
- return values
- call sites
- caller/callee relationships
- control-flow metadata such as `if` and loop regions

This layer is the bridge between raw source text and the semantic scan pipeline.

### 3. Bug-Specific Extractors

`src/tstool/dfbscan_extractor/Cpp/` contains one extractor per bug type.

Each extractor defines:

- what counts as a source
- what counts as a sink
- how source and sink candidates are restricted before prompting the LLM

For `UAF`, the extractor is source-sensitive: it does not use only generic sinks, but tries to compute sinks relevant to the specific released object.

### 4. LLM-Oriented Data-Flow Scan

`src/agent/dfbscan.py` orchestrates the full bug scan:

- enumerate source values
- find the starting function for each source
- compute sink metadata for the function
- invoke the intra-procedural LLM tool
- connect inter-procedural edges through parameters, arguments, and returns
- collect candidate buggy paths
- invoke the path validator
- emit bug reports

### 5. Memory and Prompt Compaction

`src/agent/memory_agent.py` produces compact summaries that are injected into prompts.

Its main job is to reduce prompt size while keeping:

- function summary
- source focus
- known sinks
- call sites
- return values
- a small amount of remembered past observations

### 6. Persistent Scan State

`src/memory/semantic/dfbscan_state.py` stores intermediate and final results:

- reachable values per path
- inter-procedural value matches
- potential buggy paths
- deduplicated bug reports

This state is shared across the scan and merged from worker-local states.

## DFBScan Pipeline

The practical control flow in `dfbscan` is:

```text
source value
-> find source function
-> compute sink metadata for this source in this function
-> IntraDataFlowAnalyzer
-> parse structured propagation facts from the model answer
-> filter temporally invalid UAF candidates
-> collect potential buggy paths
-> PathValidator
-> BugReport
```

### IntraDataFlowAnalyzer

`src/llmtool/dfbscan/intra_dataflow_analyzer.py` asks the model where a source propagates within one function.

It recognizes only four propagation categories:

- `Argument`
- `Return`
- `Parameter`
- `Sink`

The parser is intentionally strict: it does not trust free-form prose. It extracts facts only from the `Answer:` section and only from lines that match the expected structured format.

### PathValidator

`src/llmtool/dfbscan/path_validator.py` is the second LLM stage.

Its job is narrower:

- take a candidate bug path
- reason about reachability and bug-specific validity
- return a final `Answer: Yes` or `Answer: No`

Only paths that survive this stage become final `BugReport` objects.

## Current UAF Semantics

The current `UAF` design is important to understand before changing the system.

### UAF Source

In `src/tstool/dfbscan_extractor/Cpp/Cpp_UAF_extractor.py`, the UAF source is the released object expression, not the full deallocation statement.

Examples:

- `free(ptr)` -> source is `ptr`
- `delete p` -> source is `p`
- `delete[] items` -> source is `items`

This design intentionally tracks the object whose lifetime ended.

### UAF Known Sinks

For `UAF`, "known sinks" mean post-release uses that the extractor recognizes as relevant to the released object or its aliases.

Right now the recognized sink shapes are syntax-driven and mostly include:

- pointer dereference such as `*p`
- field access such as `p->field` or `obj.field`
- subscript access such as `p[i]`

In other words, `known sinks` are a subset of "use" sites, not all possible uses.

## Recent UAF Fixes

The current branch already includes several important fixes that improved the UAF pipeline:

### 1. UTF-8 Safe Tree-Sitter Slicing

The analyzer previously used tree-sitter byte offsets directly on Python `str`, which broke source extraction when files contained non-ASCII characters.

This was fixed by introducing UTF-8 byte-based helpers in `src/tstool/analyzer/TS_analyzer.py`.

Impact:

- function names are no longer truncated by Unicode offset mismatches
- source focus and prompt context are much more stable

### 2. Alias Reconstruction at Release Time

`Cpp_UAF_extractor.py` now rebuilds aliases at the release point more carefully.

Previously, the source variable could be "killed" by its own defining assignment, which caused obvious sinks such as `*p` after `delete p` to disappear.

Impact:

- simple direct UAF cases now generate non-empty `Known sinks`
- `PathValidator` is invoked for more real UAF paths

### 3. C++ Function Name Extraction

`Cpp_TS_analyzer.py` now avoids binding local constructors inside a function body to the outer function definition.

Impact:

- prompt context is less likely to show incorrect function names such as local struct constructors

## Known Problems

The project is in active development. The following issues are still important:

### 1. UAF Sink Coverage Is Still Narrow

The current `UAF` sink model is syntax-driven and source-sensitive, which is a good start for precision, but coverage is still limited.

Cases that are still likely to be weak include:

- complex aliasing patterns
- lambda captures
- placement new patterns
- indirect writes and API-style uses that are not represented as the current sink node shapes
- ownership transfer patterns that require richer semantics than local syntax

This is the biggest remaining issue for scaling to large real-world C++ codebases.

### 2. Intra LLM Parsing Is Format-Sensitive

The intra-procedural parser only accepts structured `Answer:` output with strict `Type: ...; Name: ...; Function: ...; Index: ...; Line: ...;` records.

Implication:

- if the model correctly explains a bug in prose but fails to emit the expected structured lines, DeepLint records no propagation

This makes the system brittle to prompt drift and model output variation.

### 3. Shared Logs Are Hard to Read Under Concurrency

`dfbscan` can run many neural workers in parallel, but all workers write to the same log file.

Implication:

- prompt and response fragments from different workers can interleave
- log reading can look misleading even when the pipeline itself is working

This is mainly an observability problem, but it slows down debugging a lot.

### 4. Function Mapping Is Still Heuristic

`TS_analyzer.get_function_from_localvalue()` maps a value to the first function whose line range contains it.

Implication:

- in unusual nested or generated constructs, function attribution can still be fragile

The recent function declarator fix improved this, but the mapping model is still simple.

### 5. LLM Cost and Latency Are Structural Bottlenecks

The current architecture performs multiple LLM calls per source and can be slow on projects with many candidate sources.

Implication:

- higher recall usually increases latency and cost
- debugging with large worker counts is expensive and noisy

## Recommended Debugging Workflow

When a bug seems to be missing, debug the pipeline in this order:

1. Check whether the source was extracted.
2. Check whether `Known sinks` for that source are empty.
3. Check whether the intra analyzer produced a `ValueLabel.SINK`.
4. Check whether `PathValidator` was invoked.
5. Check whether `detect_info.json` contains the final report.

This sequence quickly tells you which layer is responsible:

- extractor problem
- prompt/parser problem
- path collection problem
- validator problem

## Suggested Reading Order for the Code

If you are new to the repository, this order usually works best:

1. `src/repoaudit.py`
2. `src/agent/dfbscan.py`
3. `src/tstool/dfbscan_extractor/Cpp/Cpp_UAF_extractor.py`
4. `src/llmtool/dfbscan/intra_dataflow_analyzer.py`
5. `src/llmtool/dfbscan/path_validator.py`
6. `src/tstool/analyzer/Cpp_TS_analyzer.py`
7. `src/tstool/analyzer/TS_analyzer.py`

If you are specifically debugging `UAF`, start with `dfbscan.py` and `Cpp_UAF_extractor.py` before reading the lower-level analyzer utilities.
