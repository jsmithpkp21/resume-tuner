VERSION := $(shell awk 'NR==1 {sub(/[[:space:]]*#.*$$/, ""); gsub(/[[:space:]]/, ""); print; exit}' VERSION)
# Dynamically determine repo name - works in Docker and local
# Use git config if available, fallback to directory name
REPO_NAME_FROM_GIT := $(shell git config --get remote.origin.url 2>/dev/null | sed 's|.*/||; s|\.git$$||')
REPO_NAME := $(if $(REPO_NAME_FROM_GIT),$(REPO_NAME_FROM_GIT),$(notdir $(CURDIR)))
# Use stable venv name (without version) so it doesn't change with every release
ENV_PATH := $(HOME)/envs/$(REPO_NAME)-env
export ENV_PATH
DOCKER_COMPOSE ?= docker compose
DOCKER_SERVICE ?= base_env
DOCKER_EXEC := $(DOCKER_COMPOSE) exec -T $(DOCKER_SERVICE)
DOCKER_RUN := $(DOCKER_EXEC) bash -lc
MARKDOWN_LINT_TIMEOUT_SECONDS ?= 120
# Pinned markdownlint-cli version (single source of truth for local + Docker paths).
# See docs/REFERENCE/adr/0001-local-tooling-runtime-policy.md invariant (1).
MARKDOWNLINT_VERSION ?= 0.47.0

# Every recipe target below must appear in this list; enforced by tests/scripts/test_makefile_phony.py.
.PHONY: env setup active verify clean upgrade lock lint lint-fast lint-fix typecheck test test-fast test-slow test-profile test-selective test-shell precommit precommit-fix install-act bootstrap sync-tooling update-sync-script drift-check docs-check agents-drift-check tooling-toml-check check version-check version-fix env-file-check env-file-fix action-pin-check action-pin-fix dev-tool-pin-check dev-tool-pin-fix markdown-lint markdown-lint-run markdown-lint-docker commitlint-msg fix-pr-initial-commit consumer-contract-test pr-review-helper branch pr-epic docker-up docker-down docker-shell update-docker lint-docker lint-fix-docker typecheck-docker test-docker precommit-fix-docker check-docker

env:
	scripts/create_env.sh

bootstrap: clean env verify
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg"

setup: env verify
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg"
	@echo ""
	@echo "========================================="
	@echo "  Setup Complete!"
	@echo "========================================="
	@echo ""
	@echo "Environment created, verified, and pre-commit hooks installed."
	@echo "Push protection enabled for main branch."
	@echo ""
	@echo "To activate the environment, run:"
	@echo "  make active"
	@echo ""
	@echo "Or manually:"
	@echo "  source ~/envs/$(REPO_NAME)-env/bin/activate"
	@echo ""
	@echo "========================================="

active:
	@echo "========================================="
	@echo "  Activate Virtual Environment"
	@echo "========================================="
	@echo ""
	@echo "Copy and paste the command below:"
	@echo ""
	@echo "  source ~/envs/$(REPO_NAME)-env/bin/activate"
	@echo ""
	@echo "Once activated, your prompt should show:"
	@echo "  ($(REPO_NAME)-env) user@host:~$$"
	@echo ""
	@echo "To activate and enter a bash shell:"
	@echo "  source ~/envs/$(REPO_NAME)-env/bin/activate && exec bash"
	@echo ""
	@echo "========================================="

verify: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && scripts/verify_env.sh"

clean:
	rm -rf $(ENV_PATH)

upgrade:
	scripts/create_env.sh --force
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && scripts/verify_env.sh"

