# Project Template

A minimal starting point for new projects that use shared tooling.
Clone this template, run the setup script, and you are ready to code.

---

## Quick Start

```bash
# 1. Clone this template (or use the GitHub "Use this template" button)
git clone https://github.com/jsmithpkp21/project-template.git my_new_project
cd my_new_project

# 2. Run setup — choose your layer (or omit for a minimal base setup)
bash scripts/setup.sh              # Default/minimal setup
bash scripts/setup.sh playwright   # With Playwright layer
bash scripts/setup.sh api          # With API layer
bash scripts/setup.sh web          # With Web layer

# 3. Follow the printed next steps (make env → make active → make setup)
```

The script handles everything:
- Downloads and runs the shared `sync_tooling.sh` to pull in all shared config
- Initializes a git repository
- Installs git hooks (branch protection)
- Applies your chosen layer
- Removes itself once complete

---

## Available Layers

| Layer        | Description                                          |
|--------------|------------------------------------------------------|
| *(none)*     | Minimal base setup — shared config only              |
| `playwright` | Adds Playwright + pytest-playwright to the layer     |
| `api`        | Placeholder for API-specific dependencies            |
| `web`        | Placeholder for web-specific dependencies            |

---

## Environment Variables

| Variable         | Default                                        | Purpose                                    |
|------------------|------------------------------------------------|--------------------------------------------|
| `TOOLING_REPO`   | `https://github.com/jsmithpkp21/tooling`      | URL of the shared tooling repository       |
| `TOOLING_VERSION`| `main`                                         | Tag or branch to sync from                 |
| `GITHUB_TOKEN`   | *(empty)*                                      | Optional token for private tooling repos   |

---

## After Setup

```bash
make env      # Create the Python virtual environment
make active   # Print the activation command
make setup    # Full setup: env + verify + hooks + pre-commit
```

The template includes minimal `VERSION`, `tooling.toml`, and
`requirements.txt` as starting points for your project; after
`scripts/setup.sh` has synced tooling, you can run `make env` /
`make setup` using these files. They are intentionally not overwritten by
`sync_tooling.sh`, so you can adjust them to your project's needs.

---

## Updating Tooling in an Existing Project

After the initial setup, use `sync_tooling.sh` to pull in updates:

```bash
bash scripts/sync_tooling.sh main .
```

---

## Related

- [tooling repo](https://github.com/jsmithpkp21/tooling) — Source of shared scripts and config
