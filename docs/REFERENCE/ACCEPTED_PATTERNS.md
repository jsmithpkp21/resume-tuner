# Accepted Patterns / Do Not Flag

## Overview

The `## Accepted Patterns / Do Not Flag` section in `AGENTS.md` (mirrored to
`.github/copilot-instructions.md`) is the canonical place to record patterns
that PR reviewers — human or automated, including GitHub Copilot's PR
reviewer agent — should not re-raise.

The project default is "write no comments unless the WHY is non-obvious", so
inline justification comments are not the right tool: they clutter the code,
rot when the surrounding code changes, and are invisible to a reviewer agent
that only reads diffs. A single centrally-listed entry per accepted pattern
keeps the rationale discoverable, durable, and revisable.

---

## When to add an entry

Add an entry when ALL of the following hold:

1. A PR reviewer (Copilot, another agent, or a human) flagged a pattern.
2. The PR thread reached consensus that the pattern is fine as-is.
3. The same pattern is likely to be re-flagged when the file is touched again
   (e.g. it is a general stylistic preference, not a one-off).
4. The rationale is short — a one-line justification is enough. If the
   reasoning needs paragraphs, it probably belongs in a doc or an ADR, not
   here.

## When NOT to add an entry

- The flag was a genuine bug, security issue, or correctness concern — fix
  the code instead.
- The pattern is specific to a single file and unlikely to recur — handle it
  in the PR thread; don't bake it into project-wide guidance.
- The decision is provisional or contested — wait until consensus is real,
  otherwise the entry will need to be retracted.

## Path-narrow patterns

If an accepted pattern only applies inside a specific directory or file
glob, prefer adding it to the matching `.github/instructions/<area>.instructions.md`
file (which uses the `applyTo:` frontmatter glob) rather than the top-level
section. This keeps the top-level list focused on truly repo-wide guidance
and surfaces the narrower rule only when the agent is editing that area.

---

## Entry format

One bullet per accepted pattern, in `AGENTS.md`:

```markdown
- *Pattern title* — one-line rationale. (Origin: PR #N review.)
```

- **Pattern title** — italicized; short and recognizable. Should describe the
  pattern, not the file it appeared in (so a future reader recognizes the
  pattern in unrelated code).
- **One-line rationale** — *why* the pattern is acceptable. Not *what* the
  pattern is.
- **Origin** — link to the PR (and optionally the specific review thread)
  where the decision was made, so the audit trail survives.

### Worked example

Hypothetical entry for the redundant-double-`Path.resolve()` case from
PR #374 review (used here purely as a formatting illustration — this entry
is not currently in the live list):

```markdown
- *Defensive double `Path.resolve()` in CLI entrypoints* — `resolve()` is
  idempotent and the validator functions already normalize their inputs,
  so a CLI `__main__` resolving the path again is harmless. (Origin:
  PR #374 review.)
```

---

## Retiring entries

Entries are not permanent. Remove or revise an entry when:

- The pattern is no longer present in the codebase (e.g. the relevant code
  was deleted or refactored away).
- A later review supersedes the original decision.
- The rationale has changed substantively — in that case rewrite the entry
  rather than appending qualifications, and link the superseding PR.

Removal is a normal PR-sized change; it does not require a separate process.

---

## Drift-check interaction

`make agents-drift-check` validates that a curated set of policy invariants
appears in both `AGENTS.md` and `.github/copilot-instructions.md`. The
accepted-patterns section is intentionally NOT in that invariant list — its
contents are expected to evolve frequently, and per-entry drift would
generate noise without surfacing real problems.

If you want to add a *specific* accepted-pattern entry to the drift-check
(for example because the entry encodes a load-bearing rule the project must
not lose), update `scripts/validate_agents_drift.py` in the same PR.

---

## Distribution to consumer repos

This convention and its reference doc are managed files and ship to consumer
repos via `.tooling-sync-manifest.toml`, so the same accepted-pattern
conventions apply project-wide. Edit the entries in the tooling source repo's
`AGENTS.md` (and this doc) — consumers receive updates on their next
`make sync-tooling` run. Entries that are repo-specific (a pattern only
accepted in one consumer) should live in that repo's `AGENTS_LOCAL.md`
override file instead, since `AGENTS.md` is overwritten by sync.