# `id -u` / `id -g` are evaluated by the shell (`$$()`) at recipe execution
# time, mirroring how the rest of this Makefile handles runtime UID/GID
# (e.g. the markdown-lint Docker fallback). Avoids `make`'s `$(shell ...)`
# being expanded twice and during `make -n` dry runs.
#
# Allows `HOST_UID` / `HOST_GID` env-var overrides so an invoker who is
# already root (CI image, sudo bash, …) can still bake a non-root user
# into the image. Without an override, refuses to run as UID 0 — silently
# baking root would defeat issue #322. `HOST_UID_ALLOW_ROOT=1` is the
# opt-in escape hatch, matching `scripts/docker_build.sh` and the
# Dockerfile guard from issue #353; the build-arg is forwarded to docker
# compose so the in-image guard sees the same value.
update-docker:
	@set -e; \
	HOST_UID="$${HOST_UID:-$$(id -u)}"; HOST_GID="$${HOST_GID:-$$(id -g)}"; \
	HOST_UID_ALLOW_ROOT="$${HOST_UID_ALLOW_ROOT:-0}"; \
	case "$$HOST_UID" in ''|*[!0-9]*) \
		echo "update-docker: HOST_UID must be a non-negative integer, got '$$HOST_UID'." >&2; exit 1;; \
	esac; \
	case "$$HOST_GID" in ''|*[!0-9]*) \
		echo "update-docker: HOST_GID must be a non-negative integer, got '$$HOST_GID'." >&2; exit 1;; \
	esac; \
	case "$$HOST_UID_ALLOW_ROOT" in 0|1) ;; *) \
		echo "update-docker: HOST_UID_ALLOW_ROOT must be '0' or '1', got '$$HOST_UID_ALLOW_ROOT'." >&2; exit 1;; \
	esac; \
	case "$$HOST_UID" in \
		*[!0]*) : ;; \
		*) if [ "$$HOST_UID_ALLOW_ROOT" != "1" ]; then \
			echo "update-docker: refusing to bake UID 0 (root) into the image -- this would defeat the non-root-user goal (issue #322)." >&2; \
			echo "Re-run as a non-root user, pass HOST_UID/HOST_GID explicitly:" >&2; \
			echo "  HOST_UID=1000 HOST_GID=1000 make update-docker" >&2; \
			echo "Or opt in to a root-baked image: HOST_UID_ALLOW_ROOT=1 make update-docker" >&2; \
			exit 1; \
		fi ;; \
	esac; \
	$(DOCKER_COMPOSE) build --build-arg HOST_UID="$$HOST_UID" --build-arg HOST_GID="$$HOST_GID" --build-arg HOST_UID_ALLOW_ROOT="$$HOST_UID_ALLOW_ROOT"; \
	$(DOCKER_COMPOSE) up -d; \
	echo "Docker container rebuilt and restarted. jq and other dependencies are now available."; \
	echo "Container runs as non-root user (UID=$$HOST_UID, GID=$$HOST_GID); files written to /repo are host-owned."

# Ensure the project container is running before executing Docker-backed targets.
docker-up:
	@set -e; \
	TMP_LOG="$$(mktemp)"; \
	if ! $(DOCKER_COMPOSE) up -d >"$$TMP_LOG" 2>&1; then \
		cat "$$TMP_LOG"; \
		echo ""; \
		echo "docker-up: failed to start compose services."; \
		echo "Try:"; \
		echo "  1) Ensure Docker daemon is running and reachable from this shell."; \
		echo "  2) Check for stale containers/projects: docker ps -a"; \
		echo "  3) Clean this compose project: $(DOCKER_COMPOSE) down --remove-orphans"; \
		echo "  4) Rerun: make docker-up"; \
		rm -f "$$TMP_LOG"; \
		exit 1; \
	fi; \
	cat "$$TMP_LOG"; \
	rm -f "$$TMP_LOG"; \
	$(DOCKER_EXEC) git config --global --add safe.directory /repo >/dev/null 2>&1 || true

# Stop and remove the project container(s) for this compose project,
# along with any orphans left over from previous compose-project names
# or removed services. No-op (zero exit) when nothing is running.
# `--remove-orphans` matches the cleanup guidance printed by
# `docker-up`'s failure-remediation block.
docker-down:
	$(DOCKER_COMPOSE) down --remove-orphans

# Open an interactive shell in the project container.
docker-shell: docker-up
	$(DOCKER_COMPOSE) exec $(DOCKER_SERVICE) bash

