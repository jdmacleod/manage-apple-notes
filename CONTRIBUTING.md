# Contributing

Thanks for your interest in manage-apple-notes. Contributions are welcome — bug reports, feature requests, documentation improvements, and code changes.

## Reporting issues

Use the GitHub issue templates:

- **[Bug report](.github/ISSUE_TEMPLATE/bug_report.yml)** — something isn't working as expected
- **[Feature request](.github/ISSUE_TEMPLATE/feature_request.yml)** — a new feature or improvement you'd like to see

For significant changes, open an issue to discuss the approach before writing code. For small, obvious fixes (typos, broken links, one-liner corrections) a PR is fine without a prior issue.

## Development setup

```bash
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes

# Activate the pre-commit hook (blocks accidental data commits — required)
git config core.hooksPath .git-hooks

# Install dependencies
uv sync

# Copy example config files — fill in your personal values (these are gitignored)
# Choose the template for your framework, or run: uv run notes setup
cp config/taxonomy.zettelkasten.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
cp .env.example .env
```

The `.env` file holds your API key or Ollama URL. Both `.env` and `*.local.*` config files are gitignored and must never be committed.

## Code quality

All four checks must pass before a PR can merge. Run them in this order:

```bash
uv run ruff format scripts/ tests/   # format in place
uv run ruff check scripts/ tests/    # lint — must be zero errors
uv run mypy scripts/                 # type check — fix any errors your change introduces
uv run pytest                        # tests — must pass at ≥90% line coverage
```

**Formatting** is non-negotiable — run `ruff format` on every file you touch.

**Type annotations** — all new functions and methods must be fully annotated. Existing mypy errors in files you haven't touched don't need to be fixed in the same PR, but errors introduced by new code should be resolved.

**Tests** — new behavior requires tests. The project targets ≥90% line coverage; check the coverage report in the pytest output and add tests for any uncovered branches you introduce.

**Linting rules in effect**: `E`/`F` (pyflakes/pycodestyle), `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify). `SIM108` (ternary) is suppressed — explicit `if/else` is preferred throughout. `E501` (line length) is enforced by the formatter, not the linter.

## Submitting a pull request

1. Fork the repository and create a branch from `main`.
2. Make your changes, following the code quality steps above.
3. Write a clear commit message in the imperative mood: `Add notes revert command`, not `Added notes revert command` or `Adds notes revert command`.
4. Open a pull request. Fill in the PR template — the summary, type of change, test plan, and privacy checklist.
5. A maintainer will review and may request changes. Please respond to review comments or close the PR if you're no longer pursuing the change.

Keep PRs focused: one logical change per PR. A bugfix and a refactor in the same diff makes review harder; open two PRs.

## Privacy constraints

This project is a **public open-source repo** that runs against personal note content. The following files must **never** be committed:

| Pattern | Contents |
|---------|----------|
| `data/` | Note exports, proposals, dedup proposals, reports, backups |
| `config/*.local.*` | Your actual folder names and taxonomy |
| `.env` | API keys and provider URLs |

The pre-commit hook (`.git-hooks/pre-commit`) blocks these automatically once activated. Always verify before committing:

```bash
git diff --cached --name-only
```

Nothing from `data/`, `config/*.local.*`, or `.env` should appear.

## AppleScript changes

Changes to `.applescript` files cannot be unit-tested. If your PR modifies an AppleScript, describe in the PR what you tested manually — which command, macOS version, and Apple Notes version.

## Conduct

Be respectful, constructive, and welcoming. Criticism of code and ideas is welcome; personal attacks are not. If you see a problem with how someone is being treated, mention it to the maintainer.
