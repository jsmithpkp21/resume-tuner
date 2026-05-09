#!/usr/bin/env python3
"""Tests for Release Please workflow configuration.

Tests verify that the Release Please workflow is properly configured to:
- Trigger on pushes to main branch
- Use correct action version and settings
- Configure semantic versioning for Python projects
- Use correct package name from pyproject.toml (via config file)

These tests validate that the workflow will work correctly when synced to
any repository that uses it.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

# Resolve repository root from this test file's location
# tests/workflows/test_release_please.py -> repo root is 3 levels up
REPO_ROOT: Path = Path(__file__).parent.parent.parent.resolve()

# Workflow file path
RELEASE_PLEASE_WORKFLOW: Path = (
    REPO_ROOT / ".github" / "workflows" / "release-please.yml"
)


def test_release_please_workflow_exists() -> None:
    """Verify release-please.yml workflow file exists."""
    assert RELEASE_PLEASE_WORKFLOW.exists(), (
        f"Release Please workflow not found at {RELEASE_PLEASE_WORKFLOW}"
    )


def test_release_please_workflow_valid_yaml() -> None:
    """Verify release-please.yml is valid YAML."""
    with open(RELEASE_PLEASE_WORKFLOW, encoding="utf-8") as f:
        content: str = f.read()

    try:
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise AssertionError(f"Invalid YAML in release-please.yml: {e}") from e


def test_release_please_workflow_has_required_fields() -> None:
    """Verify workflow has required top-level fields."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    required_fields: list[str] = ["name", "on", "jobs"]
    for field in required_fields:
        if field == "on":
            assert _get_on_config(workflow), "Missing required field: on"
            continue
        assert field in workflow, f"Missing required field: {field}"

    assert workflow["name"] == "release-please", (
        f"Unexpected workflow name: {workflow['name']}"
    )


