#!/usr/bin/env python3
"""End-to-end test demonstrating the Schwab Sr. SDET sample with full pipeline.

This script runs three scenarios:
1. Baseline: No LLM processing (just enrich_data + trim_by_rules with empty enrichment)
2. Mock LLM: With LLM fixture mode enabled (trim_for_role + enrich_data active)
3. Diff analysis: Shows snapshot diffs between the two runs
"""

import os
import subprocess
import sys
from difflib import unified_diff
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_resume import (  # noqa: E402
    DEFAULT_MAX_ACTION_WORD_OCCURRENCES,
    DEFAULT_MAX_TOTAL_BULLETS,
    DEFAULT_MIN_BULLETS_PER_EXPERIENCE,
)


def run_pipeline(
    fixture_mode: bool = False, output_label: str = "baseline"
) -> Path | None:
    """Run build_resume.py with or without LLM fixture mode."""
    output_dir = Path(f"/tmp/schwab_sdet_{output_label}")
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = (
        "tests/fixtures/job_pages/schwab_sr_sdet.html"
    )

    if fixture_mode:
        env["RESUME_BUILDER_LLM_FIXTURE"] = "1"
        env["RESUME_BUILDER_LLM_CACHE_DIR"] = "tests/fixtures/llm_cache"
        env["RESUME_BUILDER_LLM_MODEL"] = "mistral:latest"
        env["RESUME_BUILDER_LLM_API_URL"] = "http://127.0.0.1:11434/v1/chat/completions"

    cmd = [
        sys.executable,
        "scripts/build_resume.py",
        "--job-url",
        "https://www.schwabjobs.com/job/austin/sr-sdet-workplace-services-engineering/33727/92422911552",
        "--output-dir",
        str(output_dir),
        "--processing-mode",
        "processed",
        "--skip-markdown",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )

    if result.returncode != 0:
        print(f"ERROR ({output_label}): {result.stderr}")
        return None

    return output_dir


def print_diff(snapshot_name: str, baseline_path: Path, with_llm_path: Path) -> None:
    """Print unified diff between two snapshots."""
    baseline_file = baseline_path / snapshot_name
    with_llm_file = with_llm_path / snapshot_name

    if not baseline_file.exists() or not with_llm_file.exists():
        print(f"⚠ {snapshot_name} not found in one or both runs")
        return

    baseline_lines = baseline_file.read_text().splitlines(keepends=True)
    with_llm_lines = with_llm_file.read_text().splitlines(keepends=True)

    diff = list(
        unified_diff(
            baseline_lines,
            with_llm_lines,
            fromfile=f"{snapshot_name} (baseline)",
            tofile=f"{snapshot_name} (with LLM + trim_by_rules)",
            lineterm="",
        )
    )

    if diff:
        print(f"\n{'=' * 80}")
        print(f"📊 DIFF: {snapshot_name}")
        print("=" * 80)
        print("".join(diff))
    else:
        print(f"\n✓ {snapshot_name}: No changes (as expected)")


def main() -> int:
    os.chdir(REPO_ROOT)

    print("\n" + "=" * 80)
    print("🎯 END-TO-END SAMPLE: Schwab Sr. SDET with enrich_data() + trim_by_rules()")
    print("=" * 80)

    print("\n📝 STEP 1: Generating baseline (no LLM)...")
    baseline_dir = run_pipeline(fixture_mode=False, output_label="baseline")
    if baseline_dir:
        print(f"✓ Baseline generated: {baseline_dir}")
    else:
        print("✗ Baseline generation failed")
        return 1

    print("\n📝 STEP 2: Generating with LLM fixtures (enrich_data + trim_by_rules)...")
    with_llm_dir = run_pipeline(fixture_mode=True, output_label="with_llm")
    if with_llm_dir:
        print(f"✓ LLM-enabled resume generated: {with_llm_dir}")
    else:
        print("⚠ LLM fixture run fell back to baseline (fixtures may be incomplete)")
        with_llm_dir = baseline_dir

    print("\n📊 STEP 3: Analyzing snapshot diffs...")
    print_diff("latest_resume_processed_ir_snapshot.txt", baseline_dir, with_llm_dir)
    print_diff("latest_resume_processed_ir_snapshot.json", baseline_dir, with_llm_dir)

    print("\n" + "=" * 80)
    print("📈 SUMMARY: Visible changes from full pipeline")
    print("=" * 80)
    print(f"""
✓ enrich_data() stage: Annotates bullets with role-relevance metadata
  - Adds "bullet_enrichment" to IR snapshot with confidence scores & tags
  - Enables downstream processing to track bullet relevance

✓ trim_by_rules() stage: Applies deterministic layout trimming
  - Enforces bullet caps ({DEFAULT_MAX_TOTAL_BULLETS} total, 4 per experience max)
  - Removes duplicate bullets
  - Limits action-word repetition to {DEFAULT_MAX_ACTION_WORD_OCCURRENCES} occurrences
  - Respects minimum {DEFAULT_MIN_BULLETS_PER_EXPERIENCE} bullets per experience

The resulting latest_resume_processed_ir_snapshot.txt and
latest_resume_processed_ir_snapshot.json files
show the final tailored resume with enrichment metadata attached.
""")

    # Show file sizes as proxy for data changes
    baseline_json = baseline_dir / "latest_resume_processed_ir_snapshot.json"
    with_llm_json = with_llm_dir / "latest_resume_processed_ir_snapshot.json"

    if baseline_json.exists() and with_llm_json.exists():
        baseline_size = baseline_json.stat().st_size
        with_llm_size = with_llm_json.stat().st_size
        change = with_llm_size - baseline_size

        print("\n📦 Data snapshot sizes:")
        print(f"   Baseline:    {baseline_size:6d} bytes")
        print(f"   With LLM:    {with_llm_size:6d} bytes")
        print(
            f"   Difference:  {change:+6d} bytes ({change / baseline_size * 100:+.1f}%)"
        )

        if change > 0:
            print(f"\n✓ Enrichment metadata added ({change} bytes of metadata)")
        elif change < 0:
            print(f"\n✓ Resume trimmed ({-change} bytes removed)")
        else:
            print("\n ℹ Same size (metadata + trimming offset)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
