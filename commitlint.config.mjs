export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "chore",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "revert",
      ],
    ],
    "subject-full-stop": [2, "never", "."],
    // Raise body/footer line ceilings from the @commitlint/config-conventional
    // default of 100 → 120. Bodies are read as markdown in PR/commit pages
    // (not narrow terminal git log), and AI-generated bodies plus pasted URLs,
    // stack traces, and review-link footers commonly overflow 100. 120 still
    // catches genuinely runaway prose. See tooling issue #310.
    "body-max-line-length": [2, "always", 120],
    "footer-max-line-length": [2, "always", 120],
  },
};
