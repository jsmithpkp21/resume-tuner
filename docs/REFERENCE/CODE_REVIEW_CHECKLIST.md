# Code Review Checklist

Use this checklist during PR review to catch common regressions in shared tooling docs and scripts.

## Documentation Command Safety

- [ ] No markdown examples use fragile inline activation patterns such as:
  - `source ~/envs/$(git remote get-url origin ...)-env/bin/activate`
  - `bash -lc "source ~/envs/$(git remote get-url origin ...)-env/bin/activate && ..."`
- [ ] Activation examples use the robust fallback pattern:

```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
```

- [ ] Run `make docs-check` before merge.

## Workflow and Release Safety

- [ ] `.release-please-config.json` has correct `changelog-path`.
- [ ] Workflow comments do not imply branch-protection bypass without repo settings.
- [ ] Repo-name extraction in workflows uses `GITHUB_REPOSITORY` and splits owner/repo.

## Sync Script Security

- [ ] `scripts/sync_tooling.sh` fails fast when GitHub mode is unsupported.
- [ ] `GITHUB_TOKEN` is only sent to trusted GitHub raw domains.
- [ ] Temporary files use `mktemp` (no fixed `/tmp/...` filenames).

## Environment Script Portability

- [ ] `scripts/verify_env.sh` treats `tooling.toml` as optional when intended.
- [ ] Python version checks and tool checks still run when optional files are absent.

## Shared-File Consistency

- [ ] Compare shared files between `base_repo` and `tooling` before final merge:
  - `scripts/create_env.sh`
  - `scripts/verify_env.sh`
  - `scripts/sync_tooling.sh`
  - `tests/test_setup.sh`
  - `tests/workflows/test_release_please.py`
  - `CONTRIBUTING.md`
  - `DOCKER.md`

## Useful Commands

```bash
# Validate markdown command patterns
make docs-check

# Compare key shared files (example)
diff -u ../tooling/scripts/sync_tooling.sh scripts/sync_tooling.sh
```