lock:
	@echo "Creating temporary environment for runtime-only lock..."
	@LOCK_TMP=$$(mktemp -d) && \
	python3 -m venv "$$LOCK_TMP/venv" && \
	"$$LOCK_TMP/venv/bin/pip" install --quiet --upgrade pip && \
	"$$LOCK_TMP/venv/bin/pip" install --quiet -r requirements.txt && \
	"$$LOCK_TMP/venv/bin/pip" freeze > requirements.txt && \
	rm -rf "$$LOCK_TMP" && \
	echo "requirements.txt updated (runtime-only packages)."

lint: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && ruff check . && ruff format --check . && mypy . && make markdown-lint"

# Sub-second pre-push gate. Runs only the in-process ruff linters
# (lint + format-check); skips mypy and markdown-lint, which are slower.
# Use this as a quick local sanity check before pushing — `make lint` and
# CI are still authoritative. Catches the common case where a developer
# pre-flighted with a black or isort substitute that disagrees with ruff
# format on edge cases (see tooling issue #399 for the motivating
# friction; the originating consumer-side incident was
# jsmithpkp21/resume-builder issue #326 / PR #348).
lint-fast: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && ruff check . && ruff format --check ."

# Public alias — always call this target from hooks, CI, and manually.
# Uses local markdownlint binary when available (e.g. inside the project container),
# falls back to Docker with a pinned npx invocation when not.
markdown-lint: markdown-lint-run

markdown-lint-run:
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "markdown-lint: git tracked-file context unavailable"; \
		exit 1; \
	fi; \
	USE_LOCAL=0; \
	if command -v markdownlint >/dev/null 2>&1; then \
		LOCAL_VER=$$(markdownlint --version 2>/dev/null | tr -d '[:space:]'); \
		if [ "$$LOCAL_VER" = "$(MARKDOWNLINT_VERSION)" ]; then \
			USE_LOCAL=1; \
		else \
			echo "markdown-lint: local markdownlint version '$$LOCAL_VER' does not match pinned $(MARKDOWNLINT_VERSION); falling back to pinned Docker runtime"; \
		fi; \
	fi; \
	if [ "$$USE_LOCAL" = "1" ]; then \
		LOCAL_RC=0; \
		if git ls-files '*.md' | grep -q .; then \
			git ls-files -z '*.md' | xargs -0 markdownlint --config .markdownlint.yaml; \
			LOCAL_RC=$$?; \
		fi; \
		exit $$LOCAL_RC; \
	fi; \
	if ! command -v docker >/dev/null 2>&1; then \
		echo "markdown-lint: pinned markdownlint $(MARKDOWNLINT_VERSION) not on PATH and Docker is unavailable"; \
		echo "Either run inside the project container (\`make docker-up\` or \`docker compose up\`) or install Docker Desktop"; \
		exit 1; \
	fi; \
	if ! docker info >/dev/null 2>&1; then \
		echo "markdown-lint: pinned markdownlint $(MARKDOWNLINT_VERSION) not on PATH and Docker daemon is not running"; \
		echo "Start Docker Desktop. If using WSL2, enable Docker Desktop WSL integration for this distro"; \
		exit 1; \
	fi; \
	if git ls-files '*.md' | grep -q .; then \
		RC=0; \
		CACHE_BASE=$${XDG_CACHE_HOME:-$$HOME/.cache}; \
		CACHE_DIR=$$CACHE_BASE/tooling-markdownlint/$(MARKDOWNLINT_VERSION); \
		mkdir -p "$$CACHE_DIR"; \
		HOST_UID=$$(id -u); \
		HOST_GID=$$(id -g); \
		DOCKER_CMD="set -e; \
			if [ ! -x /cache/node_modules/.bin/markdownlint ]; then \
				npm install --no-save --ignore-scripts --no-audit --no-fund --prefix /cache 'markdownlint-cli@$(MARKDOWNLINT_VERSION)' >/cache/install.log 2>&1 || { cat /cache/install.log >&2; exit 1; }; \
			fi; \
			xargs -0 /cache/node_modules/.bin/markdownlint --config /repo/.markdownlint.yaml"; \
		if command -v timeout >/dev/null 2>&1; then \
			git ls-files -z '*.md' | timeout "$(MARKDOWN_LINT_TIMEOUT_SECONDS)"s docker run --rm -i \
				--user "$$HOST_UID:$$HOST_GID" \
				-e HOME=/tmp \
				-e NPM_CONFIG_CACHE=/cache/.npm-cache \
				-e NPM_CONFIG_LOGLEVEL=silent \
				-e NPM_CONFIG_UPDATE_NOTIFIER=false \
				-v "$$PWD":/repo -v "$$CACHE_DIR":/cache -w /repo node:20-bullseye \
				sh -lc "$$DOCKER_CMD"; \
			RC=$$?; \
		else \
			git ls-files -z '*.md' | docker run --rm -i \
				--user "$$HOST_UID:$$HOST_GID" \
				-e HOME=/tmp \
				-e NPM_CONFIG_CACHE=/cache/.npm-cache \
				-e NPM_CONFIG_LOGLEVEL=silent \
				-e NPM_CONFIG_UPDATE_NOTIFIER=false \
				-v "$$PWD":/repo -v "$$CACHE_DIR":/cache -w /repo node:20-bullseye \
				sh -lc "$$DOCKER_CMD"; \
			RC=$$?; \
		fi; \
		if [ $$RC -eq 124 ]; then \
			echo "markdown-lint: Docker fallback timed out after $(MARKDOWN_LINT_TIMEOUT_SECONDS)s"; \
			echo "Try running again, or install local markdownlint $(MARKDOWNLINT_VERSION) in the active environment/container."; \
			exit 1; \
		fi; \
		if [ $$RC -ne 0 ]; then \
			exit $$RC; \
		fi; \
	fi

