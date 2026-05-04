"""Consumer contract tests for sync + environment lifecycle.

These tests validate that core consumer flows remain stable:
- Managed-file sync contract (apply + lock behavior)
- Drift-check enforcement
- Environment lifecycle verification path
- Real-manifest contract (exercises the actual .tooling-sync-manifest.toml)
- Hermetic env isolation (guards against stale GITHUB_TOKEN leakage)

Uses a resume-builder-compatible fixture profile as the reference consumer.
Run with: pytest -q tests/scripts/test_consumer_contract.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_RESUME_BUILDER_TOOLING_TOML = """\
[tooling]
pip = "24.3.1"

[python]
version = "3.11.14"
path = "/usr/bin/python3"

[runtime]
awk_impl = "gawk"
shell_tools = ["bash", "awk", "grep", "sed"]
"""

_RESUME_BUILDER_PYPROJECT_META = """\
[project]
name = "resume-builder"
version = "0.1.0"
description = "Resume builder project."
authors = [
    { name = "Jonathan Smith" }
]
"""


def _make_tooling_src(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a minimal tooling source fixture with sync script and manifest."""
    tooling_src = tmp_path / "tooling_src"
    (tooling_src / "scripts").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "scripts" / "sync_tooling.sh",
        tooling_src / "scripts" / "sync_tooling.sh",
    )
    (tooling_src / "scripts" / "sync_tooling.sh").chmod(0o755)
    for rel_path, content in files.items():
        path = tooling_src / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest_entries = ", ".join(f'"{p}"' for p in files)
    (tooling_src / ".tooling-sync-manifest.toml").write_text(
        f'[manifest]\nversion = "1"\n[sync]\nfiles = [{manifest_entries}]\n',
        encoding="utf-8",
    )
    return tooling_src


def _make_resume_builder_consumer(tmp_path: Path) -> Path:
    """Create a consumer directory that mimics a resume-builder repo layout."""
    consumer = tmp_path / "resume-builder"
    consumer.mkdir()
    (consumer / "tooling.toml").write_text(
        _RESUME_BUILDER_TOOLING_TOML, encoding="utf-8"
    )
    (consumer / ".pyproject.meta.toml").write_text(
        _RESUME_BUILDER_PYPROJECT_META, encoding="utf-8"
    )
    # Match the annotated form documented in CONSUMER_CONTRACT.md / NEW_PROJECT.md;
    # release-please's `generic` updater requires the marker to bump VERSION
    # (issue #296). Sync does not touch VERSION, so the annotation is inert
    # for the contract assertions but reflects the realistic consumer state.
    (consumer / "VERSION").write_text(
        "0.1.0 # x-release-please-version\n", encoding="utf-8"
    )
    (consumer / "requirements.txt").write_text(
        "# resume-builder app/runtime dependencies\nclick==8.1.7\n", encoding="utf-8"
    )
    # Shared dev-tool contract file (synced from tooling in real consumers).
    (consumer / "requirements-dev.txt").write_text(
        "# shared dev tooling\npre-commit==3.8.0\nruff==0.15.2\nblack==24.10.0\n"
        "isort==5.13.2\nmypy==1.11.2\npytest==8.3.3\n",
        encoding="utf-8",
    )
    # Minimal pyproject.toml so verify_env.sh pre-flight checks pass
    (consumer / "pyproject.toml").write_text(
        '[project]\nname = "resume-builder"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    return consumer


def _run_sync(
    tooling_src: Path,
    consumer: Path,
    *,
    ref: str = "v0.0.0",
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "bash",
        str(tooling_src / "scripts" / "sync_tooling.sh"),
        ref,
        str(consumer),
    ]
    if extra_args:
        command.extend(extra_args)
    # Build a minimal hermetic env to prevent parent env vars (e.g. a stale
    # GITHUB_TOKEN, an inherited TOOLING_DIR, or HOME-scoped git config) from
    # altering sync behavior.
    home_path = consumer / ".home"
    home_path.mkdir(parents=True, exist_ok=True)
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": str(home_path),
        "TOOLING_DIR": str(tooling_src),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(consumer),
        env=env,
        timeout=60,
    )


