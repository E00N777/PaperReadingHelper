#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# --- Defaults ---
LANGUAGE="Cpp"
if [[ -n "${REPOAUDIT_MODEL:-}" ]]; then
  MODEL="$REPOAUDIT_MODEL"
elif [[ -n "${DASHSCOPE_API_KEY:-}" ]]; then
  MODEL="qwen3.5-flash"
else
  MODEL="deepseek-chat"
fi
DEFAULT_PROJECT_NAME="toy"
DEFAULT_BUG_TYPE="NPD"     # allowed: MLK, NPD, UAF
SCAN_TYPE="dfbscan"

# Construct the default project *path* from LANGUAGE + DEFAULT_PROJECT_NAME
DEFAULT_PROJECT_PATH="../benchmark/${LANGUAGE}/${DEFAULT_PROJECT_NAME}"

show_usage() {
  cat <<'EOF'
Usage: run_repoaudit.sh [PROJECT_PATH] [BUG_TYPE]

Arguments:
  PROJECT_PATH   Optional absolute/relative path to the subject project.
                 Defaults to: ../benchmark/Cpp/toy
  BUG_TYPE       Optional bug type. One of: MLK, NPD, UAF. Defaults to: NPD

Environment:
  REPOAUDIT_MODEL  Optional model override. Highest priority when set.
  DASHSCOPE_API_KEY
                   If set and REPOAUDIT_MODEL is unset, defaults to: qwen3.5-flash
                   Otherwise defaults to: deepseek-chat

Bug type meanings:
  MLK  - Memory Leak
  NPD  - Null Pointer Dereference
  UAF  - Use After Free

Examples:
  ./run_repoaudit.sh
  ./run_repoaudit.sh /path/to/my/project
  ./run_repoaudit.sh ./repos/demo UAF
  bash run_repoaudit.sh /path/to/my/project NPD    # uses qwen3.5-flash if DASHSCOPE_API_KEY is set
  REPOAUDIT_MODEL=deepseek-reasoner ./run_repoaudit.sh
  REPOAUDIT_MODEL=qwen3.5-flash ./run_repoaudit.sh
  ./run_repoaudit.sh --help
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  show_usage
  exit 0
fi

# --- Args ---
PROJECT_PATH="${1:-$DEFAULT_PROJECT_PATH}"
BUG_TYPE_RAW="${2:-$DEFAULT_BUG_TYPE}"

# Normalize BUG_TYPE to uppercase (accepts mlk/npd/uaf too)
BUG_TYPE="$(echo "$BUG_TYPE_RAW" | tr '[:lower:]' '[:upper:]')"

# --- Validate BUG_TYPE ---
case "$BUG_TYPE" in
  MLK|NPD|UAF) : ;;
  *)
    echo "Error: BUG_TYPE must be one of: MLK, NPD, UAF (got '$BUG_TYPE_RAW')." >&2
    echo "       MLK = Memory Leak; NPD = Null Pointer Dereference; UAF = Use After Free." >&2
    exit 1
    ;;
esac

# --- Resolve and validate PROJECT_PATH ---
if ! PROJECT_PATH_ABS="$(cd "$(dirname -- "$PROJECT_PATH")" && pwd)/$(basename -- "$PROJECT_PATH")"; then
  echo "Error: Could not resolve PROJECT_PATH: $PROJECT_PATH" >&2
  exit 1
fi

if [[ ! -d "$PROJECT_PATH_ABS" ]]; then
  echo "Error: PROJECT_PATH does not exist or is not a directory: $PROJECT_PATH_ABS" >&2
  exit 1
fi

EXTRA_FLAGS=()
if [[ "$BUG_TYPE" != "MLK" ]]; then
  EXTRA_FLAGS+=(--is-reachable)
fi

# --- Run ---
python3 repoaudit.py \
  --language "$LANGUAGE" \
  --model-name "$MODEL" \
  --project-path "$PROJECT_PATH_ABS" \
  --bug-type "$BUG_TYPE" \
  "${EXTRA_FLAGS[@]}" \
  --temperature 0.0 \
  --scan-type "$SCAN_TYPE" \
  --call-depth 3 \
  --max-neural-workers 30