def _get_on_config(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the workflow 'on' configuration, handling YAML boolean parsing.

    PyYAML parses the key "on" as boolean True unless quoted in the YAML file.
    This helper normalizes access for tests.
    """
    raw_workflow: dict[Any, Any] = cast(dict[Any, Any], workflow)
    if "on" in raw_workflow and isinstance(raw_workflow["on"], dict):
        return cast(dict[str, Any], raw_workflow["on"])
    if True in raw_workflow and isinstance(raw_workflow[True], dict):
        return cast(dict[str, Any], raw_workflow[True])
    return {}


def _get_release_step(workflow: dict[str, Any]) -> dict[str, Any]:
    """Extract the release-please-action step from workflow.

    Args:
        workflow: Parsed workflow YAML as dict.

    Returns:
        The release-please-action step configuration.

    Raises:
        AssertionError: If step is not found.
    """
    release_job: dict[str, Any] = workflow["jobs"]["release"]
    steps: list[dict[str, Any]] = release_job["steps"]

    release_step: dict[str, Any] | None = None
    for step in steps:
        if "release-please-action" in step.get("uses", ""):
            release_step = step
            break

    assert release_step is not None, "Release Please action step not found"
    return release_step


def test_release_please_triggers_on_main() -> None:
    """Verify workflow triggers on push to main branch."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    on_config: dict[str, Any] = _get_on_config(workflow)
    assert "push" in on_config, "Workflow should trigger on push events"

    push_config: dict[str, Any] = on_config["push"]
    assert "branches" in push_config, "Push trigger should specify branches"

    branches: list[str] = push_config["branches"]
    assert "main" in branches, "Workflow should trigger on main branch"


def test_release_please_job_exists() -> None:
    """Verify release job is defined."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    jobs: dict[str, Any] = workflow.get("jobs", {})
    assert "release" in jobs, "Release job not found in workflow"


def test_release_please_job_configuration() -> None:
    """Verify release job has correct configuration."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    release_job: dict[str, Any] = workflow["jobs"]["release"]

    # Check runner is ubuntu-based (allows ubuntu-latest, ubuntu-24.04, etc.)
    runner: str = release_job.get("runs-on", "")
    assert runner.startswith("ubuntu"), (
        f"Release job should run on ubuntu runner, got: {runner}"
    )

    # Check steps exist
    assert "steps" in release_job, "Release job should have steps"
    assert len(release_job["steps"]) > 0, "Release job should have at least one step"


def test_release_please_action_version() -> None:
    """Verify Release Please action name and ref are correctly configured.

    The ref must be a strict semver tag pin with major version 4 (vX.Y.Z).
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    release_step: dict[str, Any] = _get_release_step(workflow)
    uses_value: str = cast(str, release_step.get("uses", ""))
    assert uses_value, "Release Please action step should define 'uses'"

    if "@" in uses_value:
        action_name, ref = uses_value.split("@", 1)
    else:
        action_name, ref = uses_value, ""

    assert action_name.endswith("release-please-action"), (
        f"Expected release-please-action, got: {action_name}"
    )

    assert re.fullmatch(r"v4\.\d+\.\d+", ref), (
        "Release Please action must use a strict semver tag pin with major version "
        f"4 (vX.Y.Z), got ref: {ref!r}"
    )


def test_release_please_action_inputs() -> None:
    """Verify Release Please action has required input parameters."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    release_step: dict[str, Any] = _get_release_step(workflow)
    assert "with" in release_step, "Action should have input parameters"

    with_params: dict[str, Any] = release_step.get("with", {})

    # release-type must NOT appear in the workflow with-block when config-file
    # is used — it silently disables extra-files and changelog-path from config.
    required_params: list[str] = ["token", "config-file"]
    for param in required_params:
        assert param in with_params, f"Missing required parameter: {param}"


def test_release_type_not_in_workflow_with_params() -> None:
    """release-type must be absent from the action with-block when config-file is used.

    Including release-type alongside config-file causes release-please-action@v4
    to bypass extra-files and changelog-path from the config, so VERSION and
    .pyproject.meta.toml are never updated. release-type belongs in the config only.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    release_step: dict[str, Any] = _get_release_step(workflow)
    with_params: dict[str, Any] = release_step.get("with", {})

    assert "config-file" in with_params, (
        "Action must use config-file so extra-files and changelog-path are respected"
    )
    assert "release-type" not in with_params, (
        "release-type must not appear in the workflow with-block when config-file is "
        "present. It silently disables extra-files and changelog-path, causing "
        "VERSION and .pyproject.meta.toml to drift after every release. "
        "Set release-type only inside .release-please-config.json."
    )


def test_release_type_defined_in_config_file() -> None:
    """release-type must be set to python inside the config file (not the workflow)."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)
    assert config.get("release-type") == "python", (
        "release-type must be 'python' in .release-please-config.json"
    )


def test_release_please_package_name_in_config() -> None:
    """Verify package-name in .release-please-config.json matches pyproject.toml."""
    # Read package name from config file
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    assert config_path.exists(), ".release-please-config.json not found"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)
    packages: dict[str, Any] = config.get("packages", {})
    root_package: dict[str, Any] = packages.get(".", {})
    config_package_name: str = root_package.get("package-name", "")

    # Read package name from pyproject.toml or .pyproject.meta.toml (DRY system)
    pyproject_path: Path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found"
    with open(pyproject_path, "rb") as f:
        pyproject: dict[str, Any] = tomllib.load(f)

    expected_package_name: str = pyproject.get("project", {}).get("name", "")

    # If not in pyproject.toml, check .pyproject.meta.toml (DRY system)
    if not expected_package_name:
        meta_path: Path = REPO_ROOT / ".pyproject.meta.toml"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta: dict[str, Any] = tomllib.load(f)
            expected_package_name = meta.get("project", {}).get("name", "")

    assert expected_package_name, (
        "Package name not found in pyproject.toml or .pyproject.meta.toml"
    )

    assert config_package_name == expected_package_name, (
        f"Package name mismatch: config has '{config_package_name}', "
        f"pyproject.toml has '{expected_package_name}'"
    )


def test_release_please_uses_github_token() -> None:
    """Verify workflow uses GitHub token for authentication."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    release_step: dict[str, Any] = _get_release_step(workflow)
    with_params: dict[str, Any] = release_step.get("with", {})
    token: str = with_params.get("token", "")

    assert "GITHUB_TOKEN" in token, "Should use GITHUB_TOKEN for authentication"


def test_release_please_config_exists() -> None:
    """Verify Release Please config file exists."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    assert config_path.exists(), f"Release Please config not found at {config_path}"


