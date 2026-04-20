VERSION := $(shell cat VERSION)
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

.PHONY: env setup active verify clean upgrade lock lint lint-fix typecheck test test-shell precommit precommit-fix install-act bootstrap sync-tooling update-sync-script drift-check docs-check check version-check version-fix action-pin-check action-pin-fix markdown-lint markdown-lint-run markdown-lint-docker commitlint-msg fix-pr-initial-commit consumer-contract-test docker-up docker-shell lint-docker lint-fix-docker typecheck-docker test-docker precommit-fix-docker check-docker

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

update-docker:
	docker compose build
	docker compose up -d
	@echo "Docker container rebuilt and restarted. jq and other dependencies are now available."

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

# Public alias — always call this target from hooks, CI, and manually.
# Uses local markdownlint binary when available (e.g. inside the project container),
# falls back to Docker with a pinned npx invocation when not.
markdown-lint: markdown-lint-run

markdown-lint-run:
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "markdown-lint: git tracked-file context unavailable"; \
		exit 1; \
	elif command -v markdownlint >/dev/null 2>&1; then \
		if git ls-files '*.md' | grep -q .; then \
			git ls-files -z '*.md' | xargs -0 markdownlint --config .markdownlint.yaml; \
		fi; \
	elif ! command -v docker >/dev/null 2>&1; then \
		echo "markdown-lint: markdownlint not found and Docker is unavailable"; \
		echo "Either run inside the project container (docker-compose up) or install Docker Desktop"; \
		exit 1; \
	elif ! docker info >/dev/null 2>&1; then \
		echo "markdown-lint: markdownlint not found and Docker daemon is not running"; \
		echo "Start Docker Desktop. If using WSL2, enable Docker Desktop WSL integration for this distro"; \
		exit 1; \
	elif git ls-files '*.md' | grep -q .; then \
		RC=0; \
		if command -v timeout >/dev/null 2>&1; then \
			git ls-files -z '*.md' | timeout "$(MARKDOWN_LINT_TIMEOUT_SECONDS)"s docker run --rm -i \
				-e NPM_CONFIG_LOGLEVEL=silent \
				-e NPM_CONFIG_UPDATE_NOTIFIER=false \
				-v "$$PWD":/repo -w /repo node:20-bullseye \
				sh -lc "xargs -0 npx --yes --quiet markdownlint-cli@0.47.0 --config .markdownlint.yaml"; \
			RC=$$?; \
		else \
			git ls-files -z '*.md' | docker run --rm -i \
				-e NPM_CONFIG_LOGLEVEL=silent \
				-e NPM_CONFIG_UPDATE_NOTIFIER=false \
				-v "$$PWD":/repo -w /repo node:20-bullseye \
				sh -lc "xargs -0 npx --yes --quiet markdownlint-cli@0.47.0 --config .markdownlint.yaml"; \
			RC=$$?; \
		fi; \
		if [ $$RC -eq 124 ]; then \
			echo "markdown-lint: Docker fallback timed out after $(MARKDOWN_LINT_TIMEOUT_SECONDS)s"; \
			echo "Try running again, or install local markdownlint in the active environment/container."; \
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

version-check: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_version_sync.py --root ."

version-fix: env
	bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_version_sync.py --root . --fix"

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
	@bash -lc "source \"$(ENV_PATH)/bin/activate\" && python3 scripts/validate_workflow_action_pins.py --root ."
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
	$(DOCKER_RUN) "cd /repo && source /opt/venv/bin/activate && ruff check . --fix && ruff format . && mypy . && pytest -q && pre-commit run check-yaml --all-files && pre-commit run check-toml --all-files && pre-commit run check-json --all-files && python3 scripts/validate_version_sync.py --root . && python3 scripts/validate_workflow_action_pins.py --root ."