# Backward-compatible alias: historically this target handled Docker fallback.
markdown-lint-docker: markdown-lint-run

typecheck: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && mypy ."

# Run commitlint against a commit message file.
# Usage: make commitlint-msg MSGFILE=<path-to-commit-msg-file>
# Helper target for manual/debug runs; hook currently calls scripts/run_commitlint.sh directly.
commitlint-msg:
	@if [ -z "$(MSGFILE)" ]; then \
		echo "ERROR: MSGFILE is required. Usage: make commitlint-msg MSGFILE=<path>"; \
		exit 1; \
	fi
	@bash scripts/run_commitlint.sh "$(MSGFILE)"

lint-fix: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && ruff check . --fix && ruff format ."

test: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -q --durations=10"

# Phase 4 / #124 split: fast and slow halves of the suite for parallel CI.
# Local `make test` still runs everything; CI calls these two targets in
# parallel jobs (verify-environment.yml: test-fast / test-slow).
#
# In the prebuilt Docker image, VENV_PATH is set (Dockerfile: ENV VENV_PATH=...)
# and the venv at /opt/venv already has all deps installed, so we skip the
# `env` target (which would invoke scripts/create_env.sh and rebuild a venv
# at $(ENV_PATH) that doesn't exist in the container — pure waste). Outside
# Docker, `env` runs as before to auto-create the local venv on first use.
test-fast:
	@if [ -n "$$VENV_PATH" ] && [ -f "$$VENV_PATH/bin/activate" ]; then \
		bash -lc "source \"$$VENV_PATH/bin/activate\" && pytest -q --durations=10 -m 'not slow'"; \
	else \
		$(MAKE) --no-print-directory env; \
		bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -q --durations=10 -m 'not slow'"; \
	fi

test-slow:
	@if [ -n "$$VENV_PATH" ] && [ -f "$$VENV_PATH/bin/activate" ]; then \
		bash -lc "source \"$$VENV_PATH/bin/activate\" && pytest -q --durations=10 -m slow"; \
	else \
		$(MAKE) --no-print-directory env; \
		bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -q --durations=10 -m slow"; \
	fi

# Verbose timing capture for ad-hoc profiling. Use this when investigating
# a suspected slowdown; prefer plain `make test` for normal runs.
test-profile: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -v --durations=20 --tb=no"

# Selective pytest based on git diff vs upstream (Phase 3 / #123).
# Maps changed files to relevant tests; falls back to the full suite for
# infra changes, large diffs, or unmapped paths. CI's `make test` still
# runs the full suite as the safety net.
test-selective: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/run_pytest_selective.py --stage push"

test-shell:
	@if [ -f tests/test_setup.sh ]; then bash tests/test_setup.sh; else echo "No shell tests to run"; fi