def test_release_please_config_valid_json() -> None:
    """Verify .release-please-config.json is valid JSON."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        content: str = f.read()

    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Invalid JSON in .release-please-config.json: {e}") from e


def test_version_file_carries_release_please_annotation() -> None:
    # release-please's `generic` extra-files updater only rewrites lines that
    # contain the `x-release-please-version` annotation AND a semver token on
    # the same line. Assert both: a comment-only line like
    # `# x-release-please-version` would pass a substring check but ship a
    # release with no version literal for release-please to bump (issue #272).
    version_path: Path = REPO_ROOT / "VERSION"
    first_line = next(iter(version_path.read_text(encoding="utf-8").splitlines()), "")
    assert "x-release-please-version" in first_line, (
        "VERSION must carry the `x-release-please-version` annotation on the "
        "first line so release-please bumps it on every release. See "
        "issue #272."
    )
    version_token = first_line.split("#", 1)[0].strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.]+)?(?:\+[-\w.]+)?", version_token), (
        "VERSION first line must contain a semver-shaped token before the "
        f"annotation; got {version_token!r}. See issue #272."
    )


def test_release_please_config_updates_version_files() -> None:
    """Verify config includes all version-bearing files in extra-files."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    packages: dict[str, Any] = config.get("packages", {})
    root_package: dict[str, Any] = packages.get(".", {})
    extra_files: list[dict[str, Any]] = root_package.get("extra-files", [])

    expected_entries: dict[str, dict[str, str]] = {
        "VERSION": {"type": "generic"},
        ".pyproject.meta.toml": {
            "type": "toml",
            "jsonpath": "$.project.version",
        },
    }

    indexed_entries: dict[str, dict[str, Any]] = {
        str(entry.get("path", "")): entry for entry in extra_files if entry.get("path")
    }

    for file_name, expected in expected_entries.items():
        assert file_name in indexed_entries, (
            f"{file_name} not in extra-files. Release Please won't update it."
        )
        actual = indexed_entries[file_name]
        assert actual.get("type") == expected["type"], (
            f"{file_name} should use type {expected['type']}"
        )
        if "jsonpath" in expected:
            assert actual.get("jsonpath") == expected["jsonpath"], (
                f"{file_name} should use jsonpath {expected['jsonpath']}"
            )


def test_changelog_path_at_package_level() -> None:
    """changelog-path must be under packages['.'], not at the top-level config.

    A top-level changelog-path is silently ignored by release-please-action@v4
    when packages are defined; the action falls back to the default CHANGELOG.md.
    """
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    assert "changelog-path" not in config, (
        "changelog-path must not be at the top-level config — it is silently "
        "ignored there. Move it to packages['.'].changelog-path."
    )

    root_package: dict[str, Any] = config.get("packages", {}).get(".", {})
    changelog_path: str = root_package.get("changelog-path", "")
    assert changelog_path, (
        "packages['.'].changelog-path is not set. Release Please will default to "
        "CHANGELOG.md at the repo root instead of the configured path."
    )


def test_release_please_uses_canonical_root_changelog_path() -> None:
    """Release Please should write to the canonical root CHANGELOG.md."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    root_package: dict[str, Any] = config.get("packages", {}).get(".", {})
    assert root_package.get("changelog-path") == "CHANGELOG.md", (
        "packages['.'].changelog-path must be CHANGELOG.md to avoid stale "
        "docs/REFERENCE changelog overlap and keep release history canonical."
    )


def test_release_please_disables_component_tag_prefix_for_root_package() -> None:
    """Root package should publish canonical vX.Y.Z tags (no tooling- prefix)."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    root_package: dict[str, Any] = config.get("packages", {}).get(".", {})
    assert root_package.get("include-component-in-tag") is False, (
        "Root release-please package must set include-component-in-tag=false so "
        "tags stay in canonical vX.Y.Z format."
    )


