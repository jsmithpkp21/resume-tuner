ARG PYTHON_VERSION=3.11
ARG PIP_VERSION=24.3.1
ARG AWK_IMPL_PACKAGE=gawk
# HOST_UID / HOST_GID let the in-container `app` user share UID:GID with the
# host that mounts /repo, so files written from inside the container are
# host-owned (not root) on stock Linux Docker. 1000:1000 matches a fresh
# Ubuntu/WSL user; override at build time via
# `--build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g)` for other hosts.
ARG HOST_UID=1000
ARG HOST_GID=1000
# Defense-in-depth (issue #353): refuse `HOST_UID=0` (root) by default.
# `scripts/docker_build.sh` and the `update-docker` Makefile target already
# enforce this, but a caller invoking `docker build` directly bypasses both.
# Pass `--build-arg HOST_UID_ALLOW_ROOT=1` to opt in (e.g. CI image that
# genuinely needs UID 0); matches the env-var escape hatch in docker_build.sh.
ARG HOST_UID_ALLOW_ROOT=0

FROM python:${PYTHON_VERSION}-slim

# Re-declare ARGs after FROM for use in later stages
ARG PYTHON_VERSION
ARG PIP_VERSION
ARG AWK_IMPL_PACKAGE
ARG HOST_UID
ARG HOST_GID
ARG HOST_UID_ALLOW_ROOT

# Set working directory
WORKDIR /repo

# Install system dependencies (latest versions from base image)
# Note: Using slim image (already has minimal packages)
# Only installing build essentials needed for Python package compilation
# System package versions are determined by the base image's Debian version
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    git \
    bash \
    jq \
    ${AWK_IMPL_PACKAGE} \
    nodejs \
    npm \
    fontconfig \
    fonts-crosextra-carlito \
    fonts-liberation \
    && update-alternatives --set awk /usr/bin/gawk \
    && fc-cache -f \
    && npm install -g markdownlint-cli@0.47.0 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment in /opt (persistent across runs)
ENV VENV_PATH=/opt/venv
RUN python${PYTHON_VERSION%.*} -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# Upgrade pip to required version (if specified)
# If PIP_VERSION is empty, skip explicit version pinning
RUN if [ -n "${PIP_VERSION}" ]; then \
      pip install --upgrade pip=="${PIP_VERSION}"; \
    else \
      pip install --upgrade pip; \
    fi

# Copy requirements files first for better caching
# This layer only invalidates when dependencies change
COPY requirements.txt requirements-dev.txt ./

# Install all requirements in a single resolver pass to catch conflicts early
# and avoid redundant installs from sequential pip calls.
RUN pip install -r requirements.txt -r requirements-dev.txt

# Create the non-root dev user with host-matched UID/GID and hand off
# ownership of the venv. Placed BEFORE `COPY . .` so the recursive
# `chown` of /opt/venv (the expensive part) only depends on prior
# already-cached layers (apt + venv + pip + build args). Iterative
# rebuilds triggered by code changes hit the COPY cache miss but
# reuse this layer instead of re-chowning the entire venv.
#
# Idempotent against UID/GID collisions in the base image (e.g. macOS host
# GID 20 already maps to Debian's `dialout`): if the GID/UID already exists
# we reuse it rather than failing the build. `USER` is set numerically so
# the container runs as the requested UID:GID even when no `app` row was
# added to /etc/passwd.
# Defense-in-depth (issue #349): validate HOST_UID/HOST_GID are numeric
# before any shell consumer uses them, and quote every expansion below.
# `scripts/docker_build.sh` and the `update-docker` make target already
# enforce `^[0-9]+$`, but a caller invoking `docker build` directly
# bypasses both. Docker ARG substitution is *textual* — at parse time
# Docker replaces `${HOST_UID}` with the literal build-arg value inside
# the RUN string, then hands the result to `/bin/sh -c`. So an unquoted
# expansion of an attacker-supplied value is parsed by the shell from
# scratch, with two failure modes:
#   * word-splitting / globbing — e.g. `1000 --shell /bin/sh` injects
#     extra arguments to groupadd/useradd/chown;
#   * shell metacharacter injection — e.g. `1000; rm -rf /` ends the
#     current command and starts a new one, because `;` is a control
#     operator when shell parses the substituted text.
# The numeric `case` guards short-circuit both: if either build arg
# fails the `*[!0-9]*` check the build aborts before any consumer runs.
#
# Defense-in-depth (issue #353): after the numeric check passes, also
# refuse `HOST_UID=0` unless `HOST_UID_ALLOW_ROOT=1` is set. `0` passes
# the numeric guard above but baking root into the image defeats the
# non-root-user goal from issue #322; this mirrors the gate in
# `scripts/docker_build.sh` and the `update-docker` Makefile target so
# all three entry paths enforce the same policy.
#
# An all-zeros `case` (rather than `[ "${HOST_UID}" -eq 0 ]`) catches
# the same bypass set — `0`, `00`, `000`, … — that `getent`/`useradd`/
# Docker `USER` resolve to UID 0, while sidestepping `[ -eq ]`'s
# base-detection edge cases: `08` errors in some shells (invalid octal),
# and bash's `[ -eq ]` auto-detects `0xN` as hex. The numeric `case`
# guard above already restricts the operand to pure digits, so the only
# remaining question is whether those digits represent zero or non-zero
# — a literal-character `case` answers it without invoking arithmetic.
RUN case "${HOST_UID}" in ''|*[!0-9]*) echo "HOST_UID must be numeric, got: ${HOST_UID}" >&2; exit 1;; esac \
 && case "${HOST_GID}" in ''|*[!0-9]*) echo "HOST_GID must be numeric, got: ${HOST_GID}" >&2; exit 1;; esac \
 && case "${HOST_UID}" in \
      *[!0]*) ;; \
      *) if [ "${HOST_UID_ALLOW_ROOT}" != "1" ]; then \
           echo "HOST_UID=0 (root) refused; pass --build-arg HOST_UID_ALLOW_ROOT=1 to opt in" >&2; \
           exit 1; \
         fi ;; \
    esac \
 && if ! getent group "${HOST_GID}" >/dev/null 2>&1; then \
      groupadd --gid "${HOST_GID}" app; \
    fi \
 && if ! getent passwd "${HOST_UID}" >/dev/null 2>&1; then \
      useradd --uid "${HOST_UID}" --gid "${HOST_GID}" --create-home --shell /bin/bash app; \
    fi \
 && chown -R "${HOST_UID}:${HOST_GID}" /opt/venv

# Copy repository files. Invalidates on any code change but the
# user-creation + venv-chown layer above is already cached.
COPY . .

# Ensure scripts have execute permissions in Docker, and chown the
# /repo directory entry to the dev user. The `COPY . .` snapshot
# underneath is left root-owned because at runtime the bind-mount
# (compose, CI, `docker run -v`) masks /repo with host content;
# recursing through the workspace snapshot would balloon this layer
# for no runtime benefit.
RUN chmod +x scripts/*.sh \
 && chown "${HOST_UID}:${HOST_GID}" /repo

USER ${HOST_UID}:${HOST_GID}

# Verify environment (with activated venv) as the unprivileged user, so
# verification tests the actual end-user runtime rather than a root shell.
RUN /bin/bash -c "source $VENV_PATH/bin/activate && scripts/verify_env.sh"

# Default command: activate venv and drop to shell
CMD ["/bin/bash", "-c", "source $VENV_PATH/bin/activate && /bin/bash"]
