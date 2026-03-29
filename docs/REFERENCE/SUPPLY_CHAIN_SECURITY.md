# Supply Chain Security - act Installation

## Overview

This document explains the security measures implemented for installing `act` (GitHub Actions local runner) to prevent supply-chain attacks.

## Threat Model

### Attack Vectors

**Without verification (INSECURE):**
```bash
# ❌ NEVER DO THIS
curl -fsSL https://example.com/install.sh | bash
```

**Risks:**
1. **Compromised repository:** Attacker gains write access to nektos/act
2. **Compromised DNS:** Attacker redirects raw.githubusercontent.com
3. **MITM attack:** Network attacker intercepts download
4. **Mutable 'master' branch:** Script changes without notice

**Impact if exploited:**
- Arbitrary code execution with developer privileges
- Credential theft (SSH keys, GitHub tokens, AWS credentials)
- Code modification in checked-out repositories
- Lateral movement to other systems

### Enterprise-Scale Relevance

At large organizations (tech, finance, healthcare, government):
- Thousands of developers running build tools
- Access to sensitive IP and business-critical code
- Compliance requirements (SOC2, ISO 27001, HIPAA, FedRAMP)
- Supply chain attacks target high-value companies

**Real-world examples:**
- SolarWinds (2020): Build tool compromise → 18,000 customers affected
- CodeCov (2021): Bash uploader script tampered → CI secrets stolen
- npm colors/faker (2022): Maintainer account compromised → malicious release

## Secure Installation Approach

### Implementation: `scripts/install_act.sh`

**Security measures:**

1. **Version pinning:**
   ```bash
   ACT_VERSION="0.2.84"  # Immutable - doesn't change
   ```

2. **Immutable URL (GitHub releases, not master):**
   ```bash
   # Points to tagged release, not mutable branch
   DOWNLOAD_URL="https://github.com/nektos/act/releases/download/v${ACT_VERSION}/..."
   ```

3. **Checksum verification:**
   ```bash
   # pragma: allowlist secret
   EXPECTED_CHECKSUM="1f4dd2ad76c6f8a6c63abccbc2e8bc0dbbb0c8b7596c1c3ccae2c0c7a6cd9e3e"
   ACTUAL_CHECKSUM="$(sha256sum "${TEMP_DIR}/act.tar.gz" | awk '{print $1}')"

   if [ "$ACTUAL_CHECKSUM" != "$EXPECTED_CHECKSUM" ]; then
       echo "❌ Checksum verification failed!" >&2
       exit 1
   fi
   ```

4. **Binary extraction (not script execution):**
   ```bash
   # Extract pre-compiled binary, don't execute remote script
   tar -xzf "${TEMP_DIR}/act.tar.gz" -C "$TEMP_DIR"
   install -m 0755 "${TEMP_DIR}/act" "${INSTALL_DIR}/act"
   ```

5. **Post-install verification:**
   ```bash
   if ! "${INSTALL_DIR}/act" --version >/dev/null 2>&1; then
       echo "❌ Installation verification failed" >&2
       exit 1
   fi
   ```

## Usage

### Install act

```bash
make install-act
```

**What happens:**
1. Downloads act v0.2.84 from GitHub releases (immutable)
2. Verifies SHA256 checksum matches expected value
3. Extracts binary to `~/.local/bin/act`
4. Verifies installation with `act --version`

### Update to Newer Version

**Process:**

1. **Check for new release:**
   ```bash
   # Visit: https://github.com/nektos/act/releases
   # Find latest stable version (e.g., v0.2.85)
   ```

2. **Download and verify checksum:**
   ```bash
   VERSION="0.2.85"
   curl -fsSL -o act.tar.gz \
     "https://github.com/nektos/act/releases/download/v${VERSION}/act_Linux_x86_64.tar.gz"
   sha256sum act.tar.gz
   ```

3. **Update script:**
   ```bash
   # Edit scripts/install_act.sh
   ACT_VERSION="0.2.85"  # Update version
   EXPECTED_CHECKSUM="<paste sha256sum output>"  # Update checksum
   ```

4. **Test installation:**
   ```bash
   make install-act
   act --version  # Should show v0.2.85
   ```

5. **Commit changes:**
   ```bash
   git add scripts/install_act.sh
   git commit -m "chore: Update act to v0.2.85 with verified checksum"
   ```