def test_changelog_compare_links_do_not_use_tooling_tag_prefix() -> None:
    """Changelog compare links should use canonical v* tags, not tooling-v*."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    changelog_rel_path = config.get("packages", {}).get(".", {}).get("changelog-path")
    assert isinstance(changelog_rel_path, str) and changelog_rel_path, (
        "packages['.'].changelog-path must be configured for changelog validation"
    )

    changelog_path = REPO_ROOT / changelog_rel_path
    changelog_content = changelog_path.read_text(encoding="utf-8")
    assert "compare/tooling-v" not in changelog_content, (
        "Changelog contains tooling-v compare links; use canonical v* tags instead."
    )


def test_changelog_compare_links_are_not_inverted() -> None:
    """Changelog compare links must follow compare/v{prev}...v{current} order.

    An inverted link (e.g., v1.14.0...v1.10.3) results in an empty GitHub diff
    and indicates the changelog was generated with incorrect version metadata.
    """
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)

    changelog_rel_path = config.get("packages", {}).get(".", {}).get("changelog-path")
    assert isinstance(changelog_rel_path, str) and changelog_rel_path, (
        "packages['.'].changelog-path must be configured for changelog validation"
    )

    changelog_path = REPO_ROOT / changelog_rel_path
    changelog_content = changelog_path.read_text(encoding="utf-8")

    # Match all compare links of the form compare/vX.Y.Z...vA.B.C
    compare_pattern = re.compile(r"compare/v(\d+\.\d+\.\d+)\.\.\.v(\d+\.\d+\.\d+)")
    inverted: list[str] = []
    for match in compare_pattern.finditer(changelog_content):
        prev_str, curr_str = match.group(1), match.group(2)
        prev = tuple(int(x) for x in prev_str.split("."))
        curr = tuple(int(x) for x in curr_str.split("."))
        if prev >= curr:
            inverted.append(f"compare/v{prev_str}...v{curr_str}")

    assert not inverted, (
        "Changelog contains inverted compare links (prev >= current). "
        "Each link should go from the previous release tag to the current one. "
        f"Inverted links found: {inverted}"
    )


def test_changelog_latest_version_matches_manifest() -> None:
    """The first version heading in the changelog must match the release-please manifest."""
    config_path: Path = REPO_ROOT / ".release-please-config.json"
    manifest_path: Path = REPO_ROOT / ".release-please-manifest.json"

    with open(config_path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)
    with open(manifest_path, encoding="utf-8") as f:
        manifest: dict[str, Any] = json.load(f)

    changelog_rel_path = config.get("packages", {}).get(".", {}).get("changelog-path")
    assert isinstance(changelog_rel_path, str) and changelog_rel_path, (
        "packages['.'].changelog-path must be configured for changelog validation"
    )

    manifest_version: str = manifest.get(".", "")
    assert manifest_version, "Manifest must contain a version for '.'"

    changelog_path = REPO_ROOT / changelog_rel_path
    changelog_content = changelog_path.read_text(encoding="utf-8")

    # Find the first version heading line: ## [X.Y.Z](...)
    heading_pattern = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
    first_match = heading_pattern.search(changelog_content)
    assert first_match is not None, (
        "Changelog contains no version headings matching ## [X.Y.Z]"
    )

    changelog_latest = first_match.group(1)
    assert changelog_latest == manifest_version, (
        f"Changelog latest version ({changelog_latest}) does not match "
        f"release-please manifest version ({manifest_version}). "
        "Re-align the changelog header or update the manifest."
    )


def test_post_release_version_sync_step_exists() -> None:
    """Workflow must sync VERSION after release-please creates a release.

    release-please's generic extra-files updater silently skips VERSION, so
    every release leaves version metadata out of sync. This step fixes that by
    running --fix, staging all version files, and committing only if any
    version metadata actually drifted. The commit uses [skip ci] to avoid
    triggering another release cycle.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    steps: list[dict[str, Any]] = workflow["jobs"]["release"]["steps"]

    checkout_steps = [s for s in steps if s.get("name") == "Checkout code"]
    assert checkout_steps, "Workflow is missing 'Checkout code' step"
    checkout_with = checkout_steps[0].get("with", {})
    assert checkout_with.get("ref") == "${{ steps.release.outputs.sha }}", (
        "Checkout step must pin ref to the release commit SHA so sync runs on the "
        "released tree rather than a detached pre-release commit."
    )

    sync_steps = [s for s in steps if "validate_version_sync.py" in s.get("run", "")]
    assert sync_steps, (
        "Workflow is missing a post-release step that runs validate_version_sync.py. "
        "Without it, VERSION and .pyproject.meta.toml will drift after every release."
    )

    sync_step = sync_steps[0]
    assert "release_created" in sync_step.get("if", ""), (
        "Post-release sync step must be gated on steps.release.outputs.release_created"
    )
    run_script: str = sync_step.get("run", "")
    assert "validate_version_sync.py --root . --fix" in run_script, (
        "Post-release step must run validate_version_sync.py --fix to correct VERSION "
        "drift left by release-please's generic extra-files updater"
    )
    assert "[skip ci]" in run_script, (
        "Post-release VERSION commit must include [skip ci] to avoid triggering "
        "another release-please cycle"
    )
    assert "git diff --cached --quiet" in run_script, (
        "Post-release commit must be guarded on staged diff (all version files) "
        "not just VERSION, to avoid empty commits and catch unexpected drift"
    )


