ARG PYTHON_VERSION=3.11
ARG PIP_VERSION=24.3.1
ARG AWK_IMPL_PACKAGE=gawk

FROM python:${PYTHON_VERSION}-slim

# Re-declare ARGs after FROM for use in later stages
ARG PYTHON_VERSION
ARG PIP_VERSION
ARG AWK_IMPL_PACKAGE

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
    fonts-liberation \
    fontconfig \
    && update-alternatives --set awk /usr/bin/gawk \
    && npm install -g markdownlint-cli@0.47.0 \
    && fc-cache -fv \
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

# Copy repository files
# This layer invalidates on any code change but dependencies are cached
COPY . .

# Ensure scripts have execute permissions in Docker
RUN chmod +x scripts/*.sh

# Verify environment (with activated venv)
RUN /bin/bash -c "source $VENV_PATH/bin/activate && scripts/verify_env.sh"

# Default command: activate venv and drop to shell
CMD ["/bin/bash", "-c", "source $VENV_PATH/bin/activate && /bin/bash"]
