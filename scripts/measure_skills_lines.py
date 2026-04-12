#!/usr/bin/env python3
"""Spike: PDF-first skills line measurement loop (Issue #43).

Validates a deterministic measurement loop for skills-section line packing
using actual Calibri 11pt font metrics against the Zebra_Resume.docx
reference layout.

Reference layout (extracted from sandbox/Zebra_Resume.docx):
  - Font:            Calibri 11pt
  - Page width:      8.4896 in
  - Left margin:     0.6986 in
  - Right margin:    0.6986 in
  - Usable width:    7.0924 in  (510.65 pt at 72 pt/in)
  - Skills format:   "Category: skill1 • skill2 • ..."  (bold category label)

Measurement engine: Pillow ImageFont.truetype at size=11.
  - getlength() returns width in pixels at the 72-DPI internal baseline,
    which equals width in points (1 px = 1 pt at 72 DPI).
  - No rendering is performed; only font-metric width queries are used.

Optional kerning: --kern flag enables legacy fontTools kern-table lookup.
  Calibri has 26,706 kern pairs (legacy kern table).
  Impact: −0.1 to −1.0 pt per character pair at 11pt; can shift borderline
  wrap decisions by ±1 line.

Font discovery (in order):
   1. fontconfig fc-list (finds system-installed Calibri, e.g. ~/.local/share/fonts)
   2. WSL Windows font mount (/mnt/c/Windows/Fonts/)
   3. Liberation Sans (metrically ~1% compatible with Calibri; installed in Docker CI)
   4. DejaVu Sans fallback (warns; metrics differ ~3–5% from Calibri)

Font strict mode:
  By default the script falls back gracefully to Liberation or DejaVu when
  Calibri is unavailable (safe for CI).  To require exact Calibri metrics:
    CLI:  --strict-font
    Env:  RESUME_FONT_STRICT=1  (applies to both CLI and library callers)
  Strict mode raises FileNotFoundError immediately if Calibri is not found.

Outputs:
  - stdout: summary table (category → line count, wrap trigger words)
  - default: data/review/outputs/skills_line_measurement/skills_measurement.json
    (overridable via --output-dir)

Usage:
  python scripts/measure_skills_lines.py
  python scripts/measure_skills_lines.py --kern
  python scripts/measure_skills_lines.py --csv data/skills/skills_matrix.csv --kern
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import ImageFont
except ImportError:  # pragma: no cover
    print(
        "Pillow is required for font-metric measurement: pip install Pillow",
        file=sys.stderr,
    )
    raise

if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input

# ---------------------------------------------------------------------------
# Reference layout constants — derived from sandbox/Zebra_Resume.docx
# ---------------------------------------------------------------------------
_TEXT_WIDTH_IN: float = 7.0924  # usable text column width in inches
_TEXT_WIDTH_PT: float = _TEXT_WIDTH_IN * 72  # 510.65 pt  (1 pt = 1/72 in)
_FONT_SIZE_PT: int = 11  # Calibri 11pt body text

# Pillow truetype size parameter = points at 72 DPI internal baseline.
# font.getlength() → width in pixels @ 72 DPI = width in points.
_PILLOW_SIZE: int = _FONT_SIZE_PT

_LIBERATION_REGULAR: Path = Path(
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
)
_LIBERATION_BOLD: Path = Path(
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
)
_DEJAVU_REGULAR: Path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_DEJAVU_BOLD: Path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
SKILLS_SEPARATOR: str = " \u2022 "  # " • "  — matches Zebra_Resume.docx

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_CSV: Path = _REPO_ROOT / "data" / "skills" / "skills_matrix.csv"
DEFAULT_OUTPUT_DIR: Path = (
    _REPO_ROOT / "data" / "review" / "outputs" / "skills_line_measurement"
)

# Target line budget from DESIGN.md §6 (Skills Section Line Budget)
TARGET_LINES_MIN: int = 11
TARGET_LINES_MAX: int = 13


# ---------------------------------------------------------------------------
# Font discovery
# ---------------------------------------------------------------------------


def _find_calibri_path(style: str = "Regular") -> Path | None:
    """Locate Calibri TTF via fontconfig, then WSL Windows mount.

    Args:
        style: one of "Regular", "Bold", "Italic", "Light"

    Returns:
        Path to a readable .ttf file, or None if not found.
    """
    # 1. Try fontconfig (covers ~/.local/share/fonts and system dirs)
    try:
        result = subprocess.run(
            [
                "fc-list",
                f":family=Calibri:style={style}",
                "--format=%{file}\n",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            p = Path(line.strip())
            if p.exists():
                return p
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. WSL Windows font mount
    _suffix_map = {"Regular": "", "Bold": "b", "Italic": "i", "Light": "l"}
    suffix = _suffix_map.get(style, "")
    wsl = Path(f"/mnt/c/Windows/Fonts/calibri{suffix}.ttf")
    return wsl if wsl.exists() else None


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------


def load_font_pair(
    regular_path: Path | None = None,
    bold_path: Path | None = None,
    require_calibri: bool = False,
) -> tuple[Any, Any, str]:
    """Return (font_regular, font_bold, font_name_label).

    Discovery order (per style):
      1. Explicit path argument
      2. fontconfig fc-list (system-installed Calibri, including ~/.local/share/fonts)
      3. WSL Windows font mount /mnt/c/Windows/Fonts/
      4. Liberation Sans (metrically compatible with MS Office; used in CI)
      5. DejaVu Sans fallback (warns; ~3–5% metric difference)

    Strict mode control:
      1. ``RESUME_FONT_STRICT=1`` environment variable (global override)
      2. ``require_calibri=True`` passed by the caller
      3. Default (False): graceful fallback to Liberation/DejaVu with warning

    Args:
        regular_path: explicit path to Regular font
        bold_path: explicit path to Bold font
        require_calibri: if True, raise FileNotFoundError if Calibri unavailable;
                        if False, fall back to Liberation or DejaVu with warning.
                        Forced to True when RESUME_FONT_STRICT=1 is set.

    Raises:
        FileNotFoundError: if require_calibri=True (or RESUME_FONT_STRICT=1) and
                           Calibri cannot be located.
    """
    # Environment strict mode is a global override for CLI + library callers.
    if os.environ.get("RESUME_FONT_STRICT", "0").strip() == "1":
        require_calibri = True
    reg_path = regular_path or _find_calibri_path("Regular")
    bld_path = bold_path or _find_calibri_path("Bold")

    def _looks_like_calibri(path: Path | None) -> bool:
        return bool(path and "calibri" in path.name.lower())

    if reg_path and bld_path and reg_path.exists() and bld_path.exists():
        if _looks_like_calibri(reg_path) and _looks_like_calibri(bld_path):
            font_name = "Calibri"
        else:
            font_name = "Custom font pair"
    elif require_calibri:
        raise FileNotFoundError(
            "Calibri font not found (Regular/Bold).\n"
            "This spike requires exact Calibri metrics; no fallback is allowed.\n\n"
            "Fix:\n"
            "  1) Install Calibri (Linux user-local):\n"
            "     mkdir -p ~/.local/share/fonts/calibri\n"
            "     cp /mnt/c/Windows/Fonts/calibri*.ttf ~/.local/share/fonts/calibri/\n"
            "     fc-cache -fv\n"
            "  2) Verify discovery:\n"
            "     fc-list ':family=Calibri' --format='%{file}\\n'\n"
            "  3) Re-run:\n"
            "     python3 scripts/measure_skills_lines.py --kern"
        )
    elif _LIBERATION_REGULAR.exists() and _LIBERATION_BOLD.exists():
        font_name = "Liberation Sans (Calibri not found; metrics ≈ MS Office ±1%)"
        print(
            "INFO: Using Liberation Sans instead of Calibri. "
            "Install Calibri to ~/.local/share/fonts/calibri/ for exact measurements.",
            file=sys.stderr,
        )
        reg_path = _LIBERATION_REGULAR
        bld_path = _LIBERATION_BOLD
    else:
        if not (_DEJAVU_REGULAR.exists() and _DEJAVU_BOLD.exists()):
            raise FileNotFoundError(
                "No usable font pair found for skills measurement.\n"
                "Checked (in order): Calibri, Liberation Sans, DejaVu Sans.\n"
                "DejaVu fallback files are missing:\n"
                f"  - {_DEJAVU_REGULAR}\n"
                f"  - {_DEJAVU_BOLD}\n"
                "Install Calibri (preferred) or install both Liberation/DejaVu font files."
            )
        font_name = "DejaVu Sans (Calibri not found — metrics will differ ~3–5%)"
        print(
            "WARNING: Calibri and Liberation not found; falling back to DejaVu Sans. "
            "Install Calibri to ~/.local/share/fonts/calibri/ for accurate measurements.",
            file=sys.stderr,
        )
        reg_path = _DEJAVU_REGULAR
        bld_path = _DEJAVU_BOLD
    try:
        return (
            ImageFont.truetype(str(reg_path), size=_PILLOW_SIZE),
            ImageFont.truetype(str(bld_path), size=_PILLOW_SIZE),
            font_name,
        )
    except OSError as exc:
        raise FileNotFoundError(
            "Font files were discovered but could not be loaded by Pillow.\n"
            f"Regular: {reg_path}\n"
            f"Bold:    {bld_path}\n"
            f"Original error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Kerning (optional — fontTools kern table)
# ---------------------------------------------------------------------------


class KernTable:
    """Calibri kern-pair lookup built from the legacy kern table via fontTools.

    Calibri stores 26,706 kern pairs in its kern table.  At 11pt the values
    range from ~−0.08 pt (A-C) to ~−1.0 pt (T-o, Y-o).  Negative values
    tighten spacing; adding them to advance-width sums reduces line width.

    Impact on wrap detection: lines within ~8 pt of the wrap boundary may
    change by ±1 line when kerning is enabled.  Enable with --kern for final
    confirmation of borderline cases.
    """

    def __init__(self, font_path: Path) -> None:
        try:
            from fontTools import ttLib
        except ImportError:  # pragma: no cover
            raise ImportError(
                "fontTools is required for kerning: pip install fonttools"
            ) from None

        font = ttLib.TTFont(str(font_path))
        try:
            self._upm: int = int(font["head"].unitsPerEm)
            self._pairs: dict[tuple[str, str], int] = {}

            if "kern" in font:
                cmap: dict[int, str] = font.getBestCmap() or {}
                rev: dict[str, int] = {
                    glyph: codepoint for codepoint, glyph in cmap.items()
                }
                for table in font["kern"].kernTables:
                    if hasattr(table, "kernTable"):
                        for (g1, g2), val in table.kernTable.items():
                            cp1 = rev.get(g1)
                            cp2 = rev.get(g2)
                            if cp1 is not None and cp2 is not None:
                                self._pairs[(chr(cp1), chr(cp2))] = int(val)
        finally:
            font.close()

    @property
    def pair_count(self) -> int:
        return len(self._pairs)

    def adjust_pt(self, c1: str, c2: str, font_size_pt: float = _FONT_SIZE_PT) -> float:
        """Return kern adjustment in points for one adjacent character pair.

        Negative = tighten (reduce width).  Zero = no kern pair defined.
        """
        val = self._pairs.get((c1, c2), 0)
        return val / self._upm * font_size_pt

    def line_adjustment_pt(
        self, text: str, font_size_pt: float = _FONT_SIZE_PT
    ) -> float:
        """Sum kern adjustments for all adjacent pairs in *text*."""
        if len(text) < 2:
            return 0.0
        return sum(
            self.adjust_pt(text[i], text[i + 1], font_size_pt)
            for i in range(len(text) - 1)
        )


def load_kern_table(font_path: Path | None = None) -> KernTable | None:
    """Build a KernTable from Calibri Regular, or return None if unavailable."""
    path = font_path or _find_calibri_path("Regular")
    if path is None or not path.exists():
        return None
    try:
        kt = KernTable(path)
        return kt
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: Could not load kern table: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Text measurement
# ---------------------------------------------------------------------------


def measure_pt(
    text: str,
    font: Any,
    kern_table: KernTable | None = None,
    font_size_pt: float = _FONT_SIZE_PT,
) -> float:
    """Return text width in points using Pillow TrueType metrics (72-DPI basis).

    If *kern_table* is provided, kern adjustments for adjacent character pairs
    are applied (typically negative, reducing total width by 0–8 pt per line).
    """
    width = float(font.getlength(text))
    if kern_table is not None:
        width += kern_table.line_adjustment_pt(text, font_size_pt)
    return width


def wrap_category_line(
    category: str,
    skills: list[str],
    *,
    font_regular: Any,
    font_bold: Any,
    text_width_pt: float = _TEXT_WIDTH_PT,
    kern_table: KernTable | None = None,
) -> tuple[int, list[str]]:
    """Simulate word-level line wrapping for one skills category paragraph.

    The paragraph starts with a bold prefix ``"Category: "`` followed by the
    skills joined with SKILLS_SEPARATOR (space-bullet-space).  Wrapping occurs
    at word (space) boundaries exactly as a PDF/DOCX layout engine would.

    Returns:
        line_count:     number of wrapped output lines (≥ 1)
        wrap_triggers:  first token of each continuation line (for debugging)
    """
    bold_prefix = f"{category}: "
    # kern_table is built from Calibri Regular; do not apply it to the bold
    # prefix — Bold kerning differs from Regular and we have no Bold kern table.
    prefix_width_pt = measure_pt(bold_prefix, font_bold, kern_table=None)
    skills_text = SKILLS_SEPARATOR.join(skills)
    tokens = skills_text.split(" ")
    space_pt = measure_pt(" ", font_regular, kern_table)

    line_count = 1
    wrap_triggers: list[str] = []
    pending_non_separator_trigger = False
    current_width_pt = prefix_width_pt
    current_last_char: str | None = None

    for token in tokens:
        if not token:
            continue

        is_separator_token = token == SKILLS_SEPARATOR.strip()

        token_pt = measure_pt(token, font_regular, kern_table)
        if current_last_char is None:
            # First token on a line: do not apply Regular-kern boundary to the
            # bold prefix even if kerning is enabled.
            delta = token_pt
        else:
            delta = space_pt + token_pt
            if kern_table is not None:
                delta += kern_table.adjust_pt(current_last_char, " ")
                delta += kern_table.adjust_pt(" ", token[0])

        proposed = current_width_pt + delta
        if proposed <= text_width_pt:
            if pending_non_separator_trigger and not is_separator_token:
                wrap_triggers.append(token)
                pending_non_separator_trigger = False
            current_width_pt = proposed
            current_last_char = token[-1]
        else:
            line_count += 1
            if is_separator_token:
                pending_non_separator_trigger = True
            else:
                wrap_triggers.append(token)
                pending_non_separator_trigger = False
            current_width_pt = token_pt
            current_last_char = token[-1]

    return line_count, wrap_triggers


# ---------------------------------------------------------------------------
# Skills loading
# ---------------------------------------------------------------------------


def load_skills_by_category(csv_path: Path) -> dict[str, list[str]]:
    """Return ordered dict of category → [skill, ...] from skills_matrix.csv."""
    assert_not_blocked_runtime_input(csv_path)
    by_category: dict[str, list[str]] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            skill = (row.get("Skills") or "").strip()
            category = (row.get("Category") or "").strip()
            if skill and category:
                by_category.setdefault(category, []).append(skill)
    return by_category


# ---------------------------------------------------------------------------
# Measurement report
# ---------------------------------------------------------------------------


def measure_skills_section(
    skills_by_category: dict[str, list[str]],
    *,
    font_regular: Any,
    font_bold: Any,
    text_width_pt: float = _TEXT_WIDTH_PT,
    font_name: str = "Calibri",
    kern_table: KernTable | None = None,
) -> dict[str, Any]:
    """Return a full measurement report for the skills section."""
    category_results: list[dict[str, Any]] = []
    total_lines = 0
    kern_enabled = kern_table is not None

    for category, skills in skills_by_category.items():
        line_count, wrap_triggers = wrap_category_line(
            category,
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
            text_width_pt=text_width_pt,
            kern_table=kern_table,
        )
        total_lines += line_count

        # kern_table is built from Calibri Regular; do not apply it to the bold
        # prefix — Bold kerning differs from Regular and we have no Bold kern table.
        prefix_pt = measure_pt(f"{category}: ", font_bold, kern_table=None)
        body_pt = measure_pt(SKILLS_SEPARATOR.join(skills), font_regular, kern_table)
        full_line_pt = prefix_pt + body_pt

        category_results.append(
            {
                "category": category,
                "skill_count": len(skills),
                "line_count": line_count,
                "wrap_trigger_words": wrap_triggers,
                "full_line_width_pt": round(full_line_pt, 2),
                "text_width_pt": round(text_width_pt, 2),
                "unwrapped_overflow_pt": round(full_line_pt - text_width_pt, 2),
            }
        )

    within_budget = TARGET_LINES_MIN <= total_lines <= TARGET_LINES_MAX

    return {
        "reference_layout": {
            "font": f"{font_name} {_FONT_SIZE_PT}pt",
            "source_docx": "sandbox/Zebra_Resume.docx",
            "text_width_in": round(text_width_pt / 72, 4),
            "text_width_pt": round(text_width_pt, 2),
            "reference_text_width_in": _TEXT_WIDTH_IN,
            "reference_text_width_pt": round(_TEXT_WIDTH_PT, 2),
            "measurement_engine": "Pillow ImageFont.truetype (72-DPI point basis)",
            "kerning_enabled": kern_enabled,
            "kern_pairs": kern_table.pair_count if kern_table else 0,
        },
        "summary": {
            "category_count": len(category_results),
            "total_lines": total_lines,
            "target_lines_min": TARGET_LINES_MIN,
            "target_lines_max": TARGET_LINES_MAX,
            "within_budget": within_budget,
        },
        "categories": category_results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_SKILLS_CSV,
        help="Path to skills_matrix.csv",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for debug artifact",
    )
    p.add_argument(
        "--text-width-in",
        type=float,
        default=_TEXT_WIDTH_IN,
        help="Override text column width in inches (default: Zebra reference)",
    )
    p.add_argument(
        "--kern",
        action="store_true",
        help=(
            "Enable kern-table adjustments via fontTools for borderline precision. "
            "Calibri has 26,706 kern pairs; impact is 0–8 pt per line at 11pt."
        ),
    )
    p.add_argument(
        "--strict-font",
        action="store_true",
        default=False,
        help=(
            "Require Calibri font; raise an error if Calibri is not found instead of "
            "falling back to Liberation/DejaVu. Equivalent to setting "
            "RESUME_FONT_STRICT=1 in the environment."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    font_regular, font_bold, font_name = load_font_pair(
        require_calibri=args.strict_font
    )
    text_width_pt = args.text_width_in * 72

    kern_table: KernTable | None = None
    if args.kern:
        if font_name != "Calibri":
            print(
                f"Kerning: requested but font is '{font_name}' (not Calibri); "
                "kern table skipped — install Calibri for exact kern-adjusted measurements",
                file=sys.stderr,
            )
        else:
            kern_table = load_kern_table()
            if kern_table:
                print(
                    f"Kerning: enabled ({kern_table.pair_count:,} Calibri kern pairs)"
                )
            else:
                print("Kerning: requested but kern table unavailable; running without")

    print(f"Font:         {font_name} at {_FONT_SIZE_PT}pt")
    print(f"Text column:  {args.text_width_in:.4f} in = {text_width_pt:.2f} pt")
    print(f"Skills CSV:   {args.csv}")

    assert_not_blocked_runtime_input(args.csv)
    skills_by_category = load_skills_by_category(args.csv)
    report = measure_skills_section(
        skills_by_category,
        font_regular=font_regular,
        font_bold=font_bold,
        text_width_pt=text_width_pt,
        font_name=font_name,
        kern_table=kern_table,
    )

    total = report["summary"]["total_lines"]
    t_min = report["summary"]["target_lines_min"]
    t_max = report["summary"]["target_lines_max"]
    within = report["summary"]["within_budget"]
    budget_label = (
        "✓ within budget" if within else f"✗ over budget (target {t_min}–{t_max})"
    )

    print(f"\n{'=' * 64}")
    print(f"  Skills section: {total} wrapped lines  [{budget_label}]")
    print(f"{'=' * 64}")
    print(f"  {'Category':<42} {'Skills':>6}  {'Lines':>5}  Wrap trigger")
    print(f"  {'-' * 62}")
    for cat in report["categories"]:
        trigger = cat["wrap_trigger_words"][0] if cat["wrap_trigger_words"] else "-"
        print(
            f"  {cat['category'][:42]:<42} {cat['skill_count']:>6}  "
            f"{cat['line_count']:>5}  {trigger}"
        )

    assert_not_blocked_runtime_input(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "skills_measurement.json"
    assert_not_blocked_runtime_input(out_path)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nDebug artifact: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