def test_post_release_sync_step_uses_pr_not_direct_push() -> None:
    """Sync step must open a follow-up PR rather than push directly to main.

    Direct pushes to main are blocked by branch protection rule GH013, which
    causes the sync step (and every downstream Docker/release-stable step in
    the same job) to fail. See issue #275.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    steps: list[dict[str, Any]] = workflow["jobs"]["release"]["steps"]

    sync_steps = [s for s in steps if "validate_version_sync.py" in s.get("run", "")]
    assert sync_steps, "Post-release sync step not found"
    run_script: str = sync_steps[0].get("run", "")

    assert "git push origin HEAD:main" not in run_script, (
        "Sync step must not push directly to main — branch protection rule GH013 "
        "rejects it and aborts the rest of the release job. Open a follow-up PR "
        "instead. See issue #275."
    )
    assert "gh pr create" in run_script, (
        "Sync step must open a follow-up PR with `gh pr create` so version-metadata "
        "drift can be merged through the normal review path. See issue #275."
    )
    assert "--base main" in run_script, (
        "The follow-up sync PR must target the main branch"
    )

    sync_env = sync_steps[0].get("env", {})
    assert "GH_TOKEN" in sync_env, (
        "Sync step must export GH_TOKEN so the gh CLI is authenticated"
    )

    # Under `set -euo pipefail`, a failed `git push` or `gh pr create` exits
    # before the manual `git switch --detach` runs, leaving HEAD on the
    # sync branch. Combined with continue-on-error: true, downstream steps
    # would then run from the wrong tree. The HEAD restore must be in an
    # EXIT trap so it is unconditional. See PR #278 review.
    #
    # Match a real `trap <handler> EXIT` directive, not bare keywords —
    # substring checks fire on comments or unrelated tokens and the test
    # would silently pass even if the trap were deleted.
    trap_pattern = re.compile(r"^\s*trap\s+\S.*\bEXIT\b", re.MULTILINE)
    assert trap_pattern.search(run_script), (
        "Sync step must install an EXIT trap (e.g. `trap restore_head EXIT`) so "
        "the HEAD restore runs unconditionally; otherwise an early exit under "
        "`set -e` skips the restore and downstream steps run with HEAD on the "
        "sync branch"
    )
    assert "git switch --detach" in run_script, (
        "EXIT trap must restore HEAD to the release SHA via `git switch --detach`"
    )

    # Re-runs must not leave the script wedged because the local branch,
    # remote branch, or PR already exists from a prior attempt. See PR #278
    # review (idempotency comment).
    assert "git switch -C" in run_script, (
        "Sync step must use `git switch -C` so a leftover local branch from a "
        "previous re-run is replaced rather than aborting the script"
    )
    assert "--force-with-lease" in run_script, (
        "Sync step must push with `--force-with-lease` so a leftover remote "
        "branch from a previous re-run is updated rather than failing as "
        "non-fast-forward"
    )
    assert "gh pr list" in run_script, (
        "Sync step must check for an existing PR via `gh pr list --head ... "
        "--state open` before calling `gh pr create`; this returns an empty "
        "JSON array (exit 0) for the not-found case so genuine auth/network "
        "failures remain distinguishable, unlike `gh pr view ... 2>&1` which "
        "silently swallows them"
    )

    # gh CLI failures are easiest to diagnose when the auth check is explicit.
    # AGENTS.md mandates `gh auth status` as a preflight before any `gh`
    # calls in scripts/workflows; without it, an expired token surfaces only
    # as an opaque non-zero exit. See AGENTS.md "Execution Guardrails" and
    # PR #278 review.
    assert "gh auth status" in run_script, (
        "Sync step must run `gh auth status` as an explicit preflight before "
        "any `gh` CLI calls so authentication failures surface with a clear "
        "diagnostic rather than as an opaque non-zero exit. See AGENTS.md."
    )


def test_post_release_sync_step_does_not_block_downstream() -> None:
    """Sync step failure must not abort Docker build/push or release/stable update.

    Acceptance criterion for issue #275: a benign failure in the sync step
    (e.g. a duplicate sync branch on workflow re-run) must not silently skip
    the downstream Docker publish and release/stable update steps.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    steps: list[dict[str, Any]] = workflow["jobs"]["release"]["steps"]

    sync_steps = [s for s in steps if "validate_version_sync.py" in s.get("run", "")]
    assert sync_steps, "Post-release sync step not found"
    sync_step = sync_steps[0]

    assert sync_step.get("continue-on-error") is True, (
        "Sync step must set continue-on-error: true so a failed push/PR-create "
        "does not skip downstream Docker publish and release/stable update steps. "
        "See issue #275."
    )

    # Downstream steps must be gated on release_created only, not on the
    # sync step's outcome. If they ever start referencing the sync step
    # (e.g. via steps.<id>.outcome), this guard catches the regression.
    downstream_names = {
        "Build and push Docker image",
        "Re-tag existing GHCR image without rebuild",
        "Update release/stable branch",
    }
    for step in steps:
        if step.get("name") in downstream_names:
            guard: str = step.get("if", "")
            assert "release_created" in guard, (
                f"Downstream step {step.get('name')!r} should be gated on "
                "release_created so sync-step failures cannot skip it"
            )
            assert "steps.sync" not in guard and "version_sync" not in guard, (
                f"Downstream step {step.get('name')!r} must not reference the "
                "sync step's outcome — that would re-introduce the failure mode "
                "from issue #275"
            )