## Comparison: Before vs After

| Aspect | Before (INSECURE) | After (SECURE) |
|--------|-------------------|----------------|
| **URL** | `master` branch (mutable) | `v0.2.84` tag (immutable) |
| **Verification** | None | SHA256 checksum |
| **Execution** | Pipe remote script to bash | Extract pre-built binary |
| **Version** | Unknown (latest) | Pinned (0.2.84) |
| **Attack surface** | Arbitrary code execution | Binary only |
| **Failure mode** | Silent (may run malicious code) | Loud (checksum mismatch fails) |

## Alternative Approaches Considered

### 1. GPG Signature Verification (Even More Secure)

```bash
# Download release + signature
curl -fsSL -o act.tar.gz "$DOWNLOAD_URL"
curl -fsSL -o act.tar.gz.sig "${DOWNLOAD_URL}.sig"

# Import nektos/act public key
gpg --import nektos-act-key.asc

# Verify signature
gpg --verify act.tar.gz.sig act.tar.gz
```

**Pros:** Cryptographic proof of authenticity
**Cons:** nektos/act doesn't publish GPG signatures (as of 2026-02-18)

**Future:** If act starts signing releases, switch to this approach.

### 2. Build from Source

```bash
git clone https://github.com/nektos/act.git
cd act
git checkout v0.2.84
git verify-tag v0.2.84  # If signed
make build
```

**Pros:** Full control over build process
**Cons:** Requires Go toolchain, slower, more complex

**Use case:** High-security environments where pre-built binaries are prohibited.

### 3. Use Package Manager

```bash
# Debian/Ubuntu (if available)
apt install act

# Homebrew (macOS/Linux)
brew install act
```

**Pros:** System package manager verifies signatures
**Cons:** Often outdated, not available on all systems

**Current status:** Not available in apt repositories (2026-02-18)

## AMD Interview Talking Points

**When asked about supply chain security:**

✅ **Threat modeling:**
- "Identified supply-chain risk in act installation: remote script execution without verification"
- "Modeled attack vectors: compromised repo, DNS hijacking, MITM, mutable branch"

✅ **Mitigation implementation:**
- "Replaced curl-pipe-to-bash with checksum-verified binary installation"
- "Pinned to specific release tag (immutable) instead of master branch"
- "Binary extraction only - no remote script execution"

✅ **Process improvements:**
- "Documented update procedure with checksum verification steps"
- "Post-install verification ensures binary integrity"
- "Clear failure messages guide investigation of checksum mismatches"

✅ **Industry context:**
- "Similar approach to how AMD would distribute firmware update tools"
- "Prevents SolarWinds-style build tool compromises"
- "Compliance-friendly (SOC2, ISO 27001 require supply chain controls)"

**When asked about security trade-offs:**

✅ **Usability vs Security:**
- "Chose checksum verification over GPG (act doesn't publish signatures)"
- "Automated in Makefile - one command for secure install"
- "Clear update documentation - security doesn't slow down developers"

✅ **Maintenance:**
- "Manual checksum updates on new versions (intentional - forces review)"
- "Could automate if act publishes checksums.txt in releases"
- "Trade-off: convenience vs. preventing automated attacks"

## Related Documentation

- **AMD Tasks:** `AMD_SCALE_TASKS.md` (supply chain security section)
- **Installation Guide:** `CONTRIBUTING.md` (act installation)
- **Security Policy:** `.github/SECURITY.md` (if exists)

## References

- **SLSA (Supply-chain Levels for Software Artifacts):** [https://slsa.dev/](https://slsa.dev/)
- **NIST Secure Software Development Framework:** [https://csrc.nist.gov/Projects/ssdf](https://csrc.nist.gov/Projects/ssdf)
- **CIS Software Supply Chain Security Guide:** [https://www.cisecurity.org/insights/white-papers/cis-software-supply-chain-security-guide](https://www.cisecurity.org/insights/white-papers/cis-software-supply-chain-security-guide)

## Change Log

### 2026-02-18: Initial Secure Implementation
- **Changed:** `make install-act` from curl-pipe-to-bash to checksum-verified binary
- **Added:** `scripts/install_act.sh` with SHA256 verification
- **Reason:** Mitigate supply-chain attack risk (GitHub Copilot security review)
- **Impact:** No behavior change for users, significantly improved security posture
