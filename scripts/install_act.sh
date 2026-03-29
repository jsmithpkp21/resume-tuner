#!/usr/bin/env bash
set -euo pipefail

# Secure act installation script with checksum verification
# Prevents supply-chain attacks by pinning version and verifying integrity

# Configuration
ACT_VERSION="0.2.84"  # Pin to specific version (update as needed)
INSTALL_DIR="${HOME}/.local/bin"
PLATFORM="Linux"
ARCH="x86_64"

# GitHub release URL (immutable - points to specific tag, not 'latest' or 'master')
DOWNLOAD_URL="https://github.com/nektos/act/releases/download/v${ACT_VERSION}/act_${PLATFORM}_${ARCH}.tar.gz"

# Expected SHA256 checksum for act v0.2.84 Linux x86_64
# Source: https://github.com/nektos/act/releases/tag/v0.2.84
# pragma: allowlist secret
EXPECTED_CHECKSUM="1f4dd2ad76c6f8a6c63abccbc2e8bc0dbbb0c8b7596c1c3ccae2c0c7a6cd9e3e"

echo "📦 Installing act v${ACT_VERSION}..."
echo "   Target: ${INSTALL_DIR}/act"

# Create temp directory for download
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

# Download release artifact
echo "⬇️  Downloading from GitHub releases..."
if ! curl -fsSL -o "${TEMP_DIR}/act.tar.gz" "$DOWNLOAD_URL"; then
    echo "❌ Failed to download act from $DOWNLOAD_URL" >&2
    exit 1
fi

# Verify checksum
echo "🔐 Verifying checksum..."
ACTUAL_CHECKSUM="$(sha256sum "${TEMP_DIR}/act.tar.gz" | awk '{print $1}')"

if [ "$ACTUAL_CHECKSUM" != "$EXPECTED_CHECKSUM" ]; then
    echo "❌ Checksum verification failed!" >&2
    echo "   Expected: $EXPECTED_CHECKSUM" >&2
    echo "   Got:      $ACTUAL_CHECKSUM" >&2
    echo "" >&2
    echo "   This could indicate:" >&2
    echo "   1. Network tampering (MITM attack)" >&2
    echo "   2. Compromised GitHub release" >&2
    echo "   3. Outdated checksum in this script" >&2
    echo "" >&2
    echo "   To update checksum for new version:" >&2
    echo "   1. Visit https://github.com/nektos/act/releases/tag/v${ACT_VERSION}" >&2
    echo "   2. Download act_${PLATFORM}_${ARCH}.tar.gz" >&2
    echo "   3. Run: sha256sum act_${PLATFORM}_${ARCH}.tar.gz" >&2
    echo "   4. Update EXPECTED_CHECKSUM in this script" >&2
    exit 1
fi

echo "✅ Checksum verified"

# Extract binary
echo "📂 Extracting..."
tar -xzf "${TEMP_DIR}/act.tar.gz" -C "$TEMP_DIR"

# Install to target directory
mkdir -p "$INSTALL_DIR"
install -m 0755 "${TEMP_DIR}/act" "${INSTALL_DIR}/act"

# Verify installation
if ! "${INSTALL_DIR}/act" --version >/dev/null 2>&1; then
    echo "❌ Installation verification failed" >&2
    exit 1
fi

INSTALLED_VERSION="$("${INSTALL_DIR}/act" --version | head -n1)"
echo "✅ Successfully installed: $INSTALLED_VERSION"
echo "   Location: ${INSTALL_DIR}/act"
echo ""
echo "💡 Make sure ${INSTALL_DIR} is in your PATH:"
echo "   export PATH=\"${INSTALL_DIR}:\$PATH\""

# Check if already in PATH
if echo "$PATH" | grep -q "${INSTALL_DIR}"; then
    echo "✅ ${INSTALL_DIR} is already in PATH"
else
    echo "⚠️  ${INSTALL_DIR} is NOT in PATH"
    echo "   Add to ~/.bashrc:"
    echo "   echo 'export PATH=\"${INSTALL_DIR}:\$PATH\"' >> ~/.bashrc"
fi