def test_release_please_manifest_exists_and_has_root_package_version() -> None:
    """Ensure release-please has per-repo version state persisted in manifest."""
    manifest_path = REPO_ROOT / ".release-please-manifest.json"
    assert manifest_path.exists(), f"Manifest not found at {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    assert isinstance(manifest, dict), "Manifest must be a JSON object"
    root_version = manifest.get(".")
    assert isinstance(root_version, str) and root_version.strip(), (
        "Manifest must contain a non-empty '.' version entry"
    )


def test_release_please_manifest_version_matches_repo_version_files() -> None:
    """Manifest version must stay aligned with all repository version sources."""
    manifest_path = REPO_ROOT / ".release-please-manifest.json"
    version_path = REPO_ROOT / "VERSION"
    meta_path = REPO_ROOT / ".pyproject.meta.toml"
    pyproject_path = REPO_ROOT / "pyproject.toml"

    assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert isinstance(manifest, dict), "Manifest must be a JSON object"
    root_version = manifest.get(".")
    assert isinstance(root_version, str) and root_version.strip(), (
        "Manifest must contain a non-empty '.' version entry"
    )
    manifest_version = root_version.strip()

    _version_lines = version_path.read_text(encoding="utf-8").splitlines()
    _version_first = _version_lines[0] if _version_lines else ""
    version_file = _version_first.split("#", 1)[0].strip()
    with open(meta_path, "rb") as f:
        meta = tomllib.load(f)
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    meta_version = meta.get("project", {}).get("version", "")
    pyproject_version = pyproject.get("project", {}).get("version", "")

    assert manifest_version == version_file == meta_version == pyproject_version, (
        "Version drift detected between .release-please-manifest.json, VERSION, "
        ".pyproject.meta.toml, and pyproject.toml"
    )


def test_release_please_workflow_references_config() -> None:
    """Verify workflow uses config-file parameter."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    release_step: dict[str, Any] = _get_release_step(workflow)
    with_params: dict[str, Any] = release_step.get("with", {})
    config_file: str = with_params.get("config-file", "")

    assert config_file == ".release-please-config.json", (
        "Workflow should reference .release-please-config.json"
    )


def test_release_please_has_docker_publish_steps() -> None:
    """Verify workflow has Docker login and build/push steps for ghcr.io.

    This test verifies that the workflow uses templated GitHub Actions
    expressions for the Docker image tags, making it portable across
    any repository that syncs this workflow.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    release_job: dict[str, Any] = workflow["jobs"]["release"]
    steps: list[dict[str, Any]] = release_job["steps"]

    login_step = [
        s
        for s in steps
        if s.get("uses", "").startswith("docker/login-action")
        and s.get("with", {}).get("registry") == "ghcr.io"
    ]
    build_push_step = [
        s for s in steps if s.get("uses", "").startswith("docker/build-push-action")
    ]

    assert login_step, "Workflow should have a Docker login step for ghcr.io"
    assert build_push_step, "Workflow should have a Docker build-push step for ghcr.io"

    # Check login step config
    login = login_step[0]
    with_params = login.get("with", {})
    assert with_params.get("registry") == "ghcr.io", (
        "Docker login should target ghcr.io"
    )
    assert "GITHUB_TOKEN" in with_params.get("password", ""), (
        "Docker login should use GITHUB_TOKEN"
    )

    # Check build-push step config
    build_push = build_push_step[0]
    with_params = build_push.get("with", {})
    tags = with_params.get("tags", "")
    assert (
        "ghcr.io/${{ steps.repo_info.outputs.repo_owner }}/${{ steps.repo_info.outputs.repo_name }}"
        in tags
    ), "Docker image should be tagged for ghcr.io repo with dynamic owner/name"
    assert with_params.get("push", False) in [
        True,
        "true",
        "True",
    ], "Docker build-push should push images"