precommit: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg"

precommit-fix: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit run --all-files"

install-act:
	@echo "========================================="
	@echo "  Installing act with checksum verification"
	@echo "========================================="
	@bash scripts/install_act.sh

branch:
	@bash scripts/create_branch.sh $(ISSUE)

# Open a draft PR from the current issue branch to the parent epic (or main).
# Resolution order: BASE=<branch> -> EPIC=<branch> -> auto-detect parent epic
# via GitHub sub-issues -> fallback to main with a warning.
# Usage:
#   make pr-epic ISSUE=<num>
#   make pr-epic ISSUE=<num> EPIC=epic/58-some-epic
#   make pr-epic ISSUE=<num> BASE=main
#   make pr-epic ISSUE=<num> READY=1   # non-draft
EPIC :=
BASE :=
TITLE :=
READY :=
# User-supplied values are passed via target-scoped exports rather than
# interpolated into the recipe shell command line. Two layers of safety:
#
# 1. Make-level: `$(value VAR)` returns VAR's *unexpanded* definition, so a
#    user-supplied TITLE containing `$(shell …)` (or any other make function)
#    is NOT re-evaluated by make at recipe time. Plain `$(VAR)` would do a
#    fresh recursive expansion of the value, which would execute `$(shell …)`
#    as a make function call.
# 2. Shell-level: the env var carries the literal value into bash; the script
#    consumes it as inert string content (e.g. `gh pr create --title "$TITLE"`),
#    so `$(date)` or `` `id` `` in the value never become command substitutions.
#
# To put a literal `$` in TITLE on the command line, write `$$` and quote so
# the shell hands the two characters `$$` to make verbatim; make's own escape
# rule (`$$` -> `$`) is what reduces them to a single literal `$` in the
# variable value. With single quotes the shell does no `$` expansion, so:
#   make pr-epic ISSUE=42 TITLE='price is $$5'
# In a double-quoted argument the shell would consume one `$`, so you would
# need `\$$` (or four `$`s) to deliver the same `$$` to make.
pr-epic: export PR_EPIC_ISSUE := $(value ISSUE)
pr-epic: export PR_EPIC_EPIC  := $(value EPIC)
pr-epic: export PR_EPIC_BASE  := $(value BASE)
pr-epic: export PR_EPIC_TITLE := $(value TITLE)
pr-epic: export PR_EPIC_READY := $(value READY)
pr-epic:
	@if [ -z "$$PR_EPIC_ISSUE" ]; then \
		echo "ERROR: ISSUE is required."; \
		echo "Usage: make pr-epic ISSUE=<num> [EPIC=<branch>] [BASE=<branch>] [TITLE=<text>] [READY=1]"; \
		exit 2; \
	fi
	@bash scripts/create_pr_epic.sh

