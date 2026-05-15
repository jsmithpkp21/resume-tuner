"""Static check: ban `bash -c "..."` / `bash -lc "..."` (double-quoted) +
embedded shell-var expansion in Makefile recipes.

When a Makefile recipe combines:
  - an outer double-quoted `bash -c "..."` or `bash -lc "..."`, AND
  - an embedded `$$VAR` or `$${VAR...}` shell-var expansion inside,

the recipe shell (/bin/sh) performs the variable expansion BEFORE bash sees
the command, interpolating user-supplied content into the command string
that bash then re-parses. A `"` inside the value breaks out of bash's
quoting and runs injected commands. See PR #424 for the original fix and
the probe that demonstrates the issue.

Safe form: use single quotes around the `bash -c`/`bash -lc` argument so
/bin/sh treats the contents as literal and bash itself performs the
parameter expansion at parse time. The variable's value then lands inside
an already-parsed `"..."` word where embedded `"` characters stay literal.

Per-line opt-out: `# noqa: bash-lc-quoting` on the same recipe line if the
shell var is provably safe (e.g. a make-internal value with no user reach).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"

_OPT_OUT = "noqa: bash-lc-quoting"

# Opens `bash -c "` or `bash -lc "` — the start of a double-quoted argument.
_BASH_DQ_RE = re.compile(r'bash\s+-l?c\s+"')

# `$$VAR` or `$${VAR...` — make-escaped shell-var expansion. `[A-Za-z_]`
# restricts the first char of the var name to a valid POSIX shell
# identifier start; special shells like `$$1`, `$$@`, `$$!`, `$$#` are
# intentionally excluded (not user-reachable via the patterns this check
# targets — `$1`/`$@`/etc. are positional args set by the shell, not
# values flowing in from outside). `\w` (which includes digits) is
# wrong here precisely because it would also match `$$1`. (Tightened
# in PR #430 round-1 review.)
_SHELL_VAR_RE = re.compile(r"\$\$\{?[A-Za-z_]")


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """Join lines ending in `\\` with the following line.

    Returns [(start_line_no_1_based, joined_line), ...]. start_line_no is the
    1-based line number where the joined sequence began, so error messages
    point at the first line of a multi-line recipe.
    """
    result: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        start = i + 1
        joined = lines[i].rstrip("\n")
        while joined.endswith("\\") and i + 1 < len(lines):
            joined = joined[:-1]
            i += 1
            joined += lines[i].rstrip("\n")
        result.append((start, joined))
        i += 1
    return result


def _is_recipe_line(line: str) -> bool:
    """Make recipe lines begin with a literal TAB."""
    return line.startswith("\t")


def _is_offender(line: str) -> bool:
    """True if the (joined) line has the dangerous bash + shell-var pattern.

    Heuristic: contains an opening `bash -c "` (or `-lc "`) AND a
    `$$VAR`/`$${VAR` somewhere after the opening. We don't track the
    closing `"` — in practice the `bash -lc "..."` is the recipe's single
    command and the closing quote is the last char on the line. If a recipe
    ever puts shell-var-using commands OUTSIDE the bash -lc block (where
    they're harmless), the closing quote would matter; in that case use the
    per-line opt-out.
    """
    match = _BASH_DQ_RE.search(line)
    if not match:
        return False
    return bool(_SHELL_VAR_RE.search(line, pos=match.end()))


def _scan_one(path: Path) -> tuple[int, list[tuple[str, int, str]]]:
    """Scan one Makefile for offenders.

    Returns (status, offenders). status: 0 = clean or absent, 1 = offenders
    present, 2 = unreadable (fail-closed). Each offender is
    (filename, 1-based line_no, stripped snippet).
    """
    # Distinguish "truly absent" from "exists but unreadable" so the
    # contract holds even when an OSError other than FileNotFoundError
    # fires (e.g. permission denied on parent traversal). `path.exists()`
    # was used here in round 1, but `Path.exists()` returns False on ANY
    # `os.stat` OSError — permission denied gets silently treated as
    # absent/clean instead of fail-closed exit 2 as documented.
    #
    # `lstat()` is used (not `stat()`) so broken symlinks succeed here
    # (the symlink itself exists, even though its target doesn't); they
    # fall through to the read which OSError-fails-closed below.
    # (tooling#471 round 5.)
    try:
        path.lstat()
    except FileNotFoundError:
        # Truly absent — neither a regular file nor a broken symlink.
        return 0, []
    except OSError as exc:
        sys.stderr.write(
            f"check-makefile-bash-quoting: could not stat {path}: "
            f"{exc.__class__.__name__}: {exc}\nScan is incomplete.\n"
        )
        return 2, []

    # `errors="replace"` handles a Makefile with invalid utf-8 bytes
    # gracefully (substitutes U+FFFD) rather than raising. OSError
    # fires for unreadable files / broken symlinks / permission denied;
    # mirror check_doc_drift's fail-closed exit-2 contract for that.
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write(
            f"check-makefile-bash-quoting: could not read {path}: "
            f"{exc.__class__.__name__}: {exc}\nScan is incomplete.\n"
        )
        return 2, []

    offenders: list[tuple[str, int, str]] = []
    for line_no, line in _join_continuations(text.splitlines()):
        if not _is_recipe_line(line):
            continue
        if _OPT_OUT in line:
            continue
        if _is_offender(line):
            offenders.append((path.name, line_no, line.strip()))
    return (1 if offenders else 0), offenders


def main(makefile: Path = MAKEFILE) -> int:
    # Also scan `Makefile.local` (sibling) if present. Consumer-owned and
    # loaded by the synced Makefile via `-include Makefile.local`, so unsafe
    # recipes added there would otherwise bypass this gate entirely. Absence
    # is normal — most consumers have no Makefile.local. See issue #448.
    paths = [makefile, makefile.parent / "Makefile.local"]
    all_offenders: list[tuple[str, int, str]] = []
    for path in paths:
        status, offenders = _scan_one(path)
        if status == 2:
            return 2
        all_offenders.extend(offenders)

    if not all_offenders:
        return 0

    sys.stderr.write(
        f"check-makefile-bash-quoting: {len(all_offenders)} recipe(s) combine "
        f'`bash -c/-lc "..."` (double-quoted) with `$$VAR` / `$${{VAR}}` '
        "shell-var expansion. The recipe shell (/bin/sh) expands the value "
        "BEFORE bash re-parses the command string, allowing quote-breakout "
        'injection if the value contains `"` (see PR #424).\n\n'
    )
    for filename, line_no, snippet in all_offenders:
        sys.stderr.write(f"  {filename}:{line_no}: {snippet}\n")
    sys.stderr.write(
        "\nFix: switch the outer `bash -c/-lc` argument to single quotes "
        "so /bin/sh treats it as literal and bash performs the expansion at "
        "parse time. Per-line opt-out: add `# "
        f"{_OPT_OUT}` if the shell var is provably safe.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