def test_release_please_optionally_logs_in_to_docker_hub_before_buildx() -> None:
    """Buildx pulls from Docker Hub should use optional authenticated path."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    release_job: dict[str, Any] = workflow["jobs"]["release"]
    job_env = release_job.get("env", {})
    assert "DOCKERHUB_USERNAME" not in job_env
    assert "DOCKERHUB_TOKEN" not in job_env
    steps: list[dict[str, Any]] = release_job["steps"]

    validate_steps = [
        s for s in steps if s.get("name") == "Validate Docker Hub auth configuration"
    ]
    assert len(validate_steps) == 1
    validate_env = validate_steps[0].get("env", {})
    assert "DOCKERHUB_USERNAME" in validate_env
    assert "DOCKERHUB_TOKEN" in validate_env

    docker_hub_login_steps = [
        s for s in steps if s.get("name") == "Login to Docker Hub (optional)"
    ]
    assert len(docker_hub_login_steps) == 1
    docker_hub_login = docker_hub_login_steps[0]
    assert docker_hub_login.get("uses", "").startswith("docker/login-action")
    assert "steps.dockerhub_auth.outputs.enabled" in docker_hub_login.get("if", "")
    assert "env" not in docker_hub_login

    docker_hub_with = docker_hub_login.get("with", {})
    assert docker_hub_with.get("registry") == "docker.io"
    assert "secrets.DOCKERHUB_USERNAME" in docker_hub_with.get("username", "")
    assert "secrets.DOCKERHUB_TOKEN" in docker_hub_with.get("password", "")

    buildx_steps = [s for s in steps if s.get("name") == "Set up Docker Buildx"]
    assert len(buildx_steps) == 1

    docker_hub_login_index = steps.index(docker_hub_login)
    buildx_index = steps.index(buildx_steps[0])
    assert docker_hub_login_index < buildx_index, (
        "Optional Docker Hub login must run before Buildx setup"
    )


def test_release_please_builds_only_on_input_change_or_cache_miss() -> None:
    """Verify release image build is gated by input-change or cache-miss logic."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    release_job: dict[str, Any] = workflow["jobs"]["release"]
    steps: list[dict[str, Any]] = release_job["steps"]

    checkout_steps = [s for s in steps if s.get("name") == "Checkout code"]
    assert len(checkout_steps) == 1
    checkout_with = checkout_steps[0].get("with", {})
    assert checkout_with.get("fetch-depth") in [0, "0"]

    detect_step = [s for s in steps if s.get("name") == "Detect Docker input changes"]
    assert len(detect_step) == 1
    assert detect_step[0].get("id") == "docker_inputs"
    detect_run = detect_step[0].get("run", "")
    assert "git diff --name-only" in detect_run
    assert '-- "${existing_inputs[@]}"' in detect_run
    assert "${#changed_files[@]}" in detect_run
    assert "git cat-file -e" in detect_run
    for docker_input in (
        "Dockerfile",
        "requirements.txt",
        "tooling.toml",
        "scripts",
        "tests",
    ):
        assert docker_input in detect_run

    cache_probe = [
        s for s in steps if s.get("name") == "Check for reusable GHCR latest image"
    ]
    assert len(cache_probe) == 1
    assert cache_probe[0].get("id") == "ghcr_cache"

    build_steps = [
        s
        for s in steps
        if s.get("name") == "Build and push Docker image"
        and s.get("uses", "").startswith("docker/build-push-action")
    ]
    assert len(build_steps) == 1
    build_if = build_steps[0].get("if", "")
    assert "docker_inputs.outputs.changed == 'true'" in build_if
    assert "ghcr_cache.outputs.cache_hit" in build_if

    retag_steps = [
        s
        for s in steps
        if s.get("name") == "Re-tag existing GHCR image without rebuild"
    ]
    assert len(retag_steps) == 1
    retag_if = retag_steps[0].get("if", "")
    assert "docker_inputs.outputs.changed != 'true'" in retag_if
    assert "ghcr_cache.outputs.cache_hit == 'true'" in retag_if


def test_release_please_permissions_for_packages() -> None:
    """Verify workflow sets packages: write permission for image publishing."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    permissions = workflow.get("permissions", {})
    assert permissions.get("packages") == "write", (
        "Workflow should set packages: write permission"
    )


def test_release_please_filters_docker_inputs_to_existing_paths() -> None:
    """Detect step must filter the allow-list to paths that exist in either tree.

    Lean consumers may not carry every allow-listed path (for example a freshly
    bootstrapped consumer without a `tests/` directory). Filtering by working-tree
    existence alone would hide deletions in the diff range, so the filter must
    check both `before` and the release sha — keeping removals visible while
    avoiding missing-pathspec brittleness.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    steps: list[dict[str, Any]] = workflow["jobs"]["release"]["steps"]
    detect_steps = [s for s in steps if s.get("name") == "Detect Docker input changes"]
    assert len(detect_steps) == 1
    detect_run = detect_steps[0].get("run", "")

    assert 'for p in "${docker_inputs[@]}"' in detect_run
    assert 'git cat-file -e "$before:$p"' in detect_run, (
        "Filter must check existence in the $before tree so deletions remain "
        "visible to git diff"
    )
    assert 'git cat-file -e "${{ github.sha }}:$p"' in detect_run, (
        "Filter must also check existence in the release sha tree so additions "
        "remain visible to git diff"
    )
    assert "existing_inputs+=" in detect_run
    assert '-- "${existing_inputs[@]}"' in detect_run
    assert '-- "${docker_inputs[@]}"' not in detect_run, (
        "git diff should consume the filtered existing_inputs array, not the "
        "raw docker_inputs allow-list, so missing optional paths do not leak "
        "into the pathspec"
    )


