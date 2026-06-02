## Summary

<!-- 1–3 bullet points describing what this PR does and why. -->

-

## Type of change

<!-- Check all that apply. -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Refactor / internal cleanup (no behavior change)
- [ ] Documentation only
- [ ] Tests only

## Test plan

<!-- Describe how you verified this change works. -->

- [ ] `uv run ruff format scripts/ tests/` — no changes needed or applied
- [ ] `uv run ruff check scripts/ tests/` — zero errors
- [ ] `uv run mypy scripts/` — no new errors introduced
- [ ] `uv run pytest` — all tests pass, coverage ≥90%
- [ ] For AppleScript changes: describe manual testing below

<!-- Manual testing notes (command run, macOS version, Notes version): -->

## Privacy checklist

<!-- This project runs against personal note content. Confirm before submitting. -->

- [ ] No files from `data/` are staged
- [ ] No `config/*.local.*` files are staged
- [ ] No `.env` file is staged
- [ ] No note content, folder names, or personal paths appear in any committed file

## Related issues

<!-- Link any issues this PR addresses. -->

Closes #