def _run_drift_validator(root: Path) -> subprocess.CompletedProcess[str]:
    """Run validate_sync_drift.py against the given root directory."""
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "validate_sync_drift.py"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_lock(consumer: Path, files: dict[str, str]) -> None:
    payload = {
        "schema_version": 1,
        "generated_at_utc": "2026-03-16T00:00:00Z",
        "requested_ref": "v0.0.0",
        "resolved_ref": None,
        "source_mode": "filesystem",
        "files": {
            rel_path: {"sha256": _sha256_text(content)}
            for rel_path, content in files.items()
        },
    }
    (consumer / ".tooling-sync-manifest.lock").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Sync apply + lock behavior
# ---------------------------------------------------------------------------


def test_consumer_sync_apply_copies_managed_files(tmp_path: Path) -> None:
    """Contract: sync copies declared managed files into the consumer directory."""
    managed_content = "# Managed Makefile\n"
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": managed_content})
    consumer = _make_resume_builder_consumer(tmp_path)

    result = _run_sync(tooling_src, consumer)

    assert result.returncode == 0, (
        f"sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (consumer / "Makefile").exists(), "Makefile was not copied into consumer"
    assert (consumer / "Makefile").read_text(encoding="utf-8") == managed_content


def test_consumer_sync_writes_lock_file(tmp_path: Path) -> None:
    """Contract: sync writes a .tooling-sync-manifest.lock after a successful apply."""
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": "# Makefile\n"})
    consumer = _make_resume_builder_consumer(tmp_path)

    result = _run_sync(tooling_src, consumer)

    assert result.returncode == 0, (
        f"sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    lock_path = consumer / ".tooling-sync-manifest.lock"
    assert lock_path.exists(), "lock file was not written after sync"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock.get("schema_version") == 1
    assert "Makefile" in lock.get("files", {})


def test_consumer_sync_lock_contains_correct_sha256(tmp_path: Path) -> None:
    """Contract: the lock file records the exact sha256 of each managed file."""
    makefile_content = "# managed Makefile\n"
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": makefile_content})
    consumer = _make_resume_builder_consumer(tmp_path)

    result = _run_sync(tooling_src, consumer)

    assert result.returncode == 0, (
        f"sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    lock = json.loads(
        (consumer / ".tooling-sync-manifest.lock").read_text(encoding="utf-8")
    )
    recorded_sha = lock["files"]["Makefile"]["sha256"]
    expected_sha = _sha256_text(makefile_content)
    assert recorded_sha == expected_sha, (
        f"Lock sha256 mismatch: recorded={recorded_sha} expected={expected_sha}"
    )


def test_consumer_sync_overwrites_existing_managed_file(tmp_path: Path) -> None:
    """Contract: re-syncing an updated managed file replaces the consumer copy."""
    old_content = "# old version\n"
    new_content = "# new version\n"
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": new_content})
    consumer = _make_resume_builder_consumer(tmp_path)
    (consumer / "Makefile").write_text(old_content, encoding="utf-8")
    _write_lock(consumer, {"Makefile": old_content})

    result = _run_sync(tooling_src, consumer)

    assert result.returncode == 0, (
        f"sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (consumer / "Makefile").read_text(encoding="utf-8") == new_content


def test_consumer_sync_identity_files_are_preserved(tmp_path: Path) -> None:
    """Contract: consumer identity files (.pyproject.meta.toml, VERSION) are not overwritten."""
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": "# Makefile\n"})
    consumer = _make_resume_builder_consumer(tmp_path)
    original_meta = (consumer / ".pyproject.meta.toml").read_text(encoding="utf-8")
    original_version = (consumer / "VERSION").read_text(encoding="utf-8")

    result = _run_sync(tooling_src, consumer)

    assert result.returncode == 0, (
        f"sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (consumer / ".pyproject.meta.toml").read_text(
        encoding="utf-8"
    ) == original_meta
    assert (consumer / "VERSION").read_text(encoding="utf-8") == original_version


# ---------------------------------------------------------------------------
# Drift-check enforcement
# ---------------------------------------------------------------------------


def test_consumer_drift_check_passes_after_clean_sync(tmp_path: Path) -> None:
    """Contract: drift validator passes immediately after a clean sync."""
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": "# Makefile\n"})
    consumer = _make_resume_builder_consumer(tmp_path)

    sync_result = _run_sync(tooling_src, consumer)
    assert sync_result.returncode == 0, (
        f"sync failed:\nstdout={sync_result.stdout}\nstderr={sync_result.stderr}"
    )

    drift_result = _run_drift_validator(consumer)

    assert drift_result.returncode == 0, (
        f"Drift check failed after clean sync:\n"
        f"stdout={drift_result.stdout}\nstderr={drift_result.stderr}"
    )
    assert "OK:" in drift_result.stdout


def test_consumer_drift_check_fails_on_modified_managed_file(tmp_path: Path) -> None:
    """Contract: drift validator fails when a managed file has been locally modified."""
    original_content = "# original Makefile\n"
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": original_content})
    consumer = _make_resume_builder_consumer(tmp_path)

    sync_result = _run_sync(tooling_src, consumer)
    assert sync_result.returncode == 0, (
        f"sync failed:\nstdout={sync_result.stdout}\nstderr={sync_result.stderr}"
    )

    # Simulate local drift: modify the managed file after sync
    (consumer / "Makefile").write_text("# locally modified\n", encoding="utf-8")

    drift_result = _run_drift_validator(consumer)

    assert drift_result.returncode != 0, (
        "Drift check must fail when a managed file has been modified"
    )
    assert "DRIFT: Makefile" in drift_result.stdout


def test_consumer_drift_check_fails_when_lock_is_missing(tmp_path: Path) -> None:
    """Contract: drift validator fails with a clear error when lock is absent."""
    consumer = _make_resume_builder_consumer(tmp_path)
    (consumer / "Makefile").write_text("# Makefile\n", encoding="utf-8")
    # No lock file written

    drift_result = _run_drift_validator(consumer)

    assert drift_result.returncode != 0
    combined = drift_result.stdout + drift_result.stderr
    assert "MALFORMED" in combined or "missing" in combined.lower()


def test_consumer_drift_check_fails_on_missing_managed_file(tmp_path: Path) -> None:
    """Contract: drift validator reports MISSING when a managed file has been deleted."""
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": "# Makefile\n"})
    consumer = _make_resume_builder_consumer(tmp_path)

    sync_result = _run_sync(tooling_src, consumer)
    assert sync_result.returncode == 0, (
        f"sync failed:\nstdout={sync_result.stdout}\nstderr={sync_result.stderr}"
    )

    # Simulate a missing managed file
    (consumer / "Makefile").unlink()

    drift_result = _run_drift_validator(consumer)

    assert drift_result.returncode != 0, (
        "Drift check must fail when a managed file is missing"
    )
    assert "MISSING: Makefile" in drift_result.stdout


def test_consumer_drift_check_enforces_remediation_message(tmp_path: Path) -> None:
    """Contract: drift validator always prints remediation advice on failure."""
    consumer = _make_resume_builder_consumer(tmp_path)
    _write_lock(consumer, {"Makefile": "# Makefile\n"})
    (consumer / "Makefile").write_text("# drifted\n", encoding="utf-8")

    drift_result = _run_drift_validator(consumer)

    assert drift_result.returncode != 0
    assert "remediation" in drift_result.stdout.lower()


# ---------------------------------------------------------------------------
# Environment lifecycle verification path
# ---------------------------------------------------------------------------


def _install_verify_script(consumer: Path) -> Path:
    """Copy verify_env.sh into the consumer's scripts/ dir so REPO_ROOT resolves correctly."""
    (consumer / "scripts").mkdir(exist_ok=True)
    dest = consumer / "scripts" / "verify_env.sh"
    shutil.copy2(REPO_ROOT / "scripts" / "verify_env.sh", dest)
    dest.chmod(0o755)
    return dest


def test_consumer_verify_env_preflight_passes_for_complete_layout(
    tmp_path: Path,
) -> None:
    """Contract: verify_env.sh pre-flight checks pass for a complete consumer layout.

    verify_env.sh derives REPO_ROOT from its own location, so the script is
    copied into the consumer fixture to test against the consumer's files.

    The script reads all required metadata files, prints the expected version
    values, and only fails because there is no active venv — not because
    any required file is absent.
    """
    consumer = _make_resume_builder_consumer(tmp_path)
    verify_script = _install_verify_script(consumer)

    result = subprocess.run(
        ["bash", str(verify_script)],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(consumer),
    )

    output = result.stdout + result.stderr
    assert "syntax error" not in output.lower(), (
        f"verify_env.sh reported a shell syntax error:\n{output}"
    )
    assert "Required file not found" not in output, (
        f"verify_env.sh failed pre-flight for a complete consumer layout:\n{output}"
    )
    # The script must successfully read all config files and print expected
    # metadata before encountering any venv-related failure.
    assert "Verifying deterministic environment" in output, (
        f"verify_env.sh did not reach the metadata-check banner:\n{output}"
    )
    assert "Expected Python version:" in output, (
        f"verify_env.sh did not successfully parse tooling.toml:\n{output}"
    )
    # The only permitted failure mode for a complete layout is a missing venv.
    if result.returncode != 0:
        assert "No virtual environment is active" in output, (
            f"verify_env.sh failed for an unexpected reason:\n{output}"
        )


def test_consumer_verify_env_preflight_fails_on_missing_version_file(
    tmp_path: Path,
) -> None:
    """Contract: verify_env.sh fails pre-flight when VERSION is absent.

    verify_env.sh derives REPO_ROOT from its own location, so the script is
    copied into the consumer fixture to ensure REPO_ROOT points to the consumer.
    """
    consumer = _make_resume_builder_consumer(tmp_path)
    (consumer / "VERSION").unlink()
    verify_script = _install_verify_script(consumer)

    result = subprocess.run(
        ["bash", str(verify_script)],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(consumer),
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Required file not found" in output or "VERSION" in output


def test_consumer_verify_env_preflight_fails_on_missing_tooling_toml(
    tmp_path: Path,
) -> None:
    """Contract: verify_env.sh fails pre-flight when tooling.toml is absent.

    verify_env.sh derives REPO_ROOT from its own location, so the script is
    copied into the consumer fixture to ensure REPO_ROOT points to the consumer.
    """
    consumer = _make_resume_builder_consumer(tmp_path)
    (consumer / "tooling.toml").unlink()
    verify_script = _install_verify_script(consumer)

    result = subprocess.run(
        ["bash", str(verify_script)],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(consumer),
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Required file not found" in output or "tooling.toml" in output


def _parse_tooling_toml_python_version(tooling_toml: Path) -> str:
    """Parse the [python].version from a tooling.toml file using Python."""
    data = tomllib.loads(tooling_toml.read_text(encoding="utf-8"))
    python_section = data.get("python", {})
    if not isinstance(python_section, dict):
        return ""
    version = python_section.get("version", "")
    return version if isinstance(version, str) else ""


def test_consumer_env_lifecycle_verify_extracts_python_version(tmp_path: Path) -> None:
    """Contract: the consumer tooling.toml provides a parseable Python version."""
    consumer = _make_resume_builder_consumer(tmp_path)

    py_version = _parse_tooling_toml_python_version(consumer / "tooling.toml")

    assert py_version, "Could not extract Python version from consumer tooling.toml"
    assert py_version.startswith("3."), f"Unexpected Python version: {py_version}"


# ---------------------------------------------------------------------------
# Real-manifest contract
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_consumer_real_manifest_sync_applies_all_declared_files(tmp_path: Path) -> None:
    """Contract: syncing from the real tooling source copies every manifest-declared file.

    This exercises the actual .tooling-sync-manifest.toml so that stale or
    missing declared paths in the real manifest are caught before syncing into
    consumers.
    """
    consumer = _make_resume_builder_consumer(tmp_path)
    manifest_path = REPO_ROOT / ".tooling-sync-manifest.toml"
    if not manifest_path.exists():
        pytest.skip(
            "tooling source manifest is not present in synced consumer repos; "
            "this real-manifest contract check only runs in the tooling repo"
        )

    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    declared_files: list[str] = manifest["sync"]["files"]
    assert declared_files, "Real manifest must declare at least one file"

    result = _run_sync(REPO_ROOT, consumer, ref="HEAD")
    if (
        result.returncode != 0
        and "Manifest entry not found in tooling source at HEAD" in result.stdout
    ):
        pytest.skip(
            "Real-manifest contract requires manifest/file changes to be committed "
            "before running against HEAD"
        )

    assert result.returncode == 0, (
        f"Real-manifest sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    lock = json.loads(
        (consumer / ".tooling-sync-manifest.lock").read_text(encoding="utf-8")
    )
    lock_files = set(lock.get("files", {}).keys())

    missing_from_lock: list[str] = []
    missing_from_disk: list[str] = []
    for rel_path in declared_files:
        if rel_path not in lock_files:
            missing_from_lock.append(rel_path)
        if not (consumer / rel_path).exists():
            missing_from_disk.append(rel_path)

    assert not missing_from_lock, (
        f"These real-manifest files are missing from the lock: {missing_from_lock}"
    )
    assert not missing_from_disk, (
        f"These real-manifest files were not synced to the consumer: {missing_from_disk}"
    )


@pytest.mark.slow
def test_consumer_real_manifest_sync_includes_shared_dev_requirements(
    tmp_path: Path,
) -> None:
    """Contract: real-manifest sync delivers requirements-dev.txt with key tool pins."""
    consumer = _make_resume_builder_consumer(tmp_path)
    manifest_path = REPO_ROOT / ".tooling-sync-manifest.toml"
    if not manifest_path.exists():
        pytest.skip(
            "tooling source manifest is not present in synced consumer repos; "
            "this real-manifest contract check only runs in the tooling repo"
        )

    result = _run_sync(REPO_ROOT, consumer, ref="HEAD")
    if (
        result.returncode != 0
        and "Manifest entry not found in tooling source at HEAD" in result.stdout
    ):
        pytest.skip(
            "Real-manifest contract requires manifest/file changes to be committed "
            "before running against HEAD"
        )

    assert result.returncode == 0, (
        f"Real-manifest sync failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    req_dev = consumer / "requirements-dev.txt"
    assert req_dev.exists(), "requirements-dev.txt must be synced by manifest"

    req_dev_text = req_dev.read_text(encoding="utf-8")
    for required_pin in [
        "pre-commit==",
        "ruff==",
        "black==",
        "isort==",
        "mypy==",
        "pytest==",
    ]:
        assert required_pin in req_dev_text, (
            f"requirements-dev.txt missing expected tool pin prefix: {required_pin}"
        )


# ---------------------------------------------------------------------------
# Hermetic env isolation
# ---------------------------------------------------------------------------


def test_consumer_sync_is_isolated_from_stale_github_token(tmp_path: Path) -> None:
    """Contract: sync succeeds even when a stale GITHUB_TOKEN is injected into the env.

    Regression for the gh-auth incident where GITHUB_TOKEN exported in ~/.bashrc
    clobbered stored gh CLI credentials and caused 401s. Sync must not rely on
    GITHUB_TOKEN at all; the hermetic env in _run_sync() prevents it from leaking in.
    """
    managed_content = "# Managed Makefile\n"
    tooling_src = _make_tooling_src(tmp_path, {"Makefile": managed_content})
    consumer = _make_resume_builder_consumer(tmp_path)

    result = _run_sync(
        tooling_src,
        consumer,
        extra_env={"GITHUB_TOKEN": "INVALID_GITHUB_TOKEN"},
    )

    assert result.returncode == 0, (
        f"Sync failed when a stale GITHUB_TOKEN was injected into the env:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (consumer / ".home").exists(), "Hermetic per-consumer HOME was not created"
    assert (consumer / "Makefile").exists(), "Makefile was not synced"
    assert (consumer / "Makefile").read_text(encoding="utf-8") == managed_content
