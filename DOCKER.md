# Docker Setup for Deterministic Environment

Docker containers provide a fully reproducible, isolated environment with all dependencies pre-installed. This eliminates "works on my machine" problems and system dependency issues.

> **When to use Docker (policy):** This repo family defaults to **local-runtime-first
> with Docker fallback** for individual developer tools (see
> [`docs/REFERENCE/adr/0001-local-tooling-runtime-policy.md`](docs/REFERENCE/adr/0001-local-tooling-runtime-policy.md)).
> The flows documented below — `make docker-up`, `make lint-docker`,
> `make test-docker`, `make check-docker` — are the supported **explicit Docker
> track**: opt in here when you want a fully containerized substrate end-to-end
> rather than the per-tool fallback path.

---

## Quick Start with Docker

### Option 1: Docker Compose (Recommended)

```bash
# Build and start the container (deterministic build args from setup files)
bash scripts/docker_build.sh

docker-compose up

# You'll be inside a bash shell in the container with the venv activated
$ python --version
Python X.Y.Z  # from tooling.toml [python].version

$ which python
/opt/venv/bin/python
```

### Option 2: Docker CLI

```bash
# Build the image with deterministic build args
bash scripts/docker_build.sh

# Run the container
docker run -it --rm \
  -v $(pwd):/repo \
  base_repo:$(cat VERSION) bash

# Inside the container:
$ python --version
Python X.Y.Z  # from tooling.toml [python].version
```

---

## Service Name

The Compose service is named `base_env` and defined once in `docker-compose.yml`.
The `Makefile` parameterizes container-targeted invocations via the `DOCKER_SERVICE`
variable (default: `base_env`). If you've added another service to your
`docker-compose.yml`, target it in any `make` target that execs into the container
by overriding `DOCKER_SERVICE`:

```bash
# Replace <service-name> with a service you've defined in docker-compose.yml.
make test-docker DOCKER_SERVICE=<service-name>
```

User-facing `docker-compose` examples in this doc use the literal `base_env`
name since shell snippets cannot interpolate Make variables. (`docker compose`
without the hyphen is the equivalent v2+ form; both work against the same
`docker-compose.yml`.)

---

## Why Docker?

### ✅ What Docker Solves

| Problem | Solution |
|---------|----------|
| Python 3.11 not installed | Python 3.11 pre-installed in image |
| System dependencies missing | All dependencies in Dockerfile |
| Different Python versions across machines | Docker guarantees exact version |
| Virtual environment setup | Pre-built venv in image |
| pip version mismatch | Exact pip version pinned in Dockerfile |
| "Works on my machine" issues | Identical environment everywhere |

### No More `setup-python.sh` Needed

**Without Docker:**
```bash
sudo bash setup-python.sh  # Install Python 3.11
scripts/create_env.sh      # Create venv
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
```

**With Docker:**
```bash
docker-compose up --build  # Everything is pre-configured
```

---

## Build Configuration

Docker builds require `PYTHON_VERSION` and `PIP_VERSION` build arguments. There are two ways to provide these:

### Option 1: Using docker_build.sh (Recommended)

```bash
bash scripts/docker_build.sh
```

This script:
- Reads versions from `pyproject.toml` and `tooling.toml`
- Exports them as environment variables
- Passes them to `docker build` with `--build-arg`
- Ensures build matches the repository configuration exactly

### Option 2: Using docker-compose with .env file

```bash
docker-compose up --build
```

This approach uses the `.env` file which contains:
```bash
# Python version (sourced from tooling.toml [python].version)
PYTHON_VERSION=3.11.14
# pip version (sourced from tooling.toml [tooling].pip)
PIP_VERSION=24.3.1
```

