# Agent instructions

This cache was migrated onto the shared pipeline; the `setup-cache` skill in [`cache-template`](https://github.com/dandi-cache/cache-template) describes the same shape for a new one.

## What belongs in a cache repository

A cache holds four things: `cache.toml` (what it is), `code/update.py` (what it does, per item), `envs/pyproject.toml` (its own dependencies) and a schedule.
Everything else arrives from [`dandi-cache-utils`](https://github.com/dandi-cache/dandi-cache-utils) through the base image and from [`dandi-cache-action`](https://github.com/dandi-cache/dandi-cache-action) through the workflows.

Never write an orchestration script, a compression step, a `dataset_description.json`, argument parsing, logging setup, an incremental frontier, a batch cap or testing-mode file switching in a cache.
All of it exists already.
If the shared pipeline is wrong or missing something, fix it in `dandi-cache-utils` so every cache gets the fix.

## When a cache fails, fix it where it came from

A cache that breaks at run time is usually not a bug in that cache.
Triage before patching, because a fix in the wrong place leaves every other cache to hit the same problem again.

- A defect in the shared pipeline goes to `dandi-cache-utils`, as above.
- A defect in the CI that runs it goes to `dandi-cache-action`.
- A defect in the *guidance* goes to [`cache-template`](https://github.com/dandi-cache/cache-template).
  This file is a copy of the template's, so an edit here reaches this cache alone.
  Open a pull request against the template as well, so the correction reaches every other cache and the next one to be generated.
- Only what is genuinely specific to this cache's operation belongs in `code/update.py` or `cache.toml`.

Guidance is at fault when a step was followed as written and still produced a broken cache.
The same goes for a failure mode the instructions never mention, an instruction that reads as optional but is not, and an ordering that only works one way without saying so.
A one-off mistake by whoever ran the setup is not a guidance defect, and neither is an upstream outage.

Write the correction as the instruction the next reader follows, not as a story about this incident.
Name the rule, and give just enough of the failure to show why the rule exists.
The template's [`dandi-s3-network-inputs` skill](https://github.com/dandi-cache/cache-template/blob/main/.claude/skills/dandi-s3-network-inputs/SKILL.md) is what that looks like after the fact, a short set of rules distilled from two pull requests of debugging.

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
