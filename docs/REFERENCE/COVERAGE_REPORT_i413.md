# Test Coverage Gap Analysis (issue #413)

Snapshot of `pytest --cov` across `src/{resume_builder,job_apply_kit,playwright_stealth_kit}` taken on `origin/main` and again after the targeted tests in this PR landed. Sorted ascending by coverage to surface gaps first.

## Baseline (origin/main @ 8fc2d1a, 0.54.1)

Overall: **6326 statements / 960 missing / 85% covered**, 1220 passed + 2 skipped (~3m18s).

| Module | Stmts | Cover |
| --- | --- | --- |
| `resume_builder/generate_review_packet.py` | 240 | 32% |
| `job_apply_kit/io_safety.py` | 24 | 42% |
| `resume_builder/validate_experience_data.py` | 80 | 56% |
| `resume_builder/measure_skills_lines.py` | 227 | 71% |
| `job_apply_kit/match_replay.py` | 79 | 76% |
| `job_apply_kit/label_matcher.py` | 195 | 76% |
| `playwright_stealth_kit/launch.py` | 26 | 77% |
| `resume_builder/export_resume_documents.py` | 158 | 77% |
| `resume_builder/build_resume.py` | 2113 | 84% |

Everything else is at or above 89%.

## After targeted tests (this PR)

Overall: **6326 statements / 914 missing / 86% covered**, 1253 passed + 2 skipped.

| Module | Before | After |
| --- | ---: | ---: |
| `job_apply_kit/io_safety.py` | 42% | **100%** |
| `job_apply_kit/match_replay.py` | 76% | **99%** |
| `resume_builder/validate_experience_data.py` | 56% | **96%** |

## Modules still below threshold (deferred)

These are large enough to warrant their own scoping — see the follow-up issues filed alongside this PR.

- `resume_builder/generate_review_packet.py` (32%) — most uncovered surface is the artifact-writing CLI (`write_findings`, `write_fix_queue`, `write_notes_template`, `write_summary`, `coverage_snapshot`, `_severity_for_row`). Worth a dedicated PR with golden-file fixtures.
- `resume_builder/measure_skills_lines.py` (71%) — uncovered surface is the `main()` CLI (font loading, kern-table fallback warnings, stdout reporting). Hard to test cleanly without a font-loader fixture or refactor; see follow-up.
- `job_apply_kit/label_matcher.py` (76%) — sub-key resolver branches for address/links/education/preferences/work_authorization/eeo/referral/consent are individually small but numerous; follow-up issue tracks them as a coherent unit rather than scattering tests.

## Notes

- Coverage instrumentation is `pytest-cov==7.1.0` (added to local venv only; not promoted into `requirements-dev.txt` yet — defer until tooling settles a shared coverage gate). The exact version is pinned here so the committed coverage snapshot remains reproducible until the dependency is promoted into the shared dev requirements.
- One pre-existing test-order quirk: running the full suite reports `llm_client.py` at 90% under one ordering and 74% under another. The new tests do not import `llm_client`; the variance was present on `origin/main` and is unrelated to issue #413 — separate follow-up if it persists.
