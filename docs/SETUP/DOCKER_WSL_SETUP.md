# Docker Desktop WSL 2 Integration Setup

Docker Desktop is installed on your Windows machine, but WSL 2 integration needs to be enabled so you can use Docker commands from within WSL.

## Quick Fix: Enable WSL 2 Integration

1. **Open Docker Desktop** (from Windows Start menu)
2. Click the **Settings** gear icon (top right)
3. Go to **Resources** → **WSL Integration** (left sidebar)
4. Toggle **Enable integration with my default WSL distro** to ON
5. If you see Ubuntu listed, toggle it ON
6. Click **Apply & Restart**

Docker Desktop will restart and enable WSL 2 integration.

## Verify It Works

After Docker restarts, test in WSL:

```bash
docker --version
docker run hello-world
```

If you see version info and the hello-world container runs, you're good!

## Why This Matters

Once enabled, you can:

**Run lint checks locally:**
```bash
docker compose run --rm base_env make lint
```

**Run tests:**
```bash
docker compose run --rm base_env make test
```

**Run verification:**
```bash
docker compose run --rm base_env make verify
```

**Run everything in Docker (guaranteed same as CI/CD):**
```bash
docker compose up --build
```

## After Enabling WSL Integration

Your workflow becomes:

```bash
# Everything runs in Docker - same environment everywhere
docker compose run --rm base_env make lint
docker compose run --rm base_env make test
docker compose run --rm base_env make verify

# Or start interactive container
docker compose up -d
docker compose exec base_env bash
```

## Benefits

✅ Same environment: Local = CI/CD = Production
✅ No Python 3.11 installation needed on WSL
✅ No system dependency issues
✅ Reproducible builds
✅ Works exactly like AMD/Google/Meta/etc use Docker
✅ New team members get same setup instantly

---

## If Integration Still Doesn't Work

If you've enabled it but Docker still isn't found:

1. Close all WSL terminals
2. Restart Docker Desktop
3. Reopen WSL terminal
4. Test: `docker --version`

If it still fails, you may need to:
- Update Docker Desktop to latest version
- Update WSL 2 to latest
- Or reinstall Docker Desktop

But usually, just enabling WSL Integration in Docker Desktop settings fixes it.