**Note:** Docker Compose treats everything after `=` as the literal value (no
inline comment stripping), so keep comments on their own lines. The same rule
is enforced by `scripts/validate_env_file.py`. The `.env` file has hardcoded
defaults that match the repository configuration. These are safe to commit
(they're not secrets). Docker Compose automatically loads this file.

**For user-specific overrides:** Create `.env.local` (gitignored) to override values.

### Host UID/GID Build Args

The dev container runs as a non-root `app` user whose UID/GID are baked
into the image via the `HOST_UID` / `HOST_GID` build args (defaults
`1000:1000`, which matches a fresh Ubuntu/WSL user). Aligning the
in-container UID with the host UID means files written to bind-mounted
`/repo` are host-owned — no `sudo` needed to delete or edit them on
stock Linux Docker, and no reliance on Docker Desktop's transparent
UID translation.

`make update-docker` automatically passes the current host UID/GID:

```bash
make update-docker
# Equivalent to:
docker compose build \
  --build-arg HOST_UID=$(id -u) \
  --build-arg HOST_GID=$(id -g)
docker compose up -d
```

`scripts/docker_build.sh` (the Docker-CLI fallback path) auto-detects
the host UID/GID via `id -u` / `id -g` and forwards them to
`docker build` for you; you can override either by exporting
`HOST_UID` / `HOST_GID` before invoking the script.

If you build directly with `docker compose build` or `docker build`
without going through `make update-docker` or `scripts/docker_build.sh`,
pass the flags explicitly when your host UID is not `1000`:

```bash
docker compose build \
  --build-arg HOST_UID=$(id -u) \
  --build-arg HOST_GID=$(id -g)
```

#### One-time migration (existing venv volume)

Pre-existing `<project>_base_env_cache` volumes from older root-owned
images contain a root-owned `/opt/venv`. After pulling the non-root
Dockerfile, drop the volume once so the new image's chowned `/opt/venv`
is what populates the named volume:

```bash
make docker-down                            # or: docker compose down
docker volume rm <project>_base_env_cache   # repo-derived volume name
make docker-up                              # or: make update-docker
```

(Inspect existing volumes with `docker volume ls`.)

Tool-cache directories on the host (e.g. `.ruff_cache`, `.mypy_cache`,
`.pytest_cache`, `__pycache__`) that were written by a previous root
container are also root-owned and will block writes from the new `app`
user. Clear them once after migrating; if your host user can't `rm`
them directly, use a throwaway root container:

```bash
docker run --rm -v "$PWD":/repo -w /repo --user 0:0 \
  python:3.11-slim rm -rf .ruff_cache .mypy_cache .pytest_cache
```

New runs will write these as the host user automatically.

---

## Docker Workflows

### Running Tests

```bash
# Inside the container
docker-compose exec base_env make test
docker-compose exec base_env make lint
docker-compose exec base_env make lint-fix    # Auto-fix linting issues
docker-compose exec base_env make typecheck   # Type checking only
docker-compose exec base_env make verify
```

### Development with Hot Reload

```bash
# Start container in background
docker-compose up -d

# Edit files on your host machine
# Changes are immediately available in the container
docker-compose exec base_env bash

# Inside container:
$ make test
$ scripts/verify_env.sh
```

### One-off Commands

```bash
# Run a single command without entering bash
docker-compose run --rm base_env make test
docker-compose run --rm base_env pytest tests/
docker-compose run --rm base_env python scripts/prepare_playwright_layer.py
```

### Cleanup

```bash
# Stop and remove containers (preferred; symmetric with `make docker-up`)
make docker-down

# Or directly (`docker compose` is the v2 plugin form; `docker-compose`
# is the legacy v1 binary and may not be installed on newer hosts):
docker compose down

# Remove all volumes (venv cache)
docker compose down -v

# Remove image
docker rmi base_repo
```

---

## What's in the Container

### Base Image
- `python:${PYTHON_VERSION}-slim` - Version from `pyproject.toml`

### Pre-installed System Packages
- `build-essential` - GCC, make, build tools
- `libssl-dev` - SSL/TLS libraries
- `libffi-dev` - FFI libraries for cryptography
- `git` - Version control
- `bash` - Shell

### Pre-installed Python Packages
- All packages from `requirements.txt`
- pip version from `tooling.toml`

### Pre-configured Environment
- Virtual environment at `/opt/venv`
- Automatically activated on startup
- Project code mounted at `/repo`
- Volume cache for faster rebuilds
- Runs as non-root `app` user (UID/GID match host via build args)

---

## Dockerfile Explanation

```dockerfile
ARG PYTHON_VERSION
ARG PIP_VERSION
ARG HOST_UID=1000
ARG HOST_GID=1000

FROM python:${PYTHON_VERSION}-slim
# Python version comes from tooling.toml [python].version

WORKDIR /repo
# Set working directory

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    git \
    bash \
    && rm -rf /var/lib/apt/lists/*
# Install system dependencies (latest versions from base image)
# System package versions are determined by the Python base image's Debian version

ENV VENV_PATH=/opt/venv
RUN python${PYTHON_VERSION%.*} -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"
# Create virtual environment in /opt (persistent across runs)

RUN pip install --upgrade pip==${PIP_VERSION}
# pip version comes from tooling.toml [tooling]

RUN pip install -r requirements.txt
# Install all Python dependencies

# Create the non-root dev user and chown the venv BEFORE `COPY . .`
# so the recursive chown stays cached across iterative rebuilds
# (a code change invalidates COPY but not this layer).
# Idempotent against UID/GID collisions in the base image (e.g. macOS GID 20).
RUN if ! getent group ${HOST_GID} >/dev/null 2>&1; then \
      groupadd --gid ${HOST_GID} app; \
    fi \
 && if ! getent passwd ${HOST_UID} >/dev/null 2>&1; then \
      useradd --uid ${HOST_UID} --gid ${HOST_GID} --create-home --shell /bin/bash app; \
    fi \
 && chown -R ${HOST_UID}:${HOST_GID} /opt/venv

COPY . .
# Copy project files; bind-mount masks /repo at runtime so we
# don't recurse the snapshot here.

RUN chmod +x scripts/*.sh \
 && chown ${HOST_UID}:${HOST_GID} /repo
USER ${HOST_UID}:${HOST_GID}

RUN /bin/bash -c "source $VENV_PATH/bin/activate && scripts/verify_env.sh"
# Verify environment with activated venv (runs as `app`, not root)
# Build fails if verification fails

CMD ["/bin/bash", "-c", "source $VENV_PATH/bin/activate && /bin/bash"]
# Start bash with venv activated
```

**Key Points:**
- Python version is sourced from `tooling.toml [python].version`
- pip version is sourced from `tooling.toml`
- System packages use latest versions from the Python base image
- `PYTHON_VERSION` and `PIP_VERSION` are forwarded by CI,
  `scripts/docker_build.sh`, and `make update-docker`
- `HOST_UID` / `HOST_GID` are forwarded automatically by
  `make update-docker` and `scripts/docker_build.sh` (both detect
  the host UID/GID at invocation); raw `docker compose build`
  / `docker build` use the `1000:1000` defaults unless you pass
  the args yourself
- Container runs as a non-root user with host-matched UID/GID
  (default `1000:1000`); files written to bind-mounted `/repo` are
  host-owned on stock Linux Docker. See "Host UID/GID Build Args"
  above for overrides.

---

## Docker Compose Explanation

```yaml
services:
  base_env:
    build:
      context: docs/REFERENCE
      args:
        PYTHON_VERSION: ${PYTHON_VERSION}
        PIP_VERSION: ${PIP_VERSION}
    # Build from Dockerfile

    container_name: base_repo
    # Container name for easy reference

    working_dir: /repo
    # Set working directory inside container

    volumes:
      - .:/repo                    # Mount project code
      - base_env_cache:/opt/venv   # Persist venv across runs

    environment:
      VENV_PATH: /opt/venv
      # Path to virtual environment

    stdin_open: true
    tty: true
    # Interactive terminal support

    command: /bin/bash -c "source /opt/venv/bin/activate && exec bash"
    # Activate venv and start interactive shell

volumes:
  base_env_cache:
    driver: local
    # Local volume for persisting venv across container restarts
```

**Key Points:**
- `docker-compose up`/`build` works directly: Compose auto-loads `.env` from the repo root, which provides `PYTHON_VERSION` and `PIP_VERSION` build args. No shell-level setup required.
- `scripts/load_build_env.sh` exports the same variables in your current shell from `tooling.toml`. It is needed only by `scripts/docker_build.sh` (the docker-CLI fallback path), not by `docker-compose`.
- For deterministic builds outside Compose, use `bash scripts/docker_build.sh` (which sources `load_build_env.sh` internally).
- `.env` and `tooling.toml` are kept in sync by `scripts/validate_env_file.py` (run via `make env-file-check` and the pre-commit hook); use `make env-file-fix` to update `.env` after bumping versions in `tooling.toml`.
- Venv is **automatically activated** on startup (via command override)
- Volume cache (`base_env_cache`) persists `/opt/venv` across runs (faster rebuilds)
- `$VENV_PATH` environment variable available inside container
- `stdin_open: true` and `tty: true` enable interactive use (typing commands, seeing output)
- Working directory set to `/repo` for convenience

---

## Image Size

The resulting image size depends on pinned package versions and is reproducible across machines.

---

## Comparison: Native vs Docker

### Native Setup (What You Had Before)

```bash
# 1. Install Python 3.11
sudo bash setup-python.sh

# 2. Create virtual environment
scripts/create_env.sh
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate

# 3. Run tests
make test
```

### Docker Setup (Now Available)

```bash
# 1. Build image (deterministic)
bash scripts/docker_build.sh

# 2. Use environment
docker-compose up

# 3. Run tests
docker-compose exec base_env make test
```

---

## When to Use Docker vs Native

### Use Docker if:
- ✅ Working on multiple projects with different Python versions
- ✅ Want guaranteed reproducibility
- ✅ Don't want to manage system Python installations
- ✅ Running CI/CD pipelines
- ✅ Sharing code with team members (everyone gets same env)

### Use Native if:
- ✅ Single project, single Python version
- ✅ Want direct access to system Python
- ✅ Need maximum performance (minimal Docker overhead)
- ✅ Deep integration with system tools

---

## Troubleshooting

### Container won't start
```bash
# Check Docker is running
docker ps

# View build logs
docker-compose up --build --no-cache
```

### Slow first build
- Docker builds from scratch: ~2-3 minutes
- Subsequent builds use cache: ~10-30 seconds
- Run once and leave container running

### venv not activated
- Docker-compose automatically activates venv
- If using `docker run`, activate manually:
  ```bash
  source /opt/venv/bin/activate
  ```

### Volume mount permission issues
- The image bakes in a non-root `app` user with UID/GID matching the
  host (defaults `1000:1000`). On a fresh Ubuntu/WSL host this just
  works — files written from inside the container to `/repo` are
  owned by your host user, no `sudo` needed to delete or edit them.
- If your host UID is not `1000`, build with the matching args (or
  use `make update-docker`, which auto-passes them):
  ```bash
  docker compose build \
    --build-arg HOST_UID=$(id -u) \
    --build-arg HOST_GID=$(id -g)
  ```
- See "Host UID/GID Build Args" under Build Configuration for the
  one-time migration step if you have an old root-owned `base_env_cache`
  volume.

---

## Runtime Contract (Shell Tools)

Shell tooling is part of the deterministic runtime contract, not just Python packages.

The Docker image installs and enforces:
- `bash`
- `gawk` (set as `/usr/bin/awk`)
- `grep`
- `sed`
- `jq`

Why this matters:
- Our environment scripts parse `tooling.toml` using `awk`/`grep`/`sed`.
- Different `awk` implementations can behave differently.
- Docker sets GNU awk explicitly to avoid parser drift between local and CI.

The runtime contract is enforced by `scripts/create_env.sh` and `scripts/verify_env.sh`,
and may also be declared in `tooling.toml` under `[runtime]` when that section is present.
It is validated by:
- `scripts/create_env.sh`
- `scripts/verify_env.sh`
- repository tests under `tests/` that validate environment creation, verification,
  and shell runtime contract behavior

---

## Next Steps

**Recommended workflow:**
```bash
# Start container in background
make docker-up

# Work on code (auto-synced)
# Edit files in your IDE on the host

# Run commands in the container
make test-docker
make lint-docker

# When done
make docker-down
```

This replaces the need for `setup-python.sh` entirely!
