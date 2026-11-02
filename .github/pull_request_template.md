<!--
Title: type(scope): description, with the types and scopes of
conventional-pre-commit in .pre-commit-config.yaml.
A squash merge turns the title and this description into the commit message,
so write it like a commit body: a summary, then the Validation: block.
Format: https://github.com/MattyMroz/agents/blob/main/presets/hooks/references/commit-message.md
Replace every <result> with what you saw, e.g. "12/12 passed", "failed",
"not run (<reason>)".
-->

## Summary

<!-- What changes and why. -->

## Validation

Validation:
- uv run ruff check .: <result>
- uv run ruff format --check .: <result>
- uv run mypy .: <result>
- uv run pytest -n 6: <result>
- node --test userscript/: <result>
- prek run --all-files: <result>
- used for real, not only read: <result>
