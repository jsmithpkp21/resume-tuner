#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_local_llms.sh
#
# One-shot setup for the three local LLMs used in the resume-builder
# profile-building / generation comparison flow:
#   - llama3.1:8b   (~5 GB, project default baseline)
#   - gemma2:9b     (~6 GB, different lineage / prose)
#   - qwen2.5:14b   (~9 GB, reasoning ceiling at this VRAM budget)
#
# Targets WSL2 + NVIDIA GPU (developed against RTX 3060 12 GB). Idempotent:
# safe to re-run after a WSL wipe or on a new machine to restore state.
#
# TODO(#224): pin Ollama to a specific version with sha256 verification,
# matching scripts/install_act.sh. Currently uses Ollama's official TOFU
# installer while we're still evaluating which model(s) to keep.

# --- Configuration -------------------------------------------------------
MODELS=(
  "llama3.1:8b"
  "gemma2:9b"
  "qwen2.5:14b"
)
MIN_FREE_GB=25  # ~20 GB weights + headroom for partial pulls

# --- Helpers -------------------------------------------------------------
note() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m==>\033[0m %s\n' "$*" >&2; }

confirm() {
  local prompt="$1"
  local ans
  read -r -p "$prompt [y/N] " ans
  case "$ans" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

# --- Phase 1: Preflight --------------------------------------------------
note "Phase 1/4: Preflight checks"

if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  note "Detected WSL2."
else
  warn "Not running under WSL2. Script targets WSL2 but should still work."
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  err "nvidia-smi not found. WSL2 needs the NVIDIA Windows driver + WSL GPU support."
  err "  1. Install the latest NVIDIA driver on the Windows host."
  err "  2. Restart WSL: from PowerShell run 'wsl --shutdown', then reopen."
  err "  3. Verify inside WSL: nvidia-smi"
  exit 1
fi

note "GPU info:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

OLLAMA_DIR="${HOME}/.ollama"
mkdir -p "$OLLAMA_DIR"
free_gb="$(df -BG --output=avail "$OLLAMA_DIR" | tail -1 | tr -dc '0-9')"
if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
  err "Need at least ${MIN_FREE_GB} GB free in ${OLLAMA_DIR} (have ${free_gb} GB)."
  exit 1
fi
note "Disk: ${free_gb} GB free at ${OLLAMA_DIR} (need ${MIN_FREE_GB})."

if ! confirm "Proceed with Ollama install + pull ~20 GB of model weights?"; then
  note "Aborted by user. Nothing changed."
  exit 0
fi

# --- Phase 2: Install Ollama --------------------------------------------
note "Phase 2/4: Ollama"

if command -v ollama >/dev/null 2>&1; then
  note "Ollama already installed: $(ollama --version 2>/dev/null | head -1 || echo 'unknown')"
else
  note "Installing Ollama via official installer (TOFU; see TODO at top of script)."
  curl -fsSL https://ollama.com/install.sh | sh
fi

# Make sure the daemon is up. The installer registers a systemd unit on
# typical Linux, but WSL often lacks systemd; in that case start manually.
if ! pgrep -x ollama >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1 \
     && systemctl is-system-running --quiet 2>/dev/null; then
    sudo systemctl start ollama || true
  fi
  if ! pgrep -x ollama >/dev/null 2>&1; then
    note "Starting 'ollama serve' in background (no systemd detected)."
    nohup ollama serve >"${OLLAMA_DIR}/serve.log" 2>&1 &
    disown || true
  fi
fi

# Wait for the API to answer
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  err "Ollama daemon did not respond on :11434. Check ${OLLAMA_DIR}/serve.log."
  exit 1
fi
note "Ollama daemon is up."

# --- Phase 3: Pull models -----------------------------------------------
note "Phase 3/4: Pulling models (already-present models are skipped)"

installed="$(ollama list 2>/dev/null | awk 'NR>1 {print $1}')"
for m in "${MODELS[@]}"; do
  if grep -qx "$m" <<<"$installed"; then
    note "  $m: already present, skipping."
  else
    note "  $m: pulling..."
    ollama pull "$m"
  fi
done

# --- Phase 4: GPU smoke test --------------------------------------------
note "Phase 4/4: GPU smoke test"

failed=0
for m in "${MODELS[@]}"; do
  note "  Smoke test: $m"
  ollama run "$m" "Reply with exactly: OK" >/dev/null
  ps_out="$(ollama ps 2>/dev/null)"
  line="$(grep -E "^${m}([[:space:]]|$)" <<<"$ps_out" || true)"
  if [ -n "$line" ] && grep -q '100% GPU' <<<"$line"; then
    note "    OK  $m loaded 100% on GPU."
  else
    err  "    FAIL  $m did not run fully on GPU:"
    err  "      ${line:-(model not in 'ollama ps' output)}"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  err "One or more models did not run fully on GPU. Investigate before profiling."
  exit 1
fi

# --- Done ---------------------------------------------------------------
cat <<EOF

==> All set.

Run the resume builder against each model:

  RESUME_BUILDER_LLM_ENABLED=1 \\
  RESUME_BUILDER_LLM_MODEL=llama3.1:8b \\
    python scripts/build_resume.py [args...]

  RESUME_BUILDER_LLM_ENABLED=1 \\
  RESUME_BUILDER_LLM_MODEL=gemma2:9b \\
    python scripts/build_resume.py [args...]

  RESUME_BUILDER_LLM_ENABLED=1 \\
  RESUME_BUILDER_LLM_MODEL=qwen2.5:14b \\
    python scripts/build_resume.py [args...]

Weights live in: ${OLLAMA_DIR}/models  (~20 GB)
EOF