# Reword the first commit on a PR branch to fix "Initial plan" commitlint failures.
# Usage: make fix-pr-initial-commit PR=<num> [MSG=<message>]
MSG ?= chore(ci): initial planning checkpoint
fix-pr-initial-commit:
	@if [ -z "$(PR)" ]; then \
		echo "ERROR: PR is required."; \
		echo "Usage: make fix-pr-initial-commit PR=<num> [MSG=<message>]"; \
		exit 1; \
	fi
	@if ! echo "$(PR)" | grep -qE '^[1-9][0-9]*$$'; then \
		echo "ERROR: PR must be a positive integer, got: '$(PR)'"; \
		echo "Usage: make fix-pr-initial-commit PR=<num> [MSG=<message>]"; \
		exit 1; \
	fi
	@if ! command -v gh >/dev/null 2>&1; then \
		echo "ERROR: gh CLI is not installed."; \
		echo "Install from https://cli.github.com/ or see docs/SETUP/GITHUB_CLI_AUTH.md"; \
		exit 1; \
	fi
	@if ! gh auth status >/dev/null 2>&1; then \
		echo "ERROR: gh is not authenticated. Run: gh auth login"; \
		echo "If GITHUB_TOKEN is exported in your shell, verify it is valid: gh auth status"; \
		echo "To find stale exports: grep -r GITHUB_TOKEN ~/.bashrc ~/.bash_profile ~/.profile"; \
		exit 1; \
	fi
	@set -e; \
	BASE=$$(gh pr view $(PR) --json baseRefName -q .baseRefName); \
	git fetch origin "$$BASE" --quiet; \
	MERGE_BASE=$$(git merge-base HEAD "origin/$$BASE"); \
	FIRST_SHORT=$$(git log --reverse --format="%h" "$$MERGE_BASE..HEAD" | head -1); \
	if [ -z "$$FIRST_SHORT" ]; then \
		echo "ERROR: no commits found in PR #$(PR)."; exit 1; \
	fi; \
	echo "Rewording $$FIRST_SHORT → '$(MSG)'"; \
	SEQ_ED=$$(mktemp); MSG_F=$$(mktemp); LINT_TMP=$$(mktemp); \
	trap 'rm -f "$$SEQ_ED" "$$MSG_F" "$$LINT_TMP"' EXIT; \
	printf '#!/bin/sh\nset -e\nTMP="$$1.tmp.$$$$"\nsed "s/^pick %s /reword %s /" "$$1" > "$$TMP"\nmv "$$TMP" "$$1"\n' "$$FIRST_SHORT" "$$FIRST_SHORT" > "$$SEQ_ED"; \
	chmod +x "$$SEQ_ED"; \
	printf '%s\n' "$(MSG)" > "$$MSG_F"; \
	GIT_SEQUENCE_EDITOR="$$SEQ_ED" GIT_EDITOR="cp $$MSG_F" git rebase -i "$$MERGE_BASE"; \
	FIRST_FULL=$$(git log --reverse --format="%H" "$$MERGE_BASE..HEAD" | head -1); \
	git log --format="%s%n%n%b" -1 "$$FIRST_FULL" > "$$LINT_TMP"; \
	bash scripts/run_commitlint.sh "$$LINT_TMP"; \
	echo ""; \
	echo "✓ Commit reworded and validated. Force-push with:"; \
	echo "  git push --force-with-lease"
# Run consumer contract tests using the same ENV_PATH derivation as all other targets.
# Replaces the hard-coded ~/envs/${repo}-env path in CI workflows.
consumer-contract-test: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -q tests/scripts/test_consumer_contract.py"