def test_release_please_no_rebuild_path_is_reachable_when_inputs_unchanged() -> None:
    """The no-rebuild retag path must remain reachable when image inputs are unchanged.

    Ties the upstream gate (`changed=false`) to the downstream retag step's `if`
    so a regression that pins `changed=true` unconditionally would be caught.
    """
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)
    steps: list[dict[str, Any]] = workflow["jobs"]["release"]["steps"]

    detect_steps = [s for s in steps if s.get("name") == "Detect Docker input changes"]
    assert len(detect_steps) == 1
    detect_run = detect_steps[0].get("run", "")
    assert "changed=false" in detect_run, (
        "Detect step must have a code path that emits changed=false; otherwise "
        "the retag (no-rebuild) path can never be reached"
    )

    retag_steps = [
        s
        for s in steps
        if s.get("name") == "Re-tag existing GHCR image without rebuild"
    ]
    assert len(retag_steps) == 1
    retag_if = retag_steps[0].get("if", "")
    assert "docker_inputs.outputs.changed != 'true'" in retag_if
    assert "ghcr_cache.outputs.cache_hit == 'true'" in retag_if


def test_release_please_has_release_stable_step() -> None:
    """Verify release-please workflow has release/stable branch update step."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    # Navigate to release job steps
    jobs = workflow.get("jobs", {})
    release_job = jobs.get("release", {})
    steps = release_job.get("steps", [])

    # Find the "Update release/stable branch" step
    stable_step = None
    for step in steps:
        if step.get("name") == "Update release/stable branch":
            stable_step = step
            break

    assert stable_step is not None, (
        "Workflow missing 'Update release/stable branch' step. "
        "Issue #11 requires automatic release/stable branch management."
    )


def test_release_please_stable_step_has_guard() -> None:
    """Verify release/stable update only runs when release is created."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    jobs = workflow.get("jobs", {})
    release_job = jobs.get("release", {})
    steps = release_job.get("steps", [])

    # Find the "Update release/stable branch" step
    stable_step = None
    for step in steps:
        if step.get("name") == "Update release/stable branch":
            stable_step = step
            break

    assert stable_step is not None, "Release/stable step not found"

    # Check for guard condition
    guard = stable_step.get("if")
    assert guard is not None, (
        "Release/stable step should have an 'if' guard condition "
        "to run only when a release is created"
    )
    assert "release_created" in guard, (
        f"Release/stable step guard should check release_created, got: {guard}"
    )


def test_release_please_stable_step_updates_branch() -> None:
    """Verify release/stable update step contains git branch commands."""
    workflow: dict[str, Any] = _load_yaml_as_dict(RELEASE_PLEASE_WORKFLOW)

    jobs = workflow.get("jobs", {})
    release_job = jobs.get("release", {})
    steps = release_job.get("steps", [])

    # Find the "Update release/stable branch" step
    stable_step = None
    for step in steps:
        if step.get("name") == "Update release/stable branch":
            stable_step = step
            break

    assert stable_step is not None, "Release/stable step not found"

    # Check for run script
    run_script = stable_step.get("run")
    assert run_script is not None, "Release/stable step should have a 'run' script"

    # Verify key commands are present
    assert "git branch" in run_script, (
        "Release/stable step should use 'git branch' to update branch"
    )
    assert "release/stable" in run_script, (
        "Release/stable step should reference 'release/stable' branch"
    )
    assert "git push" in run_script, (
        "Release/stable step should push the updated branch"
    )
    assert "git rev-parse HEAD" in run_script, (
        "Release/stable step must pin to an explicit local SHA via git rev-parse HEAD "
        "rather than a remote ref like origin/main, which could race with unrelated "
        "commits landing on main between the sync push and this fetch"
    )


def _load_yaml_as_dict(file_path: Path) -> dict[str, Any]:
    """Load YAML file and assert result is a dict.

    Args:
        file_path: Path to YAML file.

    Returns:
        Loaded YAML as dict.

    Raises:
        AssertionError: If file is empty, invalid, or doesn't contain a mapping.
    """
    with open(file_path, encoding="utf-8") as f:
        content: str = f.read()

    try:
        data: Any = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise AssertionError(f"Invalid YAML in {file_path.name}: {e}") from e

    if not isinstance(data, dict):
        raise AssertionError(
            f"Expected YAML mapping in {file_path.name}, "
            f"got {type(data).__name__}: {data}"
        )

    return data
