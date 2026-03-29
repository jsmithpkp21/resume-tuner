#!/usr/bin/env bash
set -euo pipefail
cd /home/jonathan_smith/projects/resume-builder

# Source gh token from config if not already set
if [ -z "${GITHUB_TOKEN:-}" ]; then
  GH_TOKEN_FILE="$HOME/.config/gh/hosts.yml"
  if [ -f "$GH_TOKEN_FILE" ]; then
    GITHUB_TOKEN=$(grep -A2 'github.com' "$GH_TOKEN_FILE" | grep 'oauth_token' | awk '{print $2}' || true)
    export GITHUB_TOKEN
  fi
fi

gh issue create \
  --title "review: review DESIGN.md and finalise system design before implementation" \
  --label "documentation,architecture" \
  --body "## Goal
Review DESIGN.md and confirm or update the system design before any code is written.

## Areas to Review
- [ ] Confirm skills CSV column names and schema
- [ ] Confirm experience YAML schema (fields, impact values, domain values)
- [ ] Decide PDF backend: weasyprint (CSS-driven, Docker-friendly) vs reportlab (pure Python)
- [ ] Decide AI provider strategy: OpenAI only, or abstract adapter for local models (ollama / litellm)
- [ ] Decide routing_rules format: plain text fed to AI prompt, or structured TOML/YAML
- [ ] Confirm planned directory structure (section 12)
- [ ] Confirm planned dependencies (section 13)
- [ ] Confirm two-page layout constraints and line budget numbers
- [ ] Any changes committed to DESIGN.md before implementation begins

## Acceptance Criteria
- [ ] All open questions in DESIGN.md resolved
- [ ] DESIGN.md status updated from Draft to Approved
- [ ] Issue #2 (initialise project) not started until this is closed"

gh issue create \
  --title "chore: initialise project — run setup.sh, sync tooling, make setup" \
  --label "chore,high-priority" \
  --body "## Goal
Bootstrap the resume-builder project properly using the tooling workflow once the
project-template fixes (tooling epic #134) are complete and DESIGN.md is approved (issue #1).

## Prerequisites
- [ ] tooling epic #134 is closed (project-template bugs fixed)
- [ ] Issue #1 (design review) is closed

## Steps
- [ ] Run bash scripts/setup.sh from the project root
- [ ] Confirm git remote is set: git@github.com:jsmithpkp21/resume-builder.git
- [ ] Run make setup (creates venv, verifies env, installs pre-commit hooks)
- [ ] Run docker compose up --build and confirm container starts cleanly
- [ ] Run make drift-check and confirm no sync drift
- [ ] Run make sync-tooling to pull all managed files from tooling
- [ ] Commit resulting lock file and generated pyproject.toml
- [ ] Confirm make lint, make test, make check all pass

## Acceptance Criteria
- [ ] make setup passes with no errors
- [ ] docker compose up --build succeeds
- [ ] make drift-check passes
- [ ] make check passes
- [ ] .tooling-sync-manifest.lock committed"