# PR review helper wrapper.
# Read-only: fetches and summarizes PR review comments / owner responses and
# emits JSON. Posting fix/defer/wontfix replies is the agent's responsibility;
# this wrapper does not call gh post APIs. PR_REVIEW_ACTION labels the proposed
# action in plan-mode JSON output; it does not cause anything to be posted.
# scripts/pr_review_helper.py is bundled in tooling and synced to consumers via
# `make sync-tooling`.
# PR_REVIEW_* variables are prefixed to avoid environment variable collisions.
# PR_REVIEW_SKIP_EXPANSION=1 passes --skip-review-expansion through to the helper
# to avoid the per-review N+1 API call on large PRs (may miss comments only
# visible via review-specific endpoints).
# REPO_SLUG can override owner/repo derivation (default: auto-detect from gh repo view --json nameWithOwner).
# Usage examples:
#   make pr-review-helper PR=123
#   make pr-review-helper PR=123 PR_REVIEW_ROOT_IDS=3112407343,3112407397 PR_REVIEW_MODE=plan PR_REVIEW_ACTION=fix PR_REVIEW_TIMING=1
#   make pr-review-helper PR=123 PR_REVIEW_SKIP_EXPANSION=1
#   make pr-review-helper PR=123 REPO_SLUG=owner/custom-repo
PR_REVIEW_MODE ?= scan
PR_REVIEW_ACTION ?= fix
PR_REVIEW_CREATED_AFTER ?=
PR_REVIEW_ROOT_IDS ?=
PR_REVIEW_TIMING ?= 0
PR_REVIEW_SKIP_EXPANSION ?= 0
REPO_SLUG ?=
pr-review-helper: env
	@if [ -z "$(PR)" ]; then \
		echo "ERROR: PR is required. Usage: make pr-review-helper PR=<num> [PR_REVIEW_MODE=scan|plan] [PR_REVIEW_ACTION=fix|defer|wontfix] [PR_REVIEW_CREATED_AFTER=<iso8601>] [PR_REVIEW_ROOT_IDS=id1,id2] [PR_REVIEW_TIMING=1] [PR_REVIEW_SKIP_EXPANSION=1] [REPO_SLUG=owner/repo]"; \
		exit 1; \
	fi
	@if ! echo "$(PR)" | grep -qE '^[1-9][0-9]*$$'; then \
		echo "ERROR: PR must be a positive integer, got: '$(PR)'"; \
		exit 1; \
	fi
	@if ! command -v gh >/dev/null 2>&1; then \
		echo "ERROR: GitHub CLI (gh) not found or not in PATH."; \
		echo "Install from https://cli.github.com/ or add to PATH."; \
		exit 1; \
	fi
	@if ! gh auth status >/dev/null 2>&1; then \
		echo "ERROR: gh is not authenticated. Run: gh auth login"; \
		echo "If GITHUB_TOKEN is exported, verify it is valid or unset it (stale tokens override stored credentials)."; \
		exit 1; \
	fi
	@if [ ! -f scripts/pr_review_helper.py ]; then \
		echo "ERROR: scripts/pr_review_helper.py was not found in this repo."; \
		echo "The helper is bundled in tooling and synced via the manifest;"; \
		echo "  run: make sync-tooling"; \
		exit 1; \
	fi
	@MODE_VAL="$(PR_REVIEW_MODE)"; \
	ACTION_VAL="$(PR_REVIEW_ACTION)"; \
	if ! echo "$$MODE_VAL" | grep -qE '^(scan|plan)$$'; then \
		echo "ERROR: PR_REVIEW_MODE must be one of: scan, plan. Got: '$$MODE_VAL'"; \
		exit 1; \
	fi; \
	if ! echo "$$ACTION_VAL" | grep -qE '^(fix|defer|wontfix)$$'; then \
		echo "ERROR: PR_REVIEW_ACTION must be one of: fix, defer, wontfix. Got: '$$ACTION_VAL'"; \
		exit 1; \
	fi
	@REPO_SLUG_VAL="$(REPO_SLUG)"; \
	if [ -z "$$REPO_SLUG_VAL" ]; then \
		REPO_SLUG_VAL=$$(gh repo view --json nameWithOwner --jq .nameWithOwner); \
	fi; \
	bash -lc 'source "$(ENV_PATH)/bin/activate" && \
		CMD=(python3 scripts/pr_review_helper.py --repo "'"$$REPO_SLUG_VAL"'" --pr "$(PR)"); \
		if [ -n "$(PR_REVIEW_CREATED_AFTER)" ]; then CMD+=(--created-after "$(PR_REVIEW_CREATED_AFTER)"); fi; \
		if [ -n "$(PR_REVIEW_ROOT_IDS)" ]; then CMD+=(--root-ids "$(PR_REVIEW_ROOT_IDS)"); fi; \
		if [ "$(PR_REVIEW_TIMING)" = "1" ]; then CMD+=(--timing); fi; \
		if [ "$(PR_REVIEW_SKIP_EXPANSION)" = "1" ]; then CMD+=(--skip-review-expansion); fi; \
		if [ "$(PR_REVIEW_MODE)" = "plan" ]; then CMD+=(--action-plan-json --default-action "$(PR_REVIEW_ACTION)"); else CMD+=(--json); fi; \
		"$${CMD[@]}"'

sync-tooling:
	./scripts/sync_tooling.sh $(TOOLING_VERSION)

update-sync-script:
	@set -e; \
	TOOLING_DIR="$${TOOLING_DIR:-../tooling}"; \
	if [ -x ./scripts/update_sync_script.sh ]; then \
		SCRIPT=./scripts/update_sync_script.sh; \
	elif [ -x "$$TOOLING_DIR/scripts/update_sync_script.sh" ]; then \
		SCRIPT="$$TOOLING_DIR/scripts/update_sync_script.sh"; \
	else \
		echo "update-sync-script: could not find update_sync_script.sh in ./scripts or $$TOOLING_DIR/scripts."; \
		echo "Set TOOLING_DIR to your tooling checkout or sync the script into the consumer repo."; \
		exit 1; \
	fi; \
	TARGET_DIR=$${TARGET_DIR:-.}; TOOLING_DIR="$$TOOLING_DIR" "$$SCRIPT" "$$TARGET_DIR"

