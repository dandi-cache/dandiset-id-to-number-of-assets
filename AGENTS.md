# Agent instructions

This cache was migrated onto the shared pipeline; the `setup-cache` skill in [`cache-template`](https://github.com/dandi-cache/cache-template) describes the same shape for a new one.

## What belongs in a cache repository

A cache holds four things: `cache.toml` (what it is), `code/update.py` (what it does, per item), `envs/pyproject.toml` (its own dependencies) and a schedule.
Everything else arrives from [`dandi-cache-utils`](https://github.com/dandi-cache/dandi-cache-utils) through the base image and from [`dandi-cache-action`](https://github.com/dandi-cache/dandi-cache-action) through the workflows.

Never write an orchestration script, a compression step, a `dataset_description.json`, argument parsing, logging setup, an incremental frontier, a batch cap or testing-mode file switching in a cache.
All of it exists already.
If the shared pipeline is wrong or missing something, fix it in `dandi-cache-utils` so every cache gets the fix.

## Commits and PRs

- Always run `pre-commit` before committing and pushing changes.
- Always link PRs to issues when possible.
- PR titles should be human-readable and in the past tense.
  They should NOT use conventional commit style.
- Every commit must include a `Co-Authored-By` trailer identifying the tool and the model that wrote it.

## Code style

- Require keyword-only arguments `(*, ...)` for multi-input functions.
  For any function with exactly one caller-supplied parameter (excluding `self` and `cls`), require positional-only usage with the `/` designator.
- Always add new imports at the top of the file.
  The only exception is a local import that avoids a circular dependency.
- For external dependencies, use the full module import style (`import xyz; xyz.abc`) rather than `from xyz import abc`.
- Prefer assigning return values to named locals before `return` when it improves readability and debugger breakpoint placement.
- Avoid excessive em-dashes, colons, and semicolons in written text such as documentation.
  Prefer breaking into separate, shorter sentences instead.
- In Markdown, give each sentence its own line rather than wrapping prose to a fixed width.
  A reworded sentence is then a one-line diff instead of a reflowed paragraph, which is what makes a prose suggestion on a pull request reviewable.
- Keep inline comments sparse.
  Explain non-obvious "why", never "what".

## Tests

Most caches have no test suite of their own: the shared library is tested in `dandi-cache-utils`, and what remains here is one operation, exercised end to end by a `--testing` run.
If a cache does grow tests:

- Ensure they pass before pushing.
- Assertion style: actual on the left, expected on the right.
- Always mark AI-generated tests with the `ai_generated` pytest marker.
- Use `pytest.mark.parametrize` wherever it reduces duplication.
- Never import private API (a leading underscore).
  Import what `dandi_cache_utils` exposes publicly.

## Verifying a change

- Locally: `uv run --project envs --extra local python code/update.py --testing`.
- Then through the real pipeline: dispatch `Update` with `testing: true` and confirm it writes `derivatives/testing_<cache_name>.jsonl` and leaves the real cache untouched.
