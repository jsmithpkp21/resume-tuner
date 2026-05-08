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

FROM python:${PYTHON_VERSION}-slim

# Re-declare ARGs after FROM for use in later stages
ARG PYTHON_VERSION
ARG PIP_VERSION
ARG AWK_IMPL_PACKAGE
ARG HOST_UID
ARG HOST_GID

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
RUN if ! getent group ${HOST_GID} >/dev/null 2>&1; then \
      groupadd --gid ${HOST_GID} app; \
    fi \
 && if ! getent passwd ${HOST_UID} >/dev/null 2>&1; then \
      useradd --uid ${HOST_UID} --gid ${HOST_GID} --create-home --shell /bin/bash app; \
    fi \
 && chown -R ${HOST_UID}:${HOST_GID} /opt/venv

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
 && chown ${HOST_UID}:${HOST_GID} /repo

USER ${HOST_UID}:${HOST_GID}

# Verify environment (with activated venv) as the unprivileged user, so
# verification tests the actual end-user runtime rather than a root shell.
RUN /bin/bash -c "source $VENV_PATH/bin/activate && scripts/verify_env.sh"

# Default command: activate venv and drop to shell
CMD ["/bin/bash", "-c", "source $VENV_PATH/bin/activate && /bin/bash"]