drift-check:
	bash -lc 'if [ -f .tooling-sync-manifest.toml ] && [ ! -f .tooling-sync-manifest.lock ] && [ -f pyproject.toml ] && grep -q '\''name *= *"tooling"'\'' pyproject.toml && [ -f project-template/scripts/setup.sh ]; then echo "drift-check: tooling source repo detected (no lock expected) -- skipping"; exit 0; fi; \
		ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "drift-check: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_sync_drift.py --root .'

docs-check:
	python3 scripts/validate_activation_commands.py --root .

agents-drift-check:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "agents-drift-check: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_agents_drift.py --root .'

tooling-toml-check:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "tooling-toml-check: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_tooling_toml_drift.py --root .'

version-check: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_version_sync.py --root ."

version-fix: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_version_sync.py --root . --fix"

env-file-check: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_env_file.py --root ."

env-file-fix: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_env_file.py --root . --fix"

action-pin-check:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "action-pin-check: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_workflow_action_pins.py --root .'

action-pin-fix:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "action-pin-fix: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_workflow_action_pins.py --root . --fix'

dev-tool-pin-check:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "dev-tool-pin-check: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_dev_tool_pins.py --root .'

dev-tool-pin-fix:
	bash -lc 'ENV_ACTIVATE=$(ENV_PATH)/bin/activate; \
		if [ -f "$$ENV_ACTIVATE" ]; then \
			. "$$ENV_ACTIVATE"; \
			PYTHON_CMD=python3; \
		elif command -v python3 >/dev/null 2>&1; then \
			PYTHON_CMD=python3; \
		else \
			echo "dev-tool-pin-fix: python3 not found. Please install python3 or create a virtualenv at $(ENV_PATH)."; \
			exit 1; \
		fi; \
		"$$PYTHON_CMD" scripts/validate_dev_tool_pins.py --root . --fix'

check: env
	@echo "========================================="
	@echo "  Running Full Quality Check"
	@echo "========================================="
	@echo ""
	@echo "1. Auto-fixing code issues..."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && ruff check . --fix && ruff format ."
	@echo ""
	@echo "2. Running type checks..."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && mypy ."
	@echo ""
	@echo "3. Running tests..."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && pytest -q"
	@echo ""
	@echo "4. Validating configs..."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit run check-yaml --all-files"
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit run check-toml --all-files"
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && pre-commit run check-json --all-files"
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_version_sync.py --root ."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_env_file.py --root ."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_workflow_action_pins.py --root ."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_dev_tool_pins.py --root ."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_agents_drift.py --root ."
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_tooling_toml_drift.py --root ."
	@echo ""
	@echo "========================================="
	@echo "  ✅ All checks passed!"
	@echo "========================================="
	@echo ""
	@echo "Your code is ready to commit and push."
	@echo ""

lint-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && ruff check . && ruff format --check . && mypy . && make markdown-lint"

lint-fix-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && ruff check . --fix && ruff format ."

typecheck-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && mypy ."

test-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && pytest -q"

precommit-fix-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && pre-commit run --all-files"

check-docker: docker-up
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && ruff check . --fix && ruff format . && mypy . && pytest -q && pre-commit run check-yaml --all-files && pre-commit run check-toml --all-files && pre-commit run check-json --all-files && python3 scripts/validate_version_sync.py --root . && python3 scripts/validate_env_file.py --root . && python3 scripts/validate_workflow_action_pins.py --root . && python3 scripts/validate_dev_tool_pins.py --root . && python3 scripts/validate_agents_drift.py --root . && python3 scripts/validate_tooling_toml_drift.py --root ."

# Consumer-specific make targets live in Makefile.local. The file is
# consumer-owned and intentionally NOT in .tooling-sync-manifest.toml, so
# tooling sync neither overwrites it nor flags it as drift. The leading `-`
# makes its absence a no-op. See AGENTS.md "Adding consumer-specific make
# targets" for the full convention.
-include Makefile.local
